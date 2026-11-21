#!/usr/bin/env bash
# Despliegue sin caída (azul/verde) de la interfaz gráfica en el LXC.
#
#   bash deploy/desplegar.sh <imagen>   despliega esa imagen (p. ej. ghcr.io/…:app-abc123def456)
#   bash deploy/desplegar.sh --volver   vuelve a la versión anterior (el otro slot)
#   bash deploy/desplegar.sh --estado   muestra el estado sin tocar nada
#
# Idea: el proxy nginx reenvía al slot activo. La imagen nueva se levanta en el slot INACTIVO, se
# espera a que esté sana, se cambia el destino del proxy (recarga instantánea) y el slot viejo
# se drena (espera a que terminen sus conversiones) y se detiene. Si algo falla antes de cambiar
# el tráfico, el servicio nunca dejó de servir la versión anterior.
#
# Variables: TIC_ESTADO (defecto /var/lib/tic-codec), TIC_OPT (defecto /opt/tic-codec), TIC_PUERTO (5000).
set -euo pipefail

ESTADO="${TIC_ESTADO:-/var/lib/tic-codec}"
OPT="${TIC_OPT:-/opt/tic-codec}"
PUERTO="${TIC_PUERTO:-5000}"
AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMG_DEF="tic-codec-gui:prueba"
# compose lee TIC_ESTADO/TIC_PUERTO del entorno para montar el proxy y publicar el puerto.
export TIC_ESTADO="$ESTADO" TIC_PUERTO="$PUERTO"

# ───────────────────────── utilidades ─────────────────────────
log()   { echo "» $*"; }
aviso() { echo "::warning::$*"; }
error() { echo "::error::$*" >&2; }

uso() {
  cat <<'USO'
Uso:
  bash deploy/desplegar.sh <imagen>   Despliega la imagen en el slot inactivo y cambia el tráfico.
  bash deploy/desplegar.sh --volver   Vuelve a la versión anterior (el otro slot).
  bash deploy/desplegar.sh --estado   Muestra el estado actual sin tocar nada.
  bash deploy/desplegar.sh -h         Esta ayuda.

Variables: TIC_ESTADO (defecto /var/lib/tic-codec), TIC_OPT (defecto /opt/tic-codec),
           TIC_PUERTO (defecto 5000).
USO
}

dc() { docker compose -f "$OPT/compose.yaml" -p tic-codec --env-file "$ESTADO/slots.env" --profile slots "$@"; }

# ID del contenedor (cualquier estado) de un servicio del proyecto; vacío si no existe.
cid() {
  docker ps -aq --filter "label=com.docker.compose.project=tic-codec" \
    --filter "label=com.docker.compose.service=$1" 2>/dev/null | head -n1 || true
}
corriendo() { [ -n "${1:-}" ] && [ "$(docker inspect -f '{{.State.Running}}' "$1" 2>/dev/null || echo false)" = true ]; }
salud_de()  { docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}-{{end}}' "$1" 2>/dev/null || echo "-"; }
imagen_de() { docker inspect -f '{{.Config.Image}}' "$1" 2>/dev/null || true; }

trim() { local s="$1"; s="${s#"${s%%[![:space:]]*}"}"; s="${s%"${s##*[![:space:]]}"}"; printf '%s' "$s"; }
otro()  { if [ "$1" = azul ]; then echo verde; else echo azul; fi; }
puerto_slot() { if [ "$1" = azul ]; then echo 5001; else echo 5002; fi; }

# Escritura atómica: archivo temporal en el mismo directorio + mv.
escribir_atomico() {
  local destino="$1" contenido="$2" tmp
  tmp="$(mktemp "$(dirname "$destino")/.tmp.XXXXXX")"
  printf '%s\n' "$contenido" > "$tmp"
  chmod 644 "$tmp"
  mv -f "$tmp" "$destino"
}

# ───────────────────────── catálogo ─────────────────────────
declare -a SV_N=() SV_T=() SV_E=() SV_S=() SV_C=()
declare -A RES_ESTADO=() RES_DET=()
leer_catalogo() {
  local f="$OPT/servicios.conf" nombre tipo entradas salud critico
  [ -f "$f" ] || f="$AQUI/servicios.conf"
  [ -f "$f" ] || { error "No encuentro servicios.conf"; exit 1; }
  while IFS='|' read -r nombre tipo entradas salud critico || [ -n "${nombre:-}" ]; do
    nombre="$(trim "$nombre")"
    case "$nombre" in ''|\#*) continue ;; esac
    SV_N+=("$nombre"); SV_T+=("$(trim "$tipo")"); SV_E+=("$(trim "$entradas")")
    SV_S+=("$(trim "$salud")"); SV_C+=("$(trim "$critico")")
  done < "$f"
}

# ───────────────────────── estado en disco ─────────────────────────
leer_activo() {
  local a=""
  [ -f "$ESTADO/activo" ] && a="$(tr -d '[:space:]' < "$ESTADO/activo")"
  case "$a" in azul|verde) echo "$a" ;; *) echo azul ;; esac
}
leer_imagen() {  # $1 = slot
  local v; v="$(grep -E "^TIC_IMAGEN_${1^^}=" "$ESTADO/slots.env" 2>/dev/null | head -n1 | cut -d= -f2- || true)"
  echo "${v:-$IMG_DEF}"
}
escribir_slots() {  # $1 = imagen azul, $2 = imagen verde
  escribir_atomico "$ESTADO/slots.env" "TIC_IMAGEN_AZUL=$1
TIC_IMAGEN_VERDE=$2"
}
poner_imagen_slot() {  # $1 = slot, $2 = imagen
  local az ve; az="$(leer_imagen azul)"; ve="$(leer_imagen verde)"
  if [ "$1" = azul ]; then escribir_slots "$2" "$ve"; else escribir_slots "$az" "$2"; fi
}

falta_estado() {
  cat >&2 <<MSG
::error::No puedo escribir en $1.
Créalo una vez con permisos para el usuario que ejecuta el despliegue (el del runner):
  sudo mkdir -p /var/lib/tic-codec/{proxy,huellas} /opt/tic-codec
  sudo chown -R <usuario del runner> /var/lib/tic-codec /opt/tic-codec
(deploy/proxmox/arranque-automatico.sh los crea como root; la fase 5 lo hará por ti.)
Con TIC_ESTADO / TIC_OPT puedes usar otras rutas.
MSG
  exit 1
}

preparar_dirs() {
  local d
  for d in "$ESTADO" "$OPT"; do
    [ -d "$d" ] || mkdir -p "$d" 2>/dev/null || true
    { [ -d "$d" ] && [ -w "$d" ]; } || falta_estado "$d"
  done
  mkdir -p "$ESTADO/proxy" "$ESTADO/huellas" 2>/dev/null || falta_estado "$ESTADO/proxy y $ESTADO/huellas"
  { [ -w "$ESTADO/proxy" ] && [ -w "$ESTADO/huellas" ]; } || falta_estado "$ESTADO/proxy y $ESTADO/huellas"
  [ -f "$ESTADO/slots.env" ] || escribir_slots "$IMG_DEF" "$IMG_DEF"
}

bloquear() {
  command -v flock >/dev/null 2>&1 || { aviso "flock no está disponible: sigo sin bloqueo (solo para pruebas)."; return 0; }
  exec 9>"$ESTADO/desplegar.lock"
  if ! flock -n 9; then
    log "Hay otro despliegue en curso: espero hasta 20 min a que termine…"
    flock -w 1200 9 || { error "Otro despliegue sigue en curso tras 20 min."; exit 1; }
  fi
}

# Copia lo versionado a $OPT (el arranque del LXC no depende del checkout del runner). No toca el estado.
copiar_archivos() {
  log "Copiando archivos de despliegue a $OPT…"
  cp -f "$AQUI/compose.yaml" "$OPT/compose.yaml"
  cp -f "$AQUI/servicios.conf" "$OPT/servicios.conf"
  mkdir -p "$OPT/nginx"
  # Se actualiza EN SITIO (sin borrar la carpeta): el proxy la tiene montada y perdería el montaje.
  local f
  for f in "$OPT"/nginx/*; do
    [ -e "$f" ] || continue
    [ -e "$AQUI/nginx/$(basename "$f")" ] || rm -rf "$f"
  done
  cp -a "$AQUI/nginx/." "$OPT/nginx/"
}

# ───────────────────────── proxy ─────────────────────────
escribir_upstream() {  # $1 = slot
  escribir_atomico "$ESTADO/proxy/upstream.conf" "map \"\" \$tic_app { default app-$1:5000; }"
}
probar_y_recargar() {
  dc exec -T proxy nginx -t || return 1
  dc exec -T proxy nginx -s reload
}
# Apunta el proxy a un slot; si nginx rechaza la recarga, restaura el upstream anterior. Ojo: el
# nombre del contenedor se resuelve en cada petición, así que `nginx -t` ya no falla si el destino
# no existe; la comprobación real del cambio es verificar_proxy (peticiones a través del proxy).
cambiar_upstream() {  # $1 = slot
  local previo=""
  [ -f "$ESTADO/proxy/upstream.conf" ] && previo="$(cat "$ESTADO/proxy/upstream.conf")"
  escribir_upstream "$1"
  if ! probar_y_recargar; then
    error "nginx rechazó la configuración; restauro el upstream anterior."
    if [ -n "$previo" ]; then escribir_atomico "$ESTADO/proxy/upstream.conf" "$previo"; fi
    return 1
  fi
}
http_ok() { curl -fsS --max-time 10 -o /dev/null "$1"; }
verificar_proxy() {
  local i
  for i in $(seq 1 10); do
    if http_ok "http://127.0.0.1:$PUERTO/salud" && http_ok "http://127.0.0.1:$PUERTO/"; then return 0; fi
    sleep 1
  done
  return 1
}

# ───────────────────────── servicios aux ─────────────────────────
esperar_healthy() {  # $1 = contenedor, $2 = segundos
  local c="$1" limite="$2" t=0 s
  while [ "$t" -lt "$limite" ]; do
    corriendo "$c" || return 1
    s="$(salud_de "$c")"
    if [ "$s" = healthy ] || [ "$s" = "-" ]; then return 0; fi
    sleep 3; t=$((t + 3))
  done
  return 1
}

# Devuelve 0 si queda bien; deja el estado/detalle en RES_ESTADO / RES_DET. 1 si falla.
aux_servicio() {  # $1 nombre, $2 entradas, $3 salud
  local n="$1" ent="$2" salud="$3" antes despues h_act="" h_ant="" cambio=0 estado="sin cambios" c
  antes="$(cid "$n")"
  if [ "$ent" != "-" ]; then
    # shellcheck disable=SC2086  # varias entradas separadas por espacios
    h_act="$("$AQUI/huella.sh" $ent)" || { RES_DET[$n]="no pude calcular la huella"; return 1; }
    h_ant="$(cat "$ESTADO/huellas/$n" 2>/dev/null || true)"
    if [ "$h_act" != "$h_ant" ]; then cambio=1; fi
  fi
  if [ "$cambio" = 1 ] && [ "$n" != proxy ] && [ -n "$antes" ]; then
    dc up -d --no-build --force-recreate "$n" || { RES_DET[$n]="falló compose up"; return 1; }
  else
    dc up -d --no-build "$n" || { RES_DET[$n]="falló compose up"; return 1; }
  fi
  despues="$(cid "$n")"
  [ -n "$despues" ] || { RES_DET[$n]="el contenedor no existe tras compose up"; return 1; }
  if [ -z "$antes" ] || [ "$antes" != "$despues" ]; then
    estado="actualizado"
  elif [ "$cambio" = 1 ] && [ "$n" = proxy ]; then
    log "$n: cambió su configuración; pruebo y recargo nginx…"
    probar_y_recargar || { RES_DET[$n]="nginx -t/reload falló; sigue con la configuración anterior"; return 1; }
    estado="recargado"
  fi
  esperar_healthy "$despues" 120 || { RES_DET[$n]="no quedó sano en 2 min"; return 1; }
  if [ "$n" = proxy ] && [ "$salud" != "-" ]; then
    c=0
    until http_ok "http://127.0.0.1:$PUERTO$salud"; do
      c=$((c + 1))
      if [ "$c" -ge 10 ]; then RES_DET[$n]="$salud no responde por :$PUERTO"; return 1; fi
      sleep 1
    done
  fi
  if [ "$ent" != "-" ]; then printf '%s\n' "$h_act" > "$ESTADO/huellas/$n"; fi
  RES_ESTADO[$n]="$estado"
  RES_DET[$n]="${h_act:+huella $h_act}"
  return 0
}

# ───────────────────────── slots de la app ─────────────────────────
esperar_slot() {  # $1 = slot; hasta 10 min
  local slot="$1" p c t=0 s=""
  p="$(puerto_slot "$slot")"
  while [ "$t" -lt 600 ]; do
    c="$(cid "app-$slot")"
    corriendo "$c" || { error "app-$slot no está en ejecución."; return 1; }
    s="$(salud_de "$c")"
    if { [ "$s" = healthy ] || [ "$s" = "-" ]; } \
       && http_ok "http://127.0.0.1:$p/salud" && http_ok "http://127.0.0.1:$p/"; then
      log "app-$slot sana (a los ${t}s)."
      return 0
    fi
    if [ $((t % 30)) -eq 0 ]; then log "esperando a app-$slot… (salud: $s, ${t}s)"; fi
    sleep 3; t=$((t + 3))
  done
  error "app-$slot no quedó sana en 10 min."
  return 1
}

SLOTS_BAK=""
# Levanta la imagen en un slot. $3 = 1 fuerza la recreación si el contenedor ya existe.
levantar_slot() {  # $1 slot, $2 imagen, $3 recrear
  local slot="$1" img="$2" rec="$3" extra=""
  SLOTS_BAK="$(cat "$ESTADO/slots.env")"
  poner_imagen_slot "$slot" "$img"
  if [ "$rec" = 1 ] && [ -n "$(cid "app-$slot")" ]; then extra="--force-recreate"; fi
  # shellcheck disable=SC2086
  dc up -d --no-build $extra "app-$slot" || return 1
  esperar_slot "$slot"
}
abortar_slot() {  # $1 slot: deja todo como estaba (el viejo nunca dejó de servir)
  local slot="$1"
  log "Descartando app-$slot…"
  dc logs --tail 100 "app-$slot" || true
  dc stop -t 30 "app-$slot" || true
  dc rm -f "app-$slot" || true
  if [ -n "$SLOTS_BAK" ]; then escribir_atomico "$ESTADO/slots.env" "$SLOTS_BAK"; fi
}

drenar() {  # $1 = slot viejo
  local slot="$1" p t=0 consec=0 out activas=0
  p="$(puerto_slot "$slot")"
  log "Drenando app-$slot (hasta 15 min esperando conversiones en curso)…"
  while [ "$t" -lt 900 ]; do
    if ! out="$(curl -fsS --max-time 5 "http://127.0.0.1:$p/salud" 2>/dev/null)"; then
      log "app-$slot ya no responde: se considera drenada."; activas=0; consec=2
    else
      activas="$(printf '%s' "$out" | sed -n 's/.*"activas"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p')"
      activas="${activas:-0}"
      if [ "$activas" -eq 0 ]; then consec=$((consec + 1)); else consec=0; log "app-$slot: $activas petición(es) activa(s)…"; fi
    fi
    if [ "$consec" -ge 2 ]; then break; fi
    sleep 5; t=$((t + 5))
  done
  if [ "$consec" -lt 2 ]; then
    aviso "app-$slot seguía con $activas petición(es) activa(s) tras 15 min; se detiene igualmente."
  fi
  # stop sin rm: el contenedor y su imagen quedan para volver rápido con --volver.
  dc stop -t 30 "app-$slot" || aviso "no pude detener app-$slot."
}

# Cambia el tráfico a $1 (sano), guarda `activo` y drena $2 (slot viejo, vacío si no hay).
cambiar_trafico() {  # $1 nuevo, $2 viejo
  local nuevo="$1" viejo="$2"
  log "Cambiando el tráfico a app-$nuevo…"
  if ! cambiar_upstream "$nuevo" || ! verificar_proxy; then
    error "El proxy no responde bien con app-$nuevo: vuelvo al anterior."
    if [ -n "$viejo" ]; then cambiar_upstream "$viejo" || true; fi
    abortar_slot "$nuevo"
    return 1
  fi
  escribir_atomico "$ESTADO/activo" "$nuevo"
  if [ -n "$viejo" ]; then drenar "$viejo"; fi
}

# ───────────────────────── resumen ─────────────────────────
FALLO=0
resumen_y_salir() {
  local i n tabla
  tabla="| servicio | estado | detalle |
|---|---|---|"
  for i in "${!SV_N[@]}"; do
    n="${SV_N[$i]}"
    tabla="$tabla
| $n | ${RES_ESTADO[$n]:-no procesado} | ${RES_DET[$n]:-} |"
  done
  echo; echo "$tabla"
  if [ -n "${GITHUB_STEP_SUMMARY:-}" ]; then
    { echo "### Despliegue"; echo; echo "$tabla"; } >> "$GITHUB_STEP_SUMMARY" || true
  fi
  exit "$FALLO"
}
detalle_app() {  # $1 = entradas de la huella, $2 = imagen
  local h; h="$("$AQUI/huella.sh" $1 2>/dev/null || echo '?')"
  echo "$2 (huella $h)"
}

# ───────────────────────── modo --estado ─────────────────────────
modo_estado() {
  command -v docker >/dev/null 2>&1 || echo "(docker no está instalado: solo muestro lo que hay en disco)"
  leer_catalogo
  local activo s c h_ant h_act i sl
  activo="$(leer_activo)"
  echo "Slot activo : $activo$([ -f "$ESTADO/activo" ] || echo ' (por defecto: aún no hay despliegues)')"
  echo "Imagen azul : $(leer_imagen azul)"
  echo "Imagen verde: $(leer_imagen verde)"
  echo; echo "Servicios:"
  for i in "${!SV_N[@]}"; do
    s="${SV_N[$i]}"
    if [ "${SV_T[$i]}" = app ]; then
      for sl in azul verde; do
        c=""; command -v docker >/dev/null 2>&1 && c="$(cid "app-$sl")"
        printf '  app-%-6s contenedor=%s corriendo=%s salud=%s imagen=%s\n' "$sl" "${c:0:12}" \
          "$(corriendo "$c" && echo si || echo no)" "$([ -n "$c" ] && salud_de "$c" || echo -)" \
          "$([ -n "$c" ] && imagen_de "$c" || echo -)"
        if corriendo "$c"; then
          printf '              activas=%s\n' "$(curl -fsS --max-time 5 "http://127.0.0.1:$(puerto_slot "$sl")/salud" 2>/dev/null \
            | sed -n 's/.*"activas"[[:space:]]*:[[:space:]]*\([0-9][0-9]*\).*/\1/p' || true)"
        fi
      done
    else
      c=""; command -v docker >/dev/null 2>&1 && c="$(cid "$s")"
      h_ant="$(cat "$ESTADO/huellas/$s" 2>/dev/null || echo '-')"; h_act="-"
      if [ "${SV_E[$i]}" != "-" ]; then h_act="$("$AQUI/huella.sh" ${SV_E[$i]} 2>/dev/null || echo '?')"; fi
      printf '  %-9s contenedor=%s corriendo=%s salud=%s huella guardada=%s actual=%s\n' "$s" "${c:0:12}" \
        "$(corriendo "$c" && echo si || echo no)" "$([ -n "$c" ] && salud_de "$c" || echo -)" "$h_ant" "$h_act"
    fi
  done
  echo
  if curl -fsS --max-time 5 "http://127.0.0.1:$PUERTO/salud" 2>/dev/null; then
    echo; echo "Proxy :$PUERTO/salud -> responde"
  else
    echo "Proxy :$PUERTO/salud -> NO responde"
  fi
  exit 0
}

# ───────────────────────── arranque ─────────────────────────
MODO=normal; IMAGEN=""
case "${1:-}" in
  -h|--help) uso; exit 0 ;;
  "") uso; exit 1 ;;
  --estado) modo_estado ;;
  --volver) MODO=volver ;;
  -*) error "Opción desconocida: $1"; uso; exit 1 ;;
  *) IMAGEN="$1" ;;
esac

command -v docker >/dev/null 2>&1 || { error "docker no está instalado."; exit 1; }
preparar_dirs
bloquear
copiar_archivos
leer_catalogo

ACTIVO="$(leer_activo)"
INACTIVO="$(otro "$ACTIVO")"
ACT_CID="$(cid "app-$ACTIVO")"
DIRECTO=0   # 1 = el slot activo no corre (primer arranque): se despliega en él y no hay nada que drenar
corriendo "$ACT_CID" || DIRECTO=1

# ── modo --volver ──
if [ "$MODO" = volver ]; then
  if [ "$DIRECTO" = 1 ]; then error "No hay un slot activo en ejecución al que sustituir."; exit 1; fi
  IMG_ANT="$(leer_imagen "$INACTIVO")"
  if [ -z "$(cid "app-$INACTIVO")" ] && [ "$IMG_ANT" = "$IMG_DEF" ]; then
    error "No hay imagen anterior conocida (app-$INACTIVO nunca tuvo un despliegue)."; exit 1
  fi
  if [ "$IMG_ANT" = "$(imagen_de "$ACT_CID")" ]; then
    error "La imagen anterior es la misma que la activa: nada a lo que volver."; exit 1
  fi
  log "Volviendo a $IMG_ANT en app-$INACTIVO (activo ahora: $ACTIVO)…"
  if [ -z "$(cid "app-$INACTIVO")" ]; then
    docker pull "$IMG_ANT" || docker image inspect "$IMG_ANT" >/dev/null 2>&1 \
      || { error "No pude obtener $IMG_ANT."; exit 1; }
  fi
  if levantar_slot "$INACTIVO" "$IMG_ANT" 0; then
    if cambiar_trafico "$INACTIVO" "$ACTIVO"; then
      log "Listo: ahora sirve app-$INACTIVO ($IMG_ANT)."
      exit 0
    fi
  else
    abortar_slot "$INACTIVO"
  fi
  error "No se pudo volver; sigue la versión actual."; exit 1
fi

# ── paso 1: pull con reintentos (si el activo ya corre esa imagen no hace falta) ──
APP_SIN_CAMBIOS=0
if corriendo "$ACT_CID" && [ "$(imagen_de "$ACT_CID")" = "$IMAGEN" ]; then
  APP_SIN_CAMBIOS=1
else
  log "Descargando $IMAGEN…"
  ok=0
  for i in 1 2 3; do
    if docker pull "$IMAGEN"; then ok=1; break; fi
    if [ "$i" -lt 3 ]; then log "Pull falló (intento $i/3); reintento en $((30 * i)) s…"; sleep $((30 * i)); fi
  done
  if [ "$ok" = 0 ]; then
    if docker image inspect "$IMAGEN" >/dev/null 2>&1; then
      aviso "No pude hacer pull de $IMAGEN; uso la copia local."
    else
      error "No pude descargar $IMAGEN. No se cambió nada."
      for i in "${!SV_N[@]}"; do
        if [ "${SV_T[$i]}" = app ]; then
          RES_ESTADO[${SV_N[$i]}]="falló (sigue la versión anterior)"; RES_DET[${SV_N[$i]}]="pull de $IMAGEN"
        fi
      done
      FALLO=1; resumen_y_salir
    fi
  fi
fi

# ── paso 2: el upstream debe existir antes de que arranque el proxy ──
if [ ! -f "$ESTADO/proxy/upstream.conf" ]; then escribir_upstream "$ACTIVO"; fi
DIFERIR_PROXY=0
if [ "$DIRECTO" = 1 ] && ! corriendo "$(cid proxy)"; then
  DIFERIR_PROXY=1
  log "Primer arranque: el proxy se levanta después de que app-$ACTIVO esté sana."
fi

# ── paso 3: servicios aux (antes de tocar la app) ──
aux_con_resultado() {  # $1 = índice en el catálogo
  local i="$1" n="${SV_N[$1]}"
  log "Servicio auxiliar: $n"
  if aux_servicio "$n" "${SV_E[$i]}" "${SV_S[$i]}"; then return 0; fi
  if [ "${SV_C[$i]}" = si ]; then
    RES_ESTADO[$n]="falló (sigue la versión anterior)"; FALLO=1
    error "$n (crítico) falló: ${RES_DET[$n]:-}. No toco la app."
    return 1
  fi
  RES_ESTADO[$n]="falló (aviso, no crítico)"
  aviso "$n falló: ${RES_DET[$n]:-}"
  return 0
}
for i in "${!SV_N[@]}"; do
  [ "${SV_T[$i]}" = aux ] || continue
  if [ "$DIFERIR_PROXY" = 1 ] && [ "${SV_N[$i]}" = proxy ]; then continue; fi
  aux_con_resultado "$i" || resumen_y_salir
done

# ── pasos 4-8: la app ──
for i in "${!SV_N[@]}"; do
  [ "${SV_T[$i]}" = app ] || continue
  N="${SV_N[$i]}"
  DET_IMG="$(detalle_app "${SV_E[$i]}" "$IMAGEN")"
  if [ "$APP_SIN_CAMBIOS" = 1 ]; then
    log "app-$ACTIVO ya corre $IMAGEN: sin cambios."
    RES_ESTADO[$N]="sin cambios"; RES_DET[$N]="$DET_IMG, slot $ACTIVO"
    continue
  fi
  if [ "$DIRECTO" = 1 ]; then DEST="$ACTIVO"; VIEJO=""; else DEST="$INACTIVO"; VIEJO="$ACTIVO"; fi
  log "Levantando $IMAGEN en app-$DEST…"
  if ! levantar_slot "$DEST" "$IMAGEN" 1; then
    abortar_slot "$DEST"
    RES_ESTADO[$N]="falló (sigue la versión anterior)"; RES_DET[$N]="$DET_IMG, slot $DEST no quedó sano"
    FALLO=1; resumen_y_salir
  fi
  if [ "$DIRECTO" = 1 ]; then
    escribir_upstream "$DEST"
    if [ "$DIFERIR_PROXY" = 1 ]; then
      for j in "${!SV_N[@]}"; do
        [ "${SV_N[$j]}" = proxy ] || continue
        if ! aux_con_resultado "$j"; then
          RES_ESTADO[$N]="actualizado"; RES_DET[$N]="$DET_IMG, slot $DEST (sin proxy)"
          escribir_atomico "$ESTADO/activo" "$DEST"
          resumen_y_salir
        fi
      done
    elif corriendo "$(cid proxy)"; then
      probar_y_recargar || { FALLO=1; error "No pude recargar el proxy."; }
    fi
    verificar_proxy || aviso "El proxy aún no responde en :$PUERTO."
    escribir_atomico "$ESTADO/activo" "$DEST"
  else
    if ! cambiar_trafico "$DEST" "$VIEJO"; then
      RES_ESTADO[$N]="falló (sigue la versión anterior)"; RES_DET[$N]="$DET_IMG, el proxy no respondió bien"
      FALLO=1; resumen_y_salir
    fi
  fi
  RES_ESTADO[$N]="actualizado"; RES_DET[$N]="$DET_IMG, slot $DEST"
done

resumen_y_salir

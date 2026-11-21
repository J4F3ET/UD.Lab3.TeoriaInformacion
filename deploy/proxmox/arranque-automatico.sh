#!/usr/bin/env bash
# Deja el LXC listo para que, cada vez que arranque (o se reinicie el host de Proxmox),
# vuelva a quedar todo arriba solo y EN ORDEN:
#
#   red + DNS  →  Docker  →  contenedores de la app (compose)  →  runner de GitHub Actions
#
# Sin esto, al reiniciar el runner podía tomar un job antes de que hubiera DNS
# ("Could not resolve host: github.com") y los contenedores dependían solo de su
# restart: unless-stopped (si alguien hacía `compose down`, no volvían).
#
# Los contenedores de la app salen de /opt/tic-codec (copia del último despliegue), no del checkout
# del runner. Arrancan el proxy y el slot activo (azul o verde, según /var/lib/tic-codec/activo).
#
# Además instala dos vigías (el "mínimo garantizado"):
#   · en el LXC, cada 2 min: Docker, el proxy y el slot activo, los servicios auxiliares críticos,
#     Tailscale/Funnel y el runner; si algo está caído lo levanta, y si el disco pasa del 90 % limpia
#     imágenes y caché de Docker.
#   · en el host, cada 5 min: si el LXC está apagado, lo enciende.
# Para apagar a propósito (mantenimiento) sin que los vigías lo vuelvan a levantar:
#   host: touch /root/vigia-lxc-<CTID>.pausa      LXC: touch /root/vigia.pausa
#
# Se puede ejecutar de dos formas (es re-ejecutable):
#   En el HOST de Proxmox, como root, con el CTID:   bash arranque-automatico.sh 111
#   DENTRO del LXC, como root:                        bash arranque-automatico.sh
# Desde el host, además, marca el LXC para arrancar con Proxmox (onboot=1).
# PROBAR=1 (solo desde el host) reinicia el LXC al final y comprueba que todo volvió.
set -euo pipefail

USUARIO="${RUNNER_USUARIO:-deployer}"
REPO="${REPO_NOMBRE:-UD.Lab3.TeoriaInformacion}"
PUERTO="${TIC_PUERTO:-5000}"

# ═══════════════ modo host: preparar el LXC desde Proxmox ═══════════════
if command -v pct >/dev/null 2>&1; then
  CTID="${1:?Uso en el host de Proxmox: $0 <CTID>}"
  pct status "$CTID" >/dev/null || { echo "No existe el LXC $CTID"; exit 1; }
  echo "» LXC $CTID: arrancar junto con Proxmox (onboot=1)…"
  pct set "$CTID" --onboot 1

  echo "» Vigía del host: enciende el LXC $CTID si está apagado (cada 5 min)…"
  cat > /usr/local/sbin/vigia-lxc <<'EOF'
#!/bin/sh
# Instalado por arranque-automatico.sh. Enciende el LXC dado si no está corriendo.
CTID="$1"
[ -e "/root/vigia-lxc-$CTID.pausa" ] && exit 0
estado=$(pct status "$CTID" 2>/dev/null | awk '{print $2}')
[ "$estado" = running ] && exit 0
echo "vigia-lxc: el LXC $CTID está '${estado:-desconocido}': lo enciendo"
pct start "$CTID" || echo "vigia-lxc: pct start $CTID falló (revisa: pct start $CTID --debug)"
exit 0
EOF
  chmod 0755 /usr/local/sbin/vigia-lxc
  cat > /etc/systemd/system/vigia-lxc@.service <<'EOF'
[Unit]
Description=Vigía: enciende el LXC %i si está apagado
After=pve-guests.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/vigia-lxc %i
EOF
  cat > /etc/systemd/system/vigia-lxc@.timer <<'EOF'
[Unit]
Description=Vigía del LXC %i cada 5 min

[Timer]
OnBootSec=5min
OnUnitActiveSec=5min

[Install]
WantedBy=timers.target
EOF
  systemctl daemon-reload
  systemctl enable --now "vigia-lxc@$CTID.timer" >/dev/null
  pct status "$CTID" | grep -q running || { echo "» Encendiendo el LXC…"; pct start "$CTID"; sleep 5; }
  pct push "$CTID" "$0" /root/arranque-automatico.sh --perms 0755
  pct exec "$CTID" -- env RUNNER_USUARIO="$USUARIO" REPO_NOMBRE="$REPO" TIC_PUERTO="$PUERTO" \
    bash /root/arranque-automatico.sh

  if [ "${PROBAR:-0}" = 1 ]; then
    echo; echo "» PROBAR=1: reiniciando el LXC $CTID para comprobar el arranque…"
    pct reboot "$CTID"
    for i in $(seq 1 40); do
      sleep 5
      if pct exec "$CTID" -- curl -fsS -o /dev/null "http://127.0.0.1:$PUERTO/salud" 2>/dev/null; then
        echo "  la app responde tras el reinicio (≈$((i * 5)) s)"; break
      fi
      [ "$i" = 40 ] && echo "✘ la app no respondió en 200 s; revisa: pct exec $CTID -- journalctl -u tic-codec -b"
    done
    pct exec "$CTID" -- bash /root/arranque-automatico.sh --estado
  fi
  exit 0
fi

# ═══════════════ modo LXC ═══════════════
[ "$(id -u)" -eq 0 ] || { echo "Ejecútalo como root dentro del LXC."; exit 1; }
HOME_USR="$(getent passwd "$USUARIO" | cut -d: -f6)"
[ -n "$HOME_USR" ] || { echo "No existe el usuario $USUARIO (¿corriste instalar-runner.sh?)"; exit 1; }
GRUPO="$(id -gn "$USUARIO")"
RUNNER_DIR="$HOME_USR/actions-runner"
# Checkout del runner: NO es fuente del despliegue; solo sirve para calcular la huella de los scripts.
TRABAJO="$RUNNER_DIR/_work/$REPO/$REPO"
SVC_RUNNER="$(cat "$RUNNER_DIR/.service" 2>/dev/null || true)"
# Estado (lo escribe el despliegue) y copia de compose/servicios/nginx: los usa el usuario del runner.
ESTADO=/var/lib/tic-codec
OPT=/opt/tic-codec
IMG_DEF=tic-codec-gui:prueba                 # mismo valor por defecto que deploy/desplegar.sh

estado() {
  echo
  echo "Estado al arrancar (enabled = arranca solo · active = corriendo ahora):"
  for u in docker.service containerd.service tailscaled.service tic-codec.service tic-codec-vigia.timer ${SVC_RUNNER:+"$SVC_RUNNER"}; do
    systemctl cat "$u" >/dev/null 2>&1 || continue
    printf "  %-58s %-9s %s\n" "$u" "$(systemctl is-enabled "$u" 2>/dev/null || true)" "$(systemctl is-active "$u" 2>/dev/null || true)"
  done
  echo
  echo "  slot activo: $(cat "$ESTADO/activo" 2>/dev/null || echo azul)"
  docker ps --format '  {{.Names}}  {{.Status}}' 2>/dev/null || true
  if curl -fsS -o /dev/null "http://127.0.0.1:$PUERTO/salud"; then
    echo "  ✔ la app responde en http://127.0.0.1:$PUERTO/salud"
  else
    echo "  ✘ la app no responde en http://127.0.0.1:$PUERTO/salud"
  fi
  echo "  disco /: $(df -h --output=pcent,avail / | tail -1)"
  echo "  últimas acciones del vigía:"
  journalctl -u tic-codec-vigia.service --no-pager -n 5 -o cat 2>/dev/null | sed 's/^/    /' || true
}
[ "${1:-}" = "--estado" ] && { estado; exit 0; }

# ── 0. Directorios de estado y de despliegue, con valores iniciales ──
# Son del usuario del runner: desplegar.sh escribe ahí sin root. Si el runner nunca desplegó, la app
# arranca igual: slot azul, imagen por defecto y proxy apuntando a azul.
echo "» Directorios $ESTADO y $OPT (dueño: $USUARIO)…"
install -d -o "$USUARIO" -g "$GRUPO" "$ESTADO" "$ESTADO/proxy" "$ESTADO/huellas" "$OPT"
[ -f "$ESTADO/activo" ] || echo azul > "$ESTADO/activo"
[ -f "$ESTADO/slots.env" ] || printf 'TIC_IMAGEN_AZUL=%s\nTIC_IMAGEN_VERDE=%s\n' "$IMG_DEF" "$IMG_DEF" > "$ESTADO/slots.env"
[ -f "$ESTADO/proxy/upstream.conf" ] || echo 'map "" $tic_app { default app-azul:5000; }' > "$ESTADO/proxy/upstream.conf"
chmod 0644 "$ESTADO/activo" "$ESTADO/slots.env" "$ESTADO/proxy/upstream.conf"
chown -R "$USUARIO:$GRUPO" "$ESTADO" "$OPT"

# ── 1. Docker y Tailscale arrancan con el sistema ──
echo "» Docker y containerd al arranque…"
systemctl enable docker.service containerd.service >/dev/null
if systemctl cat tailscaled.service >/dev/null 2>&1; then
  echo "» Tailscale al arranque (Funnel queda guardado en su estado)…"
  systemctl enable tailscaled.service >/dev/null
fi

# ── 2. Esperar a que haya red y DNS de verdad ──
# network-online.target solo dice que hay IP; el DNS puede tardar más (y Tailscale cambia
# /etc/resolv.conf al arrancar). Este script corto espera hasta poder resolver github.com.
cat > /usr/local/bin/esperar-dns <<'EOF'
#!/bin/sh
# Espera hasta 120 s a poder resolver el host dado (por defecto github.com).
h="${1:-github.com}"
for i in $(seq 1 60); do
  getent hosts "$h" >/dev/null 2>&1 && exit 0
  sleep 2
done
echo "esperar-dns: $h sigue sin resolver tras 120 s" >&2
exit 0   # no bloquear el arranque para siempre: el servicio sigue y lo reintentará
EOF
chmod 0755 /usr/local/bin/esperar-dns

# ── 3. Servicio que levanta la app del slot activo ──
# Además del restart: unless-stopped de compose.yaml: vuelve a levantarlos aunque alguien
# los haya bajado con `compose down`. Usa las imágenes ya descargadas por el último despliegue
# (sin --build ni pull: arrancar no debe depender de compilar ni de la red).
echo "» Servicio tic-codec (arranca el slot activo al iniciar)…"
cat > /usr/local/bin/tic-codec-arrancar <<'EOF'
#!/bin/sh
# Instalado por arranque-automatico.sh. Levanta el proxy, la limpieza y la app del slot activo
# (azul o verde, según /var/lib/tic-codec/activo). Sin ningún despliegue aún, sale sin error.
OPT=/opt/tic-codec
ESTADO=/var/lib/tic-codec
if [ ! -f "$OPT/compose.yaml" ]; then
  echo "tic-codec: aún no hay despliegue ($OPT/compose.yaml no existe): no hay nada que levantar."
  exit 0
fi
activo=$(cat "$ESTADO/activo" 2>/dev/null | tr -d '[:space:]')
case "$activo" in azul|verde) ;; *) activo=azul ;; esac
echo "tic-codec: levanto proxy, limpieza y app-$activo…"
exec docker compose -f "$OPT/compose.yaml" -p tic-codec --env-file "$ESTADO/slots.env" --profile slots \
  up -d --no-build proxy limpieza "app-$activo"
EOF
chmod 0755 /usr/local/bin/tic-codec-arrancar
cat > /etc/systemd/system/tic-codec.service <<'EOF'
[Unit]
Description=Códec TIC: contenedores de la interfaz (proxy y slot activo, docker compose)
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/bin/tic-codec-arrancar
TimeoutStartSec=300
# Si Docker aún no estaba listo, reintentar en vez de quedar fallido hasta el próximo arranque.
Restart=on-failure
RestartSec=30

[Install]
WantedBy=multi-user.target
EOF

# ── 4. El runner arranca DESPUÉS de red, DNS, Docker y la app ──
if [ -n "$SVC_RUNNER" ] && systemctl cat "$SVC_RUNNER" >/dev/null 2>&1; then
  echo "» Runner $SVC_RUNNER: orden de arranque y espera de DNS…"
  mkdir -p "/etc/systemd/system/$SVC_RUNNER.d"
  cat > "/etc/systemd/system/$SVC_RUNNER.d/arranque.conf" <<'EOF'
# Agregado por deploy/proxmox/arranque-automatico.sh
[Unit]
Wants=network-online.target
After=network-online.target docker.service tailscaled.service tic-codec.service

[Service]
ExecStartPre=/usr/local/bin/esperar-dns github.com
Restart=always
RestartSec=15
EOF
else
  echo "⚠ No encontré el servicio del runner en $RUNNER_DIR/.service; corre primero instalar-runner.sh."
fi

# ── 5. Vigía: el mínimo garantizado, cada 2 min ──
echo "» Vigía tic-codec-vigia (cada 2 min)…"
cat > /usr/local/bin/tic-codec-vigia <<EOF
#!/bin/sh
# Instalado por arranque-automatico.sh. Revisa y, si hace falta, levanta lo mínimo:
# Docker → proxy y app del slot activo → servicios auxiliares críticos → Tailscale/Funnel → runner.
# Nunca falla (exit 0): solo actúa y lo deja en el journal.
PUERTO="$PUERTO"
SVC_RUNNER="$SVC_RUNNER"
EOF
cat >> /usr/local/bin/tic-codec-vigia <<'EOF'
[ -e /root/vigia.pausa ] && exit 0
OPT=/opt/tic-codec
ESTADO=/var/lib/tic-codec
COMPOSE="docker compose -f $OPT/compose.yaml -p tic-codec --env-file $ESTADO/slots.env --profile slots"
ACTIVO=$(cat "$ESTADO/activo" 2>/dev/null | tr -d '[:space:]')
case "$ACTIVO" in azul|verde) ;; *) ACTIVO=azul ;; esac
case "$ACTIVO" in verde) PUERTO_SLOT=5002 ;; *) PUERTO_SLOT=5001 ;; esac

# Pasa por el proxy: si responde, el proxy y la app están bien.
sano() { curl -fsS --max-time 5 -o /dev/null "http://127.0.0.1:$PUERTO/salud"; }
# El slot activo responde directamente (sin el proxy).
slot_sano() { corre "app-$ACTIVO" && curl -fsS --max-time 5 -o /dev/null "http://127.0.0.1:$PUERTO_SLOT/salud"; }
# Hay un contenedor del servicio $1 (del proyecto tic-codec) en ejecución.
corre() { [ -n "$(docker ps -q --filter label=com.docker.compose.project=tic-codec --filter "label=com.docker.compose.service=$1" --filter status=running)" ]; }

# 1. Docker
if ! systemctl is-active --quiet docker; then
  echo "docker no está activo: lo reinicio"
  systemctl restart docker; sleep 15
fi

# 2. Proxy, app y servicios auxiliares críticos (solo si ya hubo un despliegue)
if [ -f "$OPT/compose.yaml" ]; then
  # El despliegue usa el mismo bloqueo: mientras corre uno, el vigía no toca los contenedores.
  exec 9>"$ESTADO/desplegar.lock"
  if command -v flock >/dev/null 2>&1 && ! flock -n 9; then
    echo "hay un despliegue en curso: no toco los contenedores"
  else
    if ! sano; then
      sleep 20
      if ! sano; then
        if ! corre proxy; then
          echo "proxy no está corriendo: up proxy"
          $COMPOSE up -d --no-build proxy </dev/null
          sleep 15
        fi
        if ! slot_sano; then
          echo "app-$ACTIVO no corre o no responde: up app-$ACTIVO"
          $COMPOSE up -d --no-build "app-$ACTIVO" </dev/null
          sleep 45
        fi
        sano && echo "app recuperada" || echo "la app NO se recuperó: revisar '$COMPOSE logs proxy app-$ACTIVO'"
      fi
    fi
    # Auxiliares marcados como críticos en el catálogo (critico=no: el vigía no los toca).
    while IFS='|' read -r nombre tipo entradas salud critico || [ -n "${nombre:-}" ]; do
      nombre=$(printf '%s' "$nombre" | tr -d ' \t')
      tipo=$(printf '%s' "$tipo" | tr -d ' \t')
      critico=$(printf '%s' "$critico" | tr -d ' \t')
      case "$nombre" in ''|\#*) continue ;; esac
      [ "$tipo" = aux ] && [ "$critico" = si ] || continue
      if ! corre "$nombre"; then
        echo "$nombre (auxiliar crítico) no corre: up $nombre"
        $COMPOSE up -d --no-build "$nombre" </dev/null || echo "no se pudo levantar $nombre"
      fi
    done < "$OPT/servicios.conf"
  fi
else
  echo "aún no hay despliegue ($OPT/compose.yaml no existe): no hay proxy ni app que vigilar"
fi

# 3. Tailscale y Funnel (publican la app)
if command -v tailscale >/dev/null 2>&1; then
  if ! systemctl is-active --quiet tailscaled; then
    echo "tailscaled no está activo: lo reinicio"
    systemctl restart tailscaled; sleep 10
  fi
  ts=$(tailscale status --json 2>/dev/null | grep -o '"BackendState": *"[A-Za-z]*"' | head -1 | cut -d'"' -f4)
  if [ "$ts" = Running ]; then
    tailscale funnel status 2>/dev/null | grep -q "Funnel on" || {
      echo "Funnel apagado: lo enciendo"
      tailscale funnel --bg "$PUERTO" >/dev/null 2>&1 || echo "no se pudo encender Funnel"
    }
  else
    # NeedsLogin = la clave del nodo expiró: no se arregla reiniciando (ver deploy/README.md).
    echo "tailscale en estado '${ts:-sin respuesta}'; si es NeedsLogin: tailscale up y desactivar key expiry"
    [ -z "$ts" ] && systemctl restart tailscaled
  fi
fi

# 4. Runner de GitHub Actions
if [ -n "$SVC_RUNNER" ] && ! systemctl is-active --quiet "$SVC_RUNNER"; then
  echo "runner $SVC_RUNNER caído: lo inicio"
  systemctl start "$SVC_RUNNER"
fi

# 5. Disco: un disco lleno tumba todo en silencio
uso=$(df --output=pcent / | tail -1 | tr -dc 0-9)
if [ "${uso:-0}" -ge 90 ]; then
  echo "disco al ${uso} %: limpio imágenes y caché de Docker"
  docker image prune -f >/dev/null 2>&1
  docker builder prune -f >/dev/null 2>&1
  journalctl --vacuum-size=200M >/dev/null 2>&1
fi
exit 0
EOF
chmod 0755 /usr/local/bin/tic-codec-vigia
cat > /etc/systemd/system/tic-codec-vigia.service <<'EOF'
[Unit]
Description=Vigía del códec TIC: Docker, proxy/app, Tailscale/Funnel y runner
After=docker.service tic-codec.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/tic-codec-vigia
TimeoutStartSec=600
EOF
cat > /etc/systemd/system/tic-codec-vigia.timer <<'EOF'
[Unit]
Description=Vigía del códec TIC cada 2 min

[Timer]
OnBootSec=3min
OnUnitActiveSec=2min

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl enable tic-codec.service >/dev/null
systemctl enable --now tic-codec-vigia.timer >/dev/null
[ -n "$SVC_RUNNER" ] && systemctl enable "$SVC_RUNNER" >/dev/null

# Aplicar ya, sin esperar a un reinicio.
if [ -f "$OPT/compose.yaml" ]; then
  systemctl restart tic-codec.service || echo "⚠ tic-codec no pudo levantar los contenedores: journalctl -u tic-codec"
else
  echo "⚠ Aún no hay despliegue ($OPT/compose.yaml): los contenedores se levantarán tras el primer despliegue del runner."
fi
# El runner NO se reinicia aquí: mataría un job en curso. El nuevo orden (esperar DNS,
# Docker y la app) se aplica en el próximo arranque del LXC; si está caído, se enciende.
[ -n "$SVC_RUNNER" ] && { systemctl is-active --quiet "$SVC_RUNNER" || systemctl start "$SVC_RUNNER"; }

# ── 6. Huella de los scripts del LXC: la compara el workflow y avisa si hay que volver a ejecutar esto ──
# Misma fórmula que deploy/huella.sh (git ls-tree -r HEAD sobre deploy/proxmox, sha256, 12 caracteres),
# calculada sobre el checkout del runner. Sin checkout con git no se puede: se omite y el workflow solo
# emite un aviso informativo (no falla) hasta la próxima ejecución con checkout.
HUELLA_SCRIPTS=""
if command -v git >/dev/null 2>&1 && [ -d "$TRABAJO/.git" ]; then
  lista="$(git -c "safe.directory=$TRABAJO" -C "$TRABAJO" ls-tree -r HEAD -- deploy/proxmox 2>/dev/null || true)"
  [ -n "$lista" ] && HUELLA_SCRIPTS="$(printf '%s\n' "$lista" | sha256sum | cut -c1-12)"
fi
if [ -n "$HUELLA_SCRIPTS" ]; then
  printf '%s\n' "$HUELLA_SCRIPTS" > "$ESTADO/huellas/lxc-scripts"
  chown "$USUARIO:$GRUPO" "$ESTADO/huellas/lxc-scripts"
  echo "» Huella de los scripts del LXC guardada: $HUELLA_SCRIPTS"
else
  echo "⚠ No hay checkout con git del runner en $TRABAJO: no guardo la huella de los scripts (aviso informativo del workflow)."
fi

estado
echo
echo "✔ Listo: al reiniciar el LXC arrancan Docker, la app y el runner, en ese orden,"
echo "  y el vigía revisa cada 2 min que sigan arriba (journalctl -u tic-codec-vigia)."

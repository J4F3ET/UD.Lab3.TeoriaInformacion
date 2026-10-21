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
  pct status "$CTID" | grep -q running || { echo "» Encendiendo el LXC…"; pct start "$CTID"; sleep 5; }
  pct push "$CTID" "$0" /root/arranque-automatico.sh --perms 0755
  pct exec "$CTID" -- env RUNNER_USUARIO="$USUARIO" REPO_NOMBRE="$REPO" TIC_PUERTO="$PUERTO" \
    bash /root/arranque-automatico.sh

  if [ "${PROBAR:-0}" = 1 ]; then
    echo; echo "» PROBAR=1: reiniciando el LXC $CTID para comprobar el arranque…"
    pct reboot "$CTID"
    for i in $(seq 1 40); do
      sleep 5
      if pct exec "$CTID" -- curl -fsS -o /dev/null "http://127.0.0.1:$PUERTO/" 2>/dev/null; then
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
RUNNER_DIR="$HOME_USR/actions-runner"
TRABAJO="$RUNNER_DIR/_work/$REPO/$REPO"     # donde el runner hace checkout del repo
SVC_RUNNER="$(cat "$RUNNER_DIR/.service" 2>/dev/null || true)"

estado() {
  echo
  echo "Estado al arrancar (enabled = arranca solo · active = corriendo ahora):"
  for u in docker.service containerd.service tailscaled.service tic-codec.service ${SVC_RUNNER:+"$SVC_RUNNER"}; do
    systemctl cat "$u" >/dev/null 2>&1 || continue
    printf "  %-58s %-9s %s\n" "$u" "$(systemctl is-enabled "$u" 2>/dev/null || true)" "$(systemctl is-active "$u" 2>/dev/null || true)"
  done
  echo
  docker ps --format '  {{.Names}}  {{.Status}}' 2>/dev/null || true
  if curl -fsS -o /dev/null "http://127.0.0.1:$PUERTO/"; then
    echo "  ✔ la app responde en http://127.0.0.1:$PUERTO/"
  else
    echo "  ✘ la app no responde en http://127.0.0.1:$PUERTO/"
  fi
}
[ "${1:-}" = "--estado" ] && { estado; exit 0; }

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

# ── 3. Servicio que levanta los contenedores de la app ──
# Además del restart: unless-stopped de compose.yaml: vuelve a levantarlos aunque alguien
# los haya bajado con `compose down`. Usa la imagen ya construida por el último despliegue
# (sin --build: arrancar no debe depender de compilar).
echo "» Servicio tic-codec (docker compose up al arrancar)…"
cat > /etc/systemd/system/tic-codec.service <<EOF
[Unit]
Description=Códec TIC: contenedores de la interfaz (docker compose)
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target
# Si el runner todavía no hizo ningún despliegue, no hay nada que levantar.
ConditionPathExists=$TRABAJO/deploy/compose.yaml

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=$TRABAJO
ExecStart=/usr/bin/docker compose -f deploy/compose.yaml -p tic-codec up -d --no-build --remove-orphans
TimeoutStartSec=300

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

systemctl daemon-reload
systemctl enable tic-codec.service >/dev/null
[ -n "$SVC_RUNNER" ] && systemctl enable "$SVC_RUNNER" >/dev/null

# Aplicar ya, sin esperar a un reinicio.
if [ -f "$TRABAJO/deploy/compose.yaml" ]; then
  systemctl restart tic-codec.service || echo "⚠ tic-codec no pudo levantar los contenedores: journalctl -u tic-codec"
else
  echo "⚠ Aún no hay despliegue en $TRABAJO: los contenedores se levantarán tras el primer job."
fi
# El runner NO se reinicia aquí: mataría un job en curso. El nuevo orden (esperar DNS,
# Docker y la app) se aplica en el próximo arranque del LXC; si está caído, se enciende.
[ -n "$SVC_RUNNER" ] && { systemctl is-active --quiet "$SVC_RUNNER" || systemctl start "$SVC_RUNNER"; }

estado
echo
echo "✔ Listo: al reiniciar el LXC arrancan Docker, la app y el runner, en ese orden."

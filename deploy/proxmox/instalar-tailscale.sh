#!/usr/bin/env bash
# Instala Tailscale DENTRO del LXC (no en un contenedor) y publica la app con Funnel:
#   https://<hostname>.<tailnet>.ts.net  (443)  →  127.0.0.1:5000 del LXC
#
# Se ejecuta en el HOST de Proxmox, como root, con el CTID del LXC:
#
#   bash instalar-tailscale.sh 111
#   TS_HOSTNAME=tic-codec PUERTO=5000 bash instalar-tailscale.sh 111
#
# Qué hace:
#   1. habilita /dev/net/tun para el LXC no privilegiado (reinicia el LXC si hacía falta)
#   2. instala tailscale desde el repositorio oficial (pkgs.tailscale.com)
#   3. tailscale up: la primera vez imprime un enlace de inicio de sesión (se abre una vez)
#   4. tailscale funnel --bg PUERTO (queda guardado y sobrevive reinicios)
# Es re-ejecutable.
set -euo pipefail

CTID="${1:?Uso: $0 <CTID>}"
TS_HOSTNAME="${TS_HOSTNAME:-tic-codec}"
PUERTO="${PUERTO:-5000}"
CONF="/etc/pve/lxc/${CTID}.conf"

command -v pct >/dev/null || { echo "Esto se ejecuta en el host de Proxmox (no encuentro pct)."; exit 1; }
[ -f "$CONF" ] || { echo "No existe el LXC $CTID"; exit 1; }
en_lxc() { pct exec "$CTID" -- bash -c "$1"; }

# ── 1. /dev/net/tun ──
if ! grep -q "dev/net/tun" "$CONF"; then
  echo "» Habilitando /dev/net/tun en el LXC $CTID (respaldo en /root/${CTID}.conf.bak)…"
  cp "$CONF" "/root/${CTID}.conf.bak"
  echo "lxc.cgroup2.devices.allow: c 10:200 rwm" >> "$CONF"
  echo "lxc.mount.entry: /dev/net/tun dev/net/tun none bind,create=file" >> "$CONF"
  echo "» Reiniciando el LXC para aplicar…"
  pct reboot "$CTID"
  for _ in $(seq 1 30); do en_lxc 'getent hosts pkgs.tailscale.com >/dev/null' 2>/dev/null && break; sleep 2; done
fi
en_lxc '[ -c /dev/net/tun ]' || { echo "✘ /dev/net/tun no aparece dentro del LXC"; exit 1; }

# ── 2. paquete ──
if ! en_lxc 'command -v tailscale >/dev/null'; then
  echo "» Instalando Tailscale…"
  en_lxc '. /etc/os-release
    curl -fsSL "https://pkgs.tailscale.com/stable/${ID}/${VERSION_CODENAME}.noarmor.gpg" -o /usr/share/keyrings/tailscale-archive-keyring.gpg
    curl -fsSL "https://pkgs.tailscale.com/stable/${ID}/${VERSION_CODENAME}.tailscale-keyring.list" -o /etc/apt/sources.list.d/tailscale.list
    apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq tailscale >/dev/null'
fi
en_lxc 'systemctl enable --now tailscaled >/dev/null 2>&1'

# ── 3. sesión ──
if en_lxc 'tailscale status >/dev/null 2>&1'; then
  echo "» Tailscale ya tiene sesión"
  en_lxc "tailscale set --hostname='$TS_HOSTNAME'"
else
  echo "» Abre el enlace que aparece abajo para iniciar sesión (solo esta vez):"
  en_lxc "tailscale up --hostname='$TS_HOSTNAME'"
fi

# ── 4. Funnel ──
# Se apaga y enciende para que el nodo vuelva a anunciar el ingreso de Funnel; sin esto,
# tras migrar la sesión de otro equipo/modo el relay quedaba rechazado por el filtro.
en_lxc "tailscale funnel reset >/dev/null 2>&1 || true; tailscale funnel --bg $PUERTO >/dev/null"
en_lxc 'tailscale funnel status'

cat <<EOF

✔ Tailscale en el LXC $CTID con Funnel → 127.0.0.1:$PUERTO
  Recomendado: en https://login.tailscale.com/admin/machines → ⋯ de "$TS_HOSTNAME" →
  "Disable key expiry", para que la sesión no caduque a los 180 días.
EOF

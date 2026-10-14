#!/usr/bin/env bash
# Crea en Proxmox VE el contenedor LXC que aloja Docker + el runner de GitHub Actions.
# Se ejecuta en el HOST de Proxmox, como root:
#
#   bash crear-lxc.sh                    # valores por defecto
#   CTID=210 MEMORIA=6144 bash crear-lxc.sh
#
# Al final copia y ejecuta bootstrap-lxc.sh dentro del contenedor (Docker) y deja
# instalar-runner.sh en /root/ para el siguiente paso.
set -euo pipefail

CTID="${CTID:-$(pvesh get /cluster/nextid)}"
NOMBRE="${NOMBRE:-tic-codec}"
STORAGE="${STORAGE:-local-lvm}"          # donde vive el disco raíz del LXC
TEMPLATE_STORAGE="${TEMPLATE_STORAGE:-local}"
DISCO_GB="${DISCO_GB:-20}"
NUCLEOS="${NUCLEOS:-2}"
MEMORIA="${MEMORIA:-4096}"               # MB; el códec usa bastante RAM con archivos grandes
SWAP="${SWAP:-1024}"
PUENTE="${PUENTE:-vmbr0}"
IP="${IP:-dhcp}"                         # o p. ej. 192.168.1.50/24 (con GW=192.168.1.1)
GW="${GW:-}"
SSH_PUBKEY="${SSH_PUBKEY:-}"             # ruta a una clave pública para entrar como root (opcional)

AQUI="$(cd "$(dirname "$0")" && pwd)"

command -v pct >/dev/null || { echo "Esto se ejecuta en el host de Proxmox (no encuentro pct)."; exit 1; }
if pct status "$CTID" &>/dev/null; then
  echo "Ya existe un contenedor con CTID $CTID. Usa CTID=<otro> bash $0"; exit 1
fi

# ── plantilla: la Debian "standard" más reciente disponible ──
echo "» Actualizando lista de plantillas…"
pveam update >/dev/null
PLANTILLA="$(pveam available --section system | awk '{print $2}' | grep -E '^debian-1[2-9]-standard' | sort -V | tail -1)"
[ -n "$PLANTILLA" ] || { echo "No encontré plantilla debian-*-standard"; exit 1; }
if ! pveam list "$TEMPLATE_STORAGE" | grep -q "$PLANTILLA"; then
  echo "» Descargando $PLANTILLA…"
  pveam download "$TEMPLATE_STORAGE" "$PLANTILLA"
fi

RED="name=eth0,bridge=${PUENTE},ip=${IP}"
[ -n "$GW" ] && RED="${RED},gw=${GW}"

ARGS=(
  --hostname "$NOMBRE"
  --ostype debian
  --unprivileged 1
  # nesting + keyctl: lo mínimo para que Docker funcione dentro de un LXC no privilegiado
  --features nesting=1,keyctl=1
  --cores "$NUCLEOS" --memory "$MEMORIA" --swap "$SWAP"
  --rootfs "${STORAGE}:${DISCO_GB}"
  --net0 "$RED"
  --onboot 1
  --start 1
  --description "Códec TIC (UD Lab3): Docker + Tailscale Funnel + runner de GitHub Actions"
)
[ -n "$SSH_PUBKEY" ] && ARGS+=(--ssh-public-keys "$SSH_PUBKEY")

echo "» Creando LXC $CTID ($NOMBRE) con $PLANTILLA…"
pct create "$CTID" "${TEMPLATE_STORAGE}:vztmpl/${PLANTILLA}" "${ARGS[@]}"

echo "» Esperando red dentro del contenedor…"
for _ in $(seq 1 30); do
  pct exec "$CTID" -- sh -c 'getent hosts deb.debian.org >/dev/null' && break
  sleep 2
done

echo "» Instalando Docker dentro del contenedor…"
pct push "$CTID" "$AQUI/bootstrap-lxc.sh" /root/bootstrap-lxc.sh --perms 0755
pct push "$CTID" "$AQUI/instalar-runner.sh" /root/instalar-runner.sh --perms 0755
pct exec "$CTID" -- /root/bootstrap-lxc.sh

IP_REAL="$(pct exec "$CTID" -- hostname -I | awk '{print $1}')"
cat <<EOF

✔ LXC $CTID listo ($NOMBRE, IP $IP_REAL) con Docker instalado.

Siguiente paso — registrar el runner de GitHub Actions (crea el usuario deployer y el servicio):
  1. En GitHub: Settings → Actions → Runners → New self-hosted runner → copia el token.
  2. En este host:
       pct exec $CTID -- bash /root/instalar-runner.sh https://github.com/J4F3ET/UD.Lab3.TeoriaInformacion <TOKEN>
EOF

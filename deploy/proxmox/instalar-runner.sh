#!/usr/bin/env bash
# Registra este LXC como runner self-hosted de GitHub Actions y lo deja como servicio.
# Se ejecuta DENTRO del LXC como el usuario deployer (no como root):
#
#   bash /opt/instalar-runner.sh https://github.com/J4F3ET/UD.Lab3.TeoriaInformacion <TOKEN>
#
# El TOKEN sale de GitHub → Settings → Actions → Runners → New self-hosted runner
# (dura 1 hora y solo sirve para registrar). Versión fija: RUNNER_VERSION=2.xxx.x
set -euo pipefail

URL_REPO="${1:?Uso: $0 <url-del-repo> <token-de-registro>}"
TOKEN="${2:?Falta el token de registro}"
NOMBRE="${RUNNER_NOMBRE:-$(hostname)}"
ETIQUETAS="${RUNNER_ETIQUETAS:-tic-codec,proxmox}"
DIR="${RUNNER_DIR:-$HOME/actions-runner}"

[ "$(id -u)" -ne 0 ] || { echo "Ejecútalo como el usuario deployer, no como root."; exit 1; }
docker info >/dev/null 2>&1 || { echo "Este usuario no puede usar Docker (¿está en el grupo docker?)."; exit 1; }

case "$(uname -m)" in
  x86_64) ARQ=x64 ;; aarch64) ARQ=arm64 ;; *) echo "Arquitectura no soportada: $(uname -m)"; exit 1 ;;
esac

if [ -z "${RUNNER_VERSION:-}" ]; then
  RUNNER_VERSION="$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest | jq -r .tag_name | sed 's/^v//')"
fi
echo "» actions/runner v$RUNNER_VERSION ($ARQ) en $DIR"

mkdir -p "$DIR" && cd "$DIR"
if [ ! -f ./config.sh ]; then
  curl -fsSL -o runner.tar.gz \
    "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-linux-${ARQ}-${RUNNER_VERSION}.tar.gz"
  tar xzf runner.tar.gz && rm runner.tar.gz
fi

./config.sh --unattended --replace \
  --url "$URL_REPO" --token "$TOKEN" \
  --name "$NOMBRE" --labels "$ETIQUETAS" --work _work

cat <<EOF

✔ Runner registrado como "$NOMBRE" con etiquetas: self-hosted, linux, $ETIQUETAS

Falta instalarlo como servicio (necesita root). Desde el host de Proxmox:
  pct exec <CTID> -- bash -c 'cd $DIR && ./svc.sh install $(whoami) && ./svc.sh start'
EOF

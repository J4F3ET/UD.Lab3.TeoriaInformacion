#!/usr/bin/env bash
# Instala el runner self-hosted de GitHub Actions en este LXC y lo deja corriendo como
# servicio systemd, siguiendo la guía oficial de GitHub ("Adding self-hosted runners" y
# "Configuring the self-hosted runner application as a service").
#
# Se ejecuta DENTRO del LXC como root (sirve tanto con el LXC de crear-lxc.sh como con el
# del script "Docker" de community-scripts.org):
#
#   bash instalar-runner.sh https://github.com/J4F3ET/UD.Lab3.TeoriaInformacion <TOKEN>
#
# El TOKEN sale de GitHub → Settings → Actions → Runners → New self-hosted runner
# (dura 1 hora y solo sirve para registrar).
#
# Qué hace:
#   1. dependencias del sistema (curl, jq, git, tar) y verifica que Docker funcione
#   2. crea el usuario sin privilegios "deployer" en el grupo docker (el runner NO corre como root)
#   3. descarga actions/runner, verifica su SHA-256 e instala sus dependencias (installdependencies.sh)
#   4. registra el runner con config.sh como deployer
#   5. ./svc.sh install deployer + ./svc.sh start, y excluye el servicio de needrestart
#
# Es re-ejecutable: si el runner ya está registrado, salta al paso 5.
# Variables opcionales: RUNNER_USUARIO (deployer), RUNNER_NOMBRE (hostname),
# RUNNER_ETIQUETAS (tic-codec,proxmox), RUNNER_VERSION (la última), FORZAR=1 (re-registrar).
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

URL_REPO="${1:?Uso: $0 <url-del-repo> <token-de-registro>}"
TOKEN="${2:?Falta el token de registro}"
USUARIO="${RUNNER_USUARIO:-deployer}"
NOMBRE="${RUNNER_NOMBRE:-$(hostname)}"
ETIQUETAS="${RUNNER_ETIQUETAS:-tic-codec,proxmox}"

[ "$(id -u)" -eq 0 ] || { echo "Ejecútalo como root dentro del LXC."; exit 1; }

# ── 1. dependencias y Docker ──
echo "» Dependencias del sistema…"
apt-get update -qq
apt-get install -y -qq curl jq git tar ca-certificates >/dev/null
command -v docker >/dev/null || { echo "Docker no está instalado en este LXC."; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker está instalado pero no responde (systemctl status docker)."; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Falta el plugin docker compose (apt-get install docker-compose-plugin)."; exit 1; }

# ── 2. usuario sin privilegios ──
if ! id "$USUARIO" &>/dev/null; then
  echo "» Creando usuario $USUARIO…"
  useradd --create-home --shell /bin/bash "$USUARIO"
fi
usermod -aG docker "$USUARIO"
DIR="$(getent passwd "$USUARIO" | cut -d: -f6)/actions-runner"
como() { su - "$USUARIO" -s /bin/bash -c "cd '$DIR' && $*"; }

# ── 3. descarga + checksum + dependencias del runner ──
case "$(uname -m)" in
  x86_64) ARQ=x64 ;; aarch64) ARQ=arm64 ;; *) echo "Arquitectura no soportada: $(uname -m)"; exit 1 ;;
esac
install -d -o "$USUARIO" -g "$USUARIO" "$DIR"

if [ ! -x "$DIR/config.sh" ]; then
  if [ -n "${RUNNER_VERSION:-}" ]; then RUTA="tags/v${RUNNER_VERSION}"; else RUTA="latest"; fi
  RELEASE="$(curl -fsSL "https://api.github.com/repos/actions/runner/releases/$RUTA")"
  VERSION="$(jq -r .tag_name <<<"$RELEASE" | sed 's/^v//')"
  ARCHIVO="actions-runner-linux-${ARQ}-${VERSION}.tar.gz"
  # El API publica el SHA-256 de cada asset en el campo "digest" ("sha256:…").
  SHA="$(jq -r --arg a "$ARCHIVO" '.assets[] | select(.name == $a) | .digest // empty' <<<"$RELEASE" | sed 's/^sha256://')"
  echo "» Descargando actions/runner v$VERSION ($ARQ)…"
  curl -fsSL -o "$DIR/$ARCHIVO" "https://github.com/actions/runner/releases/download/v${VERSION}/${ARCHIVO}"
  if [ -n "$SHA" ]; then
    echo "$SHA  $DIR/$ARCHIVO" | sha256sum -c --quiet - || { echo "✘ El SHA-256 no coincide"; rm -f "$DIR/$ARCHIVO"; exit 1; }
    echo "  SHA-256 verificado"
  else
    echo "  (el API no publicó el SHA-256 de este asset; se omite la verificación)"
  fi
  tar xzf "$DIR/$ARCHIVO" -C "$DIR" && rm "$DIR/$ARCHIVO"
  chown -R "$USUARIO:$USUARIO" "$DIR"
  echo "» Dependencias del runner (installdependencies.sh)…"
  "$DIR/bin/installdependencies.sh" >/dev/null
fi

# ── 4. registro (como el usuario, nunca como root) ──
if [ -f "$DIR/.runner" ] && [ "${FORZAR:-0}" = 1 ]; then
  echo "» FORZAR=1: quitando el registro local anterior…"
  (cd "$DIR" && { ./svc.sh stop || true; ./svc.sh uninstall || true; })
  rm -f "$DIR/.runner" "$DIR/.credentials" "$DIR/.credentials_rsaparams" "$DIR/.service"
fi
if [ -f "$DIR/.runner" ]; then
  echo "» El runner ya estaba registrado; se deja como está (FORZAR=1 para re-registrar)."
else
  echo "» Registrando runner \"$NOMBRE\"…"
  como ./config.sh --unattended --replace \
    --url "'$URL_REPO'" --token "'$TOKEN'" \
    --name "'$NOMBRE'" --labels "'$ETIQUETAS'" --work _work
fi

# ── 5. servicio systemd ──
cd "$DIR"
if [ ! -f .service ]; then
  echo "» Instalando servicio systemd (usuario $USUARIO)…"
  ./svc.sh install "$USUARIO"
fi
./svc.sh start || true
# Que needrestart no reinicie el runner en medio de un job (recomendación de GitHub).
if [ -d /etc/needrestart ]; then
  mkdir -p /etc/needrestart/conf.d
  echo '$nrconf{override_rc}{qr(^actions\.runner\..+\.service$)} = 0;' \
    > /etc/needrestart/conf.d/actions_runner_services.conf
fi

sleep 2
if systemctl is-active --quiet "$(cat .service)"; then
  cat <<EOF

✔ Runner "$NOMBRE" activo como servicio $(cat .service)
  usuario: $USUARIO · etiquetas: self-hosted, linux, $ETIQUETAS
  Debe aparecer "Idle" en GitHub → Settings → Actions → Runners.
  Estado:   cd $DIR && ./svc.sh status
  Logs:     journalctl -u $(cat .service) -f
EOF
else
  echo "✘ El servicio no quedó activo:"; ./svc.sh status || true; exit 1
fi

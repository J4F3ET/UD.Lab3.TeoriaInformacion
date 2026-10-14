#!/usr/bin/env bash
# Prepara el LXC (Debian) por dentro: Docker Engine + plugin compose desde el
# repositorio oficial y un usuario "deployer" (grupo docker) para el runner.
# Se ejecuta como root dentro del contenedor; crear-lxc.sh lo llama solo.
# Es idempotente: se puede volver a correr sin romper nada.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

USUARIO="${USUARIO:-deployer}"

echo "» Paquetes base…"
apt-get update -qq
apt-get upgrade -y -qq
apt-get install -y -qq ca-certificates curl gnupg jq git tar unattended-upgrades

echo "» Repositorio oficial de Docker…"
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
. /etc/os-release
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian ${VERSION_CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list
apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# Rotación de logs de contenedores para no llenar el disco del LXC.
cat > /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
EOF
systemctl enable --now docker
systemctl restart docker

echo "» Usuario $USUARIO…"
id "$USUARIO" &>/dev/null || useradd --create-home --shell /bin/bash "$USUARIO"
usermod -aG docker "$USUARIO"
[ -f /root/instalar-runner.sh ] && install -m 0755 /root/instalar-runner.sh /opt/instalar-runner.sh

echo "» Prueba de Docker…"
if docker run --rm hello-world >/dev/null; then
  echo "✔ Docker funciona dentro del LXC"
else
  echo "✘ Docker no pudo arrancar un contenedor. Revisa deploy/README.md → Problemas comunes."
  exit 1
fi

# Despliegue — Proxmox LXC + Docker + Tailscale Funnel + GitHub Actions

```
GitHub (push a main)
   │  job "pruebas" en ubuntu-latest: pytest + docker build
   ▼
Runner self-hosted (dentro del LXC)  ── job "desplegar"
   │  docker compose -f deploy/compose.yaml -p tic-codec up -d --build
   ▼
LXC (Debian, no privilegiado, nesting=1, /dev/net/tun)
 ├─ tailscaled (instalado en el LXC)  ── Funnel :443 ──►  https://tic-codec.<tailnet>.ts.net
 │        └─ proxy → 127.0.0.1:5000
 ├─ contenedor app: la interfaz src/app.py con gunicorn, publicada en 127.0.0.1:5000
 └─ contenedor limpieza: borra data/gui/<id>/ viejos
```

**Por qué 443:** Funnel solo acepta los puertos 443, 8443 y 10000. Con 443 la URL pública es
`https://tic-codec.<tailnet>.ts.net` sin `:puerto`, con certificado TLS válido que Tailscale
emite y renueva solo. No se abre ningún puerto en el router, y la app solo escucha en `127.0.0.1` del LXC.

**Por qué Tailscale en el LXC y no en un contenedor:** con un contenedor sidecar, la app comparte
su red; cada vez que ese contenedor se reiniciaba, la app quedaba en una red muerta y Funnel daba
**502**. Instalado en el LXC, Tailscale y la app se reinician sin afectarse.

---

## 1. Tailscale (consola, una sola vez)

En https://login.tailscale.com/admin:

1. **DNS:** **MagicDNS** y **HTTPS Certificates** activados (Funnel necesita el certificado).
2. Que tu política permita Funnel. La política por defecto ya lo trae
   (`"nodeAttrs": [{"target": ["autogroup:member"], "attr": ["funnel"]}]`); si la editaste y lo
   quitaste, vuelve a agregarlo.

No hace falta auth key, secret ni etiquetas: el inicio de sesión se hace una vez con un enlace
(paso 3b).

## 2. Crear el LXC en Proxmox

### Opción A (recomendada): script "Docker" de community-scripts.org

En la shell del **host** de Proxmox (como root). Crea un LXC Debian 13 no privilegiado con Docker
ya instalado; las variables suben los recursos por defecto (2 GB RAM / 4 GB disco no alcanzan):

```bash
var_os=debian var_cpu=2 var_ram=4096 var_disk=20 bash -c "$(curl -fsSL https://raw.githubusercontent.com/community-scripts/ProxmoxVE/main/ct/docker.sh)"
```

- Si muestra el menú, elige **Default** (las variables ya fijan los recursos) o **Advanced** para
  cambiar hostname/IP. Un nombre como `tic-codec` ayuda a reconocerlo.
- Cuando ofrezca complementos (Portainer, Dockge, Komodo…) puedes decir que **no**: el despliegue
  lo hace GitHub Actions.
- Al terminar imprime el **CTID** del contenedor; anótalo.

### Opción B: `crear-lxc.sh` de este repo

```bash
bash deploy/proxmox/crear-lxc.sh
```

| Variable | Defecto | Para qué |
|---|---|---|
| `CTID` | siguiente libre | ID del contenedor |
| `STORAGE` | `local-lvm` | almacenamiento del disco raíz |
| `DISCO_GB` / `NUCLEOS` / `MEMORIA` | `20` / `2` / `4096` | recursos (MEMORIA en MB) |
| `PUENTE` / `IP` / `GW` | `vmbr0` / `dhcp` / — | red; ej. `IP=192.168.1.50/24 GW=192.168.1.1` |
| `SSH_PUBKEY` | — | ruta a una clave pública para entrar por SSH |

Descarga la plantilla Debian *standard* más reciente, crea el LXC con `nesting=1,keyctl=1`,
instala Docker desde el repositorio oficial y deja `instalar-runner.sh` en `/root/`.

## 3. Registrar el runner de GitHub Actions

`deploy/proxmox/instalar-runner.sh` hace todo lo que pide la guía oficial de GitHub, como root
dentro del LXC:

1. instala `curl jq git tar` y comprueba que Docker y `docker compose` respondan;
2. crea el usuario **`deployer`** (sin privilegios, en el grupo `docker`) — el runner **no** corre como root;
3. descarga la última versión de `actions/runner`, **verifica su SHA-256** con el que publica
   GitHub y corre `bin/installdependencies.sh`;
4. registra el runner con `config.sh` **como `deployer`**, con las etiquetas `tic-codec,proxmox`;
5. `./svc.sh install deployer` + `./svc.sh start` (servicio systemd que arranca con el LXC) y
   excluye el servicio de `needrestart` para que no lo reinicien a mitad de un job.

Es re-ejecutable: si el runner ya está registrado solo se asegura de que el servicio esté
instalado y activo (`FORZAR=1` para registrarlo de nuevo).

**Pasos** (cambia `111` por tu CTID):

1. Copia el script al LXC desde el host de Proxmox (el repo es privado, no se puede bajar con
   `curl`; hace falta el repo clonado en el host, o pega el archivo a mano en el LXC).
   Con la opción B ya está en `/root/` y te saltas esto.
   ```bash
   pct push 111 deploy/proxmox/instalar-runner.sh /root/instalar-runner.sh --perms 0755
   ```
2. GitHub → repo → **Settings → Actions → Runners → New self-hosted runner** → copia solo
   el **token** (dura 1 hora).
3. Ejecuta:
   ```bash
   pct exec 111 -- bash /root/instalar-runner.sh https://github.com/J4F3ET/UD.Lab3.TeoriaInformacion TOKEN_AQUI
   ```
4. Debe terminar con `✔ Runner "…" activo como servicio actions.runner.…` y salir **Idle** en
   Settings → Actions → Runners, con las etiquetas `self-hosted, linux, tic-codec, proxmox`.

> El repo es privado, así que nadie de afuera puede mandar código a ese runner. Si algún día
> se vuelve público, el job de despliegue igual nunca corre en `pull_request`, pero conviene
> activar *Require approval for all outside collaborators* en Settings → Actions.

## 3b. Instalar Tailscale en el LXC y activar Funnel

En el host de Proxmox, con el repo (o el script) a mano:

```bash
bash deploy/proxmox/instalar-tailscale.sh 111
```

1. Habilita `/dev/net/tun` para el LXC (agrega dos líneas a `/etc/pve/lxc/111.conf`, deja un
   respaldo en `/root/111.conf.bak` y reinicia el LXC una vez).
2. Instala Tailscale desde el repositorio oficial.
3. `tailscale up --hostname=tic-codec`: la primera vez imprime un enlace; ábrelo y autoriza el
   equipo. La sesión queda en `/var/lib/tailscale` del LXC.
4. `tailscale funnel --bg 5000`: queda guardado y sobrevive reinicios del LXC.

Recomendado: en la consola, menú `⋯` de `tic-codec` → **Disable key expiry**.

## 4. Variables en GitHub (opcional)

**Settings → Secrets and variables → Actions:**

| Tipo | Nombre | Valor |
|---|---|---|
| Variable | `URL_PUBLICA` | `https://tic-codec.<tailnet>.ts.net` — sale como enlace en cada despliegue |

## 5. Desplegar

Cualquier push a `main` (o **Actions → CI/CD → Run workflow**) hace:

1. **pruebas** (`ubuntu-latest`): `pytest` de la interfaz (`tests/test_app.py`: subir → codificar → decodificar) y `docker build` para confirmar que la imagen construye.
2. **desplegar** (runner del LXC): `docker compose up -d --build`, espera a que el healthcheck de
   la app quede `healthy`, muestra `tailscale funnel status` (del Tailscale del LXC) y borra
   imágenes viejas. Si el Funnel está apagado, el job lo avisa en amarillo.

En el log de "Estado de Tailscale / Funnel" debe aparecer
`https://tic-codec.<tailnet>.ts.net (Funnel on)`.

## Operación

Desde el host de Proxmox: `pct enter 111`, luego `su - deployer` y
`cd ~/actions-runner/_work/UD.Lab3.TeoriaInformacion/UD.Lab3.TeoriaInformacion`:

```bash
docker compose -f deploy/compose.yaml -p tic-codec ps
```
```bash
docker compose -f deploy/compose.yaml -p tic-codec logs -f app
```
```bash
tailscale funnel status
```

Ajustes (variables de entorno del job o de un `.env` junto a `compose.yaml`):

| Variable | Defecto | |
|---|---|---|
| `TIC_MAX_MB` | `256` | tamaño máximo de subida en el despliegue (en local sigue siendo 2 GB) |
| `TIC_TTL_MIN` | `120` | minutos que se conservan las fuentes, `.tic` y reconstruidos de `data/gui/` |
| `TIC_MEM` | `3g` | límite de RAM del contenedor app |

La interfaz guarda todo lo que se sube o genera en el volumen `tic-codec_datos`; el servicio
`limpieza` borra cada 10 min las carpetas con más de `TIC_TTL_MIN` minutos para que el disco
del LXC no se llene. Si subes `TIC_MAX_MB`, sube también `TIC_MEM` (con k grandes el códec usa
varias veces el tamaño del archivo en RAM) y el disco del LXC (`pct resize <CTID> rootfs +10G`).

## Probar en local sin Proxmox

```bash
pip install -r requirements-dev.txt
```
```bash
python src/app.py
```
y abrir http://127.0.0.1:5000. Con Docker, igual que en producción:
`docker build -t tic-codec-gui . && docker run --rm -p 5000:5000 tic-codec-gui`.

## Problemas comunes

- **`hello-world` falla con un error de AppArmor / `permission denied` sobre `sysctl` o `/proc`.**
  Algunas combinaciones de Proxmox + versiones nuevas de `containerd.io`/`runc` rompen Docker
  en LXC no privilegiados. Solución: en el host, añadir a `/etc/pve/lxc/<CTID>.conf`
  ```
  lxc.apparmor.profile: unconfined
  ```
  y reiniciar el LXC (`pct reboot <CTID>`). Alternativa más estricta: fijar una versión anterior
  de `containerd.io` con `apt-mark hold`.
- **Disco raíz en ZFS y Docker se queja de `overlay`.** Con ZFS ≥ 2.2 (Proxmox 8.1+) overlay
  funciona; en versiones viejas usa `STORAGE=local-lvm` o configura `"storage-driver": "fuse-overlayfs"`.
- **Funnel no aparece / `funnel not available`.** Tu política no tiene el `nodeAttrs` con
  `funnel`, o HTTPS Certificates está desactivado en el tailnet.
- **Funnel da 502.** La app no responde en `127.0.0.1:5000` del LXC: revisa
  `docker compose … ps` y `curl -I http://127.0.0.1:5000/` dentro del LXC.
- **Funnel da error de TLS / no conecta pero `tailscale funnel status` dice "Funnel on".**
  El relay de Funnel no está llegando al nodo (en `journalctl -u tailscaled` aparecen líneas
  `Drop: TCP … no rules matched`). Vuelve a correr `instalar-tailscale.sh 111`, que apaga y
  enciende el Funnel para que se anuncie de nuevo.
- **El nodo aparece como `tic-codec-1`.** Quedó un nodo viejo con el mismo nombre: bórralo en la
  consola de Tailscale y corre `tailscale set --hostname=tic-codec` en el LXC.
- **Cambiar de tailnet o regenerar identidad:** en el LXC, `tailscale logout` y vuelve a correr
  `instalar-tailscale.sh`.

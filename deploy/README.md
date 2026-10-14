# Despliegue — Proxmox LXC + Docker + Tailscale Funnel + GitHub Actions

```
GitHub (push a main)
   │  job "pruebas" en ubuntu-latest: pytest + docker build
   ▼
Runner self-hosted (dentro del LXC)  ── job "desplegar"
   │  docker compose -f deploy/compose.yaml -p tic-codec up -d --build
   ▼
LXC "tic-codec" (Debian, no privilegiado, nesting=1)
 ├─ contenedor tailscale  ── Funnel :443 ──►  https://tic-codec.<tailnet>.ts.net
 └─ contenedor app (uvicorn :8000, comparte la red del de tailscale)
```

**Por qué 443:** Funnel solo acepta los puertos 443, 8443 y 10000. Con 443 la URL pública es
`https://tic-codec.<tailnet>.ts.net` sin `:puerto`, con certificado TLS válido que Tailscale
emite y renueva solo. No se abre ningún puerto en el router ni en el LXC.

---

## 1. Tailscale (una sola vez, en https://login.tailscale.com/admin)

1. **DNS → MagicDNS** activado y **HTTPS Certificates** activado.
2. **Access controls** (política del tailnet): declarar la etiqueta y darle permiso de Funnel.
   ```jsonc
   "tagOwners": {
     "tag:tic-codec": ["autogroup:admin"]
   },
   "nodeAttrs": [
     { "target": ["tag:tic-codec"], "attr": ["funnel"] }
   ]
   ```
   Si ya tienes un bloque `nodeAttrs`, agrega solo el objeto. Si tu política tiene
   `grants`/`acls` restrictivos no hace falta abrir nada: Funnel entra por fuera del tailnet.
3. **Settings → Keys → Generate auth key**: *Reusable* no, *Ephemeral* **no**, *Tags*
   `tag:tic-codec`. Copia el `tskey-auth-…` — va a GitHub en el paso 4.
   (La llave solo se usa en el primer arranque; la identidad queda en el volumen `ts-state`,
   y los nodos con etiqueta no expiran.)

## 2. Crear el LXC en Proxmox

Desde una shell en el **host** de Proxmox (como root), con el repo o solo la carpeta
`deploy/proxmox/` copiada:

```bash
bash deploy/proxmox/crear-lxc.sh
```

Variables opcionales (todas tienen valor por defecto):

| Variable | Defecto | Para qué |
|---|---|---|
| `CTID` | siguiente libre | ID del contenedor |
| `STORAGE` | `local-lvm` | almacenamiento del disco raíz |
| `DISCO_GB` / `NUCLEOS` / `MEMORIA` | `20` / `2` / `4096` | recursos (MEMORIA en MB) |
| `PUENTE` / `IP` / `GW` | `vmbr0` / `dhcp` / — | red; ej. `IP=192.168.1.50/24 GW=192.168.1.1` |
| `SSH_PUBKEY` | — | ruta a una clave pública para entrar por SSH |

Ejemplo: `CTID=210 MEMORIA=6144 STORAGE=local-zfs bash deploy/proxmox/crear-lxc.sh`

El script descarga la plantilla Debian *standard* más reciente, crea un LXC **no privilegiado**
con `nesting=1,keyctl=1`, instala Docker desde el repositorio oficial, crea el usuario
`deployer` (grupo `docker`) y prueba `hello-world`.

## 3. Registrar el runner de GitHub Actions

1. GitHub → repo → **Settings → Actions → Runners → New self-hosted runner** → copia solo
   el **token** (dura 1 hora).
2. En el host de Proxmox (cambia `210` por tu CTID):
   ```bash
   pct exec 210 -- su - deployer -c 'bash /opt/instalar-runner.sh https://github.com/J4F3ET/UD.Lab3.TeoriaInformacion TOKEN_AQUI'
   ```
   ```bash
   pct exec 210 -- bash -c 'cd /home/deployer/actions-runner && ./svc.sh install deployer && ./svc.sh start'
   ```
3. El runner debe salir **Idle** en Settings → Actions → Runners, con las etiquetas
   `self-hosted, linux, tic-codec, proxmox`. El workflow lo elige por `tic-codec`.

> El repo es privado, así que nadie de afuera puede mandar código a ese runner. Si algún día
> se vuelve público, el job de despliegue igual nunca corre en `pull_request`, pero conviene
> activar *Require approval for all outside collaborators* en Settings → Actions.

## 4. Secretos y variables en GitHub

**Settings → Secrets and variables → Actions:**

| Tipo | Nombre | Valor |
|---|---|---|
| Secret | `TS_AUTHKEY` | la llave `tskey-auth-…` del paso 1.3 |
| Variable (opcional) | `TS_HOSTNAME` | nombre del nodo; define la URL. Defecto `tic-codec` |
| Variable (opcional) | `URL_PUBLICA` | `https://tic-codec.<tailnet>.ts.net` — sale como enlace en cada despliegue |

Además, en **Settings → Environments** se crea solo el entorno `produccion` en el primer
despliegue; ahí puedes exigir aprobación manual o limitarlo a la rama `main`.

## 5. Desplegar

Cualquier push a `main` (o **Actions → CI/CD → Run workflow**) hace:

1. **pruebas** (`ubuntu-latest`): `pytest` de la API y `docker build` para confirmar que la imagen construye.
2. **desplegar** (runner del LXC): `docker compose up -d --build`, espera a que el healthcheck de
   la app quede `healthy`, muestra `tailscale funnel status` y borra imágenes viejas.

La primera vez, en el log de "Estado de Tailscale / Funnel" debe aparecer la URL
`https://tic-codec.<tailnet>.ts.net (Funnel on)`. El primer acceso puede tardar ~1 min
mientras se emite el certificado.

## Operación

Desde el host de Proxmox: `pct enter 210`, luego `su - deployer` y
`cd ~/actions-runner/_work/UD.Lab3.TeoriaInformacion/UD.Lab3.TeoriaInformacion`:

```bash
docker compose -f deploy/compose.yaml -p tic-codec ps
```
```bash
docker compose -f deploy/compose.yaml -p tic-codec logs -f app
```
```bash
docker compose -f deploy/compose.yaml -p tic-codec exec tailscale tailscale funnel status
```

Ajustes de la app (variables de entorno del job o de un `.env` junto a `compose.yaml`):

| Variable | Defecto | |
|---|---|---|
| `TIC_MAX_MB` | `64` | tamaño máximo de subida |
| `TIC_TRABAJOS` | `1` | codificaciones simultáneas (el resto espera en cola) |
| `TIC_TTL_MIN` | `30` | minutos que se guardan .tic / gráfica / reporte para descargar |
| `TIC_MEM` | `3g` | límite de RAM del contenedor app |
| `TIC_TMP_MB` | `1024` | tamaño del tmpfs donde se procesan los archivos |

Si subes `TIC_MAX_MB`, sube también `TIC_TMP_MB` (entrada + .tic + gráfica caben ahí) y
`TIC_MEM` (con k grandes el códec usa varias veces el tamaño del archivo en RAM).

## Probar en local sin Proxmox

```bash
pip install -r requirements-dev.txt
```
```bash
python -m uvicorn web.app:app --reload
```
o con Docker: `docker build -t tic-codec-web . && docker run --rm -p 8000:8000 tic-codec-web`
y abrir http://localhost:8000.

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
- **Funnel no aparece / `funnel not available`.** Falta el `nodeAttrs` con `funnel` para
  `tag:tic-codec`, o HTTPS Certificates está desactivado en el tailnet.
- **El nodo aparece como `tic-codec-1`.** Quedó un nodo viejo con el mismo nombre: bórralo en la
  consola de Tailscale y reinicia el contenedor `tailscale`.
- **Cambiar de tailnet o regenerar identidad:** `docker compose … down` y
  `docker volume rm tic-codec_ts-state`; el próximo despliegue usa `TS_AUTHKEY` de nuevo
  (genera una llave nueva si la anterior expiró).

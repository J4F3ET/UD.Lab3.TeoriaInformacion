# Despliegue — Proxmox LXC + Docker + Tailscale Funnel + GitHub Actions

```
GitHub (push a main)
   │  pruebas: pytest (ubuntu-latest)
   │  imagen:  docker build + push, solo si app-<huella> aún no existe
   ▼
GHCR  ghcr.io/j4f3et/ud.lab3.teoriainformacion:app-<huella>
   │  el LXC solo hace docker pull: no compila nada
   ▼
Runner self-hosted (dentro del LXC)  ── job "desplegar"
   │  bash deploy/desplegar.sh <imagen>
   ▼
LXC (Debian, no privilegiado, nesting=1, /dev/net/tun)
 ├─ tailscaled (instalado en el LXC)  ── Funnel :443 ──►  https://tic-codec.<tailnet>.ts.net
 │        └─► 127.0.0.1:5000
 ├─ proxy nginx en 127.0.0.1:5000 ──┬──► app-azul   (127.0.0.1:5001)
 │   upstream.conf elige el slot    └──► app-verde  (127.0.0.1:5002)
 │   azul y verde montan el mismo volumen `datos` (/app/data)
 ├─ limpieza: borra data/gui/<id>/ viejos cada 10 min
 ├─ /var/lib/tic-codec   estado: activo, slots.env, proxy/upstream.conf, huellas/
 └─ /opt/tic-codec       copia de compose.yaml, nginx/ y servicios.conf
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
4. `tailscale funnel --bg 5000`: queda guardado y sobrevive reinicios del LXC. Funnel apunta al
   proxy (`:5000`), no a la app.

Recomendado: en la consola, menú `⋯` de `tic-codec` → **Disable key expiry**.

## 3c. Arranque automático (después de un reinicio)

Para que, al reiniciar el LXC o el host de Proxmox, todo vuelva a quedar arriba solo y **en orden**
(red y DNS → Docker → proxy y app → runner), en el host de Proxmox:

```bash
bash deploy/proxmox/arranque-automatico.sh 111
```

1. `pct set 111 --onboot 1`: el LXC arranca junto con Proxmox.
2. Deja `docker`, `containerd` y `tailscaled` habilitados al arranque.
3. Crea el estado y la copia de despliegue, con dueño el usuario del runner: `/var/lib/tic-codec`
   (slot activo `azul`, `slots.env` e `upstream.conf` con la imagen por defecto) y `/opt/tic-codec`.
   Si nunca se ha desplegado, la app arranca igual en el slot azul.
4. Crea el servicio **`tic-codec`**, que al arrancar ejecuta `/usr/local/bin/tic-codec-arrancar`:
   levanta el proxy, la limpieza y el slot activo (`app-azul` o `app-verde`, según
   `/var/lib/tic-codec/activo`) desde `/opt/tic-codec`, sin build ni pull. Así vuelven aunque alguien
   los haya bajado con `compose down`, además del `restart: unless-stopped` de `compose.yaml`.
5. Al servicio del runner le agrega un *drop-in* para que arranque **después** de la red, Docker,
   Tailscale y la app, y que antes **espere a poder resolver `github.com`** (hasta 120 s). Sin esto,
   tras un reinicio el runner llegó a tomar un job sin DNS y falló con
   `Could not resolve host: github.com`. También se reinicia solo si se cae (`Restart=always`).
6. Instala el **vigía del LXC** (`tic-codec-vigia.timer`, cada 2 min). Revisa `:5000/salud` a través
   del proxy; si no responde, espera 20 s y levanta el proxy y/o `app-<activo>`. Levanta también los
   auxiliares con `critico=si` del catálogo, y revisa Tailscale/Funnel y el runner. Si el disco pasa
   del 90 %, borra imágenes y caché de construcción de Docker. No toca los contenedores mientras hay
   un despliegue en curso (usa el mismo bloqueo). Cada acción queda registrada en
   `journalctl -u tic-codec-vigia`.
7. Instala en el **host** el vigía del LXC (`vigia-lxc@111.timer`, cada 5 min): si el LXC está
   apagado, lo enciende. `onboot=1` solo actúa al arrancar Proxmox; el vigía cubre el caso en que
   el LXC se apaga o no arranca después.

Para apagar algo a propósito sin que los vigías lo vuelvan a levantar:
`touch /root/vigia-lxc-111.pausa` en el host, o `touch /root/vigia.pausa` dentro del LXC.
Borra el archivo para reactivarlos.

No reinicia el runner mientras pueda estar corriendo un job: el nuevo orden se aplica en el próximo
arranque. Para comprobarlo de una vez, `PROBAR=1 bash deploy/proxmox/arranque-automatico.sh 111`
reinicia el LXC y verifica que la app responda. Ver el estado en cualquier momento:

```bash
pct exec 111 -- bash /root/arranque-automatico.sh --estado
```

## 4. Variables en GitHub (opcional)

**Settings → Secrets and variables → Actions:**

| Tipo | Nombre | Valor |
|---|---|---|
| Variable | `URL_PUBLICA` | `https://tic-codec.<tailnet>.ts.net` — sale como enlace en cada despliegue |

## 5. Desplegar

Cualquier push a `main` que toque algo más que documentación (o **Actions → CI/CD → Run workflow**)
lanza tres jobs en cadena:

1. **pruebas** (`ubuntu-latest`, 20 min): `pytest` de la interfaz (`tests/test_app.py`: subir → codificar → decodificar).
   En pull requests además comprueba que la imagen construye (`docker build`), sin publicarla.
2. **imagen** (`ubuntu-latest`, 30 min, solo en push o ejecución manual): calcula la huella de la app.
   Si `ghcr.io/j4f3et/ud.lab3.teoriainformacion:app-<huella>` ya existe, lo reutiliza y no construye;
   si no, construye y publica con la caché de GitHub Actions.
3. **desplegar** (runner del LXC, 45 min, un despliegue a la vez): entra en ghcr.io con `GITHUB_TOKEN`,
   ejecuta `bash deploy/desplegar.sh <imagen>`, muestra el estado de Tailscale/Funnel, avisa si
   cambiaron los scripts del LXC y borra imágenes sin uso.

Cómo se despliega la app sin caída está en la sección siguiente; qué se toca según lo que cambió,
en la siguiente a esa.

**Monitor externo** (`.github/workflows/monitor.yml`): cada 30 min un runner de GitHub (no el del
LXC) prueba `URL_PUBLICA`. Si no responde 3 veces seguidas, abre el issue «Servicio caído…»
(GitHub te avisa por correo) y lo cierra cuando el servicio vuelve. Es la única alarma que funciona
aunque el LXC entero esté apagado. Necesita la variable `URL_PUBLICA` del paso 4.

En el log de "Estado de Tailscale / Funnel" debe aparecer
`https://tic-codec.<tailnet>.ts.net (Funnel on)`.

## Cómo se despliega sin caída

El proxy (servicio `proxy`, nginx) es el único punto de entrada, en `127.0.0.1:5000`, y reenvía al
slot activo (`app-azul` o `app-verde`, según `/var/lib/tic-codec/activo`). Un despliegue levanta la
versión nueva en el slot **inactivo**, la verifica y solo entonces mueve el tráfico.
`bash deploy/desplegar.sh <imagen>` hace esto en orden:

1. **Preparación.** Copia `compose.yaml`, `servicios.conf` y `nginx/` del checkout a `/opt/tic-codec`
   y toma el bloqueo `desplegar.lock`. Si otro despliegue está en curso, espera hasta 20 min.
2. **Pull.** Descarga la imagen con 3 intentos (espera de 30 s y 60 s entre ellos). Si el slot activo
   ya corre esa imagen, no hace pull y marca `sin cambios`. Si no puede descargarla y no hay copia
   local, aborta sin tocar nada: el job falla con `falló (sigue la versión anterior)`.
3. **Servicios auxiliares** (`proxy`, `limpieza` y los que haya en el catálogo; ver
   «Desplegar solo lo que cambió»). Van antes que la app. Si un auxiliar con `critico=si` no queda
   bien, el despliegue se detiene aquí y la app no se toca. Si es `critico=no`, solo avisa. Si la
   nueva configuración de nginx no pasa `nginx -t`, el proxy sigue con la anterior. El proxy puede
   arrancar antes que la app: resuelve el nombre del slot en cada petición (resolver de Docker,
   127.0.0.11) y responde 502 hasta que la app esté.
4. **Slot inactivo.** Levanta `app-<inactivo>` con la imagen nueva (con `--force-recreate` si ya
   existía) y espera hasta 10 min a que esté `healthy` (o sin healthcheck) y responda `/salud` y `/`
   en su puerto directo (5001 o 5002). Si no lo consigue, guarda los últimos 100 logs, lo detiene,
   lo quita y restaura `slots.env`.
   **Garantía:** el slot activo y el tráfico no se han tocado.
5. **Cambio de tráfico.** Escribe `upstream.conf` (`map "" $tic_app { default app-<slot>:5000; }`), ejecuta `nginx -t` y
   `nginx -s reload` (la recarga no corta las conexiones en curso). Si nginx rechaza la
   configuración, restaura el upstream anterior (`nginx -t` no detecta un contenedor inexistente: el
   nombre se resuelve en cada petición). Luego comprueba `/salud` y `/` **a través del
   proxy** (10 intentos de 1 s). Si no responde bien, vuelve al slot anterior y descarta el nuevo.
   **Garantía:** el tráfico solo pasa al slot nuevo cuando ya ha respondido por el proxy.
6. **Activo.** Escribe `/var/lib/tic-codec/activo` con el slot nuevo. Desde aquí es el oficial.
7. **Drenaje del viejo.** Sondea `/salud` del slot viejo cada 5 s, hasta 15 min, y da el drenaje por
   terminado cuando `activas` vale 0 dos veces seguidas (terminan las conversiones largas en curso).
   Luego hace `docker stop -t 30 app-<viejo>`. **No lo borra**: el contenedor y su imagen se quedan
   para `--volver`. Si tras 15 min seguía con peticiones, avisa y lo detiene igualmente.
8. **Resumen.** Imprime la tabla `servicio | estado | detalle` en el log y en el resumen del job.

En el primer despliegue no hay slot corriendo: no hay nada que drenar, la app se levanta en azul y,
si el proxy todavía no existe, se levanta cuando la app está sana.

**Qué pasa si falla algo:** antes del paso 5 el usuario sigue viendo la versión anterior. Si falla
el drenaje, la versión nueva ya es la activa y solo queda un contenedor parado.

### Ver el estado y volver atrás

Desde el checkout del runner (ver «Operación»):

```bash
bash deploy/desplegar.sh --estado
```

No cambia nada. Muestra el slot activo, las imágenes de azul y verde, cada contenedor con su
salud y sus conexiones activas, la huella guardada frente a la actual de cada servicio, y si el
proxy responde en `:5000/salud`.

```bash
bash deploy/desplegar.sh --volver
```

Vuelve al otro slot, con la imagen que tenía (la versión anterior). Si su contenedor sigue creado,
lo reutiliza; si no, descarga la imagen. Falla si nunca hubo un despliegue anterior o si la imagen
anterior es la misma que la activa. El cambio de tráfico tarda segundos, pero el comando luego
espera a drenar el slot que deja (hasta 15 min), así que puede tardar más. Como toda ejecución del
script, copia antes `compose.yaml`, `nginx/` y `servicios.conf` desde el checkout en el que lo lanzas.

## Desplegar solo lo que cambió

Hay tres niveles, de fuera hacia dentro:

1. **Qué lanza el workflow.** Los cambios que solo tocan `**/*.md`, `docs/`, `reports/`, `diagrams/`,
   `plans/` o `examples/` no disparan el workflow (`paths-ignore`). **Run workflow** siempre lo lanza.
2. **Qué imagen se construye (job `imagen`).** La huella de la app es el resultado de
   `deploy/huella.sh` sobre las entradas de la línea `app` de `servicios.conf` (hoy
   `Dockerfile requirements.txt src`): `git ls-tree -r HEAD`, sha256, 12 caracteres hexadecimales.
   Depende solo del contenido de esos archivos, no del commit ni de los tests. Si ya existe
   `app-<huella>` en GHCR, se reutiliza y no se construye. El workflow y `desplegar.sh` usan el mismo
   script, así que siempre calculan la misma huella.
3. **Qué se toca en el LXC (job `desplegar`).** Por cada línea de `servicios.conf`:
   - **`app`:** si el slot activo ya corre esa imagen, `sin cambios`. Si no, despliegue azul/verde
     (sección anterior).
   - **`aux` con entradas** (p. ej. `proxy` con `deploy/nginx`): guarda su huella en
     `/var/lib/tic-codec/huellas/<servicio>`. Si cambió, recrea el contenedor → `actualizado`. El
     proxy es la excepción: si solo cambió su configuración, no se recrea (montar la carpeta permite
     cambiar archivos sin tocar el contenedor); se prueba con `nginx -t` y se recarga → `recargado`.
     Si no cambió, `sin cambios`.
   - **`aux` sin entradas** (`-`, p. ej. `limpieza`): se ejecuta `up -d` siempre. Compose solo recrea
     el contenedor si cambió su definición en `compose.yaml` → `actualizado` o `sin cambios`.

Los estados del resumen (`$GITHUB_STEP_SUMMARY`) son:

| Estado | Significado |
|---|---|
| `sin cambios` | nada que hacer |
| `actualizado` | creado o recreado |
| `recargado` | nginx recargado con la nueva configuración del proxy |
| `falló (sigue la versión anterior)` | un auxiliar `critico=si` o la app no quedaron sanos; la app no se cambió |
| `falló (aviso, no crítico)` | un auxiliar `critico=no` falló; el despliegue continúa |

**Scripts del LXC.** Si cambian archivos de `deploy/proxmox/`, el workflow no los aplica. Solo emite
un `::notice::` cuando la huella de esa carpeta no coincide con la que guardó
`arranque-automatico.sh` (o nunca se guardó). Para aplicarlos, corre `arranque-automatico.sh` como
root en el LXC.

## Agregar un servicio

Un servicio nuevo se declara en dos sitios, `deploy/compose.yaml` y `deploy/servicios.conf`, y el
despliegue lo trata según su tipo. Pauta:

1. **Bloque en `deploy/compose.yaml`** con `<<: *base` (logs acotados, `restart: unless-stopped`,
   `init`). Publica el puerto solo en `127.0.0.1`. Si guarda datos, un volumen propio declarado al
   final del archivo. Pon `mem_limit`.
2. **Línea en `deploy/servicios.conf`.** Tipo `aux` si es una imagen externa con versión fija
   (**nunca `:latest`**). Tipo `app` solo para la interfaz: el workflow construye una única imagen
   (la línea `app`). En entradas, los archivos del repo que el contenedor monta o configura (p. ej.
   `deploy/grafana`); `-` si toda su configuración está en `compose.yaml`.
3. **Publicación hacia fuera (opcional).** Si debe verse desde internet, hay dos caminos:
   - una ruta en el proxy: un `location` nuevo dentro de `deploy/nginx/default.conf`. No crees otro
     `.conf` en esa carpeta: `default.conf` debe ser el único. Ojo: con `proxy_pass` a un nombre
     literal nginx lo resuelve
     solo al cargar (y `nginx -t` falla si el contenedor no existe); usa una variable (`set $destino
     servicio:puerto; proxy_pass http://$destino;`), que se resuelve por petición con el resolver ya
     definido;
   - o un puerto de Funnel aparte (443, 8443 o 10000; la sintaxis está en `tailscale funnel --help`).
     El vigía solo restaura el Funnel del `:5000`, así que el puerto extra hay que vigilarlo a mano.

   Si el servicio no tiene nada que ver con las rutas del proxy, no hace falta tocar nginx.
4. **Healthcheck y criticidad.** Pon un `healthcheck` en compose: el despliegue espera hasta 2 min a
   que quede `healthy`. Si el servicio es `critico=si`, el vigía lo levanta cada 2 min y el despliegue
   se detiene antes de tocar la app si no queda sano; pon también su ruta en la columna `salud`. Si
   es `critico=no`, solo avisa y el vigía no lo toca. Ojo: hoy el script solo comprueba por HTTP la
   columna `salud` del proxy; para los demás cuenta el healthcheck de compose.
5. **RAM.** Suma los `mem_limit` de lo que corre y añade un slot extra de la app (`TIC_MEM`) durante
   el despliegue, porque el slot viejo sigue vivo hasta drenar. Compara la suma con la RAM del LXC
   (ver «Operación»). Si no cabe, sube el LXC antes de desplegar.
6. **Secretos.** Nunca en el repo ni como valor literal en `compose.yaml`. Hoy no hay un cauce que
   los lleve al LXC: `desplegar.sh` solo carga `slots.env` (`--env-file`) y el entorno del propio
   proceso; un `.env` en `/opt/tic-codec` no se lee, y el arranque automático no recibe las
   variables del job. Antes de dar un secreto a un servicio, decide dónde vive en el LXC y cómo
   llega a `compose` también al arrancar. Un `${VAR:?...}` sin definir hace que **compose se niegue
   a correr para todos los servicios**, incluidos la app y el proxy.
7. **Probar.** `bash deploy/desplegar.sh --estado` debe mostrar el servicio con su contenedor, su
   salud y su huella. Después, el checklist de verificación de más abajo.

### Ejemplo completo: Grafana

Tipo `aux`, `critico=no`, versión fija, volumen propio, puerto solo en `127.0.0.1:3000`.

Bloque en `deploy/compose.yaml`, dentro de `services:` (después de `limpieza`):

```yaml
  grafana:
    <<: *base
    image: grafana/grafana:11.2.0
    ports:
      - "127.0.0.1:3000:3000"
    volumes:
      - grafana:/var/lib/grafana
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:?define GRAFANA_ADMIN_PASSWORD}
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://127.0.0.1:3000/api/health"]
      interval: 30s
      timeout: 5s
      retries: 3
    mem_limit: 512m
```

Y en el bloque `volumes:` del final del archivo, junto a `datos`:

```yaml
volumes:
  datos:
  grafana:
```

Antes de fiarte del healthcheck, comprueba que la imagen trae `wget` o `curl`:
`docker run --rm --entrypoint sh grafana/grafana:11.2.0 -c 'command -v wget curl'`.

Línea en `deploy/servicios.conf` (los campos van alineados con la cabecera):

```
grafana    | aux  | -                               | -      | no
```

Sin ruta en nginx: Grafana va por su propio puerto (`127.0.0.1:3000`). Si quieres verlo desde
internet, usa un puerto de Funnel aparte (paso 3). El siguiente despliegue lo levanta, porque el
paso de auxiliares recorre todo el catálogo. Tras un reinicio lo levanta Docker
(`restart: unless-stopped`).

**RAM:** Grafana suma 512 MB de tope. Con `TIC_MEM=2g` y un LXC de 4 GB, durante un despliegue hay
dos slots (4 GB de tope) más proxy, limpieza, Grafana, el runner, Docker y Tailscale: no cabe
holgado. Por eso se recomienda el LXC de 6 GB (ver «Operación»).

## Operación

Desde el host de Proxmox: `pct enter 111`, luego `su - deployer` y
`cd ~/actions-runner/_work/UD.Lab3.TeoriaInformacion/UD.Lab3.TeoriaInformacion` (el checkout del
runner: ahí están `deploy/desplegar.sh` y los demás scripts; el compose que se usa en producción
es la copia de `/opt/tic-codec`).

Para hablar con el compose desplegado, define una vez en la sesión:

```bash
C="docker compose -f /opt/tic-codec/compose.yaml -p tic-codec --env-file /var/lib/tic-codec/slots.env --profile slots"
```

Sin `--profile slots` no aparecen `app-azul` ni `app-verde`; sin `--env-file`, las variables salen mal.

```bash
$C ps
```
```bash
$C logs -f app-azul      # o app-verde: el que esté activo (ver --estado)
```
```bash
$C logs --tail 200 proxy
```
```bash
$C restart proxy
```
```bash
tailscale funnel status
```

Reiniciar el slot activo corta las conversiones en curso. Para cambiar de versión usa
`desplegar.sh` o `--volver`, no `restart`.

Ajustes (variables de entorno del proceso de `desplegar.sh`):

| Variable | Defecto | |
|---|---|---|
| `TIC_MAX_MB` | `256` | tamaño máximo de subida en el despliegue (en local sigue siendo 2 GB) |
| `TIC_TTL_MIN` | `120` | minutos que se conservan las fuentes, `.tic` y reconstruidos de `data/gui/` |
| `TIC_MEM` | `2g` | límite de RAM de **cada** slot de la app (tope, no reserva) |
| `TIC_PUERTO` | `5000` | puerto local del proxy (el que apunta Funnel) |

Hoy el workflow no pasa estas variables. Si las cambias, hay que fijarlas en el entorno del runner,
y el arranque automático (`tic-codec-arrancar` y el vigía) no las ve: tras un reinicio se quedan con
los defectos. La interfaz guarda todo lo que se sube o genera en el volumen `tic-codec_datos`; el
servicio `limpieza` borra cada 10 min las carpetas con más de `TIC_TTL_MIN` minutos para que el disco
del LXC no se llene. Si subes `TIC_MAX_MB`, sube también `TIC_MEM` (con k grandes el códec usa
varias veces el tamaño del archivo en RAM) y el disco del LXC (`pct resize <CTID> rootfs +10G`).

**RAM del LXC.** El LXC se crea con 4 GB. Durante un despliegue viven dos slots a la vez (el viejo se
detiene al terminar de drenar), así que con 4 GB el límite real de cada slot es justo. Para tener
3 GB por slot: en el host `pct set 111 --memory 6144` y `TIC_MEM=3g` en el entorno del runner.

## Si el servicio está caído

**Mínimo garantizado:** la app (slot activo), el proxy, la limpieza, Tailscale/Funnel y el runner
deben estar arriba. Lo que no forma parte del despliegue (por ejemplo Grafana u otros paneles de
monitoreo, `critico=no`) puede faltar sin que eso cuente como caída.

En el host de Proxmox, como root, en este orden:

```bash
pct status 111
```
Si dice `stopped`, enciéndelo y mira por qué no arrancaba:
```bash
pct start 111 --debug
```
Con el LXC arriba, reinstala el arranque y los vigías (es re-ejecutable) y comprueba el estado:
```bash
bash deploy/proxmox/arranque-automatico.sh 111
```
```bash
pct exec 111 -- bash /root/arranque-automatico.sh --estado
```
Si la app no responde, mira qué dice el estado de despliegue dentro del LXC, como `deployer`:
```bash
bash deploy/desplegar.sh --estado
```
Si Tailscale aparece en `NeedsLogin`, la clave del nodo expiró: dentro del LXC corre
`tailscale up`, abre el enlace que imprime y, en la consola de Tailscale, marca **Disable key
expiry** en `tic-codec` para que no vuelva a pasar.

Si el runner estaba apagado, el último push a `main` quedó sin desplegar (GitHub cancela el job a
las 24 h). Vuelve a lanzarlo: **Actions → CI/CD → Run workflow**, o
`gh workflow run deploy.yml --ref main`.

## Checklist de verificación

Úsalo tras cambiar algo del despliegue (el script, nginx, compose o el arranque). Los pasos 2 a 4 se
hacen con dos despliegues reales.

1. **Estado inicial.** `bash deploy/desplegar.sh --estado`: slot activo, salud de los dos slots y
   `Proxy :5000/salud -> responde`.
2. **Sin caída.** Desde el host, deja corriendo el bucle y no lo cortes hasta el final de los dos
   despliegues (Ctrl+C):
   ```bash
   pct exec 111 -- bash -c 'while true; do echo "$(date +%T) $(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5000/salud)"; sleep 1; done'
   ```
   Todas las líneas deben ser `200`, también cuando cambia el slot activo. Cualquier otro código es
   una caída: no des el cambio por bueno.
3. **Imagen que no queda sana.** Un despliegue cuya imagen no pase las comprobaciones (no responde
   en `/salud`) debe terminar con `falló (sigue la versión anterior)`; el bucle sigue en `200` y
   `--estado` muestra el mismo slot activo, con la misma imagen.
4. **Vuelta atrás.** Tras un despliegue correcto, `bash deploy/desplegar.sh --volver`: `--estado`
   muestra el otro slot con la versión anterior, y el bucle sigue en `200`.
5. **Reinicio del LXC.** Desde el host, `PROBAR=1 bash deploy/proxmox/arranque-automatico.sh 111`:
   reinicia el LXC y debe confirmar que `/salud` responde tras el reinicio.

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
- **Funnel da 502.** El proxy o la app no responden en `127.0.0.1:5000` del LXC. Revisa
  `bash deploy/desplegar.sh --estado` y `curl -I http://127.0.0.1:5000/salud` dentro del LXC. Si
  el proxy está parado, el vigía lo levanta en un máximo de 2 min. Para no esperar, dentro del LXC: `systemctl restart tic-codec.service`.
- **El despliegue termina con `falló (sigue la versión anterior)`.** El servicio sigue con la
  versión anterior: no hay caída. El detalle está en la tabla del resumen del job. Si fue la app,
  los últimos logs del slot descartado salen en el log del job (`app-<slot>`).
- **Aviso `Los scripts de deploy/proxmox cambiaron`.** Es informativo: corre
  `arranque-automatico.sh` como root en el LXC para aplicarlos.
- **Funnel da error de TLS / no conecta pero `tailscale funnel status` dice "Funnel on".**
  El relay de Funnel no está llegando al nodo (en `journalctl -u tailscaled` aparecen líneas
  `Drop: TCP … no rules matched`). Vuelve a correr `instalar-tailscale.sh 111`, que apaga y
  enciende el Funnel para que se anuncie de nuevo.
- **El nodo aparece como `tic-codec-1`.** Quedó un nodo viejo con el mismo nombre: bórralo en la
  consola de Tailscale y corre `tailscale set --hostname=tic-codec` en el LXC.
- **Cambiar de tailnet o regenerar identidad:** en el LXC, `tailscale logout` y vuelve a correr
  `instalar-tailscale.sh`.

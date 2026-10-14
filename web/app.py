"""Servidor web del códec TIC: expone codificar / decodificar / barrido de
tic_codec.py como API REST y sirve una interfaz web mínima, los diagramas y
los PDF de docs/.

No reimplementa nada del códec: guarda el archivo subido en una carpeta
temporal, llama a CodecTIC igual que lo haría el CLI y devuelve el reporte
JSON. Los resultados (.tic, gráfica, reporte) quedan disponibles para
descarga durante TIC_TTL_MIN minutos.

Configuración por variables de entorno:
  TIC_MAX_MB    tamaño máximo de subida en MB            (64)
  TIC_TRABAJOS  codificaciones simultáneas permitidas    (1)
  TIC_TTL_MIN   minutos que se conservan los resultados  (30)
  TIC_DATOS     carpeta de trabajo                       (/tmp/tic-web)
"""
import hashlib, json, math, os, shutil, struct, sys, threading, time, uuid
from pathlib import Path

import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))
from tic_codec import K_BASE, K_EXT, CabeceraTIC, CodecTIC  # noqa: E402

MAX_MB = float(os.environ.get("TIC_MAX_MB", "64"))
MAX_BYTES = int(MAX_MB * 1024 * 1024)
TTL_S = float(os.environ.get("TIC_TTL_MIN", "30")) * 60
DATOS = Path(os.environ.get("TIC_DATOS", "/tmp/tic-web"))
K_MAX = max(K_EXT)

# El códec usa mucha RAM con archivos grandes; el semáforo evita que varias
# peticiones a la vez tumben el contenedor. Las que llegan después esperan.
_cupos = threading.BoundedSemaphore(int(os.environ.get("TIC_TRABAJOS", "1")))
# Archivos de un trabajo que se pueden descargar (lista blanca, evita rutas arbitrarias).
DESCARGABLES = {"salida.tic": "application/octet-stream",
                "grafica.png": "image/png",
                "reporte.json": "application/json"}

app = FastAPI(title="Códec TIC", version="1.0",
              description="Códec adaptable de k bits/símbolo con métricas de teoría de la información")


# ═══════════════════════════ utilidades ═══════════════════════════
def _limpiar(x):
    """Convierte el reporte a JSON estándar: tipos de NumPy a Python e
    inf/NaN a None (JSON no tiene infinito; el PSNR sin error lo es)."""
    if isinstance(x, dict):
        return {k: _limpiar(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_limpiar(v) for v in x]
    if isinstance(x, np.generic):
        x = x.item()
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def _purgar_viejos():
    """Borra las carpetas de trabajos con más de TTL_S segundos."""
    if not DATOS.exists():
        return
    limite = time.time() - TTL_S
    for d in DATOS.iterdir():
        if d.is_dir() and d.stat().st_mtime < limite:
            shutil.rmtree(d, ignore_errors=True)


def _nuevo_trabajo() -> tuple[str, Path]:
    _purgar_viejos()
    tid = uuid.uuid4().hex
    carpeta = DATOS / tid
    carpeta.mkdir(parents=True)
    return tid, carpeta


async def _guardar_subida(archivo: UploadFile, destino: Path) -> int:
    """Copia la subida a disco por trozos, cortando si pasa de MAX_BYTES."""
    total = 0
    with open(destino, "wb") as f:
        while trozo := await archivo.read(1 << 20):
            total += len(trozo)
            if total > MAX_BYTES:
                raise HTTPException(413, f"El archivo supera el límite de {MAX_MB:g} MB")
            f.write(trozo)
    if total == 0:
        raise HTTPException(422, "El archivo está vacío")
    return total


def _validar_k(k: int):
    if k < 8 or k % 8 or k > K_MAX:
        raise HTTPException(422, f"k debe ser múltiplo de 8 entre 8 y {K_MAX}")


def _con_cupo(fn, *args):
    with _cupos:
        return fn(*args)


# ═══════════════════════════ API ═══════════════════════════
@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/info")
def info():
    return {"ks_base": K_BASE, "ks_ext": K_EXT, "k_max": K_MAX, "max_mb": MAX_MB}


@app.post("/api/codificar")
async def codificar(archivo: UploadFile = File(...), k: int = Form(8), perdida: int = Form(0),
                    bloques: int = Form(50), grafica: bool = Form(True)):
    _validar_k(k)
    if not 0 <= perdida <= 7:
        raise HTTPException(422, "perdida debe estar entre 0 y 7")
    if not 1 <= bloques <= 500:
        raise HTTPException(422, "bloques debe estar entre 1 y 500")
    tid, carpeta = _nuevo_trabajo()
    entrada = carpeta / "entrada.bin"
    await _guardar_subida(archivo, entrada)

    def trabajo():
        return CodecTIC(bloques=bloques).codificar(
            str(entrada), str(carpeta / "salida.tic"), k, perdida,
            grafica=str(carpeta / "grafica.png") if grafica else None,
            reporte=str(carpeta / "reporte.json"))

    try:
        rep = await run_in_threadpool(_con_cupo, trabajo)
    except MemoryError:
        shutil.rmtree(carpeta, ignore_errors=True)
        raise HTTPException(507, "Sin memoria para ese archivo con ese k; prueba un k menor")
    finally:
        entrada.unlink(missing_ok=True)  # el original no se vuelve a servir

    base = f"/api/trabajos/{tid}"
    return {
        "id": tid,
        "nombre": archivo.filename,
        "reporte": _limpiar(rep.a_dict()),
        "descargas": {"tic": f"{base}/salida.tic", "reporte": f"{base}/reporte.json",
                      "grafica": f"{base}/grafica.png" if grafica else None},
    }


@app.get("/api/trabajos/{tid}/{nombre}")
def descargar(tid: str, nombre: str):
    if nombre not in DESCARGABLES or not tid.isalnum():
        raise HTTPException(404)
    ruta = DATOS / tid / nombre
    if not ruta.is_file():
        raise HTTPException(404, "El resultado no existe o ya expiró")
    return FileResponse(ruta, media_type=DESCARGABLES[nombre], filename=nombre)


@app.post("/api/decodificar")
async def decodificar(archivo: UploadFile = File(...)):
    tid, carpeta = _nuevo_trabajo()
    entrada, salida = carpeta / "entrada.tic", carpeta / "decodificado.bin"
    try:
        await _guardar_subida(archivo, entrada)
        blob = entrada.read_bytes()
        if blob[:4] != CodecTIC.MAGIC:
            raise HTTPException(422, "No es un archivo .tic (falta la marca TIC1)")
        hl = struct.unpack("<I", blob[4:8])[0]
        cabecera = CabeceraTIC.desde_json(blob[8:8 + hl])
        try:
            out = await run_in_threadpool(_con_cupo, CodecTIC().decodificar,
                                          str(entrada), str(salida), True)
        except Exception as e:  # .tic corrupto o truncado
            raise HTTPException(422, f"No se pudo decodificar: {e}")
        ok = hashlib.sha256(out.tobytes()).hexdigest() == cabecera.sha256
        nombre = Path(archivo.filename or "archivo").stem + ".decodificado"
        return Response(salida.read_bytes(), media_type="application/octet-stream", headers={
            "Content-Disposition": f'attachment; filename="{nombre}"',
            "X-TIC-SHA256-OK": "1" if ok else "0",
            "X-TIC-K": str(cabecera.k),
            "Access-Control-Expose-Headers": "X-TIC-SHA256-OK, X-TIC-K, Content-Disposition",
        })
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)


@app.post("/api/barrido")
async def barrido(archivo: UploadFile = File(...), ks: str = Form(""), extendido: bool = Form(False)):
    try:
        lista = [int(v) for v in ks.split(",") if v.strip()] or K_BASE + (K_EXT if extendido else [])
    except ValueError:
        raise HTTPException(422, "ks debe ser una lista separada por comas, ej. 8,64,2048")
    for k in lista:
        _validar_k(k)
    tid, carpeta = _nuevo_trabajo()
    entrada = carpeta / "entrada.bin"
    try:
        tam = await _guardar_subida(archivo, entrada)
        filas = await run_in_threadpool(_con_cupo, CodecTIC().barrido, str(entrada), lista)
        return {"nombre": archivo.filename, "tamano_B": tam, "resultados": _limpiar(filas)}
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)


# ═══════════════════════════ estáticos ═══════════════════════════
# El orden importa: "/" va de último para no tapar las rutas de arriba.
for ruta, carpeta in (("/diagramas", RAIZ / "diagrams"), ("/docs-pdf", RAIZ / "docs")):
    if carpeta.is_dir():
        app.mount(ruta, StaticFiles(directory=carpeta), name=ruta.strip("/"))
app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="ui")

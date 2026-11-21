#!/usr/bin/env python3
"""
app.py — Interfaz gráfica (backend Flask) del códec TIC

  python src/app.py            →  http://127.0.0.1:5000

La interfaz no reimplementa nada del códec: cada endpoint llama a las mismas
clases que usa el CLI (CodecTIC, GeneradorFuentes) y devuelve sus reportes
como JSON. Lo que cada etapa produce queda en data/gui/<id>/, un directorio
por fuente cargada:

  data/gui/<id>/
    meta.json              nombre original y tamaño de la fuente
    <fuente>               el archivo subido o generado
    <stem>.k16.tic         lo que produce /api/codificar (uno por k y pérdida)
    <stem>.k16.json        su reporte antes/durante/después
    <stem>.k16.rec<ext>    lo que produce /api/decodificar

Endpoints (todos responden JSON salvo /api/descargar):
  POST /api/subir         multipart "archivo"                  → fuente nueva
  POST /api/generar       {tipo, mb, semilla}                  → fuente sintética nueva
  POST /api/barrido       {id, conjunto | ks}                  → métricas "antes" por k
  POST /api/codificar     {id, k, perdida, bloques}            → reporte completo
  POST /api/decodificar   {id, tic}  o multipart "archivo"     → cabecera + verificación
  GET  /api/descargar/<id>/<nombre>                            → el archivo
"""
from __future__ import annotations

import hashlib, json, math, mimetypes, os, sys, threading, time, uuid
from pathlib import Path

import numpy as np
from flask import Flask, g, jsonify, render_template, request, send_from_directory
from werkzeug.utils import secure_filename
from werkzeug.wsgi import ClosingIterator

# tic_codec.py vive en la misma carpeta; se importa como módulo, no se copia nada.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tic_codec import K_BASE, K_EXT, CodecTIC, GeneradorFuentes  # noqa: E402
from tic_bandido import DIR_DATOS, UMBRAL_CAMBIO, FlujoBloques, SimuladorFlujo, Tramo  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
TRABAJO = RAIZ / "data" / "gui"   # data/* ya está en .gitignore
GUI = Path(__file__).resolve().parent / "gui"

app = Flask(__name__, template_folder=str(GUI / "templates"), static_folder=str(GUI / "static"))
# 2 GB por archivo subido; en el despliegue público se baja con TIC_MAX_MB (ver deploy/compose.yaml).
app.config["MAX_CONTENT_LENGTH"] = int(float(os.environ.get("TIC_MAX_MB", 2048)) * 1024 ** 2)
app.config["TEMPLATES_AUTO_RELOAD"] = True  # ver cambios en index.html sin reiniciar el servidor


# ═══════════════════════════ peticiones en curso ═══════════════════════════
# Contador para /salud (healthcheck, proxy y drenaje en el despliegue). gunicorn usa 4 hilos,
# así que el entero va protegido por un Lock. /salud no se cuenta: ni sube ni baja.
_activas = 0
_cerrojo_activas = threading.Lock()


@app.before_request
def _contar_entrada():
    global _activas
    if request.path == "/salud":
        return None
    with _cerrojo_activas:
        _activas += 1
    g.contada = True  # marca para restar exactamente lo que se sumó


def _restar_una_vez():
    """Devuelve una función que resta 1 al contador solo la primera vez que se llama,
    para que nunca haya doble decremento aunque se invoque dos veces."""
    hecho = False

    def _restar():
        global _activas
        nonlocal hecho
        with _cerrojo_activas:
            if not hecho:
                hecho = True
                _activas -= 1

    return _restar


@app.after_request
def _contar_cierre(response):
    # La respuesta puede seguir enviándose en streaming (p. ej. send_from_directory) cuando
    # termina el teardown, así que la petición no se da por terminada aquí: se resta cuando
    # el servidor cierra la respuesta del todo (call_on_close).
    if g.get("contada"):
        restar = _restar_una_vez()
        response.call_on_close(restar)
        if response.direct_passthrough:
            # send_from_directory/send_file usan direct_passthrough: el servidor WSGI recibe el
            # iterable del fichero y cierra ESE objeto, no el Response, así que call_on_close
            # no correría. Envolvemos el iterable para que su close también reste (una sola vez).
            response.response = ClosingIterator(response.response, [restar])
        g.cierre_registrado = True
    return response


@app.teardown_request
def _contar_salida(_error=None):
    # Respaldo: solo si after_request no llegó a registrar el cierre (p. ej. una excepción
    # que impidió llegar a after_request). Si ya se registró, lo resta call_on_close.
    global _activas
    if g.get("contada") and not g.get("cierre_registrado"):
        with _cerrojo_activas:
            _activas -= 1
        g.cierre_registrado = True


@app.get("/salud")
def salud():
    # Solo lee el contador, sin tocar disco. Excluye esta propia petición.
    with _cerrojo_activas:
        n = _activas
    return jsonify(activas=n)


# ═══════════════════════════ utilidades ═══════════════════════════
class ErrorAPI(Exception):
    """Error esperable (parámetro inválido, id inexistente...): se responde con 400/404."""
    def __init__(self, mensaje: str, estado: int = 400):
        super().__init__(mensaje)
        self.estado = estado


@app.errorhandler(ErrorAPI)
def _error_api(e: ErrorAPI):
    return jsonify(error=str(e)), e.estado


@app.errorhandler(ValueError)
def _error_valor(e: ValueError):
    # El códec lanza ValueError ante entradas inválidas (p. ej. "no es un archivo TIC1").
    return jsonify(error=str(e)), 400


def a_json(x):
    """Convierte el reporte a algo que JSON.parse acepte: los numpy pasan a
    tipos de Python y los float no finitos (PSNR = inf sin error) a null."""
    if isinstance(x, dict):
        return {k: a_json(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [a_json(v) for v in x]
    if isinstance(x, np.ndarray):
        return a_json(x.tolist())
    if isinstance(x, np.generic):
        x = x.item()
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def sha256_archivo(ruta: Path) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for trozo in iter(lambda: f.read(1 << 20), b""):
            h.update(trozo)
    return h.hexdigest()


def tipo_de(nombre: str) -> str:
    """Tipo de fuente aproximado por la extensión, solo para mostrarlo."""
    mime = mimetypes.guess_type(nombre)[0] or ""
    if mime.startswith(("image/", "audio/", "video/", "text/")):
        return mime.split("/")[0]
    return "binario"


def carpeta(id_: str) -> Path:
    # El id lo genera el servidor (hex); cualquier otra cosa se rechaza para no salir de TRABAJO.
    if not id_ or not all(c in "0123456789abcdef" for c in id_):
        raise ErrorAPI("id inválido")
    d = TRABAJO / id_
    if not d.is_dir():
        raise ErrorAPI("fuente no encontrada", 404)
    return d


def leer_meta(d: Path) -> dict:
    return json.loads((d / "meta.json").read_text(encoding="utf-8"))


def ruta_fuente(id_: str) -> tuple[Path, dict]:
    d = carpeta(id_)
    meta = leer_meta(d)
    return d / meta["archivo"], meta


def nueva_fuente(nombre: str) -> tuple[str, Path]:
    id_ = uuid.uuid4().hex[:12]
    d = TRABAJO / id_
    d.mkdir(parents=True)
    return id_, d / (secure_filename(nombre) or "fuente.bin")


def registrar(id_: str, ruta: Path, nombre: str, origen: str) -> dict:
    meta = {
        "id": id_, "nombre": nombre, "archivo": ruta.name, "origen": origen,
        "tamano_B": ruta.stat().st_size, "tipo": tipo_de(nombre), "sha256": sha256_archivo(ruta),
    }
    (ruta.parent / "meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    return meta


def url_descarga(id_: str, nombre: str) -> str:
    return f"/api/descargar/{id_}/{nombre}"


def entero(datos: dict, clave: str, defecto: int, minimo: int, maximo: int) -> int:
    try:
        v = int(datos.get(clave, defecto))
    except (TypeError, ValueError):
        raise ErrorAPI(f"{clave} debe ser un entero")
    if not minimo <= v <= maximo:
        raise ErrorAPI(f"{clave} debe estar entre {minimo} y {maximo}")
    return v


def validar_k(k: int) -> int:
    if k <= 0 or k % 8:
        raise ErrorAPI(f"k = {k} no es múltiplo positivo de 8")
    return k


def curva_rango_frecuencia(frecuencias: np.ndarray, puntos: int = 200) -> list[list[float]]:
    """Rango-frecuencia (log-log) muestreado en ~`puntos` rangos espaciados
    logarítmicamente, para no mandar U valores al navegador."""
    p = np.sort(frecuencias)[::-1] / frecuencias.sum()
    rangos = np.unique(np.geomspace(1, len(p), num=min(puntos, len(p))).astype(int))
    return [[int(r), float(p[r - 1])] for r in rangos]


# ═══════════════════════════ páginas ═══════════════════════════
@app.get("/")
def inicio():
    return render_template("index.html")


# ═══════════════════════════ fuente ═══════════════════════════
@app.post("/api/subir")
def subir():
    f = request.files.get("archivo")
    if f is None or not f.filename:
        raise ErrorAPI("falta el archivo (campo 'archivo')")
    id_, ruta = nueva_fuente(f.filename)
    f.save(ruta)
    if ruta.stat().st_size == 0:
        raise ErrorAPI("el archivo está vacío")
    return jsonify(registrar(id_, ruta, f.filename, "subido"))


@app.post("/api/generar")
def generar():
    datos = request.get_json(silent=True) or {}
    tipo = datos.get("tipo", "estructurado")
    if tipo not in ("uniforme", "no_uniforme", "estructurado"):
        raise ErrorAPI("tipo: uniforme | no_uniforme | estructurado")
    try:
        mb = float(datos.get("mb", 2))
    except (TypeError, ValueError):
        raise ErrorAPI("mb debe ser un número")
    if not 0 < mb <= 512:
        raise ErrorAPI("mb debe estar entre 0 y 512")
    semilla = entero(datos, "semilla", 0, 0, 2 ** 32 - 1)
    nombre = f"{tipo}_{mb:g}MB_s{semilla}.bin"
    id_, ruta = nueva_fuente(nombre)
    GeneradorFuentes.generar(tipo, str(ruta), mb, semilla)
    return jsonify(registrar(id_, ruta, nombre, "sintético"))


@app.get("/api/fuente/<id_>")
def fuente(id_: str):
    return jsonify(leer_meta(carpeta(id_)))


# ═══════════════════════════ barrido ═══════════════════════════
@app.post("/api/barrido")
def barrido():
    datos = request.get_json(silent=True) or {}
    ruta, _ = ruta_fuente(datos.get("id", ""))
    if datos.get("ks"):
        try:
            ks = [validar_k(int(v)) for v in datos["ks"]]
        except (TypeError, ValueError):
            raise ErrorAPI("ks debe ser una lista de enteros")
    else:
        ks = K_BASE + (K_EXT if datos.get("conjunto") == "extendido" else [])
    t0 = time.time()
    resultados = CodecTIC().barrido(str(ruta), ks)
    mejor = max(resultados, key=lambda r: r["razon_estimada"])
    return jsonify(a_json({
        "resultados": resultados,
        "mejor_k": mejor["k_bits"],
        "tiempo_s": time.time() - t0,
    }))


# ═══════════════════════════ IA: bandido UCB ═══════════════════════════
BLOQUE_IA_MAX = 256 * 1024   # el mismo bloque por defecto que tic_bandido.py
BLOQUE_IA_MIN = 4 * 1024
BLOQUES_IA_OBJETIVO = 64     # el bandido gasta los primeros 9 bloques explorando: hacen falta muchos más
BLOQUES_IA_MIN = 24
BLOQUES_IA_MAX = 200         # tope de bloques para acotar el tiempo con archivos grandes


@app.post("/api/ia")
def ia():
    """Corre el bandido UCB descontado de tic_bandido.py sobre los bloques del
    archivo, como un flujo de un solo tramo, y devuelve el k que eligió."""
    datos = request.get_json(silent=True) or {}
    id_ = datos.get("id", "")
    ruta, meta = ruta_fuente(id_)
    try:
        gamma = float(datos.get("gamma", 0.98))
        c = float(datos.get("c", 0.05))
    except (TypeError, ValueError):
        raise ErrorAPI("gamma y c deben ser números")
    if not (0 < gamma <= 1 and c >= 0):
        raise ErrorAPI("gamma debe estar en (0, 1] y c ≥ 0")

    # Bloque de 256 KB si el archivo da al menos 64; si no, el archivo partido en ~64,
    # en múltiplos de 256 B (un símbolo de k = 2048) para que todos los k cuadren.
    tamano = meta["tamano_B"]
    bloque = max(BLOQUE_IA_MIN, min(BLOQUE_IA_MAX, tamano // BLOQUES_IA_OBJETIVO // 256 * 256))
    n_bloques = min(BLOQUES_IA_MAX, tamano // bloque)
    if n_bloques < BLOQUES_IA_MIN:
        raise ErrorAPI(f"el archivo es muy pequeño para la IA: necesita al menos "
                       f"{BLOQUES_IA_MIN * BLOQUE_IA_MIN // 1024} KB ({BLOQUES_IA_MIN} bloques de 4 KB)")

    # FlujoBloques lee los tramos "archivo" relativos a data/; la fuente vive en data/gui/<id>/.
    relativa = ruta.relative_to(DIR_DATOS).as_posix()
    flujo = FlujoBloques([Tramo(meta["nombre"], "archivo", relativa)], bloque, n_bloques)
    sim = SimuladorFlujo(flujo, gamma=gamma, c=c)
    t0 = time.time()
    sim.calcular_matriz()
    sim.reproducir()
    resultado = sim.a_dict()
    tramo = resultado["detalle_tramos"][0]
    secuencia = resultado["secuencia"]
    # El k de la IA es el que más elige en la segunda mitad del flujo, cuando ya terminó
    # de explorar (en la primera prueba cada k una vez). Empate → el k menor.
    convergido = [s["k_bandido"] for s in secuencia[len(secuencia) // 2:]]
    k_ia = max(K_BASE, key=lambda k: (convergido.count(k), -k))

    return jsonify(a_json({
        "k_ia": k_ia,
        "k_ia_mas_elegido": tramo["k_bandido_mas_elegido"],
        "k_ia_final": secuencia[-1]["k_bandido"],
        "k_optimo_bloques": tramo["k_optimo_mas_frecuente"],
        "conteo_k_bandido": tramo["conteo_k_bandido"],
        "resumen_politicas": resultado["resumen_politicas"],
        "secuencia": [{"bloque": s["bloque"], "contexto": s["contexto"], "k_bandido": s["k_bandido"],
                       "k_optimo": s["k_optimo"], "barrido_reinicio": s["barrido_reinicio"]} for s in secuencia],
        "parametros": {"gamma": gamma, "c": c, "bloque_B": bloque, "bloques": n_bloques,
                       "bytes_analizados": bloque * n_bloques, "umbral_cambio": UMBRAL_CAMBIO, "ks": K_BASE},
        "tiempo_s": time.time() - t0,
    }))


# ═══════════════════════════ codificar ═══════════════════════════
@app.post("/api/codificar")
def codificar():
    datos = request.get_json(silent=True) or {}
    id_ = datos.get("id", "")
    ruta, meta = ruta_fuente(id_)
    k = validar_k(entero(datos, "k", 8, 8, 1 << 20))
    perdida = entero(datos, "perdida", 0, 0, 7)
    bloques = entero(datos, "bloques", 50, 1, 1000)

    base = f"{Path(meta['archivo']).stem}.k{k}" + (f".p{perdida}" if perdida else "")
    tic, rep = ruta.parent / f"{base}.tic", ruta.parent / f"{base}.json"
    reporte = CodecTIC(bloques=bloques).codificar(str(ruta), str(tic), k, perdida, reporte=str(rep))

    return jsonify(a_json({
        "reporte": reporte.a_dict(),
        "entropia_por_bit": reporte.entropia_por_bit,
        "rango_frecuencia": curva_rango_frecuencia(reporte.frecuencias),
        "tic": {"nombre": tic.name, "tamano_B": tic.stat().st_size, "url": url_descarga(id_, tic.name)},
        "reporte_json": {"nombre": rep.name, "url": url_descarga(id_, rep.name)},
    }))


# ═══════════════════════════ decodificar ═══════════════════════════
@app.post("/api/decodificar")
def decodificar():
    codec = CodecTIC()
    original = None  # la fuente de la sesión, si el .tic salió de ella, para comparar byte a byte
    if "archivo" in request.files:
        f = request.files["archivo"]
        if not f.filename:
            raise ErrorAPI("falta el archivo .tic")
        id_, tic = nueva_fuente(f.filename)
        f.save(tic)
        extension = ".bin"
    else:
        datos = request.get_json(silent=True) or {}
        id_ = datos.get("id", "")
        d = carpeta(id_)
        tic = d / secure_filename(datos.get("tic", ""))
        if tic.suffix != ".tic" or not tic.is_file():
            raise ErrorAPI("archivo .tic no encontrado", 404)
        meta = leer_meta(d)
        original = d / meta["archivo"]
        extension = Path(meta["archivo"]).suffix or ".bin"

    cabecera = codec.leer_cabecera(str(tic))
    salida = tic.with_name(f"{tic.stem}.rec{extension}")
    t0 = time.time()
    rec = codec.decodificar(str(tic), str(salida))
    t_dec = time.time() - t0

    respuesta = {
        "id": id_,
        "cabecera": vars(cabecera),
        "tamano_tic_B": tic.stat().st_size,
        "tamano_reconstruido_B": int(len(rec)),
        "sha256_reconstruido": hashlib.sha256(rec.tobytes()).hexdigest(),
        "tiempo_s": t_dec,
        "reconstruido": {"nombre": salida.name, "url": url_descarga(id_, salida.name)},
    }
    respuesta["verificacion_sha256"] = respuesta["sha256_reconstruido"] == cabecera.sha256
    if original is not None and original.is_file():
        # Con pérdida la huella guardada es la de los datos cuantizados, así que coincide
        # aunque el reconstruido difiera del original; esta comparación lo deja explícito.
        respuesta["identico_al_original"] = bool(np.array_equal(rec, np.fromfile(original, np.uint8)))
    return jsonify(a_json(respuesta))


# ═══════════════════════════ descargas ═══════════════════════════
@app.get("/api/descargar/<id_>/<nombre>")
def descargar(id_: str, nombre: str):
    # send_from_directory rechaza rutas que intenten salir de la carpeta.
    return send_from_directory(carpeta(id_), nombre, as_attachment=True)


if __name__ == "__main__":
    TRABAJO.mkdir(parents=True, exist_ok=True)
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", 5000)), debug=False, threaded=True)

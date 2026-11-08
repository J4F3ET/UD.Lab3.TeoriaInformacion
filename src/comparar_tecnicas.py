"""comparar_tecnicas.py — Punto (b) del proyecto: comparar el códec TIC con técnicas de
compresión ACTUALES sobre los mismos archivos reales de audio, video, imagen y texto.

Qué se compara (todas sin pérdida):
  · Generales, sirven para cualquier archivo: zlib (DEFLATE, niveles 6 y 9), bz2 (BWT), lzma
    (LZMA2, el de .xz/.7z), zstd (Zstandard, niveles 3 y 19) y Brotli si está instalado.
  · Especializadas, entienden el formato: FLAC para el audio WAV, PNG y WebP sin pérdida para
    la imagen BMP.
  · Referencia: el códec TIC de este laboratorio, con el mejor k entre 8, 16, 32 y 64.

Qué se mide por archivo y técnica (los criterios del tablero: desempeño, velocidad, confiabilidad):
  · desempeño   razón de compresión y ahorro
  · velocidad   MB/s al comprimir y al descomprimir
  · exactitud   SHA-256 de lo recuperado = SHA-256 del original
  · confiabilidad  se corrompe 1 byte del archivo comprimido (en el 25 %, 50 % y 75 % de su
                largo) y se mide cuánto del original se recupera, como información mutua
                I(X;Y) / H(X). Es el equivalente, en archivos, de perder un paquete en la red:
                muestra qué formatos arrastran el daño al resto del archivo.

La "calidad" (el otro criterio del tablero) solo tiene sentido con pérdida: está en
tasa_distorsion.py.

Muestras: para que lzma, zstd -19 y TIC terminen en minutos, el video RGB crudo se corta a sus
primeros 16 MB y la imagen BMP se recorta a una franja de 16 MB guardada otra vez como BMP. El
WAV se vuelve a escribir con soundfile, para que FLAC → WAV devuelva exactamente los mismos
bytes. Las muestras se guardan en data/muestras/ y se declaran en el reporte.

Uso:
  python comparar_tecnicas.py                         (usa la carpeta data/ del proyecto)
  python comparar_tecnicas.py --datos D:/ruta/data --salida ../examples/comparacion_tecnicas
"""
from __future__ import annotations

import argparse, bz2, contextlib, hashlib, io, json, lzma, os, sys, tempfile, time, zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from tic_codec import CodecTIC

if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8")

# zstd: en Python 3.14 viene en la biblioteca estándar (compression.zstd); antes, el paquete
# `zstandard`. Si no hay ninguno, la técnica simplemente no se ofrece.
try:
    from compression import zstd as _zstd_std
except ImportError:
    _zstd_std = None
try:
    import zstandard as _zstd_pip
except ImportError:
    _zstd_pip = None
try:
    import brotli as _brotli
except ImportError:
    _brotli = None
try:
    import soundfile as _soundfile  # FLAC
except ImportError:
    _soundfile = None
try:
    from PIL import Image as _pil  # PNG y WebP
except ImportError:
    _pil = None

DIR_DATOS = Path(__file__).resolve().parent.parent / "data"
MUESTRA_MAX = 16 * 1024 * 1024  # 16 MB

# Los archivos de prueba del laboratorio: nombre → (tipo de dato, archivo en data/, nota).
ARCHIVOS = {
    "texto":       ("texto",  "texto_prueba.txt",  "apuntes de clase, texto plano"),
    "audio_wav":   ("audio",  "audio_prueba.wav",  "voz, PCM sin comprimir"),
    "audio_mp3":   ("audio",  "audio_prueba.mp3",  "la misma voz, ya comprimida con MP3"),
    "imagen_bmp":  ("imagen", "imagen_prueba.bmp", "foto, píxeles sin comprimir"),
    "imagen_jpg":  ("imagen", "imagen_prueba.jpg", "la misma foto, ya comprimida con JPEG"),
    "video_rgb":   ("video",  "video_prueba.rgb",  "grabación de pantalla, cuadros RGB crudos"),
    "video_mp4":   ("video",  "video_prueba.mp4",  "la misma grabación, ya comprimida con H.264"),
}


# ═══════════════════════════ las técnicas ═══════════════════════════
@dataclass
class Tecnica:
    """Una técnica de compresión: cómo comprimir, cómo descomprimir y a qué archivos aplica."""
    nombre: str
    familia: str                        # "general", "especializada" o "referencia"
    descripcion: str
    comprimir: Callable[[bytes], bytes]
    descomprimir: Callable[[bytes], bytes]
    solo_para: tuple[str, ...] = ()     # nombres de ARCHIVOS donde aplica; vacío = todos
    # Descompresión "tolerante" para la prueba de confiabilidad: entrega lo que alcanzó a salir
    # antes del error en vez de no entregar nada, como haría un reproductor o un receptor real.
    # Si es None se usa `descomprimir` (y un error = nada recuperado).
    tolerante: Callable[[bytes], bytes] | None = None

    def aplica(self, archivo: str) -> bool:
        return not self.solo_para or archivo in self.solo_para


def _por_trozos(nuevo_descompresor: Callable, trozo: int = 4096) -> Callable[[bytes], bytes]:
    """Descomprime de a `trozo` bytes con un objeto descompresor de flujo y se queda con todo lo
    que salió hasta el primer error (zlib, bz2, lzma y zstd ofrecen ese tipo de objeto)."""
    def desc(datos: bytes) -> bytes:
        d, out = nuevo_descompresor(), []
        try:
            for i in range(0, len(datos), trozo):
                out.append(d.decompress(datos[i:i + trozo]))
        except Exception:
            pass
        return b"".join(out)
    return desc


def _zstd_tolerante() -> Callable[[bytes], bytes]:
    if _zstd_std is not None:
        return _por_trozos(_zstd_std.ZstdDecompressor)
    return _por_trozos(lambda: _zstd_pip.ZstdDecompressor().decompressobj())


def _zstd(nivel: int) -> tuple[Callable, Callable]:
    if _zstd_std is not None:
        return (lambda d: _zstd_std.compress(d, level=nivel)), _zstd_std.decompress
    c, dz = _zstd_pip.ZstdCompressor(level=nivel), _zstd_pip.ZstdDecompressor()
    # max_output_size: el marco guarda el tamaño, pero se pone un tope por si viene corrupto.
    return c.compress, (lambda d: dz.decompress(d, max_output_size=1 << 30))


def _flac_comprimir(wav: bytes) -> bytes:
    import soundfile as sf
    datos, sr = sf.read(io.BytesIO(wav), dtype="int16")
    out = io.BytesIO()
    sf.write(out, datos, sr, format="FLAC", subtype="PCM_16")
    return out.getvalue()


def _flac_descomprimir(flac: bytes) -> bytes:
    import soundfile as sf
    datos, sr = sf.read(io.BytesIO(flac), dtype="int16")
    out = io.BytesIO()
    sf.write(out, datos, sr, format="WAV", subtype="PCM_16")
    return out.getvalue()


def _imagen(formato: str, **opciones) -> tuple[Callable, Callable]:
    """PNG o WebP sin pérdida: BMP → píxeles → formato; y de vuelta píxeles → BMP."""
    from PIL import Image

    def comp(bmp: bytes) -> bytes:
        out = io.BytesIO()
        Image.open(io.BytesIO(bmp)).save(out, format=formato, **opciones)
        return out.getvalue()

    def desc(datos: bytes) -> bytes:
        out = io.BytesIO()
        Image.open(io.BytesIO(datos)).convert("RGB").save(out, format="BMP")
        return out.getvalue()
    return comp, desc


class _TIC:
    """El códec del laboratorio, envuelto para que reciba y devuelva bytes. Elige el k con la
    razón estimada más alta entre 8, 16, 32 y 64 (CodecTIC.estimar, sin codificar) y luego
    codifica de verdad. Su tiempo incluye el cálculo de métricas que hace CodecTIC.codificar."""
    KS = (8, 16, 32, 64)

    def __init__(self):
        self.k_elegido: dict[int, int] = {}

    def comprimir(self, datos: bytes) -> bytes:
        raw = np.frombuffer(datos, np.uint8)
        k = max(self.KS, key=lambda k: CodecTIC.estimar(raw, k)[1])
        with tempfile.TemporaryDirectory() as d:
            ent, sal = os.path.join(d, "x.bin"), os.path.join(d, "x.tic")
            raw.tofile(ent)
            with contextlib.redirect_stdout(io.StringIO()):
                CodecTIC().codificar(ent, sal, k)
            out = Path(sal).read_bytes()
        self.k_elegido[len(out)] = k
        return out

    def descomprimir(self, datos: bytes) -> bytes:
        with tempfile.TemporaryDirectory() as d:
            ent = os.path.join(d, "x.tic")
            Path(ent).write_bytes(datos)
            with contextlib.redirect_stdout(io.StringIO()):
                return CodecTIC().decodificar(ent, None, silencioso=True).tobytes()


TIC = _TIC()


def tecnicas() -> list[Tecnica]:
    tz, tb, tl = _por_trozos(zlib.decompressobj), _por_trozos(bz2.BZ2Decompressor), _por_trozos(lzma.LZMADecompressor)
    t = [Tecnica("zlib-6", "general", "DEFLATE (LZ77 + Huffman), nivel por defecto de gzip",
                 lambda d: zlib.compress(d, 6), zlib.decompress, tolerante=tz),
         Tecnica("zlib-9", "general", "DEFLATE, nivel máximo",
                 lambda d: zlib.compress(d, 9), zlib.decompress, tolerante=tz),
         Tecnica("bz2-9", "general", "Burrows-Wheeler + Huffman (bzip2)",
                 lambda d: bz2.compress(d, 9), bz2.decompress, tolerante=tb),
         Tecnica("lzma-6", "general", "LZMA2, el de .xz y 7-Zip",
                 lambda d: lzma.compress(d, preset=6), lzma.decompress, tolerante=tl)]
    if _zstd_std is not None or _zstd_pip is not None:
        t += [Tecnica("zstd-3", "general", "Zstandard nivel 3 (por defecto): pensado para velocidad", *_zstd(3),
                      tolerante=_zstd_tolerante()),
              Tecnica("zstd-19", "general", "Zstandard nivel 19: máxima compresión", *_zstd(19),
                      tolerante=_zstd_tolerante())]
    if _brotli is not None:
        t.append(Tecnica("brotli-11", "general", "Brotli nivel 11 (el de HTTP)",
                         lambda d: _brotli.compress(d, quality=11), _brotli.decompress))
    if _soundfile is not None:
        t.append(Tecnica("flac", "especializada", "FLAC: predicción lineal de muestras + Rice", _flac_comprimir,
                         _flac_descomprimir, ("audio_wav",)))
    if _pil is not None:
        t += [Tecnica("png", "especializada", "PNG: filtro por fila + DEFLATE", *_imagen("PNG", optimize=True),
                  ("imagen_bmp",)),
          Tecnica("webp-sin-perdida", "especializada", "WebP en modo sin pérdida (predicción + LZ77 + códigos de color)",
                  *_imagen("WEBP", lossless=True, quality=100, method=4), ("imagen_bmp",))]
    t += [Tecnica("tic", "referencia", "Códec TIC del laboratorio (Huffman o bitstrip con k adaptable)",
                  TIC.comprimir, TIC.descomprimir)]
    return t


# ═══════════════════════════ teoría de la información ═══════════════════════════
BORRADO = 256  # símbolo extra para los bytes que no se pudieron recuperar


def entropia_bytes(x: np.ndarray) -> float:
    """H(X) de orden 0 en bits por byte."""
    p = np.bincount(x, minlength=256) / len(x)
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())


def info_mutua_bytes(x: np.ndarray, y: np.ndarray) -> float:
    """I(X;Y) en bits por byte entre el original x (0..255) y lo recuperado y (0..256, donde
    256 = borrado). Es la misma fórmula que Informacion.informacion_mutua de tic_codec.py, pero
    con np.bincount sobre la tabla 256 × 257 en vez de np.unique: con 16 MB es mucho más rápido."""
    n = len(x)
    conj = np.bincount(x.astype(np.int64) * 257 + y, minlength=256 * 257).reshape(256, 257) / n
    px, py = conj.sum(1, keepdims=True), conj.sum(0, keepdims=True)
    m = conj > 0
    return float((conj[m] * np.log2(conj[m] / (px @ py)[m])).sum())


def recuperado_alineado(original: np.ndarray, recuperado: bytes | None) -> np.ndarray:
    """Alinea lo recuperado con el original posición a posición: lo que falta es BORRADO."""
    y = np.full(len(original), BORRADO, dtype=np.int64)
    if recuperado:
        r = np.frombuffer(recuperado, np.uint8)[:len(original)]
        y[:len(r)] = r
    return y


# ═══════════════════════════ muestras ═══════════════════════════
def preparar_muestra(nombre: str, dir_datos: Path, dir_muestras: Path) -> tuple[bytes, str]:
    """Devuelve los bytes que se van a comprimir y una nota de cómo se obtuvieron."""
    tipo, archivo, _ = ARCHIVOS[nombre]
    ruta = dir_datos / archivo
    datos = ruta.read_bytes()
    if nombre == "imagen_bmp":
        from PIL import Image
        im = Image.open(ruta).convert("RGB")
        filas = min(im.height, MUESTRA_MAX // (im.width * 3))
        destino = dir_muestras / "imagen_prueba_franja.bmp"
        if not destino.exists():
            im.crop((0, 0, im.width, filas)).save(destino, format="BMP")
        return destino.read_bytes(), f"franja superior de {im.width}×{filas} píxeles de {im.width}×{im.height}, guardada como BMP"
    if nombre == "audio_wav":
        import soundfile as sf
        destino = dir_muestras / "audio_prueba_pcm16.wav"
        if not destino.exists():
            d, sr = sf.read(ruta, dtype="int16")
            sf.write(destino, d, sr, format="WAV", subtype="PCM_16")
        return destino.read_bytes(), "el mismo audio reescrito como WAV PCM 16 bits (cabecera canónica)"
    if len(datos) > MUESTRA_MAX:
        return datos[:MUESTRA_MAX], f"primeros 16 MB de {len(datos) / 2**20:.1f} MB"
    return datos, "archivo completo"


# ═══════════════════════════ la medición ═══════════════════════════
POSICIONES_CORRUPCION = (0.25, 0.50, 0.75)


@dataclass
class Resultado:
    archivo: str
    tecnica: str
    familia: str
    bytes_orig: int
    bytes_comp: int
    razon: float
    ahorro_pct: float
    mb_s_comprimir: float
    mb_s_descomprimir: float
    exacto: bool
    recuperado_pct: float               # promedio sobre las 3 corrupciones
    info_entregada_pct: float           # I(X;Y)/H(X) promedio con 1 byte corrupto
    detalle_corrupcion: list = field(default_factory=list)
    k_tic: int | None = None


def medir(nombre: str, datos: bytes, t: Tecnica, h_x: float) -> Resultado:
    x = np.frombuffer(datos, np.uint8)
    t0 = time.perf_counter(); comp = t.comprimir(datos); t1 = time.perf_counter()
    rec = t.descomprimir(comp); t2 = time.perf_counter()
    exacto = hashlib.sha256(rec).digest() == hashlib.sha256(datos).digest()
    mb = len(datos) / 2**20

    detalle = []
    for frac in POSICIONES_CORRUPCION:
        dañado = bytearray(comp)
        pos = int(len(comp) * frac)
        dañado[pos] ^= 0xFF  # se invierten los 8 bits de un solo byte
        try:
            r = (t.tolerante or t.descomprimir)(bytes(dañado))
            error = None
        except Exception as e:  # el formato detectó el daño (checksum) o se rompió
            r, error = None, type(e).__name__
        y = recuperado_alineado(x, r)
        detalle.append({"posicion": frac, "error": error,
                        "recuperado_pct": round(100 * float((y == x).mean()), 3),
                        "info_entregada_pct": round(100 * info_mutua_bytes(x, y) / h_x, 3) if h_x else 100.0})
    return Resultado(
        archivo=nombre, tecnica=t.nombre, familia=t.familia, bytes_orig=len(datos), bytes_comp=len(comp),
        razon=round(len(datos) / len(comp), 4), ahorro_pct=round(100 * (1 - len(comp) / len(datos)), 2),
        mb_s_comprimir=round(mb / (t1 - t0), 2), mb_s_descomprimir=round(mb / (t2 - t1), 2), exacto=exacto,
        recuperado_pct=round(float(np.mean([d["recuperado_pct"] for d in detalle])), 2),
        info_entregada_pct=round(float(np.mean([d["info_entregada_pct"] for d in detalle])), 2),
        detalle_corrupcion=detalle, k_tic=TIC.k_elegido.get(len(comp)) if t.nombre == "tic" else None)


def correr(dir_datos: Path, salida: Path, solo: list[str] | None = None) -> dict:
    dir_muestras = dir_datos / "muestras"
    dir_muestras.mkdir(exist_ok=True)
    lista = tecnicas()
    informe = {"muestra_max_bytes": MUESTRA_MAX, "posiciones_corrupcion": POSICIONES_CORRUPCION,
               "tecnicas": [{"nombre": t.nombre, "familia": t.familia, "descripcion": t.descripcion,
                             "solo_para": list(t.solo_para)} for t in lista],
               "archivos": {}, "resultados": []}
    for nombre, (tipo, archivo, nota) in ARCHIVOS.items():
        if solo and nombre not in solo:
            continue
        if not (dir_datos / archivo).exists():
            print(f"  (falta {archivo}, se omite)")
            continue
        datos, como = preparar_muestra(nombre, dir_datos, dir_muestras)
        h = entropia_bytes(np.frombuffer(datos, np.uint8))
        informe["archivos"][nombre] = {"tipo": tipo, "archivo": archivo, "nota": nota, "muestra": como,
                                       "bytes": len(datos), "H_bits_por_byte": round(h, 4)}
        print(f"\n{nombre}: {len(datos):,} bytes, H = {h:.3f} bits/byte ({como})")
        for t in lista:
            if not t.aplica(nombre):
                continue
            r = medir(nombre, datos, t, h)
            informe["resultados"].append(r.__dict__)
            print(f"  {t.nombre:<17} razón {r.razon:>8.3f}  ahorro {r.ahorro_pct:>6.2f} %  "
                  f"{r.mb_s_comprimir:>8.2f} / {r.mb_s_descomprimir:>8.2f} MB/s  "
                  f"{'exacto' if r.exacto else 'DISTINTO'}  1 byte dañado → {r.info_entregada_pct:6.2f} % de la información")
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "comparacion_tecnicas.json").write_text(json.dumps(informe, indent=1, ensure_ascii=False), encoding="utf-8")
    (salida / "comparacion_tecnicas.md").write_text(markdown(informe), encoding="utf-8")
    graficar(informe, salida / "comparacion_tecnicas.png")
    print(f"\nGuardado en {salida}")
    return informe


# ═══════════════════════════ salida ═══════════════════════════
def markdown(inf: dict) -> str:
    md = ["# Técnicas actuales frente al códec TIC\n",
          "Generado por `src/comparar_tecnicas.py`. Todas las técnicas son sin pérdida. "
          "«1 byte dañado» = información entregada I(X;Y)/H(X) cuando se invierte un byte del archivo "
          "comprimido (promedio de tres posiciones: 25, 50 y 75 % del largo).\n"]
    for nombre, a in inf["archivos"].items():
        md.append(f"\n## {nombre} — {a['nota']}\n\n{a['bytes']:,} bytes, H = {a['H_bits_por_byte']} bits/byte. "
                  f"Muestra: {a['muestra']}.\n\n"
                  "| técnica | razón | ahorro % | comprimir MB/s | descomprimir MB/s | exacto | 1 byte dañado: info. entregada % |\n"
                  "|---|---:|---:|---:|---:|:---:|---:|\n")
        filas = sorted((r for r in inf["resultados"] if r["archivo"] == nombre), key=lambda r: -r["razon"])
        for r in filas:
            k = f" (k={r['k_tic']})" if r.get("k_tic") else ""
            md.append(f"| {r['tecnica']}{k} | {r['razon']:.3f} | {r['ahorro_pct']:.2f} | {r['mb_s_comprimir']:.2f} | "
                      f"{r['mb_s_descomprimir']:.2f} | {'sí' if r['exacto'] else 'NO'} | {r['info_entregada_pct']:.2f} |\n")
    return "".join(md)


def graficar(inf: dict, ruta: Path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    archivos = list(inf["archivos"])
    tecs = [t["nombre"] for t in inf["tecnicas"]]
    fig, axs = plt.subplots(1, 2, figsize=(15, 5.5))
    ancho = 0.8 / len(tecs)
    for j, t in enumerate(tecs):
        xs, rs, vs = [], [], []
        for i, a in enumerate(archivos):
            r = next((r for r in inf["resultados"] if r["archivo"] == a and r["tecnica"] == t), None)
            if r:
                xs.append(i + (j - len(tecs) / 2) * ancho); rs.append(r["razon"]); vs.append(r["mb_s_comprimir"])
        axs[0].bar(xs, rs, ancho, label=t)
        axs[1].bar(xs, vs, ancho, label=t)
    for ax, tit, log in ((axs[0], "Razón de compresión (más alto = mejor)", True),
                         (axs[1], "Velocidad al comprimir, MB/s (escala log)", True)):
        ax.set_xticks(range(len(archivos))); ax.set_xticklabels(archivos, rotation=20)
        ax.set_title(tit); ax.grid(axis="y", alpha=.3)
        if log: ax.set_yscale("log")
    axs[0].axhline(1, color="k", lw=.8)
    axs[1].legend(fontsize=8, ncol=2)
    fig.tight_layout(); fig.savefig(ruta, dpi=110); plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--datos", type=Path, default=DIR_DATOS, help="carpeta con los archivos de prueba")
    p.add_argument("--salida", type=Path, default=Path(__file__).resolve().parent.parent / "examples" / "comparacion_tecnicas")
    p.add_argument("--solo", nargs="*", choices=list(ARCHIVOS), help="medir solo estos archivos")
    a = p.parse_args()
    correr(a.datos, a.salida, a.solo)


if __name__ == "__main__":
    main()

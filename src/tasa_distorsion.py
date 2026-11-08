"""tasa_distorsion.py — La "calidad" del punto (b): compresión CON pérdida y su curva
tasa-distorsión (cuántos bits cuesta cada nivel de calidad) en la imagen y el audio reales.

Sin pérdida, la calidad siempre es 100 % y la información mutua entre el original X y lo
recuperado Y vale H(X): no distingue nada. Con pérdida se cambia fidelidad por bits, y entonces:
  · la calidad se mide con PSNR (imagen) o SNR (audio), en decibeles: más alto = más parecido;
  · I(X;Y) < H(X): la información mutua dice cuánta información del original sobrevive.

Métodos comparados:
  Imagen (franja BMP de 16 MB de imagen_prueba.bmp, la misma que usa comparar_tecnicas.py)
    · JPEG con calidad 10 … 95 (DCT por bloques de 8×8 + cuantización + Huffman)
    · WebP con pérdida, calidad 10 … 90 (predicción por bloques + DCT, de VP8)
    · Cuantización uniforme: se anulan los n bits menos significativos de cada byte (lo mismo que
      `tic_codec.py --perdida n`) y luego zstd -19 sin pérdida
  Audio (voz, WAV PCM de 16 bits)
    · MP3 a distintas calidades (modelo psicoacústico + MDCT)
    · Cuantización uniforme: se anulan n bits de cada muestra de 16 bits y luego FLAC

I(X;Y) se mide símbolo a símbolo: byte a byte en la imagen (X, Y ∈ 0..255) y muestra a muestra en
el audio (X, Y ∈ valores de 16 bits). Es un estimador de orden 0: no ve la correlación entre
vecinos, así que sirve para comparar métodos entre sí, no como medida perceptual.

Uso:
  python tasa_distorsion.py --datos D:/ruta/data
"""
from __future__ import annotations

import argparse, io, json, sys, time
from pathlib import Path

import numpy as np

from comparar_tecnicas import DIR_DATOS, _zstd, entropia_bytes, info_mutua_bytes, preparar_muestra
from tic_codec import Informacion

if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8")

CALIDADES_JPEG = [10, 20, 30, 50, 70, 85, 95]
CALIDADES_WEBP = [10, 30, 50, 70, 90]
BITS_IMAGEN = [1, 2, 3, 4, 5]
CALIDADES_MP3 = [0.0, 0.25, 0.5, 0.75, 0.95]   # compression_level de libsndfile: 0 = mejor calidad
BITS_AUDIO = [2, 4, 6, 8, 10]


# ═══════════════════════════ medidas ═══════════════════════════
def psnr(x: np.ndarray, y: np.ndarray, pico: float) -> float:
    mse = float(np.mean((x.astype(np.float64) - y.astype(np.float64)) ** 2))
    return float("inf") if mse == 0 else 10 * np.log10(pico ** 2 / mse)


def snr(x: np.ndarray, y: np.ndarray) -> float:
    x, y = x.astype(np.float64), y.astype(np.float64)
    ruido = float(np.sum((x - y) ** 2))
    return float("inf") if ruido == 0 else 10 * np.log10(float(np.sum(x ** 2)) / ruido)


def info_mutua_muestras(x: np.ndarray, y: np.ndarray) -> float:
    """I(X;Y) en bits por muestra para muestras de 16 bits (se corren a 0..65535)."""
    return Informacion.informacion_mutua(x.astype(np.int64) + 32768, y.astype(np.int64) + 32768)


def entropia_muestras(x: np.ndarray) -> float:
    p = np.bincount(x.astype(np.int64) + 32768) / len(x)
    p = p[p > 0]
    return float(-(p * np.log2(p)).sum())


def alinear(x: np.ndarray, y: np.ndarray, max_lag: int = 4096) -> np.ndarray:
    """MP3 puede correr la señal unas muestras (retardo del codificador). Busca el corrimiento
    que mejor alinea y con x (correlación en un tramo de 1 s) y devuelve y alineada al largo de x."""
    n = min(len(x), len(y), 48000)
    a = x[:n].astype(np.float64)
    mejor, lag_mejor = -np.inf, 0
    for lag in range(-max_lag, max_lag + 1, 1):
        b = y[max(lag, 0):max(lag, 0) + n - abs(lag)].astype(np.float64)
        aa = a[max(-lag, 0):max(-lag, 0) + len(b)]
        if len(b) < n // 2:
            continue
        c = float(np.dot(aa, b))
        if c > mejor:
            mejor, lag_mejor = c, lag
    out = np.zeros(len(x), dtype=y.dtype)
    if lag_mejor >= 0:
        seg = y[lag_mejor:lag_mejor + len(x)]
        out[:len(seg)] = seg
    else:
        seg = y[:len(x) + lag_mejor]
        out[-lag_mejor:-lag_mejor + len(seg)] = seg
    return out


# ═══════════════════════════ imagen ═══════════════════════════
def curva_imagen(bmp: bytes) -> dict:
    from PIL import Image
    im = Image.open(io.BytesIO(bmp)).convert("RGB")
    x = np.asarray(im, dtype=np.uint8)
    px = x.shape[0] * x.shape[1]
    plano = x.reshape(-1)
    h = entropia_bytes(plano)
    zcomp, zdesc = _zstd(19)
    filas = []

    def anotar(metodo, param, comp_bytes, y, t):
        yp = y.reshape(-1)
        filas.append({"metodo": metodo, "parametro": param, "bytes": comp_bytes,
                      "bits_por_pixel": round(8 * comp_bytes / px, 4),
                      "razon": round(len(plano) / comp_bytes, 3),
                      "psnr_db": round(psnr(plano, yp, 255), 2),
                      "info_entregada_pct": round(100 * info_mutua_bytes(plano, yp.astype(np.int64)) / h, 2),
                      "segundos": round(t, 2)})
        print(f"  {metodo:<14} {str(param):>5}  {8 * comp_bytes / px:6.3f} bits/píxel  "
              f"PSNR {filas[-1]['psnr_db']:6.2f} dB  I/H {filas[-1]['info_entregada_pct']:6.2f} %")

    # Referencia sin pérdida: PNG.
    t = time.perf_counter(); b = io.BytesIO(); im.save(b, format="PNG", optimize=True)
    anotar("png (sin pérdida)", "-", len(b.getvalue()), x, time.perf_counter() - t)
    for q in CALIDADES_JPEG:
        t = time.perf_counter(); b = io.BytesIO(); im.save(b, format="JPEG", quality=q)
        y = np.asarray(Image.open(io.BytesIO(b.getvalue())).convert("RGB"))
        anotar("jpeg", q, len(b.getvalue()), y, time.perf_counter() - t)
    for q in CALIDADES_WEBP:
        t = time.perf_counter(); b = io.BytesIO(); im.save(b, format="WEBP", quality=q, method=4)
        y = np.asarray(Image.open(io.BytesIO(b.getvalue())).convert("RGB"))
        anotar("webp", q, len(b.getvalue()), y, time.perf_counter() - t)
    for n in BITS_IMAGEN:
        t = time.perf_counter()
        y = x & np.uint8((0xFF << n) & 0xFF)          # igual que tic_codec.py --perdida n
        c = zcomp(y.tobytes())
        assert zdesc(c) == y.tobytes()
        anotar("cuantizar+zstd", n, len(c), y, time.perf_counter() - t)
    return {"ancho": x.shape[1], "alto": x.shape[0], "H_bits_por_byte": round(h, 4), "puntos": filas}


# ═══════════════════════════ audio ═══════════════════════════
def curva_audio(wav: bytes) -> dict:
    import soundfile as sf
    x, sr = sf.read(io.BytesIO(wav), dtype="int16")
    n = len(x)
    h = entropia_muestras(x)
    filas = []

    def anotar(metodo, param, comp_bytes, y, t):
        filas.append({"metodo": metodo, "parametro": param, "bytes": comp_bytes,
                      "bits_por_muestra": round(8 * comp_bytes / n, 3),
                      "kbps": round(8 * comp_bytes / (n / sr) / 1000, 1),
                      "razon": round(2 * n / comp_bytes, 3),
                      "snr_db": round(snr(x, y), 2),
                      "info_entregada_pct": round(100 * info_mutua_muestras(x, y) / h, 2),
                      "segundos": round(t, 2)})
        print(f"  {metodo:<14} {str(param):>5}  {filas[-1]['kbps']:7.1f} kbps  "
              f"SNR {filas[-1]['snr_db']:6.2f} dB  I/H {filas[-1]['info_entregada_pct']:6.2f} %")

    def flac(s):
        b = io.BytesIO(); sf.write(b, s, sr, format="FLAC", subtype="PCM_16"); return b.getvalue()

    t = time.perf_counter(); c = flac(x)
    anotar("flac (sin pérdida)", "-", len(c), x, time.perf_counter() - t)
    for q in CALIDADES_MP3:
        t = time.perf_counter(); b = io.BytesIO()
        sf.write(b, x, sr, format="MP3", subtype="MPEG_LAYER_III", compression_level=q)
        b.seek(0); y, _ = sf.read(b, dtype="int16")
        anotar("mp3", q, len(b.getvalue()), alinear(x, y), time.perf_counter() - t)
    for bits in BITS_AUDIO:
        t = time.perf_counter()
        y = (x.astype(np.int32) >> bits << bits).astype(np.int16)   # anula los `bits` bits bajos
        anotar("cuantizar+flac", bits, len(flac(y)), y, time.perf_counter() - t)
    return {"muestras": n, "frecuencia_hz": sr, "H_bits_por_muestra": round(h, 4), "puntos": filas}


# ═══════════════════════════ salida ═══════════════════════════
def markdown(inf: dict) -> str:
    im, au = inf["imagen"], inf["audio"]
    md = ["# Calidad: curvas tasa-distorsión\n",
          "Generado por `src/tasa_distorsion.py`. «I/H» = información mutua entre original y recuperado "
          "dividida por la entropía del original (100 % = sin pérdida).\n",
          f"\n## Imagen ({im['ancho']}×{im['alto']} píxeles, H = {im['H_bits_por_byte']} bits/byte)\n\n"
          "| método | parámetro | bits/píxel | razón | PSNR dB | I/H % |\n|---|---:|---:|---:|---:|---:|\n"]
    for p in im["puntos"]:
        md.append(f"| {p['metodo']} | {p['parametro']} | {p['bits_por_pixel']:.3f} | {p['razon']:.2f} | "
                  f"{p['psnr_db']} | {p['info_entregada_pct']:.2f} |\n")
    md.append(f"\n## Audio ({au['muestras']:,} muestras a {au['frecuencia_hz']} Hz, H = {au['H_bits_por_muestra']} "
              "bits/muestra)\n\n| método | parámetro | kbps | bits/muestra | razón | SNR dB | I/H % |\n"
              "|---|---:|---:|---:|---:|---:|---:|\n")
    for p in au["puntos"]:
        md.append(f"| {p['metodo']} | {p['parametro']} | {p['kbps']} | {p['bits_por_muestra']:.3f} | {p['razon']:.2f} | "
                  f"{p['snr_db']} | {p['info_entregada_pct']:.2f} |\n")
    return "".join(md)


def graficar(inf: dict, ruta: Path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    fig, axs = plt.subplots(2, 2, figsize=(13, 9))
    for fila, (clave, eje_x, calidad, unidad) in enumerate((("imagen", "bits_por_pixel", "psnr_db", "PSNR (dB)"),
                                                             ("audio", "kbps", "snr_db", "SNR (dB)"))):
        puntos = inf[clave]["puntos"]
        for metodo in dict.fromkeys(p["metodo"] for p in puntos):
            ps = [p for p in puntos if p["metodo"] == metodo]
            xs = [p[eje_x] for p in ps]
            ys = [min(p[calidad], 99) for p in ps]
            ii = [p["info_entregada_pct"] for p in ps]
            estilo = "*" if "sin pérdida" in metodo else "o-"
            axs[fila, 0].plot(xs, ys, estilo, label=metodo, ms=9 if estilo == "*" else 5)
            axs[fila, 1].plot(xs, ii, estilo, label=metodo, ms=9 if estilo == "*" else 5)
        xl = "bits por píxel" if clave == "imagen" else "kbps"
        axs[fila, 0].set(title=f"{clave.capitalize()}: calidad contra tasa", xlabel=xl, ylabel=unidad)
        axs[fila, 1].set(title=f"{clave.capitalize()}: información mutua contra tasa", xlabel=xl,
                         ylabel="I(X;Y) / H(X)  (%)")
        for ax in axs[fila]:
            ax.grid(alpha=.3); ax.legend(fontsize=8)
    fig.tight_layout(); fig.savefig(ruta, dpi=110); plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--datos", type=Path, default=DIR_DATOS)
    p.add_argument("--salida", type=Path, default=Path(__file__).resolve().parent.parent / "examples" / "tasa_distorsion")
    a = p.parse_args()
    muestras = a.datos / "muestras"; muestras.mkdir(exist_ok=True)
    print("Imagen:")
    bmp, nota_im = preparar_muestra("imagen_bmp", a.datos, muestras)
    imagen = curva_imagen(bmp); imagen["muestra"] = nota_im
    print("Audio:")
    wav, nota_au = preparar_muestra("audio_wav", a.datos, muestras)
    audio = curva_audio(wav); audio["muestra"] = nota_au
    inf = {"imagen": imagen, "audio": audio}
    a.salida.mkdir(parents=True, exist_ok=True)
    (a.salida / "tasa_distorsion.json").write_text(json.dumps(inf, indent=1, ensure_ascii=False), encoding="utf-8")
    (a.salida / "tasa_distorsion.md").write_text(markdown(inf), encoding="utf-8")
    graficar(inf, a.salida / "tasa_distorsion.png")
    print(f"Guardado en {a.salida}")


if __name__ == "__main__":
    main()

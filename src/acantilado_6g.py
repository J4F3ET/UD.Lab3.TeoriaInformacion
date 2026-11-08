#!/usr/bin/env python3
"""
acantilado_6g.py — La idea de 6G en una gráfica: "todo o nada" (5G) contra "se degrada de a poco"
(codificación conjunta fuente-canal, la idea detrás de DeepJSCC). Simulación, no 6G implementado.

Se manda la misma imagen por un canal con ruido (AWGN), con el MISMO ancho de banda (usos del
canal) y la MISMA potencia, de dos maneras:

  · Digital, como 5G:  JPEG → código de canal ideal (en el límite de Shannon) → canal.
    Se diseña para una calidad de señal (SNR de diseño): se mete el JPEG más grande que el código
    puede proteger a esa SNR. Si el canal real es igual o mejor, la imagen llega perfecta (y no
    mejora aunque la señal mejore). Si es peor, el código falla y no llega nada: el acantilado.
    El código ideal favorece al digital: uno real necesita 1–2 dB más.

  · Analógico, al estilo SoftCast (Jakubczak y Katabi, 2011), sin red neuronal: la DCT de la imagen
    se corta en trozos, se mandan los de más energía (los que caben en el ancho de banda), cada uno
    escalado según su energía (λ^-1/4), directamente como amplitudes de la señal. El receptor estima
    con mínimos cuadrados lineales (LLSE). Más ruido = imagen más borrosa, pero siempre llega algo.
    La media de la imagen y la energía de cada trozo viajan aparte como metadatos (pocos bytes, se
    suponen sin error, como en SoftCast).

Medidas por SNR: PSNR e I(X;Y)/H(X) entre los píxeles originales y los recibidos (si no llegó
nada, el receptor muestra gris: I = 0).

Uso:  python src/acantilado_6g.py [--datos DIR] [--salida DIR]
"""
from __future__ import annotations

import argparse, io, json, time
from pathlib import Path

import numpy as np
from PIL import Image

from comparar_tecnicas import DIR_DATOS, entropia_bytes, info_mutua_bytes
from tasa_distorsion import psnr

LADO = 512                          # imagen de 512 × 512 en escala de grises
TROZO = 32                          # trozos de 32 × 32 coeficientes DCT (256 trozos)
ANCHO_BANDA = 0.25                  # usos del canal por píxel (los dos esquemas por igual)
POTENCIA = 1.0                      # potencia media por uso del canal
SNRS = list(range(0, 31))           # dB
DISENOS = [5, 12, 20]               # SNR de diseño del esquema digital, dB
SNRS_MUESTRA = [4, 10, 16, 25]      # dB, para las imágenes de ejemplo
SEMILLA = 7


# ═══════════════════════════ imagen y DCT ═══════════════════════════
def cargar_imagen(dir_datos: Path) -> np.ndarray:
    """imagen_prueba.bmp en grises, reducida y recortada al centro a LADO × LADO."""
    im = Image.open(dir_datos / "imagen_prueba.bmp").convert("L")
    w, h = im.size
    esc = LADO / min(w, h)
    im = im.resize((max(LADO, round(w * esc)), max(LADO, round(h * esc))), Image.LANCZOS)
    w, h = im.size
    x0, y0 = (w - LADO) // 2, (h - LADO) // 2
    return np.asarray(im.crop((x0, y0, x0 + LADO, y0 + LADO)), dtype=np.uint8)


def matriz_dct(n: int) -> np.ndarray:
    """DCT-II ortonormal: dct2(X) = D X Dᵀ, idct2(C) = Dᵀ C D."""
    k, i = np.arange(n)[:, None], np.arange(n)[None, :]
    d = np.cos(np.pi * (2 * i + 1) * k / (2 * n)) * np.sqrt(2 / n)
    d[0] /= np.sqrt(2)
    return d


def medir(x: np.ndarray, y: np.ndarray, h_x: float) -> dict:
    return {"psnr_db": round(psnr(x, y, 255), 2),
            "info_pct": round(100 * info_mutua_bytes(x.ravel(), y.ravel().astype(np.int64)) / h_x, 2)}


# ═══════════════════════════ analógico (SoftCast) ═══════════════════════════
class Analogico:
    def __init__(self, img: np.ndarray):
        self.img, self.d = img, matriz_dct(LADO)
        self.media = float(img.mean())
        c = self.d @ (img - self.media) @ self.d.T
        m = LADO // TROZO
        self.trozos = c.reshape(m, TROZO, m, TROZO).swapaxes(1, 2).reshape(m * m, TROZO * TROZO)
        lam = (self.trozos ** 2).mean(1)
        k = int(round(ANCHO_BANDA * LADO * LADO / (TROZO * TROZO)))   # trozos que caben
        self.enviados = np.argsort(lam)[::-1][:k]
        self.lam = lam[self.enviados]
        # Ganancia óptima de SoftCast: g ∝ λ^-1/4, normalizada a la potencia media POTENCIA.
        self.g = np.sqrt(POTENCIA * k / np.sqrt(self.lam).sum()) * self.lam ** -0.25
        self.k, self.m = k, m

    def recibir(self, snr_db: float, rng: np.random.Generator) -> np.ndarray:
        s2 = POTENCIA / 10 ** (snr_db / 10)
        tx = self.g[:, None] * self.trozos[self.enviados]
        rx = tx + rng.normal(0, np.sqrt(s2), tx.shape)
        est = np.zeros_like(self.trozos)
        g, lam = self.g[:, None], self.lam[:, None]
        est[self.enviados] = g * lam / (g ** 2 * lam + s2) * rx       # LLSE
        c = est.reshape(self.m, self.m, TROZO, TROZO).swapaxes(1, 2).reshape(LADO, LADO)
        return np.clip(np.rint(self.d.T @ c @ self.d + self.media), 0, 255).astype(np.uint8)


# ═══════════════════════════ digital (JPEG + código ideal) ═══════════════════════════
def capacidad(snr_db: float) -> float:
    """Bits por uso de un canal real con ruido gaussiano: ½·log2(1 + SNR)."""
    return 0.5 * np.log2(1 + 10 ** (snr_db / 10))


def _jpeg(img: np.ndarray, q: int) -> bytes:
    b = io.BytesIO()
    Image.fromarray(img).save(b, "JPEG", quality=q)
    return b.getvalue()


class Digital:
    def __init__(self, img: np.ndarray, diseno_db: float):
        self.img, self.diseno = img, diseno_db
        self.tasa = capacidad(diseno_db)
        self.presupuesto = int(self.tasa * ANCHO_BANDA * img.size)       # bits que caben
        q_ok, lo, hi = None, 1, 95
        while lo <= hi:                                                  # JPEG más grande que cabe
            q = (lo + hi) // 2
            if len(_jpeg(img, q)) * 8 <= self.presupuesto:
                q_ok, lo = q, q + 1
            else:
                hi = q - 1
        self.calidad = q_ok
        self.bytes = len(_jpeg(img, q_ok)) if q_ok else 0
        self.recibida = (np.asarray(Image.open(io.BytesIO(_jpeg(img, q_ok)))) if q_ok
                         else np.full_like(img, round(img.mean())))
        self.gris = np.full_like(img, round(img.mean()))

    def recibir(self, snr_db: float) -> np.ndarray:
        return self.recibida if self.calidad and capacidad(snr_db) >= self.tasa else self.gris


# ═══════════════════════════ corrida ═══════════════════════════
def correr(dir_datos: Path, salida: Path) -> dict:
    t0 = time.time()
    img = cargar_imagen(dir_datos)
    h_x = entropia_bytes(img.ravel())
    rng = np.random.default_rng(SEMILLA)
    ana = Analogico(img)
    digs = [Digital(img, d) for d in DISENOS]
    curvas = {"analogico": [dict(snr_db=s, **medir(img, ana.recibir(s, rng), h_x)) for s in SNRS]}
    for dg in digs:
        curvas[f"digital_{dg.diseno}dB"] = [dict(snr_db=s, **medir(img, dg.recibir(s), h_x)) for s in SNRS]
    muestras = {"analogico": {s: ana.recibir(s, rng) for s in SNRS_MUESTRA},
                "digital": {s: digs[1].recibir(s) for s in SNRS_MUESTRA}}
    inf = {"lado": LADO, "h_x": round(h_x, 4), "ancho_banda_usos_por_pixel": ANCHO_BANDA,
           "trozos_enviados": int(ana.k), "trozos_totales": int(ana.m ** 2),
           "digital": [{"snr_diseno_db": dg.diseno, "bits_por_uso": round(dg.tasa, 3),
                        "presupuesto_bytes": dg.presupuesto // 8, "jpeg_calidad": dg.calidad,
                        "jpeg_bytes": dg.bytes} for dg in digs],
           "curvas": curvas, "segundos": round(time.time() - t0, 1)}
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "acantilado_6g.json").write_text(json.dumps(inf, indent=1, ensure_ascii=False), encoding="utf-8")
    (salida / "acantilado_6g.md").write_text(markdown(inf), encoding="utf-8")
    graficar(inf, img, muestras, digs[1], salida / "acantilado_6g.png")
    return inf


def _en(curva, snr):
    return next(p for p in curva if p["snr_db"] == snr)


def markdown(inf: dict) -> str:
    d12 = next(d for d in inf["digital"] if d["snr_diseno_db"] == 12)
    ana, dig = inf["curvas"]["analogico"], inf["curvas"]["digital_12dB"]
    md = ["# 6G en una gráfica: todo o nada contra degradación gradual",
          "",
          "Generado por `src/acantilado_6g.py`. **Es una simulación de la idea, no 6G implementado.**",
          "",
          "## La idea, para cualquiera",
          "",
          "Hoy (5G) una imagen se manda en una **cadena**: primero se comprime (JPEG), después se "
          "protege con un código contra errores y por último se transmite. Cada eslabón depende del "
          "anterior. Si el ruido de la radio pasa de cierto punto, el código ya no puede corregir, el "
          "JPEG llega con errores y **no se puede abrir: se pierde entero**. Es como un archivo .zip: "
          "o abre perfecto o dice «archivo dañado». A eso se le llama **efecto acantilado**.",
          "",
          "La idea que se estudia para 6G es **juntar la compresión y la protección en un solo paso** "
          "(codificación conjunta fuente-canal; con redes neuronales se llama DeepJSCC). La imagen se "
          "manda casi «en analógico»: lo importante con más fuerza, los detalles con menos. Con más "
          "ruido llega **más borrosa, pero llega**. Es como ver una foto a través de niebla: más "
          "niebla, menos nitidez, pero siempre se ve algo.",
          "",
          "## El experimento",
          "",
          f"La misma imagen ({inf['lado']}×{inf['lado']}, grises) por un canal con ruido, con el mismo "
          f"ancho de banda ({inf['ancho_banda_usos_por_pixel']} usos del canal por píxel) y la misma "
          "potencia:",
          "",
          f"- **Digital (como 5G):** JPEG + un código de canal *ideal* (en el límite de Shannon, mejor "
          f"que cualquiera real). Diseñado para 12 dB, le caben {d12['presupuesto_bytes']:,} bytes: "
          f"JPEG con calidad {d12['jpeg_calidad']} ({d12['jpeg_bytes']:,} B). También se prueba diseñado "
          "para 5 y 20 dB.",
          f"- **Analógico (idea de 6G, estilo SoftCast, sin red neuronal):** la imagen en frecuencias "
          f"(DCT), se mandan los {inf['trozos_enviados']} de {inf['trozos_totales']} trozos con más "
          "energía, cada uno con la fuerza que le corresponde.",
          "",
          "| Calidad de la señal (SNR) | Digital, diseñado a 12 dB: PSNR / info. | Analógico: PSNR / info. |",
          "|---:|---|---|"]
    for s in (2, 6, 10, 11, 12, 16, 20, 25, 30):
        a, g = _en(ana, s), _en(dig, s)
        md.append(f"| {s} dB | {g['psnr_db']} dB / {g['info_pct']} % | {a['psnr_db']} dB / {a['info_pct']} % |")
    md += ["",
           "«Info.» = I(X;Y)/H(X): qué parte de la información de los píxeles llega al receptor.",
           "",
           "## Qué se ve",
           "",
           "- **El acantilado.** El digital diseñado a 12 dB entrega su JPEG completo desde 12 dB, pero a "
           "11 dB entrega **nada** (gris, 0 % de información). Un decibel de diferencia es todo o nada.",
           "- **La meseta.** Por encima de su diseño el digital no mejora: aunque la señal sea excelente, "
           "sigue entregando el mismo JPEG. Para aprovechar la señal buena habría que haber elegido otro diseño "
           "antes de transmitir, y adivinar mal tira la imagen.",
           f"- **La rampa.** El analógico mejora de a poco con cada decibel, sin saltos: nunca se cae del todo. "
           f"A 4 dB, donde el digital no entrega nada, el analógico ya da {_en(ana, 4)['psnr_db']} dB: se lee la "
           "pizarra. Tiene techo (unos 33,6 dB) porque solo caben las frecuencias más importantes: los "
           "detalles finos quedan fuera desde el principio.",
           f"- **El precio.** Justo en su punto de diseño el digital gana: a 16 dB entrega {_en(dig, 16)['psnr_db']} "
           f"dB contra {_en(ana, 16)['psnr_db']} del analógico. Separar compresión y protección es lo óptimo (Shannon) "
           "*si se conoce la señal de antemano*. En un celular que se mueve la señal cambia todo el tiempo: el "
           "digital tiene que elegir un diseño y arriesgarse; el analógico no elige nada y funciona en todas. "
           "6G cambia algo de calidad máxima por no caerse nunca.",
           "",
           "## Cómo se relaciona con el resto del trabajo",
           "",
           "- Es el mismo fenómeno que la prueba de **1 byte dañado** del bloque A: bz2, FLAC o PNG entregaban "
           "0 % con un solo byte malo. Encadenar compresión y protección amplifica un error pequeño.",
           "- El **compresor con pérdida para IoT** (5G, `predictivo_iot`) y las **curvas tasa-distorsión** son la "
           "otra mitad de la idea de 6G (comunicación semántica): mandar lo que importa y medir con I(X;Y) cuánto "
           "se entrega.",
           "",
           "## Límites",
           "",
           "- Simulación con ruido gaussiano, sin desvanecimiento ni pérdidas de paquetes. El código digital es "
           "ideal (favorece al digital: uno real necesita 1–2 dB más).",
           "- El analógico es SoftCast (2011), no DeepJSCC: sin red neuronal. DeepJSCC aprende la transformación y "
           "gana más calidad, pero la forma de la curva (rampa sin acantilado) es la misma.",
           "- No corre sobre la red 5G del lab: UERANSIM simula la radio sin capa física, no hay señal que modular.",
           ""]
    return "\n".join(md)


def graficar(inf: dict, img: np.ndarray, muestras: dict, dg: Digital, ruta: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.gridspec import GridSpec, GridSpecFromSubplotSpec

    fig = plt.figure(figsize=(13, 10.5))
    gs = GridSpec(3, 5, figure=fig, height_ratios=[1.25, 1, 1], hspace=0.35, wspace=0.08, top=0.93)
    arriba = GridSpecFromSubplotSpec(1, 2, subplot_spec=gs[0, :], wspace=0.22)
    colores = {"analogico": "#1f77b4", "digital_5dB": "#f2a541", "digital_12dB": "#d62728", "digital_20dB": "#8c564b"}
    nombres = {"analogico": "analógico (idea de 6G)", "digital_5dB": "digital diseñado a 5 dB",
               "digital_12dB": "digital diseñado a 12 dB", "digital_20dB": "digital diseñado a 20 dB"}
    for col, (clave, etiqueta) in enumerate((("psnr_db", "Calidad (PSNR, dB)"), ("info_pct", "Información que llega, I(X;Y)/H(X) %"))):
        ax = fig.add_subplot(arriba[0, col])
        for nombre, curva in inf["curvas"].items():
            ax.plot([p["snr_db"] for p in curva], [p[clave] for p in curva], color=colores[nombre],
                    lw=2.2 if nombre == "analogico" else 1.8, label=nombres[nombre],
                    drawstyle="default" if nombre == "analogico" else "steps-post")
        ax.set_xlabel("Calidad de la señal de radio (SNR, dB)  →  mejor")
        ax.set_ylabel(etiqueta)
        ax.grid(alpha=0.3)
        ax.legend(fontsize=8, loc="lower right")
    fig.text(0.5, 0.975, "Todo o nada (5G) contra degradación gradual (idea de 6G): misma imagen, mismo ancho de banda, misma potencia",
             ha="center", fontsize=11.5, weight="bold")
    for fila, (clave, titulo) in enumerate((("digital", f"Digital (JPEG q{dg.calidad} + código ideal, diseño 12 dB)"),
                                           ("analogico", "Analógico (estilo SoftCast)"))):
        ax0 = fig.add_subplot(gs[fila + 1, 0])
        ax0.imshow(img, cmap="gray", vmin=0, vmax=255)
        ax0.set_title("original", fontsize=9)
        ax0.axis("off")
        ax0.text(-0.08, 0.5, titulo, transform=ax0.transAxes, rotation=90, va="center", ha="right", fontsize=9)
        for j, s in enumerate(SNRS_MUESTRA):
            ax = fig.add_subplot(gs[fila + 1, j + 1])
            y = muestras[clave][s]
            ax.imshow(y, cmap="gray", vmin=0, vmax=255)
            p = psnr(img, y, 255)
            ax.set_title(f"SNR {s} dB · PSNR {p:.1f} dB" if np.isfinite(p) else f"SNR {s} dB", fontsize=9)
            ax.axis("off")
    fig.savefig(ruta, dpi=110, bbox_inches="tight")
    plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datos", type=Path, default=DIR_DATOS)
    ap.add_argument("--salida", type=Path, default=Path(__file__).resolve().parent.parent / "examples" / "acantilado_6g")
    a = ap.parse_args()
    inf = correr(a.datos, a.salida)
    for nombre, curva in inf["curvas"].items():
        print(f"{nombre:<14}", " ".join(f"{p['snr_db']}:{p['psnr_db']}" for p in curva if p["snr_db"] % 5 == 0))
    print("digital:", inf["digital"])
    print(f"Guardado en {a.salida} ({inf['segundos']} s)")


if __name__ == "__main__":
    main()

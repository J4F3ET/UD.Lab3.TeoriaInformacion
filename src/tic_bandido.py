#!/usr/bin/env python3
"""
tic_bandido.py — Elección en línea del tamaño de símbolo k con un bandido UCB descontado
Teoría de la Información — Ingeniería en Telemática

Problema: el mejor k depende del tipo de fuente, y la fuente cambia con el tiempo
(un flujo puede pasar de texto a audio a una imagen). Medir TODOS los k en cada bloque
(el "barrido" de tic_codec.py) es exacto pero caro. Un "bandido" aprende cuál k conviene
usando solo la razón de compresión que el códec ya mide, sin etiquetas ni reentrenamiento.

Idea (bandido multibrazo con contexto):
  - El flujo se parte en bloques de tamaño fijo (por defecto 256 KB).
  - Contexto de un bloque: la categoría de `Informacion.clasificar` medida con k = 8.
  - Brazos: los 9 valores de K_BASE (8, 16, ..., 2048).
  - Recompensa: r = min(1, log2(max(razón, 1)) / 8), un número entre 0 y 1.
  - Regla: UCB con descuento (Garivier & Moulines) por contexto. Se elige el k con mayor
        X(k) + c · sqrt( ln(Σ N) / N(k) )
    donde N(k) y X(k) son el conteo y la recompensa media DESCONTADOS (lo viejo pesa menos).
  - Reinicio por cambio: si la recompensa se aleja más de 0,25 de lo esperado (hacia abajo
    O hacia arriba), se mide el bloque con los 9 k y se actualizan todos los brazos
    ("barrido de reinicio"). Con --solo-caidas solo cuenta el alejamiento hacia abajo.

Se simula sobre archivos: la matriz bloques × k de razones se calcula UNA vez y sobre ella
se reproducen las políticas bandido, k fijo = 8, k fijo = 16, aleatoria y óptimo.

Uso:
  python tic_bandido.py simular
  python tic_bandido.py simular --bloque-kb 256 --tramo-bloques 30 --gamma 0.98 --c 0.05 --semilla 0 \\
                                --reporte r.json --grafica g.png
  python tic_bandido.py simular --solo-caidas     (reinicio solo cuando la recompensa cae)
  python tic_bandido.py simular --tramos estructurado_256   (flujo de un solo tipo)

Organización del código (POO)
──────────────────────────────
  BandidoUCBDescontado  la regla de decisión y su estado (arreglos NumPy por contexto)
  Tramo                 descripción de un tramo del flujo (nombre, tipo de fuente, parámetro)
  FlujoBloques          arma el flujo concatenando tramos y lo entrega en bloques fijos
  SimuladorFlujo        calcula la matriz de razones, reproduce las políticas, imprime,
                        grafica y guarda el JSON

Igual que en tic_codec.py, ningún símbolo es un objeto de Python: todo el cómputo pesado
está vectorizado con NumPy.

Glosario de nombres cortos
──────────────────────────
  k        bits por símbolo (uno de K_BASE); también es el "brazo" del bandido
  j        posición de un k dentro de K_BASE (0 para k = 8, 8 para k = 2048)
  ctx      contexto de un bloque (texto de la categoría de Informacion.clasificar)
  N        conteo descontado de veces que se eligió cada brazo (arreglo de 9 números)
  S        suma descontada de las recompensas obtenidas con cada brazo
  X        recompensa media descontada de cada brazo = S / N
  r        recompensa de un bloque, entre 0 y 1
  nb       número de bloques del flujo
"""
from __future__ import annotations

import argparse, json, math, sys, time
from dataclasses import dataclass
from pathlib import Path
import numpy as np

from tic_codec import CodecTIC, GeneradorFuentes, K_BASE

# La consola de Windows usa cp1252 por defecto; igual que en tic_codec.py se pasa a UTF-8
# para poder imprimir tildes y símbolos sin que el programa falle.
if sys.platform == "win32":
    # _s recorre las dos salidas de consola: la normal (stdout) y la de errores (stderr).
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8")

# Carpeta data/ del proyecto, calculada a partir de la ubicación de ESTE archivo
# (así funciona sin importar desde qué carpeta se ejecute el programa).
# __file__ = ruta de este script; resolve() la vuelve absoluta; .parent sube una carpeta
# (src/), y un .parent más sube a la raíz del proyecto.
DIR_DATOS = Path(__file__).resolve().parent.parent / "data"

# Cambio de recompensa (respecto de la media descontada del brazo elegido) que dispara el reinicio.
# Se mira en AMBAS direcciones: una caída fuerte significa que el k elegido dejó de servir, y una
# subida fuerte también significa que la fuente cambió y que puede haber un k mucho mejor sin probar
# (si no, el bandido se conforma con el primer k que le da algo en la fuente nueva).
UMBRAL_CAMBIO = 0.25


# ═══════════════════════════ recompensa ═══════════════════════════
def recompensa(razon):
    """r = min(1, log2(max(razón, 1)) / 8). Funciona con un número o con un arreglo NumPy
    completo (np.maximum / np.minimum actúan elemento a elemento). El logaritmo evita que
    una razón enorme (p. ej. 165) domine a las demás; el tope 1 acota r entre 0 y 1."""
    return np.minimum(1.0, np.log2(np.maximum(razon, 1.0)) / 8.0)


# ═══════════════════════════ el bandido ═══════════════════════════
@dataclass
class EstadoContexto:
    """Lo que el bandido recuerda de UN contexto: un número por brazo (9 en total)."""
    N: np.ndarray        # (9,) conteo descontado de elecciones
    S: np.ndarray        # (9,) suma descontada de recompensas
    probado: np.ndarray  # (9,) bool — True si el brazo ya se probó alguna vez

    @classmethod
    def nuevo(cls, n_brazos: int) -> "EstadoContexto":
        # np.zeros crea un arreglo lleno de ceros; dtype=bool lo llena de False.
        return cls(N=np.zeros(n_brazos), S=np.zeros(n_brazos), probado=np.zeros(n_brazos, dtype=bool))


# c = 0.05 (y no 0.5): la recompensa es log2(razón)/8, así que las diferencias entre k vecinos son de
# centésimas; con c = 0.5 el bono de exploración las tapa y el bandido recorre los k en ciclo.
class BandidoUCBDescontado:
    """UCB con descuento, con un estado independiente por contexto.

    En cada actualización, N y S del contexto se multiplican por gamma (lo viejo pierde
    peso) y luego se suma la observación nueva. Así, si la fuente cambia, el bandido
    "olvida" poco a poco y vuelve a explorar. Es determinista: los empates se resuelven
    a favor del k menor."""

    def __init__(self, ks: list[int] = K_BASE, gamma: float = 0.98, c: float = 0.05):
        self.ks = list(ks)
        self.gamma = gamma
        self.c = c
        # Diccionario k → posición, para pasar de "k = 64" a "brazo número 3".
        # {k: j for j, k in enumerate(ks)} es una comprensión de diccionario; equivale a:
        #   d = {};  for j, k in enumerate(ks): d[k] = j
        self.pos = {k: j for j, k in enumerate(self.ks)}
        self.estados: dict[str, EstadoContexto] = {}  # contexto → su estado (se crea al verlo)

    def _estado(self, contexto: str) -> EstadoContexto:
        # Si el contexto es nuevo, se crea su estado vacío; luego se devuelve.
        if contexto not in self.estados:
            self.estados[contexto] = EstadoContexto.nuevo(len(self.ks))
        return self.estados[contexto]

    def media(self, contexto: str, k: int) -> float | None:
        """X(k): recompensa media descontada del brazo k, o None si nunca se probó."""
        e = self._estado(contexto)
        j = self.pos[k]
        if not e.probado[j]:
            return None
        return float(e.S[j] / e.N[j])

    def elegir(self, contexto: str) -> int:
        """Devuelve el k con mayor X(k) + c·sqrt(ln(ΣN)/N(k)). No modifica el estado."""
        e = self._estado(contexto)
        # `~` invierte un arreglo booleano. Si queda algún brazo sin probar, se elige el
        # primero (el de k menor): np.argmax sobre booleanos devuelve la primera posición True.
        if not e.probado.all():
            return self.ks[int(np.argmax(~e.probado))]
        X = e.S / e.N                                   # media descontada de cada brazo, de una vez
        total = max(float(e.N.sum()), 1.0)              # ΣN (con piso 1 para que ln no sea negativo)
        bono = self.c * np.sqrt(math.log(total) / e.N)  # premio por incertidumbre: crece si N(k) es chico
        # np.argmax devuelve la PRIMERA posición del máximo: en un empate gana el k menor.
        return self.ks[int(np.argmax(X + bono))]

    def actualizar(self, contexto: str, k: int, r: float):
        """Descuenta todo el contexto y suma la recompensa r observada con el brazo k."""
        e = self._estado(contexto)
        e.N *= self.gamma   # `*=` modifica el arreglo en su lugar: cada elemento × gamma
        e.S *= self.gamma
        j = self.pos[k]
        e.N[j] += 1.0       # una elección más de este brazo
        e.S[j] += r
        e.probado[j] = True

    def actualizar_todos(self, contexto: str, recompensas: np.ndarray):
        """Barrido: descuenta el contexto y suma a CADA brazo su recompensa real
        (recompensas[j] es la del brazo j)."""
        e = self._estado(contexto)
        e.N *= self.gamma
        e.S *= self.gamma
        e.N += 1.0          # cada brazo cuenta como observado una vez
        e.S += recompensas  # suma elemento a elemento (arreglo de 9 con arreglo de 9)
        e.probado[:] = True # `[:]` = todas las posiciones


# ═══════════════════════════ el flujo de bloques ═══════════════════════════
@dataclass
class Tramo:
    """Un tramo del flujo: una fuente que dura varios bloques seguidos."""
    nombre: str  # nombre que se muestra y se guarda
    tipo: str    # "uniforme", "no_uniforme", "estructurado" o "archivo"
    param: int | str | None = None  # estructurado: bytes por bloque repetido; archivo: nombre dentro de data/


# Tramos por defecto, en este orden.
TRAMOS_DEFECTO = [
    Tramo("uniforme", "uniforme"),
    Tramo("estructurado_256", "estructurado", 256),
    Tramo("texto", "archivo", "texto_prueba.txt"),
    Tramo("no_uniforme", "no_uniforme"),
    Tramo("estructurado_32", "estructurado", 32),
    Tramo("audio_wav", "archivo", "audio_prueba.wav"),
    Tramo("imagen_bmp", "archivo", "imagen_prueba.bmp"),
    Tramo("imagen_jpg", "archivo", "imagen_prueba.jpg"),
]


class FlujoBloques:
    """Concatena tramos de fuentes distintas y los entrega en bloques de tamaño fijo.
    Para cada bloque recuerda a qué tramo pertenece."""

    def __init__(self, tramos: list[Tramo] = TRAMOS_DEFECTO, bloque_bytes: int = 256 * 1024,
                 tramo_bloques: int = 30, semilla: int = 0):
        self.bloque_bytes = bloque_bytes
        self.tramos = tramos
        self.avisos: list[str] = []         # mensajes sobre tramos recortados
        self.tramos_usados: list[Tramo] = []  # tramos que sí aportaron bloques (en orden)
        rng = np.random.default_rng(semilla)  # un solo generador, usado en orden → reproducible
        trozos = []        # un arreglo de bytes por tramo
        nombres = []       # nombre del tramo de cada bloque
        for t in tramos:
            if t.tipo == "archivo":
                ruta = DIR_DATOS / str(t.param)
                # Bloques COMPLETOS que caben en el archivo (// = división entera hacia abajo).
                disponibles = ruta.stat().st_size // bloque_bytes
                nb = min(tramo_bloques, disponibles)
                if nb < tramo_bloques:
                    self.avisos.append(f"{t.nombre}: {ruta.name} solo da {nb} bloque(s) completo(s) "
                                       f"de {bloque_bytes // 1024} KB (se pedían {tramo_bloques})")
                if nb == 0:
                    continue  # el archivo no alcanza ni para un bloque: el tramo se omite
                # count = cuántos bytes leer, desde el inicio del archivo.
                datos = np.fromfile(ruta, dtype=np.uint8, count=nb * bloque_bytes)
            else:
                nb = tramo_bloques
                n = nb * bloque_bytes
                if t.tipo == "uniforme":
                    datos = GeneradorFuentes.uniforme(n, rng)
                elif t.tipo == "no_uniforme":
                    datos = GeneradorFuentes.no_uniforme(n, rng)
                elif t.tipo == "estructurado":
                    datos = GeneradorFuentes.estructurado(n, rng, bloque=int(t.param))
                else:
                    raise ValueError(f"tipo de tramo desconocido: {t.tipo}")
            trozos.append(datos)
            nombres += [t.nombre] * nb  # lista repetida nb veces; `+=` la pega al final
            self.tramos_usados.append(t)
        self.datos = np.concatenate(trozos)      # todo el flujo en un solo arreglo de bytes
        self.nombres_bloque = nombres            # nombres_bloque[b] = tramo del bloque b

    @property
    def n_bloques(self) -> int:
        return len(self.nombres_bloque)

    def bloque(self, b: int) -> np.ndarray:
        # Rebanada: los bytes desde b·tamaño hasta (b+1)·tamaño − 1.
        return self.datos[b * self.bloque_bytes:(b + 1) * self.bloque_bytes]


# ═══════════════════════════ el simulador ═══════════════════════════
class SimuladorFlujo:
    """Calcula la matriz bloques × k de razones una sola vez y reproduce sobre ella
    las políticas de elección de k."""

    POLITICAS = ["bandido", "k fijo = 8", "k fijo = 16", "aleatoria", "óptimo"]

    def __init__(self, flujo: FlujoBloques, gamma: float = 0.98, c: float = 0.05, semilla: int = 0,
                 ks: list[int] = K_BASE, solo_caidas: bool = False):
        self.flujo = flujo
        self.gamma, self.c, self.semilla = gamma, c, semilla
        # solo_caidas=True conserva la regla anterior (reinicio únicamente si la recompensa baja).
        self.solo_caidas = solo_caidas
        self.ks = list(ks)

    # ---- paso 1: medir todo una vez ----
    def calcular_matriz(self):
        """Llena `razones` (nb × 9) con la razón estimada de cada bloque con cada k, y
        `contextos` (nb) con la categoría de cada bloque medida con k = 8."""
        nb = self.flujo.n_bloques
        self.razones = np.zeros((nb, len(self.ks)))
        self.contextos: list[str] = []
        t0 = time.time()
        for b in range(nb):
            datos = self.flujo.bloque(b)
            for j, k in enumerate(self.ks):
                m, razon = CodecTIC.estimar(datos, k)
                self.razones[b, j] = razon
                if k == 8:
                    # El contexto sale de la misma medida con k = 8 (no se repite el cálculo).
                    self.contextos.append(m.estructura)
            # Progreso cada 10 bloques y en el último.
            if (b + 1) % 10 == 0 or b + 1 == nb:
                print(f"  matriz de razones: {b + 1}/{nb} bloques ({time.time() - t0:.0f} s)", flush=True)
        self.recompensas = recompensa(self.razones)  # misma forma (nb × 9), de una vez

    # ---- paso 2: reproducir las políticas ----
    def _politica_bandido(self):
        """Corre el bandido bloque a bloque. Devuelve las posiciones j elegidas, cuántos
        barridos de reinicio hubo y en qué bloques ocurrieron."""
        bandido = BandidoUCBDescontado(self.ks, self.gamma, self.c)
        nb = self.flujo.n_bloques
        elegidos = np.zeros(nb, dtype=int)
        barrido = np.zeros(nb, dtype=bool)  # True en los bloques donde hubo barrido de reinicio
        for b in range(nb):
            ctx = self.contextos[b]
            k = bandido.elegir(ctx)
            j = bandido.pos[k]
            r = float(self.recompensas[b, j])
            esperado = bandido.media(ctx, k)  # X(k) ANTES de actualizar (None si era nuevo)
            if esperado is None:
                cambio = False  # brazo sin historia: no hay nada con qué comparar
            elif self.solo_caidas:
                cambio = r < esperado - UMBRAL_CAMBIO       # solo hacia abajo
            else:
                cambio = abs(r - esperado) > UMBRAL_CAMBIO  # abs() = distancia, en cualquier dirección
            if cambio:
                # Cambio fuerte: se "mide" el bloque con los 9 k y se actualizan todos los brazos.
                bandido.actualizar_todos(ctx, self.recompensas[b])
                barrido[b] = True
            else:
                bandido.actualizar(ctx, k, r)
            elegidos[b] = j
        return elegidos, barrido

    def reproducir(self):
        """Construye, para cada política, el brazo elegido en cada bloque y sus métricas."""
        nb = self.flujo.n_bloques
        rng = np.random.default_rng(self.semilla)
        self.elegidos = {}
        self.elegidos["bandido"], self.barrido_bandido = self._politica_bandido()
        self.elegidos["k fijo = 8"] = np.full(nb, self.ks.index(8))
        self.elegidos["k fijo = 16"] = np.full(nb, self.ks.index(16))
        self.elegidos["aleatoria"] = rng.integers(0, len(self.ks), nb)
        self.elegidos["óptimo"] = np.argmax(self.razones, axis=1)  # mejor k de cada bloque
        self.j_optimo = self.elegidos["óptimo"]
        # Recompensa del óptimo en cada bloque y del brazo elegido por cada política.
        filas = np.arange(nb)
        self.r_opt = self.recompensas[filas, self.j_optimo]
        tam = self.flujo.bloque_bytes
        self.metricas = {}
        self.regret_acum = {}
        for nombre in self.POLITICAS:
            j = self.elegidos[nombre]
            # Indexar con dos arreglos: razones[filas[i], j[i]] para cada bloque i.
            razon_b = self.razones[filas, j]
            comprimidos = tam / razon_b                       # bytes que ocupa cada bloque comprimido
            regret_b = self.r_opt - self.recompensas[filas, j]  # arrepentimiento por bloque
            self.regret_acum[nombre] = np.cumsum(regret_b)
            self.metricas[nombre] = {
                "bytes_originales": int(tam * nb),
                "bytes_comprimidos": float(comprimidos.sum()),
                "razon_global": float(tam * nb / comprimidos.sum()),
                "arrepentimiento_acumulado": float(regret_b.sum()),
                "barridos_reinicio": int(self.barrido_bandido.sum()) if nombre == "bandido" else None,
            }

    # ---- resúmenes ----
    def detalle_tramos(self) -> list[dict]:
        """Por tramo: bloques, contextos, k óptimo más frecuente, conteo de k del bandido y
        razón global de cada política dentro del tramo."""
        nombres = np.array(self.flujo.nombres_bloque)
        tam = self.flujo.bloque_bytes
        filas_todas = np.arange(self.flujo.n_bloques)
        out = []
        for t in self.flujo.tramos_usados:
            idx = np.flatnonzero(nombres == t.nombre)  # posiciones de los bloques de este tramo
            nbt = len(idx)
            # np.bincount cuenta cuántas veces aparece cada entero 0..8.
            cuenta_opt = np.bincount(self.j_optimo[idx], minlength=len(self.ks))
            cuenta_band = np.bincount(self.elegidos["bandido"][idx], minlength=len(self.ks))
            # argmax devuelve la primera posición del máximo (en empate, el k menor).
            ctxs, cuentas_ctx = np.unique([self.contextos[i] for i in idx], return_counts=True)
            razon_pol = {}
            for nombre in self.POLITICAS:
                comp = tam / self.razones[idx, self.elegidos[nombre][idx]]
                razon_pol[nombre] = float(tam * nbt / comp.sum())
            out.append({
                "tramo": t.nombre,
                "primer_bloque": int(idx[0]),
                "bloques": nbt,
                "contextos": {str(c): int(n) for c, n in zip(ctxs, cuentas_ctx)},
                "k_optimo_mas_frecuente": self.ks[int(np.argmax(cuenta_opt))],
                "k_bandido_mas_elegido": self.ks[int(np.argmax(cuenta_band))],
                "conteo_k_optimo": {str(k): int(n) for k, n in zip(self.ks, cuenta_opt)},
                "conteo_k_bandido": {str(k): int(n) for k, n in zip(self.ks, cuenta_band)},
                "barridos_reinicio": int(self.barrido_bandido[idx].sum()),
                "razon_global_por_politica": razon_pol,
            })
        return out

    def imprimir(self):
        """Tabla resumen por política y tabla por tramo."""
        f = self.flujo
        print(f"\nFlujo: {f.n_bloques} bloques de {f.bloque_bytes // 1024} KB "
              f"({f.n_bloques * f.bloque_bytes:,} bytes) | gamma={self.gamma} c={self.c} semilla={self.semilla}")
        for a in f.avisos:
            print(f"  AVISO: {a}")
        cab = f"{'política':<14} {'bytes comprimidos':>18} {'razón global':>13} {'arrepentimiento':>16} {'barridos reinicio':>18}"
        print("\n" + cab); print("─" * len(cab))
        for nombre in self.POLITICAS:
            m = self.metricas[nombre]
            barr = str(m["barridos_reinicio"]) if m["barridos_reinicio"] is not None else "—"
            print(f"{nombre:<14} {m['bytes_comprimidos']:>18,.0f} {m['razon_global']:>13.4f} "
                  f"{m['arrepentimiento_acumulado']:>16.3f} {barr:>18}")
        cab2 = (f"\n{'tramo':<18} {'bloques':>7} {'k óptimo (más frec.)':>21} {'k bandido (más elegido)':>24} "
                f"{'razón óptimo':>13} {'razón bandido':>14} {'razón k=8':>10}")
        print(cab2); print("─" * (len(cab2) - 1))
        for d in self.detalle_tramos():
            rp = d["razon_global_por_politica"]
            print(f"{d['tramo']:<18} {d['bloques']:>7} {d['k_optimo_mas_frecuente']:>21} "
                  f"{d['k_bandido_mas_elegido']:>24} {rp['óptimo']:>13.4f} {rp['bandido']:>14.4f} {rp['k fijo = 8']:>10.4f}")

    def a_dict(self) -> dict:
        """Todo el resultado, listo para JSON (sin tiempos, para que sea reproducible)."""
        f = self.flujo
        secuencia = []
        for b in range(f.n_bloques):
            secuencia.append({
                "bloque": b,
                "tramo": f.nombres_bloque[b],
                "contexto": self.contextos[b],
                "k_optimo": self.ks[int(self.j_optimo[b])],
                "k_bandido": self.ks[int(self.elegidos["bandido"][b])],
                "barrido_reinicio": bool(self.barrido_bandido[b]),
                # Razón estimada de este bloque con cada k (en el orden de `ks`).
                "razones": [float(x) for x in self.razones[b]],
            })
        return {
            "parametros": {
                "gamma": self.gamma, "c": self.c, "semilla": self.semilla,
                "bloque_bytes": f.bloque_bytes, "umbral_cambio": UMBRAL_CAMBIO,
                "solo_caidas": self.solo_caidas,
                "ks": self.ks, "bloques_totales": f.n_bloques,
                "tramos": [{"nombre": t.nombre, "tipo": t.tipo, "param": t.param} for t in f.tramos],
            },
            "avisos": f.avisos,
            "resumen_politicas": self.metricas,
            "detalle_tramos": self.detalle_tramos(),
            "secuencia": secuencia,
        }

    def guardar_json(self, ruta: str):
        with open(ruta, "w", encoding="utf-8") as fh:
            json.dump(self.a_dict(), fh, indent=2, ensure_ascii=False)
        print(f"\nReporte guardado en {ruta}")

    def graficar(self, ruta: str):
        # matplotlib se importa aquí adentro (igual que en ReporteCodificacion.graficar) para
        # que el resto funcione aunque no esté instalado; "Agg" dibuja a archivo sin ventanas.
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        f = self.flujo
        nb = f.n_bloques
        x = np.arange(nb)
        # Primer bloque de cada tramo y su largo, para las líneas verticales y las etiquetas.
        detalle = self.detalle_tramos()
        fig, ax = plt.subplots(2, 1, figsize=(13, 10), sharex=True)

        # (a) arrepentimiento acumulado de cada política
        estilos = {"bandido": ("tab:red", 2.2), "k fijo = 8": ("tab:blue", 1.4),
                   "k fijo = 16": ("tab:green", 1.4), "aleatoria": ("tab:gray", 1.4)}
        for nombre, (color, ancho) in estilos.items():
            ax[0].plot(x, self.regret_acum[nombre], label=nombre, color=color, lw=ancho)
        ax[0].set_title("Arrepentimiento acumulado frente al k óptimo de cada bloque", pad=48)
        ax[0].set_ylabel("arrepentimiento (escala de recompensa)")
        ax[0].legend(loc="upper left", bbox_to_anchor=(0.0, 0.93))
        ax[0].grid(alpha=0.3)

        # (b) k elegido por el bandido frente al k óptimo (eje y logarítmico en base 2)
        k_opt = np.array([self.ks[j] for j in self.j_optimo])
        k_ban = np.array([self.ks[j] for j in self.elegidos["bandido"]])
        ax[1].scatter(x, k_opt, s=55, facecolors="none", edgecolors="tab:blue", label="k óptimo del bloque")
        ax[1].scatter(x, k_ban, s=14, color="tab:red", label="k elegido por el bandido")
        # Marcas de reinicio por cambio (barrido) sobre el eje inferior.
        xb = x[self.barrido_bandido]
        ax[1].scatter(xb, np.full(len(xb), self.ks[0] * 0.8), marker="^", s=30, color="black",
                      label="barrido de reinicio", clip_on=False)
        ax[1].set_yscale("log", base=2)
        ax[1].set_yticks(self.ks)
        ax[1].set_yticklabels([str(k) for k in self.ks])
        ax[1].minorticks_off()
        ax[1].set_ylabel("k (bits por símbolo)")
        ax[1].set_xlabel("bloque del flujo")
        ax[1].set_title("k elegido por el bandido frente al k óptimo, por bloque")
        ax[1].legend(loc="center left", bbox_to_anchor=(1.0, 0.5))
        ax[1].grid(alpha=0.3)

        # Líneas verticales en los cambios de tramo (ambos paneles) y nombre del tramo arriba
        # del primer panel, escalonado en 3 alturas para que los nombres no se encimen.
        for i, d in enumerate(detalle):
            ini = d["primer_bloque"] - 0.5
            for a in ax:
                if i > 0:
                    a.axvline(ini, color="black", ls="--", lw=0.8, alpha=0.6)
            centro = d["primer_bloque"] + (d["bloques"] - 1) / 2
            ax[0].annotate(d["tramo"], xy=(centro, 1.0), xycoords=("data", "axes fraction"),
                           xytext=(0, 4 + 13 * (i % 3)), textcoords="offset points",
                           ha="center", va="bottom", fontsize=8,
                           arrowprops=dict(arrowstyle="-", lw=0.4, color="gray"))
        ax[0].set_xlim(-0.5, nb - 0.5)
        m = self.metricas
        fig.suptitle(f"Bandido UCB descontado (gamma={self.gamma}, c={self.c}) | razón global: "
                     f"bandido {m['bandido']['razon_global']:.2f}, k=8 {m['k fijo = 8']['razon_global']:.2f}, "
                     f"óptimo {m['óptimo']['razon_global']:.2f}")
        fig.tight_layout(rect=(0, 0, 1, 0.97))
        fig.savefig(ruta, dpi=130)
        print(f"Gráfica guardada en {ruta}")

    def correr(self, reporte: str | None = None, grafica: str | None = None):
        t0 = time.time()
        print(f"Calculando la matriz de razones ({self.flujo.n_bloques} bloques × {len(self.ks)} valores de k)...")
        self.calcular_matriz()
        self.reproducir()
        self.imprimir()
        if reporte:
            self.guardar_json(reporte)
        if grafica:
            self.graficar(grafica)
        print(f"\nTiempo total: {time.time() - t0:.1f} s")


# ═══════════════════════════ CLI ═══════════════════════════
def main():
    # argparse define los comandos y opciones que acepta el programa desde la terminal.
    ap = argparse.ArgumentParser(description="Bandido UCB descontado para elegir k en un flujo de bloques")
    sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("simular")
    s.add_argument("--bloque-kb", type=int, default=256)
    s.add_argument("--tramo-bloques", type=int, default=30)
    s.add_argument("--gamma", type=float, default=0.98)
    # c = 0.05 (y no 0.5): la recompensa es log2(razón)/8, así que las diferencias entre k vecinos son de
    # centésimas; con c = 0.5 el bono de exploración las tapa y el bandido recorre los k en ciclo.
    s.add_argument("--c", type=float, default=0.05)
    s.add_argument("--semilla", type=int, default=0)
    s.add_argument("--tramos", help="nombres de tramos separados por coma (por defecto, todos), "
                                    "ej. estructurado_256")
    s.add_argument("--solo-caidas", action="store_true",
                   help="reinicio solo cuando la recompensa cae (regla anterior); por defecto, en ambas direcciones")
    s.add_argument("--reporte"); s.add_argument("--grafica")
    x = ap.parse_args()
    tramos = TRAMOS_DEFECTO
    if x.tramos:
        # Se conservan solo los tramos pedidos, en el orden en que se pidieron.
        por_nombre = {t.nombre: t for t in TRAMOS_DEFECTO}
        tramos = [por_nombre[n.strip()] for n in x.tramos.split(",")]
    flujo = FlujoBloques(tramos, x.bloque_kb * 1024, x.tramo_bloques, x.semilla)
    SimuladorFlujo(flujo, x.gamma, x.c, x.semilla, solo_caidas=x.solo_caidas).correr(x.reporte, x.grafica)


# Solo se ejecuta si el archivo se corre directamente, no cuando otro lo importa.
if __name__ == "__main__":
    main()

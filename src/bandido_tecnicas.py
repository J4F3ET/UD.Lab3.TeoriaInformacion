"""bandido_tecnicas.py — La IA del laboratorio eligiendo la TÉCNICA de compresión (no k) bloque
a bloque, y premiando también la velocidad.

En tic_bandido.py el bandido elige k para el códec TIC y su recompensa es solo la razón de
compresión. Aquí los brazos son técnicas actuales (ninguna, zlib, zstd, bz2, lzma) y hay dos
recompensas posibles:

  · solo razón (como hoy):   r = min(1, log2(razón) / 8)
  · tiempo ganado en un enlace de v bit/s (la misma del bandido por latencia de lab-free5gc):
        r = ahorro − t_cpu · v / (8 · bytes)      acotada a [−1, 1]
    ahorro = 1 − 1/razón es la fracción de tiempo de transmisión que se ahorra; t_cpu·v/(8·bytes)
    es el tiempo de compresión expresado en la misma unidad. Si comprimir tarda más de lo que se
    ahorra transmitiendo, r es negativa y el bandido aprende a no comprimir (brazo "ninguna", r = 0).

Reutiliza de tic_bandido.py el bandido (BandidoUCBDescontado: UCB con descuento y un estado por
contexto), el flujo de bloques (FlujoBloques, los mismos tramos de archivos reales y sintéticos) y
el contexto de cada bloque (la "estructura" que mide CodecTIC.estimar con k = 8).

Uso:
  python bandido_tecnicas.py                    (velocidades: solo razón, 10 Mbps, 100 Mbps, 1 Gbps)
  python bandido_tecnicas.py --bloque-kb 128 --tramo-bloques 20
"""
from __future__ import annotations

import argparse, json, sys, time
from pathlib import Path

import numpy as np

from comparar_tecnicas import tecnicas
from tic_bandido import BandidoUCBDescontado, FlujoBloques, TRAMOS_DEFECTO, recompensa
from tic_codec import CodecTIC

if sys.platform == "win32":
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8")

# Brazos: "ninguna" primero (en un empate el bandido elige el brazo de índice menor).
BRAZOS = ["ninguna", "zlib-6", "zstd-3", "zstd-19", "bz2-9", "lzma-6"]
VELOCIDADES = [None, 10e6, 100e6, 1e9]  # None = recompensa solo por razón


def nombre_vel(v: float | None) -> str:
    if v is None:
        return "solo razón"
    return f"{v / 1e9:g} Gbps" if v >= 1e9 else f"{v / 1e6:g} Mbps"


def recompensa_tiempo(razon: np.ndarray, t_cpu: np.ndarray, bytes_bloque: int, v: float) -> np.ndarray:
    """Tiempo neto ganado, en fracción del tiempo de transmitir el bloque sin comprimir."""
    ahorro = 1 - 1 / razon
    return np.clip(ahorro - t_cpu * v / (8 * bytes_bloque), -1.0, 1.0)


class SimuladorTecnicas:
    """Mide una vez la razón y el tiempo de cada técnica en cada bloque, y reproduce las
    políticas (bandido, técnica fija, aleatoria, óptimo) para cada recompensa."""

    def __init__(self, flujo: FlujoBloques, gamma: float = 0.98, c: float = 0.05, semilla: int = 0):
        self.flujo, self.gamma, self.c, self.semilla = flujo, gamma, c, semilla
        por_nombre = {t.nombre: t for t in tecnicas()}
        self.brazos = [b for b in BRAZOS if b == "ninguna" or b in por_nombre]
        self.funcs = [None if b == "ninguna" else por_nombre[b].comprimir for b in self.brazos]

    def medir(self):
        nb, na = self.flujo.n_bloques, len(self.brazos)
        self.razon = np.ones((nb, na))
        self.t_cpu = np.zeros((nb, na))
        self.contextos = []
        t0 = time.time()
        for b in range(nb):
            datos = self.flujo.bloque(b).tobytes()
            self.contextos.append(CodecTIC.estimar(np.frombuffer(datos, np.uint8), 8)[0].estructura)
            for j, f in enumerate(self.funcs):
                if f is None:
                    continue
                t = time.perf_counter(); out = f(datos); self.t_cpu[b, j] = time.perf_counter() - t
                self.razon[b, j] = len(datos) / len(out)
            if (b + 1) % 20 == 0 or b + 1 == nb:
                print(f"  midiendo: {b + 1}/{nb} bloques ({time.time() - t0:.0f} s)", flush=True)

    def recompensas(self, v: float | None) -> np.ndarray:
        if v is None:
            return recompensa(self.razon)
        r = recompensa_tiempo(self.razon, self.t_cpu, self.flujo.bloque_bytes, v)
        r[:, 0] = 0.0  # "ninguna": ni ahorra ni gasta
        return r

    def _bandido(self, R: np.ndarray) -> np.ndarray:
        """Bandido bloque a bloque: solo ve la recompensa del brazo que eligió."""
        bandido = BandidoUCBDescontado(list(range(len(self.brazos))), self.gamma, self.c)
        elegidos = np.zeros(len(R), dtype=int)
        for b in range(len(R)):
            j = bandido.elegir(self.contextos[b])
            bandido.actualizar(self.contextos[b], j, float(R[b, j]))
            elegidos[b] = j
        return elegidos

    def reproducir(self, v: float | None) -> dict:
        R = self.recompensas(v)
        nb, tam = self.flujo.n_bloques, self.flujo.bloque_bytes
        filas = np.arange(nb)
        rng = np.random.default_rng(self.semilla)
        politicas = {"bandido": self._bandido(R), "óptimo": np.argmax(R, axis=1),
                     "aleatoria": rng.integers(0, len(self.brazos), nb)}
        for j, b in enumerate(self.brazos):
            politicas[f"siempre {b}"] = np.full(nb, j)
        r_opt = R[filas, politicas["óptimo"]]
        salida = {}
        for nombre, j in politicas.items():
            comp = tam / self.razon[filas, j]
            cpu = self.t_cpu[filas, j]
            m = {"razon_global": round(float(tam * nb / comp.sum()), 4),
                 "cpu_s": round(float(cpu.sum()), 3),
                 "arrepentimiento": round(float((r_opt - R[filas, j]).sum()), 3),
                 "elegidos_pct": {b: round(100 * float((j == k).mean()), 1) for k, b in enumerate(self.brazos)}}
            if v is not None:
                # Tiempo total de mandar todo el flujo: comprimir + transmitir lo comprimido.
                m["tiempo_total_s"] = round(float((cpu + comp * 8 / v).sum()), 3)
            salida[nombre] = m
        return salida

    def por_tramo(self, elegidos: np.ndarray) -> dict:
        """Qué eligió el bandido en cada tramo (la segunda mitad, ya terminada la exploración)."""
        out = {}
        nombres = np.array(self.flujo.nombres_bloque)
        for t in dict.fromkeys(self.flujo.nombres_bloque):
            idx = np.where(nombres == t)[0]
            idx = idx[len(idx) // 2:]
            cuenta = np.bincount(elegidos[idx], minlength=len(self.brazos))
            out[t] = self.brazos[int(np.argmax(cuenta))]
        return out


def correr(bloque_kb: int, tramo_bloques: int, salida: Path) -> dict:
    flujo = FlujoBloques(TRAMOS_DEFECTO, bloque_bytes=bloque_kb * 1024, tramo_bloques=tramo_bloques)
    for a in flujo.avisos:
        print("  aviso:", a)
    sim = SimuladorTecnicas(flujo)
    print(f"{flujo.n_bloques} bloques de {bloque_kb} KB, brazos: {', '.join(sim.brazos)}")
    sim.medir()
    inf = {"bloque_bytes": flujo.bloque_bytes, "n_bloques": flujo.n_bloques, "brazos": sim.brazos,
           "nombres_bloque": flujo.nombres_bloque,
           "tramos": [t.nombre for t in flujo.tramos_usados], "avisos": flujo.avisos,
           "razon_media_por_brazo": {b: round(float(sim.razon[:, j].mean()), 4) for j, b in enumerate(sim.brazos)},
           "mb_s_por_brazo": {b: (round(float(flujo.bloque_bytes * flujo.n_bloques / 2**20 / sim.t_cpu[:, j].sum()), 2)
                                  if sim.t_cpu[:, j].sum() else None) for j, b in enumerate(sim.brazos)},
           "corridas": {}}
    for v in VELOCIDADES:
        res = sim.reproducir(v)
        el = sim._bandido(sim.recompensas(v))
        inf["corridas"][nombre_vel(v)] = {"velocidad_bps": v, "politicas": res, "bandido_por_tramo": sim.por_tramo(el),
                                          "bandido_secuencia": [sim.brazos[j] for j in el]}
        b = res["bandido"]
        extra = f", tiempo total {b['tiempo_total_s']} s" if v else ""
        print(f"\n[{nombre_vel(v)}] bandido: razón {b['razon_global']}, CPU {b['cpu_s']} s{extra}; "
              f"elige {b['elegidos_pct']}")
        print("   por tramo:", sim.por_tramo(el))
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "bandido_tecnicas.json").write_text(json.dumps(inf, indent=1, ensure_ascii=False), encoding="utf-8")
    (salida / "bandido_tecnicas.md").write_text(markdown(inf), encoding="utf-8")
    graficar(inf, salida / "bandido_tecnicas.png")
    print(f"\nGuardado en {salida}")
    return inf


def markdown(inf: dict) -> str:
    md = ["# El bandido elige la técnica de compresión\n",
          f"Generado por `src/bandido_tecnicas.py`: {inf['n_bloques']} bloques de {inf['bloque_bytes'] // 1024} KB "
          f"de los tramos {', '.join(inf['tramos'])}. Brazos: {', '.join(inf['brazos'])}.\n\n"
          "| técnica | razón media por bloque | MB/s al comprimir |\n|---|---:|---:|\n"]
    for b in inf["brazos"]:
        mbs = inf["mb_s_por_brazo"][b]
        md.append(f"| {b} | {inf['razon_media_por_brazo'][b]:.3f} | {mbs if mbs else '—'} |\n")
    for nombre, c in inf["corridas"].items():
        con_t = c["velocidad_bps"] is not None
        md.append(f"\n## Recompensa: {nombre}\n\n| política | razón global | CPU s | "
                  + ("tiempo total s | " if con_t else "") + "arrepentimiento |\n|---|---:|---:|"
                  + ("---:|" if con_t else "") + "---:|\n")
        for p, m in sorted(c["politicas"].items(), key=lambda kv: kv[1]["arrepentimiento"]):
            md.append(f"| {p} | {m['razon_global']:.3f} | {m['cpu_s']:.2f} | "
                      + (f"{m['tiempo_total_s']:.2f} | " if con_t else "") + f"{m['arrepentimiento']:.2f} |\n")
        md.append("\nQué elige el bandido en cada tramo (segunda mitad del tramo): "
                  + ", ".join(f"{t} → **{b}**" for t, b in c["bandido_por_tramo"].items()) + ".\n")
    return "".join(md)


def graficar(inf: dict, ruta: Path):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return
    corridas = list(inf["corridas"].items())
    fig, axs = plt.subplots(len(corridas), 1, figsize=(13, 2.1 * len(corridas)), sharex=True)
    brazos = inf["brazos"]
    for ax, (nombre, c) in zip(axs, corridas):
        seq = [brazos.index(b) for b in c["bandido_secuencia"]]
        ax.scatter(range(len(seq)), seq, s=6, c=seq, cmap="tab10", vmin=0, vmax=9)
        ax.set_yticks(range(len(brazos))); ax.set_yticklabels(brazos, fontsize=8)
        ax.set_title(f"Qué elige el bandido bloque a bloque — recompensa: {nombre}", fontsize=10, loc="left")
        ax.grid(alpha=.3)
        # Línea vertical donde empieza cada tramo; el nombre del tramo, en la gráfica de arriba.
        anterior = None
        for b, t in enumerate(inf["nombres_bloque"]):
            if t != anterior:
                ax.axvline(b - .5, color="k", lw=.6, alpha=.5)
                if ax is axs[0]:
                    ax.text(b, len(brazos) - .4, t, fontsize=7, va="bottom")
                anterior = t
    axs[-1].set_xlabel("bloque")
    fig.tight_layout(); fig.savefig(ruta, dpi=110); plt.close(fig)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--bloque-kb", type=int, default=256)
    p.add_argument("--tramo-bloques", type=int, default=30)
    p.add_argument("--salida", type=Path, default=Path(__file__).resolve().parent.parent / "examples" / "bandido_tecnicas")
    p.add_argument("--datos", type=Path, default=None, help="carpeta con los archivos de prueba (por defecto data/)")
    a = p.parse_args()
    if a.datos:
        import tic_bandido
        tic_bandido.DIR_DATOS = a.datos  # FlujoBloques lee los archivos de esta carpeta
    correr(a.bloque_kb, a.tramo_bloques, a.salida)


if __name__ == "__main__":
    main()

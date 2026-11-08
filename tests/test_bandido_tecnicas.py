"""Pruebas de src/bandido_tecnicas.py: la recompensa por tiempo y que el bandido aprenda a no
comprimir cuando el enlace es tan rápido que comprimir cuesta más de lo que ahorra."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import bandido_tecnicas as bt  # noqa: E402


def test_recompensa_tiempo():
    # Razón 2 (ahorro 0,5) y CPU gratis: se gana la mitad del tiempo.
    assert bt.recompensa_tiempo(np.array([2.0]), np.array([0.0]), 1000, 1e6)[0] == pytest.approx(0.5)
    # 1 ms de CPU para 1000 bytes a 1 Mbps (transmitirlos tarda 8 ms): 0,5 − 0,125.
    assert bt.recompensa_tiempo(np.array([2.0]), np.array([1e-3]), 1000, 1e6)[0] == pytest.approx(0.375)
    # A 1 Gbps ese mismo milisegundo pesa 125 veces el tiempo de transmitir: tope −1.
    assert bt.recompensa_tiempo(np.array([2.0]), np.array([1e-3]), 1000, 1e9)[0] == -1.0


class _FlujoFalso:
    """Bloques de bytes aleatorios (incompresibles), sin leer archivos."""
    def __init__(self, n=40, tam=32 * 1024):
        rng = np.random.default_rng(0)
        self.bloques = [rng.integers(0, 256, tam, dtype=np.uint8) for _ in range(n)]
        self.bloque_bytes, self.n_bloques = tam, n
        self.nombres_bloque = ["aleatorio"] * n

    def bloque(self, b):
        return self.bloques[b]


def test_con_enlace_rapido_aprende_a_no_comprimir():
    sim = bt.SimuladorTecnicas(_FlujoFalso())
    sim.medir()
    res = sim.reproducir(1e9)
    # Datos aleatorios a 1 Gbps: comprimir solo gasta tiempo; el óptimo es siempre "ninguna".
    assert res["óptimo"]["elegidos_pct"]["ninguna"] == 100.0
    assert res["bandido"]["elegidos_pct"]["ninguna"] > 50

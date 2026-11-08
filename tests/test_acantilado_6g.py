"""Pruebas de src/acantilado_6g.py: el digital es todo o nada y el analógico se degrada de a poco."""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import acantilado_6g as A  # noqa: E402


def _imagen():
    """Imagen sintética suave (gradiente + ondas), sin leer archivos."""
    y, x = np.mgrid[0:A.LADO, 0:A.LADO]
    z = 128 + 60 * np.sin(x / 23) * np.cos(y / 31) + 0.1 * (x - y)
    return np.clip(z, 0, 255).astype(np.uint8)


def test_dct_ortonormal():
    d = A.matriz_dct(16)
    assert np.allclose(d @ d.T, np.eye(16))


def test_digital_es_todo_o_nada():
    img = _imagen()
    dg = A.Digital(img, 12)
    assert dg.calidad is not None and dg.bytes * 8 <= dg.presupuesto
    assert np.array_equal(dg.recibir(30), dg.recibir(12))          # meseta: no mejora con más señal
    assert len(np.unique(dg.recibir(11))) == 1                      # por debajo del diseño: gris, nada


def test_analogico_mejora_de_a_poco_y_nunca_se_cae():
    img = _imagen()
    an = A.Analogico(img)
    p = [A.psnr(img, an.recibir(s, np.random.default_rng(0)), 255) for s in (0, 10, 20, 30)]
    assert p == sorted(p)                                           # más señal, más calidad
    assert p[0] > A.psnr(img, np.full_like(img, round(img.mean())), 255) + 5   # a 0 dB ya llega algo
    # potencia media por uso del canal = POTENCIA
    tx = an.g[:, None] * an.trozos[an.enviados]
    assert abs(float((tx ** 2).mean()) - A.POTENCIA) < 1e-6

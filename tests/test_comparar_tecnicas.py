"""Pruebas de src/comparar_tecnicas.py: cada técnica devuelve exactamente los bytes originales,
la información mutua rápida coincide con la de tic_codec.py y la prueba de corrupción funciona."""
import io
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import comparar_tecnicas as ct  # noqa: E402
from tic_codec import Informacion  # noqa: E402


@pytest.fixture(scope="module")
def datos():
    # Texto con repeticiones + algo de ruido: comprime, pero no trivialmente.
    rng = np.random.default_rng(1)
    palabras = [b"entropia ", b"codigo ", b"canal ", b"bit ", b"huffman ", b"5G "]
    return b"".join(palabras[i] for i in rng.integers(0, len(palabras), 6000)) + rng.bytes(2000)


@pytest.fixture(scope="module")
def bmp():
    Image = pytest.importorskip("PIL.Image")
    # Degradado horizontal de 64 × 48 píxeles RGB.
    x = np.tile(np.arange(64, dtype=np.uint8), (48, 1)).reshape(48, 64, 1).repeat(3, 2)
    out = io.BytesIO()
    Image.fromarray(x, "RGB").save(out, format="BMP")
    return out.getvalue()


@pytest.fixture(scope="module")
def wav():
    # Con la biblioteca estándar (wave): la prueba no necesita soundfile; FLAC solo se prueba si está.
    import wave
    t = np.arange(8000) / 8000
    s = (8000 * np.sin(2 * np.pi * 440 * t)).astype("<i2")
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(8000)
        w.writeframes(s.tobytes())
    return out.getvalue()


def test_todas_las_tecnicas_son_exactas(datos, bmp, wav):
    for t in ct.tecnicas():
        entrada = bmp if t.solo_para == ("imagen_bmp",) else wav if t.solo_para == ("audio_wav",) else datos
        assert t.descomprimir(t.comprimir(entrada)) == entrada, t.nombre


def test_info_mutua_rapida_igual_a_la_del_codec():
    rng = np.random.default_rng(2)
    x = rng.integers(0, 256, 20000)
    y = np.where(rng.random(20000) < 0.1, ct.BORRADO, x)  # 10 % de bytes borrados
    assert ct.info_mutua_bytes(x, y) == pytest.approx(Informacion.informacion_mutua(x, y), abs=1e-9)
    assert ct.info_mutua_bytes(x, x) == pytest.approx(ct.entropia_bytes(x.astype(np.uint8)), abs=1e-9)


def test_medir_detecta_corrupcion(datos):
    zlib6 = next(t for t in ct.tecnicas() if t.nombre == "zlib-6")
    r = ct.medir("texto", datos, zlib6, ct.entropia_bytes(np.frombuffer(datos, np.uint8)))
    assert r.exacto and r.razon > 1
    # Con un byte dañado no se entrega todo, pero la versión tolerante sí recupera el comienzo.
    assert 0 < r.info_entregada_pct < 100


def test_alineado_marca_lo_que_falta_como_borrado():
    x = np.frombuffer(b"abcdef", np.uint8)
    y = ct.recuperado_alineado(x, b"abc")
    assert list(y[3:]) == [ct.BORRADO] * 3
    assert list(ct.recuperado_alineado(x, None)) == [ct.BORRADO] * 6

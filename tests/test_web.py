"""Pruebas de humo de la API web: codificar → descargar .tic → decodificar
debe devolver exactamente los bytes originales."""
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="module")
def cliente(tmp_path_factory):
    import os
    os.environ["TIC_DATOS"] = str(tmp_path_factory.mktemp("datos"))
    from web.app import app
    return TestClient(app)


@pytest.fixture(scope="module")
def datos():
    # Fuente con estructura (bytes repetidos por bloques) para que sí comprima.
    rng = np.random.default_rng(0)
    return np.repeat(rng.integers(0, 16, 4096, dtype=np.uint8), 8).tobytes()


def test_salud_e_info(cliente):
    assert cliente.get("/healthz").json() == {"ok": True}
    assert 8 in cliente.get("/api/info").json()["ks_base"]
    assert "Códec TIC" in cliente.get("/").text


def test_ida_y_vuelta(cliente, datos):
    r = cliente.post("/api/codificar", files={"archivo": ("x.bin", datos)},
                     data={"k": "16", "grafica": "false"})
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert cuerpo["reporte"]["despues"]["verificacion_sha256"] is True
    assert cuerpo["reporte"]["despues"]["razon_compresion"] > 1

    tic = cliente.get(cuerpo["descargas"]["tic"]).content
    r = cliente.post("/api/decodificar", files={"archivo": ("x.tic", tic)})
    assert r.status_code == 200
    assert r.headers["X-TIC-SHA256-OK"] == "1"
    assert r.content == datos


def test_con_perdida_es_json_valido(cliente, datos):
    r = cliente.post("/api/codificar", files={"archivo": ("x.bin", datos)},
                     data={"k": "8", "perdida": "3", "grafica": "false"})
    assert r.status_code == 200, r.text
    assert "MSE_por_byte" in r.json()["reporte"]["despues"]


def test_barrido(cliente, datos):
    r = cliente.post("/api/barrido", files={"archivo": ("x.bin", datos)}, data={"ks": "8,16,64"})
    assert r.status_code == 200, r.text
    assert [f["k_bits"] for f in r.json()["resultados"]] == [8, 16, 64]


@pytest.mark.parametrize("k", ["7", "0", "99999"])
def test_k_invalido(cliente, datos, k):
    r = cliente.post("/api/codificar", files={"archivo": ("x.bin", datos)}, data={"k": k})
    assert r.status_code == 422


def test_rechaza_no_tic(cliente):
    r = cliente.post("/api/decodificar", files={"archivo": ("x.tic", b"no soy un tic")})
    assert r.status_code == 422


def test_descarga_no_permite_rutas(cliente):
    assert cliente.get("/api/trabajos/abc/entrada.bin").status_code == 404

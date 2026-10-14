"""Pruebas de humo de la interfaz gráfica (src/app.py) antes de desplegarla:
subir → barrido → codificar → decodificar debe devolver los bytes originales."""
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import app as gui  # noqa: E402


@pytest.fixture()
def cliente():
    return gui.app.test_client()


@pytest.fixture()
def fuente(cliente):
    # Bytes repetidos por bloques: fuente con estructura, para que sí comprima.
    rng = np.random.default_rng(0)
    datos = np.repeat(rng.integers(0, 16, 4096, dtype=np.uint8), 8).tobytes()
    r = cliente.post("/api/subir", data={"archivo": (__import__("io").BytesIO(datos), "x.bin")},
                     content_type="multipart/form-data")
    assert r.status_code == 200, r.get_data(as_text=True)
    id_ = r.get_json()["id"]
    yield id_, datos
    shutil.rmtree(gui.carpeta(id_), ignore_errors=True)


def test_pagina_principal(cliente):
    r = cliente.get("/")
    assert r.status_code == 200
    assert b"<html" in r.data.lower()


def test_barrido(cliente, fuente):
    id_, _ = fuente
    r = cliente.post("/api/barrido", json={"id": id_, "ks": [8, 16, 64]})
    assert r.status_code == 200, r.get_data(as_text=True)


def test_ida_y_vuelta(cliente, fuente):
    id_, datos = fuente
    r = cliente.post("/api/codificar", json={"id": id_, "k": 16})
    assert r.status_code == 200, r.get_data(as_text=True)
    tic = r.get_json()["tic"]["nombre"]

    r = cliente.post("/api/decodificar", json={"id": id_, "tic": tic})
    assert r.status_code == 200, r.get_data(as_text=True)
    cuerpo = r.get_json()
    assert cuerpo["verificacion_sha256"] is True
    assert cuerpo["identico_al_original"] is True
    assert cliente.get(cuerpo["reconstruido"]["url"]).data == datos

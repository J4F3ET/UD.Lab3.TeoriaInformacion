"""Pruebas de humo de la interfaz gráfica (src/app.py) antes de desplegarla:
subir → barrido → codificar → decodificar debe devolver los bytes originales."""
import shutil
import sys
from pathlib import Path

import numpy as np
import pytest
from flask.testing import FlaskClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
import app as gui  # noqa: E402


class ClienteQueCierra(FlaskClient):
    """Cierra cada respuesta al devolverla, como hace el servidor WSGI real (gunicorn) al
    terminar de enviarla. Sin esto, las respuestas que la prueba no cierra dejarían el
    contador de peticiones en curso sin restar."""
    def open(self, *args, **kwargs):
        r = super().open(*args, **kwargs)
        r.get_data()  # sirve el cuerpo entero para que .data siga disponible tras cerrar
        r.close()
        return r


@pytest.fixture()
def cliente():
    return ClienteQueCierra(gui.app, gui.app.response_class, use_cookies=True)


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


def test_salud_sin_peticiones_en_curso(cliente):
    r = cliente.get("/salud")
    assert r.status_code == 200
    assert r.get_json() == {"activas": 0}


def test_contador_vuelve_a_cero_tras_peticiones(cliente):
    assert cliente.get("/").status_code == 200
    assert cliente.get("/no-existe").status_code == 404
    assert cliente.get("/salud").get_json() == {"activas": 0}


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


def test_descarga_cuenta_mientras_se_envia_y_resta_al_cerrar(cliente, fuente):
    # La descarga sigue "en curso" hasta que la respuesta se cierra del todo, no al terminar el teardown.
    # Se usa el cliente de Flask sin cierre automático para mantener la respuesta abierta.
    id_, _ = fuente
    tic = cliente.post("/api/codificar", json={"id": id_, "k": 16}).get_json()["tic"]["nombre"]
    esperado = (gui.carpeta(id_) / tic).read_bytes()
    abierto = gui.app.test_client()
    with abierto.get(f"/api/descargar/{id_}/{tic}") as r:
        assert r.status_code == 200
        # Respuesta abierta: el contador debe valer 1.
        assert cliente.get("/salud").get_json() == {"activas": 1}
        assert r.data == esperado
    # Respuesta cerrada: el contador vuelve a 0.
    assert cliente.get("/salud").get_json() == {"activas": 0}

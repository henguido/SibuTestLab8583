"""Prueba vertical: HTTP -> nucleo real -> TCP real -> 0110 -> SQLite -> HTML.

Sin ningun doble del nucleo. Usa el cliente ASGI asincrono en lugar del
`TestClient` sincrono porque el host simulado corre en el mismo event loop de la
prueba: con un cliente sincrono, ese loop quedaria bloqueado y el host no podria
atender la conexion.
"""

from __future__ import annotations

import sqlite3

import httpx2
import pytest

from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, PAN_DEMO, inicializar
from sibutestlab8583.composicion import Composicion, Configuracion
from sibutestlab8583.domain.modelos import EstadoEjecucion
from sibutestlab8583.web.app import crear_app


@pytest.fixture
async def entorno(tmp_path):
    """Base temporal real, host simulado en puerto efimero y app FastAPI."""
    ruta = await inicializar(tmp_path / "vertical.db")
    composicion = Composicion(
        Configuracion(ruta_base_datos=ruta, host_destino="127.0.0.1", tiempo_limite=3.0)
    )
    return ruta, composicion


async def _ejecutar(composicion, ruta, *, codigo="00", monto="150.00", puerto=None):
    """Levanta el host, hace el POST HTTP y devuelve (html, estado_http)."""
    host = composicion.host_simulado(codigo_respuesta=codigo)
    async with host:
        app = crear_app(composicion)
        transporte = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(transport=transporte, base_url="http://prueba") as cliente:
            respuesta = await cliente.post(
                "/compra",
                data={
                    "card_id": CARD_ID_DEMO,
                    "monto": monto,
                    "host": host.host,
                    "puerto": str(puerto if puerto is not None else host.puerto),
                },
            )
    return respuesta.text, respuesta.status_code, host


async def test_post_http_recorre_el_nucleo_real_y_persiste(entorno):
    ruta, composicion = entorno
    html, estado, host = await _ejecutar(composicion, ruta, codigo="00")

    # 1. La peticion HTTP se atendio.
    assert estado == 200

    # 2. El host simulado recibio de verdad un 0100 por TCP.
    assert host.solicitudes_recibidas == 1

    # 3. El HTML refleja la aprobacion.
    assert "Transaccion aprobada" in html
    assert "Isoscopio · respuesta 0110" in html

    # 4. La ejecucion quedo persistida en SQLite.
    with sqlite3.connect(ruta) as conexion:
        conexion.row_factory = sqlite3.Row
        filas = conexion.execute("SELECT * FROM ejecuciones").fetchall()
    assert len(filas) == 1
    assert filas[0]["estado"] == EstadoEjecucion.APROBADA.value
    assert filas[0]["codigo_respuesta"] == "00"
    assert filas[0]["card_id"] == CARD_ID_DEMO
    assert filas[0]["latencia_ms"] is not None


async def test_el_html_devuelto_nunca_contiene_el_pan_completo(entorno):
    ruta, composicion = entorno
    html, _, _ = await _ejecutar(composicion, ruta, codigo="00")

    assert PAN_DEMO not in html, "el navegador recibio el PAN completo"
    assert "************6666" in html, "el PAN enmascarado debe verse en el isoscopio"

    with sqlite3.connect(ruta) as conexion:
        for fila in conexion.execute("SELECT * FROM ejecuciones").fetchall():
            for valor in fila:
                assert PAN_DEMO not in str(valor)


async def test_un_rechazo_real_llega_al_html_como_rechazo(entorno):
    ruta, composicion = entorno
    html, estado, _ = await _ejecutar(composicion, ruta, codigo="05")
    assert estado == 200
    assert "Transaccion rechazada" in html
    assert "Transaccion aprobada" not in html


async def test_el_historial_muestra_lo_que_el_recorrido_persistio(entorno):
    ruta, composicion = entorno
    await _ejecutar(composicion, ruta, codigo="00")

    app = crear_app(composicion)
    transporte = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transporte, base_url="http://prueba") as cliente:
        respuesta = await cliente.get("/historial")

    assert respuesta.status_code == 200
    assert CARD_ID_DEMO in respuesta.text
    assert "aprobada" in respuesta.text
    assert PAN_DEMO not in respuesta.text


async def test_un_destino_sin_host_no_rompe_la_interfaz(entorno):
    """Puerto donde no hay nadie: la web informa, no lanza un 500."""
    ruta, composicion = entorno
    app = crear_app(composicion)
    transporte = httpx2.ASGITransport(app=app)
    async with httpx2.AsyncClient(transport=transporte, base_url="http://prueba") as cliente:
        respuesta = await cliente.post(
            "/compra",
            data={
                "card_id": CARD_ID_DEMO,
                "monto": "10.00",
                "host": "host-que-no-existe.sibutestlab.invalid",
                "puerto": "9",
            },
        )
    assert respuesta.status_code == 200
    assert "No fue posible establecer conexion con el destino" in respuesta.text
    assert "Traceback" not in respuesta.text

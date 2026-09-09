"""Filtros y paginación del historial: `GET /historial`.

Se prueba contra SQLite real, insertando filas directamente -mismo criterio
que `test_detalle_historial.py`- para poder tener mas de 20 ejecuciones y
combinaciones de filtro sin pasar por el recorrido de compra completo.
"""

from __future__ import annotations

import sqlite3

import httpx2

from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO
from sibutestlab8583.composicion import Composicion, Configuracion
from sibutestlab8583.web.app import crear_app


def _app(base):
    return crear_app(Composicion(Configuracion(ruta_base_datos=base)))


async def _obtener(base, ruta):
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app(base)), base_url="http://prueba"
    ) as cliente:
        return await cliente.get(ruta)


def _insertar(base, **campos) -> int:
    fila = {
        "creada_en": "2026-08-23T05:00:00+00:00",
        "card_id": CARD_ID_DEMO,
        "mti_solicitud": "0100",
        "mti_respuesta": "0110",
        "monto": "150.00",
        "moneda": "188",
        "stan": "000501",
        "destino_host": "127.0.0.1",
        "destino_puerto": 8583,
        "estado": "aprobada",
        "codigo_respuesta": "00",
        "solicitud_enmascarada": None,
        "respuesta_enmascarada": None,
        "solicitud_json": None,
        "respuesta_json": None,
        "latencia_ms": 5,
    }
    fila.update(campos)
    columnas = ", ".join(fila)
    marcas = ", ".join("?" * len(fila))
    with sqlite3.connect(base) as conexion:
        cursor = conexion.execute(
            f"INSERT INTO ejecuciones ({columnas}) VALUES ({marcas})", tuple(fila.values())
        )
        conexion.commit()
        return cursor.lastrowid


def _insertar_lote(base, cantidad: int, **comunes) -> None:
    for indice in range(cantidad):
        _insertar(
            base,
            creada_en=f"2026-08-{(indice % 27) + 1:02d}T05:00:00+00:00",
            stan=f"{indice:06d}",
            **comunes,
        )


# ----------------------------------------------------------- paginacion -----


async def test_hay_paginacion_mas_alla_de_las_ultimas_20(base):
    _insertar_lote(base, 25)
    respuesta = await _obtener(base, "/historial")
    assert respuesta.status_code == 200
    assert "página 1 de 2" in respuesta.text.lower()
    assert "Siguiente" in respuesta.text
    assert "Anterior" not in respuesta.text


async def test_la_segunda_pagina_muestra_los_restantes(base):
    _insertar_lote(base, 25)
    respuesta = await _obtener(base, "/historial?pagina=2")
    assert respuesta.status_code == 200
    assert "página 2 de 2" in respuesta.text.lower()
    assert "Anterior" in respuesta.text
    assert "Siguiente" not in respuesta.text


# -------------------------------------------------------------- filtros -----


async def test_filtro_por_estado(base):
    _insertar(base, stan="000001", estado="aprobada")
    _insertar(base, stan="000002", estado="rechazada")
    respuesta = await _obtener(base, "/historial?estado=rechazada")
    assert "000002" in respuesta.text
    assert "000001" not in respuesta.text


async def test_filtro_por_stan(base):
    _insertar(base, stan="123456")
    _insertar(base, stan="999999")
    respuesta = await _obtener(base, "/historial?stan=1234")
    assert "123456" in respuesta.text
    assert "999999" not in respuesta.text


async def test_filtro_por_evaluacion_sin_expectativas(base):
    _insertar(base, stan="000001", evaluacion_estado=None)
    _insertar(base, stan="000002", evaluacion_estado="pass")
    respuesta = await _obtener(base, "/historial?evaluacion=sin_expectativas")
    assert "000001" in respuesta.text
    assert "000002" not in respuesta.text


async def test_filtro_por_destino(base):
    _insertar(base, stan="000001", destino_host="10.0.0.1", destino_puerto=9000)
    _insertar(base, stan="000002", destino_host="10.0.0.2", destino_puerto=9000)
    respuesta = await _obtener(base, "/historial?destino=10.0.0.1")
    assert "000001" in respuesta.text
    assert "000002" not in respuesta.text


async def test_filtros_se_mantienen_en_la_paginacion(base):
    _insertar_lote(base, 25, estado="rechazada")
    _insertar(base, stan="999000", estado="aprobada")
    respuesta = await _obtener(base, "/historial?estado=rechazada&pagina=2")
    assert respuesta.status_code == 200
    assert "estado=rechazada" in respuesta.text
    assert "999000" not in respuesta.text


async def test_historial_vacio_distinto_de_busqueda_sin_resultados(base):
    sin_filtros = await _obtener(base, "/historial")
    assert "Todavía no hay ejecuciones registradas" in sin_filtros.text

    _insertar(base, stan="000001", estado="aprobada")
    con_filtro_sin_resultados = await _obtener(base, "/historial?estado=timeout")
    assert "no encontró ejecuciones con estos filtros" in con_filtro_sin_resultados.text
    assert "Todavía no hay ejecuciones registradas" not in con_filtro_sin_resultados.text


async def test_filtro_de_fecha_invalida_se_rechaza_con_error_explicado(base):
    respuesta = await _obtener(base, "/historial?desde=no-es-una-fecha")
    assert respuesta.status_code == 400
    assert "fecha" in respuesta.text.lower()


async def test_estado_de_filtro_invalido_se_rechaza(base):
    respuesta = await _obtener(base, "/historial?estado=no-existe")
    assert respuesta.status_code == 400


async def test_filtros_combinados_se_aplican_todos_a_la_vez(base):
    """estado + tarjeta + destino + evaluacion combinados: solo la fila que
    cumple TODOS los criterios a la vez debe aparecer -no basta con cumplir
    uno solo-.
    """
    _insertar(
        base, stan="000001", estado="rechazada", card_id="TARJ-A",
        destino_host="10.0.0.1", destino_puerto=9000, evaluacion_estado="fail",
    )
    # Cumple estado y tarjeta, pero no destino ni evaluacion: no debe aparecer.
    _insertar(
        base, stan="000002", estado="rechazada", card_id="TARJ-A",
        destino_host="10.0.0.9", destino_puerto=9000, evaluacion_estado="pass",
    )
    # Cumple todo salvo el estado: no debe aparecer.
    _insertar(
        base, stan="000003", estado="aprobada", card_id="TARJ-A",
        destino_host="10.0.0.1", destino_puerto=9000, evaluacion_estado="fail",
    )

    respuesta = await _obtener(
        base,
        "/historial?estado=rechazada&card_id=TARJ-A&destino=10.0.0.1&evaluacion=fail",
    )
    texto = respuesta.text
    assert "000001" in texto
    assert "000002" not in texto
    assert "000003" not in texto

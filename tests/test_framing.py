"""Framing de demostracion: prefijo de 2 bytes big-endian.

Se prueba aislado del transporte y del codec, porque el framing no debe conocer
ninguno de los dos.
"""

from __future__ import annotations

import asyncio

import pytest

from sibutestlab8583.adapters.transporte.framing_demo import (
    LARGO_PREFIJO,
    MAXIMO_PAYLOAD,
    FramingDemostracion,
)
from sibutestlab8583.domain.errores import ErrorDeFraming

FRAMING = FramingDemostracion()


def _lector(datos: bytes) -> asyncio.StreamReader:
    lector = asyncio.StreamReader()
    lector.feed_data(datos)
    lector.feed_eof()
    return lector


def test_el_prefijo_lleva_la_longitud_en_big_endian():
    enmarcado = FRAMING.preparar(b"hola")
    assert enmarcado[:LARGO_PREFIJO] == b"\x00\x04"
    assert enmarcado[LARGO_PREFIJO:] == b"hola"


async def test_ida_y_vuelta():
    payload = b"0110" + bytes(range(40))
    leido = await FRAMING.leer_mensaje_completo(_lector(FRAMING.preparar(payload)))
    assert leido == payload


async def test_dos_mensajes_seguidos_en_el_mismo_stream():
    """El framing debe delimitar, no leer hasta el final del stream."""
    lector = _lector(FRAMING.preparar(b"primero") + FRAMING.preparar(b"segundo"))
    assert await FRAMING.leer_mensaje_completo(lector) == b"primero"
    assert await FRAMING.leer_mensaje_completo(lector) == b"segundo"


def test_un_payload_vacio_se_rechaza():
    with pytest.raises(ErrorDeFraming):
        FRAMING.preparar(b"")


def test_un_payload_mayor_al_maximo_se_rechaza():
    with pytest.raises(ErrorDeFraming):
        FRAMING.preparar(b"x" * (MAXIMO_PAYLOAD + 1))


def test_el_maximo_exacto_se_acepta():
    assert len(FRAMING.preparar(b"x" * MAXIMO_PAYLOAD)) == MAXIMO_PAYLOAD + LARGO_PREFIJO


async def test_prefijo_incompleto():
    with pytest.raises(ErrorDeFraming, match="prefijo"):
        await FRAMING.leer_mensaje_completo(_lector(b"\x00"))


async def test_stream_cortado_antes_de_completar_el_payload():
    completo = FRAMING.preparar(b"mensaje entero")
    with pytest.raises(ErrorDeFraming, match="payload"):
        await FRAMING.leer_mensaje_completo(_lector(completo[:-3]))


async def test_un_prefijo_que_anuncia_cero_se_rechaza():
    with pytest.raises(ErrorDeFraming, match="cero"):
        await FRAMING.leer_mensaje_completo(_lector(b"\x00\x00"))


async def test_el_framing_no_interpreta_iso8583():
    """Debe transportar bytes arbitrarios sin mirarlos."""
    basura = bytes([0, 255, 1, 254, 127])
    assert await FRAMING.leer_mensaje_completo(_lector(FRAMING.preparar(basura))) == basura

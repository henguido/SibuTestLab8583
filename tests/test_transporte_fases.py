"""Cada fase del transporte produce el resultado que corresponde.

Los fallos posteriores a conectar se provocan con dobles del lector y del
escritor, sustituyendo `asyncio.open_connection`. Es determinista y portable: no
depende de que un sistema operativo rechace o descarte una conexion a un puerto
cerrado, particularidad que en Windows produce un tiempo agotado en lugar de un
rechazo.

RN-2 conserva al menos una prueba con TCP real, en
`test_semantica_comunicacion.py` y en `test_integracion_end_to_end.py`.
"""

from __future__ import annotations

import asyncio

import pytest

from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.adapters.transporte.tcp import TransporteTcp
from sibutestlab8583.domain.errores import ErrorDeFraming
from sibutestlab8583.domain.modelos import (
    DestinoTcp,
    FalloDeConexion,
    FalloDeTransmision,
    TiempoAgotado,
)

DESTINO = DestinoTcp(host="127.0.0.1", puerto=9999)
PAYLOAD = b"0100 carga de prueba"
LIMITE = 0.2


class EscritorFalso:
    """Doble de `asyncio.StreamWriter` con el fallo que se le indique."""

    def __init__(self, *, error_al_drenar=None, drenaje_lento=False) -> None:
        self._error = error_al_drenar
        self._lento = drenaje_lento
        self.escrito = b""
        self.cerrado = False

    def write(self, datos: bytes) -> None:
        # Como el real: encola en el buffer local y no transmite nada por si mismo.
        self.escrito += datos

    async def drain(self) -> None:
        if self._lento:
            await asyncio.sleep(LIMITE * 20)
        if self._error is not None:
            raise self._error

    def close(self) -> None:
        self.cerrado = True

    async def wait_closed(self) -> None:
        return None


class LectorFalso:
    """Doble de `asyncio.StreamReader`."""

    def __init__(self, *, datos: bytes = b"", error=None, lento: bool = False) -> None:
        self._datos = datos
        self._error = error
        self._lento = lento

    async def readexactly(self, n: int) -> bytes:
        if self._lento:
            await asyncio.sleep(LIMITE * 20)
        if self._error is not None:
            raise self._error
        trozo, self._datos = self._datos[:n], self._datos[n:]
        if len(trozo) != n:
            raise asyncio.IncompleteReadError(trozo, n)
        return trozo


def _conexion_falsa(monkeypatch, lector, escritor):
    async def abrir(host, puerto):
        return lector, escritor

    monkeypatch.setattr(asyncio, "open_connection", abrir)


def _transporte() -> TransporteTcp:
    return TransporteTcp(FramingDemostracion(), tiempo_limite=LIMITE)


# ------------------------------------- fase 0: enmarcar, antes de conectar ---


async def test_un_payload_vacio_lanza_antes_de_tocar_la_red(monkeypatch):
    """La unica excepcion que el transporte deja salir."""
    intentos = []

    async def abrir(host, puerto):
        intentos.append((host, puerto))
        raise AssertionError("no debio intentar conectar")

    monkeypatch.setattr(asyncio, "open_connection", abrir)

    with pytest.raises(ErrorDeFraming):
        await _transporte().enviar(b"", DESTINO)
    assert intentos == [], "preparar() corre antes de conectar"


# --------------------------------------------------- fase 1: conectar --------


async def test_conexion_rechazada_da_fallo_de_conexion(monkeypatch):
    async def abrir(host, puerto):
        raise ConnectionRefusedError("conexion rechazada")

    monkeypatch.setattr(asyncio, "open_connection", abrir)
    resultado = await _transporte().enviar(PAYLOAD, DESTINO)

    assert isinstance(resultado, FalloDeConexion)
    assert "establecer la conexion" in resultado.detalle


async def test_conexion_que_se_agota_da_fallo_de_conexion(monkeypatch):
    async def abrir(host, puerto):
        await asyncio.sleep(LIMITE * 20)

    monkeypatch.setattr(asyncio, "open_connection", abrir)
    resultado = await _transporte().enviar(PAYLOAD, DESTINO)

    assert isinstance(resultado, FalloDeConexion)
    assert not isinstance(resultado, FalloDeTransmision)


# ----------------------------------------------------- fase 2: enviar --------


async def test_drenaje_que_falla_da_fallo_de_transmision(monkeypatch):
    """La conexion existio: no puede decirse que no se envio."""
    escritor = EscritorFalso(error_al_drenar=ConnectionResetError("el par cerro"))
    _conexion_falsa(monkeypatch, LectorFalso(), escritor)

    resultado = await _transporte().enviar(PAYLOAD, DESTINO)

    assert isinstance(resultado, FalloDeTransmision)
    assert not isinstance(resultado, FalloDeConexion)
    assert "no puede determinarse" in resultado.detalle


async def test_drenaje_que_se_agota_da_fallo_de_transmision_y_no_rn2(monkeypatch):
    """Un tiempo agotado enviando NO es RN-2: RN-2 exige que el envio termine."""
    _conexion_falsa(monkeypatch, LectorFalso(), EscritorFalso(drenaje_lento=True))

    resultado = await _transporte().enviar(PAYLOAD, DESTINO)

    assert isinstance(resultado, FalloDeTransmision)
    assert not isinstance(resultado, TiempoAgotado), "no cumple las premisas de RN-2"


async def test_el_detalle_no_afirma_que_no_se_envio(monkeypatch):
    """Prohibido decir "nunca salio" cuando no puede demostrarse."""
    _conexion_falsa(
        monkeypatch, LectorFalso(), EscritorFalso(error_al_drenar=OSError("roto"))
    )
    resultado = await _transporte().enviar(PAYLOAD, DESTINO)

    texto = resultado.detalle.lower()
    for prohibido in ("nunca salio", "no se envio", "cero bytes", "nada salio"):
        assert prohibido not in texto, f"el detalle afirma lo indemostrable: {prohibido!r}"


# ------------------------------------------ fase 3: esperar la respuesta -----


async def test_sin_respuesta_dentro_del_limite_es_rn2(monkeypatch):
    """Las cuatro premisas cumplidas: conecto, drenaje ok, espero, no llego."""
    escritor = EscritorFalso()
    _conexion_falsa(monkeypatch, LectorFalso(lento=True), escritor)

    resultado = await _transporte().enviar(PAYLOAD, DESTINO)

    assert isinstance(resultado, TiempoAgotado)
    assert resultado.limite_segundos == LIMITE
    assert escritor.escrito, "el drenaje debio completarse antes de esperar"


async def test_canal_roto_esperando_respuesta_da_fallo_de_transmision(monkeypatch):
    """Hubo sesion y el intercambio quedo sin cerrar. Ni RN-2 ni error de conexion."""
    _conexion_falsa(
        monkeypatch, LectorFalso(error=ConnectionResetError("cerro")), EscritorFalso()
    )

    resultado = await _transporte().enviar(PAYLOAD, DESTINO)

    assert isinstance(resultado, FalloDeTransmision)
    assert not isinstance(resultado, TiempoAgotado)
    assert not isinstance(resultado, FalloDeConexion)
    assert "no puede determinarse" in resultado.detalle


async def test_desenmarcado_incompleto_da_fallo_de_transmision(monkeypatch):
    """El framing no pudo completar un mensaje: es fallo del mecanismo, no ISO."""
    # Anuncia 100 bytes y entrega 5.
    parcial = (100).to_bytes(2, "big") + b"12345"
    _conexion_falsa(monkeypatch, LectorFalso(datos=parcial), EscritorFalso())

    resultado = await _transporte().enviar(PAYLOAD, DESTINO)

    assert isinstance(resultado, FalloDeTransmision)


async def test_una_respuesta_completa_se_devuelve_tal_cual(monkeypatch):
    respuesta = b"0110 respuesta completa"
    enmarcada = FramingDemostracion().preparar(respuesta)
    _conexion_falsa(monkeypatch, LectorFalso(datos=enmarcada), EscritorFalso())

    assert await _transporte().enviar(PAYLOAD, DESTINO) == respuesta


# ----------------------------------------------------------- invariantes -----


async def test_la_conexion_se_cierra_en_todos_los_caminos(monkeypatch):
    for escritor, lector in (
        (EscritorFalso(error_al_drenar=OSError("x")), LectorFalso()),
        (EscritorFalso(), LectorFalso(lento=True)),
        (EscritorFalso(), LectorFalso(error=OSError("y"))),
    ):
        _conexion_falsa(monkeypatch, lector, escritor)
        await _transporte().enviar(PAYLOAD, DESTINO)
        assert escritor.cerrado, "el transporte debe cerrar aunque falle"


async def test_ninguna_excepcion_de_red_cruza_el_contrato(monkeypatch):
    """Ni OSError ni asyncio.TimeoutError deben salir de enviar()."""
    casos = [
        (LectorFalso(), EscritorFalso(error_al_drenar=OSError("a"))),
        (LectorFalso(), EscritorFalso(drenaje_lento=True)),
        (LectorFalso(error=OSError("b")), EscritorFalso()),
        (LectorFalso(lento=True), EscritorFalso()),
    ]
    for lector, escritor in casos:
        _conexion_falsa(monkeypatch, lector, escritor)
        resultado = await _transporte().enviar(PAYLOAD, DESTINO)
        assert isinstance(resultado, (bytes, TiempoAgotado, FalloDeConexion, FalloDeTransmision))

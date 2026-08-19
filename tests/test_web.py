"""Capa web con dobles del orquestador.

Se prueba la interfaz, no el nucleo: el nucleo ya tiene sus propias pruebas. Lo
que importa aqui es que cada desenlace se presente distinto, que un error de
entrada no produzca un 500 y que el PAN completo no llegue nunca al navegador.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, PAN_DEMO
from sibutestlab8583.application.consultas import TarjetaListada
from sibutestlab8583.domain.datos_sinteticos import monto_iso
from sibutestlab8583.application.orquestador import TarjetaDesconocida
from sibutestlab8583.domain.errores import ErrorDeConexion
from sibutestlab8583.domain.modelos import (
    MTI_RESPUESTA_COMPRA,
    CampoInterpretado,
    Ejecucion,
    EstadoEjecucion,
    MensajeInterpretado,
    MensajeIso,
    ResultadoCompra,
)
from sibutestlab8583.web.app import crear_app

MOMENTO = datetime(2026, 8, 19, 12, 0, 0, tzinfo=timezone.utc)


class ConsultasFalsas:
    def __init__(self, ejecuciones=()):
        self._ejecuciones = list(ejecuciones)

    async def tarjetas(self):
        return [
            TarjetaListada(
                card_id=CARD_ID_DEMO,
                pan_enmascarado="************6666",
                descripcion="Tarjeta sintetica de demostracion",
                sintetica=True,
            )
        ]

    async def ejecuciones_recientes(self, limite=20):
        return self._ejecuciones


class OrquestadorFalso:
    def __init__(self, resultado=None, error=None):
        self._resultado = resultado
        self._error = error

    async def ejecutar_compra(self, datos):
        if self._error is not None:
            raise self._error
        return self._resultado


class ComposicionFalsa:
    def __init__(self, resultado=None, error=None, ejecuciones=()):
        from sibutestlab8583.composicion import Configuracion

        self.configuracion = Configuracion(
            ruta_base_datos="no-se-usa.db", host_destino="127.0.0.1", puerto_destino=8583
        )
        self.consultas = ConsultasFalsas(ejecuciones)
        self.descripciones_de_campos = {"2": "Numero de tarjeta (PAN)", "4": "Monto"}
        self._orquestador = OrquestadorFalso(resultado, error)

    def orquestador(self, destino):
        return self._orquestador


def _resultado(estado, *, codigo=None, con_respuesta=True, motivos=()):
    ejecucion = Ejecucion(
        card_id=CARD_ID_DEMO,
        monto=Decimal("150.00"),
        moneda="188",
        stan="000042",
        estado=estado,
        mti_respuesta=MTI_RESPUESTA_COMPRA if con_respuesta else None,
        codigo_respuesta=codigo,
        destino_host="127.0.0.1",
        destino_puerto=8583,
        latencia_ms=7,
        creada_en=MOMENTO,
    )
    respuesta = None
    if con_respuesta:
        respuesta = MensajeInterpretado(
            MTI_RESPUESTA_COMPRA,
            {"39": CampoInterpretado("39", codigo or "00", codigo or "00", "Codigo de respuesta")},
        )
    return ResultadoCompra(
        ejecucion=ejecucion,
        solicitud=MensajeIso("0100", {"2": "************6666", "4": monto_iso("15000")}),
        respuesta=respuesta,
        motivos=tuple(motivos),
    )


def _cliente(**kwargs) -> TestClient:
    return TestClient(crear_app(ComposicionFalsa(**kwargs)))


FORMULARIO = {"card_id": CARD_ID_DEMO, "monto": "150.00", "host": "127.0.0.1", "puerto": "8583"}


# ------------------------------------------------------------------ pantalla --


def test_la_pantalla_de_compra_responde():
    respuesta = _cliente().get("/")
    assert respuesta.status_code == 200
    assert "Nueva compra" in respuesta.text
    assert "SibuTestLab8583" in respuesta.text


def test_la_tarjeta_se_muestra_solo_enmascarada():
    texto = _cliente().get("/").text
    assert "************6666" in texto
    assert PAN_DEMO not in texto


def test_no_hay_campo_para_escribir_el_pan():
    """El PAN se obtiene por card_id; el usuario nunca lo teclea."""
    texto = _cliente().get("/").text.lower()
    assert 'name="card_id"' in texto
    for prohibido in ('name="pan"', 'name="numero_tarjeta"', 'name="tarjeta"'):
        assert prohibido not in texto


# ------------------------------------------------------------- cada desenlace --


def test_una_compra_aprobada_muestra_el_resultado():
    respuesta = _cliente(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00")).post(
        "/compra", data=FORMULARIO
    )
    assert respuesta.status_code == 200
    assert "Transaccion aprobada" in respuesta.text
    assert "000042" in respuesta.text
    assert "7 ms" in respuesta.text


def test_un_rechazo_no_aparece_como_aprobacion():
    texto = _cliente(resultado=_resultado(EstadoEjecucion.RECHAZADA, codigo="05")).post(
        "/compra", data=FORMULARIO
    ).text
    assert "Transaccion rechazada" in texto
    assert "Transaccion aprobada" not in texto


def test_un_timeout_se_representa_distinto_de_un_rechazo():
    texto = _cliente(
        resultado=_resultado(EstadoEjecucion.TIMEOUT, con_respuesta=False)
    ).post("/compra", data=FORMULARIO).text
    assert "Sin respuesta" in texto
    assert "Transaccion rechazada" not in texto
    assert "Transaccion aprobada" not in texto
    assert 'class="aviso timeout"' in texto


def test_una_respuesta_invalida_no_aparece_como_exito():
    texto = _cliente(
        resultado=_resultado(
            EstadoEjecucion.INVALIDA, codigo="00", motivos=("el campo 11 no corresponde",)
        )
    ).post("/compra", data=FORMULARIO).text
    assert "Respuesta invalida" in texto
    assert "Transaccion aprobada" not in texto
    assert "el campo 11 no corresponde" in texto


def test_un_mensaje_incompleto_se_distingue():
    texto = _cliente(
        resultado=_resultado(
            EstadoEjecucion.NO_ENVIADA, con_respuesta=False, motivos=("faltan campos: 14",)
        )
    ).post("/compra", data=FORMULARIO).text
    assert "no se envio" in texto
    assert 'class="aviso no-enviada"' in texto


def test_un_fallo_de_conexion_no_se_presenta_como_rechazo():
    texto = _cliente(error=ErrorDeConexion("no se pudo conectar")).post(
        "/compra", data=FORMULARIO
    ).text
    assert "No se pudo conectar con el destino" in texto
    assert "Transaccion rechazada" not in texto


# --------------------------------------------------------- entradas invalidas --


@pytest.mark.parametrize(
    "campo,valor",
    [("monto", "abc"), ("monto", "-5"), ("monto", "0"), ("monto", ""), ("puerto", "99999"),
     ("puerto", "cero"), ("host", "")],
)
def test_una_entrada_invalida_produce_respuesta_controlada_y_no_500(campo, valor):
    respuesta = _cliente().post("/compra", data={**FORMULARIO, campo: valor})
    assert respuesta.status_code == 400, "debe ser un error de entrada, no un fallo del servidor"
    assert "Revise los datos" in respuesta.text
    assert "Traceback" not in respuesta.text


def test_una_tarjeta_inexistente_se_informa_sin_traza():
    respuesta = _cliente(error=TarjetaDesconocida("no existe")).post("/compra", data=FORMULARIO)
    assert respuesta.status_code == 400
    assert "No existe la tarjeta" in respuesta.text
    assert "Traceback" not in respuesta.text


def test_un_error_inesperado_no_expone_detalles_internos():
    from sibutestlab8583.domain.errores import ErrorDelSimulador

    class ErrorInterno(ErrorDelSimulador):
        """Error del simulador sin traduccion especifica en presentacion."""

    respuesta = _cliente(error=ErrorInterno("detalle interno confidencial")).post(
        "/compra", data=FORMULARIO
    )
    assert "detalle interno confidencial" not in respuesta.text
    assert "Ocurrio un error inesperado" in respuesta.text


# ------------------------------------------------------------------ isoscopio --


def test_el_isoscopio_muestra_campos_con_descripcion_y_nunca_el_pan():
    texto = _cliente(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00")).post(
        "/compra", data=FORMULARIO
    ).text
    assert "Isoscopio · solicitud 0100" in texto
    assert "Isoscopio · respuesta 0110" in texto
    assert "Numero de tarjeta (PAN)" in texto
    assert "************6666" in texto
    assert PAN_DEMO not in texto
    assert "enmascarado" in texto


# ------------------------------------------------------------------ historial --


def test_el_historial_lista_las_ejecuciones():
    ejecucion = _resultado(EstadoEjecucion.APROBADA, codigo="00").ejecucion
    respuesta = _cliente(ejecuciones=[ejecucion]).get("/historial")
    assert respuesta.status_code == 200
    assert CARD_ID_DEMO in respuesta.text
    assert "150.00" in respuesta.text
    assert "aprobada" in respuesta.text
    assert PAN_DEMO not in respuesta.text


def test_el_historial_vacio_no_falla():
    respuesta = _cliente().get("/historial")
    assert respuesta.status_code == 200
    assert "Todavia no hay ejecuciones" in respuesta.text

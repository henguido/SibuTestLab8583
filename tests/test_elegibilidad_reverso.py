"""B6: `domain.elegibilidad_reverso.puede_generar_operacion_derivada`.

Cubre exactamente los candidatos que el pedido de B6 enumero: 0200 aprobada
(el unico elegible hoy), 0200 rechazada (excluido explicitamente, punto 8),
Echo, autorizacion 0100 (fuera en esta primera version), y los estados sin
respuesta confirmada (error/timeout). Pura -sin red, sin base de datos-,
igual que `domain/validacion.py`: se construye un `Ejecucion` a mano, nunca
se pasa por un repositorio.
"""

from __future__ import annotations

from sibutestlab8583.domain.elegibilidad_reverso import puede_generar_operacion_derivada
from sibutestlab8583.domain.modelos import (
    Ejecucion,
    EstadoEjecucion,
    MTI_COMPRA,
    MTI_COMPRA_FINANCIERA,
    MTI_ECHO,
)


def _ejecucion(mti: str, estado: EstadoEjecucion) -> Ejecucion:
    return Ejecucion(stan="000001", estado=estado, mti_solicitud=mti)


def test_compra_financiera_aprobada_es_elegible():
    assert puede_generar_operacion_derivada(_ejecucion(MTI_COMPRA_FINANCIERA, EstadoEjecucion.APROBADA))


def test_compra_financiera_rechazada_no_es_elegible():
    """Punto 8 de B6: un rechazo (DE39=51 u otro) nunca tuvo un efecto que
    deshacer -decision explicita de este laboratorio, no una afirmacion
    sobre el comportamiento de ninguna marca."""
    assert not puede_generar_operacion_derivada(
        _ejecucion(MTI_COMPRA_FINANCIERA, EstadoEjecucion.RECHAZADA)
    )


def test_autorizacion_0100_no_es_elegible_todavia():
    """Fuera de alcance en esta primera version (ver docstring del modulo):
    una autorizacion tampoco mueve fondos por si sola, y este laboratorio
    prefiere no afirmar la regla real sin evidencia mas especifica."""
    assert not puede_generar_operacion_derivada(_ejecucion(MTI_COMPRA, EstadoEjecucion.APROBADA))


def test_echo_no_es_elegible():
    assert not puede_generar_operacion_derivada(_ejecucion(MTI_ECHO, EstadoEjecucion.APROBADA))


def test_un_error_de_conexion_no_es_elegible():
    """Sin respuesta confirmada, no hay efecto demostrado que deshacer."""
    assert not puede_generar_operacion_derivada(
        _ejecucion(MTI_COMPRA_FINANCIERA, EstadoEjecucion.ERROR_CONEXION)
    )


def test_un_timeout_no_es_elegible():
    assert not puede_generar_operacion_derivada(
        _ejecucion(MTI_COMPRA_FINANCIERA, EstadoEjecucion.TIMEOUT)
    )


def test_una_respuesta_invalida_no_es_elegible():
    assert not puede_generar_operacion_derivada(
        _ejecucion(MTI_COMPRA_FINANCIERA, EstadoEjecucion.INVALIDA)
    )


def test_no_enviada_no_es_elegible():
    assert not puede_generar_operacion_derivada(
        _ejecucion(MTI_COMPRA_FINANCIERA, EstadoEjecucion.NO_ENVIADA)
    )

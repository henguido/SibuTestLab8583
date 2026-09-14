"""Modelo de politica de continuacion (`PoliticaContinuacion`,
`PasoSecuencia.on_error`/`on_qa_fail`/`max_retries`, C3, 2026-09-14).

Pruebas puras: sin red, sin base de datos. Cubren la validacion de
`PasoSecuencia.__post_init__` y `es_estado_tecnico` -el fundamento que
`EjecutorDeSecuencia` usa despues para no confundir un rechazo transaccional
sin expectativa con una falla tecnica sin expectativa (punto 3 del
checkpoint).
"""

from __future__ import annotations

import pytest

from sibutestlab8583.domain.modelos import (
    ORIGEN_PASO_DERIVADO,
    ORIGEN_PASO_INDEPENDIENTE,
    EstadoEjecucion,
    PasoSecuencia,
    PoliticaContinuacion,
    es_estado_tecnico,
)


def test_defaults_preservan_el_comportamiento_de_c1():
    """El default de on_error/on_qa_fail es CONTINUAR -no DETENER-, porque
    el motor de secuencias NUNCA se detuvo por si solo antes de C3 (auditado
    explicitamente): lo que en C1 parecia "detenerse" era siempre el efecto
    emergente de un paso derivado sin contexto valido (BLOQUEADO), nunca una
    decision de flujo real. CONTINUAR es el unico default que no cambia el
    comportamiento observable de una secuencia definida antes de C3."""
    paso = PasoSecuencia(orden=1, origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id="ESC-1")
    assert paso.on_error == PoliticaContinuacion.CONTINUAR.value
    assert paso.on_qa_fail == PoliticaContinuacion.CONTINUAR.value
    assert paso.max_retries == 0


def test_on_error_y_on_qa_fail_solo_admiten_valores_conocidos():
    with pytest.raises(ValueError, match="on_error"):
        PasoSecuencia(orden=1, origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id="ESC-1", on_error="quizas")
    with pytest.raises(ValueError, match="on_qa_fail"):
        PasoSecuencia(orden=1, origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id="ESC-1", on_qa_fail="quizas")


def test_max_retries_negativo_se_rechaza():
    with pytest.raises(ValueError, match="max_retries"):
        PasoSecuencia(orden=1, origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id="ESC-1", max_retries=-1)


def test_un_paso_derivado_nunca_admite_retries():
    """Punto 8 del checkpoint: un paso derivado (siempre 0400/0420, efecto
    financiero o de reverso) nunca debe reintentarse automaticamente -el
    estado remoto de un intento previo no se puede demostrar con certeza."""
    with pytest.raises(ValueError, match="derivado"):
        PasoSecuencia(
            orden=2, origen_tipo=ORIGEN_PASO_DERIVADO, origen_paso_orden=1, max_retries=1
        )


def test_un_paso_derivado_con_max_retries_cero_es_valido():
    paso = PasoSecuencia(orden=2, origen_tipo=ORIGEN_PASO_DERIVADO, origen_paso_orden=1, max_retries=0)
    assert paso.max_retries == 0


@pytest.mark.parametrize(
    "estado,es_tecnico",
    [
        (EstadoEjecucion.APROBADA, False),
        (EstadoEjecucion.RECHAZADA, False),
        (EstadoEjecucion.INVALIDA, True),
        (EstadoEjecucion.TIMEOUT, True),
        (EstadoEjecucion.ERROR_CONEXION, True),
        (EstadoEjecucion.ERROR_TRANSMISION, True),
        (EstadoEjecucion.NO_ENVIADA, True),
    ],
)
def test_es_estado_tecnico_distingue_respuesta_real_de_falla_tecnica(estado, es_tecnico):
    """Punto 3 del checkpoint: aprobada/rechazada SON una respuesta
    transaccional real (con o sin expectativas); el resto nunca tuvo una
    respuesta que evaluar."""
    assert es_estado_tecnico(estado) is es_tecnico

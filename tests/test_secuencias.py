"""Pruebas puras (sin red, sin base de datos) del modelo de Secuencias (C1):
validacion de `PasoSecuencia`, el agregador de resultado global, y
`ContextoSecuencia`.
"""

from __future__ import annotations

import pytest

from sibutestlab8583.application.contexto_secuencia import ContextoSecuencia
from sibutestlab8583.domain.modelos import (
    ORIGEN_PASO_DERIVADO,
    ORIGEN_PASO_INDEPENDIENTE,
    EstadoPasoSecuencia,
    PasoSecuencia,
)
from sibutestlab8583.domain.secuencias import calcular_resultado_global_secuencia
from sibutestlab8583.domain.modelos import ResultadoGlobalSuite


# ------------------------------------------------------------ PasoSecuencia --


def test_paso_independiente_necesita_escenario_id():
    with pytest.raises(ValueError):
        PasoSecuencia(orden=1, origen_tipo=ORIGEN_PASO_INDEPENDIENTE)


def test_paso_independiente_no_puede_tener_origen_paso_orden():
    with pytest.raises(ValueError):
        PasoSecuencia(
            orden=1, origen_tipo=ORIGEN_PASO_INDEPENDIENTE,
            escenario_id="ESC-1", origen_paso_orden=1,
        )


def test_paso_derivado_necesita_origen_paso_orden():
    with pytest.raises(ValueError):
        PasoSecuencia(orden=2, origen_tipo=ORIGEN_PASO_DERIVADO)


def test_paso_derivado_no_puede_tener_escenario_id():
    with pytest.raises(ValueError):
        PasoSecuencia(
            orden=2, origen_tipo=ORIGEN_PASO_DERIVADO,
            escenario_id="ESC-1", origen_paso_orden=1,
        )


def test_paso_derivado_no_puede_derivar_de_si_mismo():
    with pytest.raises(ValueError):
        PasoSecuencia(orden=1, origen_tipo=ORIGEN_PASO_DERIVADO, origen_paso_orden=1)


def test_origen_tipo_desconocido_se_rechaza():
    with pytest.raises(ValueError):
        PasoSecuencia(orden=1, origen_tipo="paralelo", escenario_id="ESC-1")


def test_un_paso_independiente_valido_se_construye_sin_problema():
    paso = PasoSecuencia(orden=1, origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id="ESC-1")
    assert paso.escenario_id == "ESC-1"
    assert paso.origen_paso_orden is None


def test_un_paso_derivado_valido_se_construye_sin_problema():
    paso = PasoSecuencia(orden=2, origen_tipo=ORIGEN_PASO_DERIVADO, origen_paso_orden=1)
    assert paso.escenario_id is None
    assert paso.origen_paso_orden == 1


# ---------------------------------------- calcular_resultado_global_secuencia --


def _conteos(**kwargs) -> dict:
    base = {estado: 0 for estado in EstadoPasoSecuencia}
    base.update(kwargs)
    return base


def test_todos_pass_es_pass():
    conteos = _conteos(**{EstadoPasoSecuencia.PASS: 2})
    assert calcular_resultado_global_secuencia(conteos) == ResultadoGlobalSuite.PASS


def test_algun_fail_es_fail():
    conteos = _conteos(**{EstadoPasoSecuencia.PASS: 1, EstadoPasoSecuencia.FAIL: 1})
    assert calcular_resultado_global_secuencia(conteos) == ResultadoGlobalSuite.FAIL


def test_algun_error_es_error_incluso_con_pass():
    conteos = _conteos(**{EstadoPasoSecuencia.PASS: 1, EstadoPasoSecuencia.ERROR: 1})
    assert calcular_resultado_global_secuencia(conteos) == ResultadoGlobalSuite.ERROR


def test_algun_bloqueado_sin_error_ni_fail_es_incompleta():
    conteos = _conteos(**{EstadoPasoSecuencia.PASS: 1, EstadoPasoSecuencia.BLOQUEADO: 1})
    assert calcular_resultado_global_secuencia(conteos) == ResultadoGlobalSuite.INCOMPLETA


def test_error_tiene_prioridad_sobre_bloqueado():
    conteos = _conteos(**{EstadoPasoSecuencia.ERROR: 1, EstadoPasoSecuencia.BLOQUEADO: 1})
    assert calcular_resultado_global_secuencia(conteos) == ResultadoGlobalSuite.ERROR


def test_todos_sin_expectativas_es_sin_expectativas():
    conteos = _conteos(**{EstadoPasoSecuencia.SIN_EXPECTATIVAS: 2})
    assert calcular_resultado_global_secuencia(conteos) == ResultadoGlobalSuite.SIN_EXPECTATIVAS


def test_pass_mezclado_con_sin_expectativas_es_incompleta():
    conteos = _conteos(
        **{EstadoPasoSecuencia.PASS: 1, EstadoPasoSecuencia.SIN_EXPECTATIVAS: 1}
    )
    assert calcular_resultado_global_secuencia(conteos) == ResultadoGlobalSuite.INCOMPLETA


# C3 (2026-09-14): un paso saltado por politica DETENER se cuenta como
# BLOQUEADO -mismo estado que "precondicion no cumplida"-, nunca un enum
# nuevo (ver docstring de `PoliticaContinuacion`). Estas pruebas confirman,
# sin cambiar la funcion, que la tabla YA existente produce el resultado
# correcto para los dos disparadores de DETENER (punto 28 del checkpoint:
# "formalizar la precedencia... agregar tabla/test de verdad").


def test_un_paso_error_que_detiene_la_secuencia_produce_resultado_error():
    """Paso 1 ERROR con on_error=DETENER -> pasos siguientes BLOQUEADO. El
    resultado global debe seguir siendo ERROR (un fallo tecnico real
    domina), no INCOMPLETA -que subestimaria la severidad-."""
    conteos = _conteos(**{EstadoPasoSecuencia.ERROR: 1, EstadoPasoSecuencia.BLOQUEADO: 2})
    assert calcular_resultado_global_secuencia(conteos) == ResultadoGlobalSuite.ERROR


def test_un_paso_fail_qa_que_detiene_la_secuencia_produce_resultado_fail():
    """Paso 1 FAIL QA con on_qa_fail=DETENER -> pasos siguientes BLOQUEADO.
    El resultado global debe ser FAIL -nada fallo tecnicamente, solo una
    expectativa no se cumplio-, nunca ERROR ni "el ultimo paso gana"."""
    conteos = _conteos(**{EstadoPasoSecuencia.FAIL: 1, EstadoPasoSecuencia.BLOQUEADO: 2})
    assert calcular_resultado_global_secuencia(conteos) == ResultadoGlobalSuite.FAIL


# ----------------------------------------------------------- ContextoSecuencia --


def test_contexto_devuelve_none_para_un_paso_no_registrado():
    contexto = ContextoSecuencia()
    assert contexto.ejecucion_id_de(1) is None


def test_contexto_devuelve_lo_registrado():
    contexto = ContextoSecuencia()
    contexto.registrar(1, 42)
    assert contexto.ejecucion_id_de(1) == 42
    assert contexto.ejecucion_id_de(2) is None

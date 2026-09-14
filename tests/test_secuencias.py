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


# ----------------------------------------------------------- ContextoSecuencia --


def test_contexto_devuelve_none_para_un_paso_no_registrado():
    contexto = ContextoSecuencia()
    assert contexto.ejecucion_id_de(1) is None


def test_contexto_devuelve_lo_registrado():
    contexto = ContextoSecuencia()
    contexto.registrar(1, 42)
    assert contexto.ejecucion_id_de(1) == 42
    assert contexto.ejecucion_id_de(2) is None

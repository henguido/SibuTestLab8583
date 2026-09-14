"""Modelo puro de reglas del Host Simulado (Fase D1, 2026-09-14).

Sin red, sin base de datos. Cubre: construccion/validacion de
`CondicionRegla`/`ComportamientoRegla`/`RespuestaRegla`/`ReglaHost`,
matching por operador, precedencia determinista, y seguridad (campos
sensibles prohibidos).
"""

from __future__ import annotations

import pytest

from sibutestlab8583.domain.datos_sinteticos import pan_sintetico
from sibutestlab8583.domain.reglas_host import (
    CAMPO_MTI,
    CondicionRegla,
    ComportamientoRegla,
    GeneradorValor,
    ReglaHost,
    RespuestaRegla,
    TipoComportamiento,
    es_generador,
    evaluar_reglas,
    generador_referenciado,
    regla_coincide,
    validar_regla,
)
from sibutestlab8583.profiles.generico import PERFIL_GENERICO


def _regla(nombre="R", prioridad=10, activa=True, condiciones=None, de39="00", **kw):
    return ReglaHost(
        nombre=nombre, prioridad=prioridad, activa=activa,
        condiciones=condiciones or (CondicionRegla(CAMPO_MTI, "igual", "0200"),),
        respuesta=RespuestaRegla(de39=de39),
        **kw,
    )


# ------------------------------------------------------------ Modelo ------


def test_una_regla_necesita_al_menos_una_condicion():
    with pytest.raises(ValueError, match="condicion"):
        ReglaHost(nombre="R", prioridad=1, activa=True, condiciones=(), respuesta=RespuestaRegla(de39="00"))


def test_una_regla_necesita_nombre():
    with pytest.raises(ValueError, match="nombre"):
        _regla(nombre="   ")


def test_prioridad_negativa_se_rechaza():
    with pytest.raises(ValueError, match="prioridad"):
        _regla(prioridad=-1)


def test_operador_presente_no_admite_valor():
    with pytest.raises(ValueError, match="no admite"):
        CondicionRegla(campo="4", operador="presente", valor="100")


def test_operador_igual_necesita_valor():
    with pytest.raises(ValueError, match="necesita un valor"):
        CondicionRegla(campo="4", operador="igual", valor=None)


def test_operador_desconocido_se_rechaza():
    with pytest.raises(ValueError, match="operador"):
        CondicionRegla(campo="4", operador="parecido_a", valor="1")


def test_respuesta_necesita_de39():
    with pytest.raises(ValueError, match="DE39"):
        RespuestaRegla(de39="")


# ------------------------------------------------------- Comportamiento ---


def test_comportamiento_delay_necesita_delay_mayor_a_cero():
    with pytest.raises(ValueError, match="DELAY"):
        ComportamientoRegla(tipo=TipoComportamiento.DELAY.value, delay_ms=0)


def test_comportamiento_no_delay_no_admite_delay_ms():
    with pytest.raises(ValueError, match="delay_ms solo aplica"):
        ComportamientoRegla(tipo=TipoComportamiento.NORMAL.value, delay_ms=5)


def test_delay_negativo_se_rechaza():
    with pytest.raises(ValueError, match="negativo"):
        ComportamientoRegla(tipo=TipoComportamiento.DELAY.value, delay_ms=-1)


def test_delay_por_encima_del_maximo_se_rechaza():
    with pytest.raises(ValueError, match="superar"):
        ComportamientoRegla(tipo=TipoComportamiento.DELAY.value, delay_ms=999_999)


def test_timeout_y_disconnect_no_admiten_delay_ms():
    ComportamientoRegla(tipo=TipoComportamiento.TIMEOUT.value)
    ComportamientoRegla(tipo=TipoComportamiento.DISCONNECT.value)
    with pytest.raises(ValueError):
        ComportamientoRegla(tipo=TipoComportamiento.TIMEOUT.value, delay_ms=1)


# ------------------------------------------------------------- Matching ---


@pytest.mark.parametrize(
    "operador,valor_regla,valor_mensaje,esperado",
    [
        ("igual", "100000.00", "100000.00", True),
        ("igual", "100000.00", "50.00", False),
        ("distinto", "100000.00", "50.00", True),
        ("distinto", "100000.00", "100000.00", False),
        ("mayor_que", "100000.00", "200000.00", True),
        ("mayor_que", "100000.00", "50.00", False),
        ("menor_que", "100000.00", "50.00", True),
        ("menor_que", "100000.00", "200000.00", False),
    ],
)
def test_operadores_de_comparacion(operador, valor_regla, valor_mensaje, esperado):
    condicion = CondicionRegla(campo="4", operador=operador, valor=valor_regla)
    assert bool(_condicion_coincide_helper(condicion, {"4": valor_mensaje})) is esperado


def _condicion_coincide_helper(condicion, campos_mensaje, mti="0200"):
    from sibutestlab8583.domain.reglas_host import _condicion_coincide
    return _condicion_coincide(condicion, campos_mensaje, mti)


def test_presente_y_ausente():
    presente = CondicionRegla(campo="4", operador="presente")
    ausente = CondicionRegla(campo="4", operador="ausente")
    assert _condicion_coincide_helper(presente, {"4": "10.00"}) is True
    assert _condicion_coincide_helper(presente, {}) is False
    assert _condicion_coincide_helper(ausente, {}) is True
    assert _condicion_coincide_helper(ausente, {"4": "10.00"}) is False


def test_mayor_que_contra_valor_no_numerico_no_coincide_sin_excepcion():
    condicion = CondicionRegla(campo="41", operador="mayor_que", valor="100")
    assert _condicion_coincide_helper(condicion, {"41": "TERM0001"}) is False


def test_condicion_sobre_mti():
    condicion = CondicionRegla(campo=CAMPO_MTI, operador="igual", valor="0200")
    assert _condicion_coincide_helper(condicion, {}, mti="0200") is True
    assert _condicion_coincide_helper(condicion, {}, mti="0800") is False


def test_regla_coincide_requiere_todas_las_condiciones_and():
    regla = _regla(condiciones=(
        CondicionRegla(CAMPO_MTI, "igual", "0200"),
        CondicionRegla("4", "mayor_que", "100000.00"),
    ))
    assert regla_coincide(regla, {"4": "200000.00"}, "0200") is True
    assert regla_coincide(regla, {"4": "50.00"}, "0200") is False
    assert regla_coincide(regla, {"4": "200000.00"}, "0800") is False


# ---------------------------------------------------------- Precedencia ---


def test_menor_prioridad_se_evalua_primero():
    regla_alta = _regla(nombre="alta", prioridad=1, de39="51")
    regla_baja = _regla(nombre="baja", prioridad=10, de39="00")
    ganadora = evaluar_reglas([regla_baja, regla_alta], {}, "0200")
    assert ganadora.nombre == "alta"


def test_dos_reglas_coincidentes_gana_una_sola_segun_prioridad():
    r1 = _regla(nombre="r1", prioridad=5)
    r2 = _regla(nombre="r2", prioridad=3)
    r3 = _regla(nombre="r3", prioridad=8)
    ganadora = evaluar_reglas([r1, r2, r3], {}, "0200")
    assert ganadora.nombre == "r2"


def test_regla_inactiva_nunca_gana():
    inactiva = _regla(nombre="inactiva", prioridad=1, activa=False)
    activa = _regla(nombre="activa", prioridad=99, activa=True)
    ganadora = evaluar_reglas([inactiva, activa], {}, "0200")
    assert ganadora.nombre == "activa"


def test_ninguna_regla_coincide_devuelve_none():
    regla = _regla(condiciones=(CondicionRegla(CAMPO_MTI, "igual", "0800"),))
    assert evaluar_reglas([regla], {}, "0200") is None


# -------------------------------------------------------------- Generadores


def test_es_generador_y_generador_referenciado():
    assert es_generador("@stan_request") is True
    assert es_generador("00") is False
    assert generador_referenciado("@stan_request") == GeneradorValor.STAN_REQUEST.value
    assert generador_referenciado("@algo_inventado") is None
    assert generador_referenciado("00") is None


# --------------------------------------------------------------- Seguridad


@pytest.mark.parametrize("campo_sensible", ["2", "35", "45"])
def test_validar_regla_rechaza_condicion_sobre_campo_sensible(campo_sensible):
    regla = _regla(condiciones=(CondicionRegla(campo_sensible, "igual", "x"),))
    with pytest.raises(ValueError, match="sensible"):
        validar_regla(regla, PERFIL_GENERICO)


@pytest.mark.parametrize("campo_sensible", ["2", "35", "45"])
def test_validar_regla_rechaza_respuesta_sobre_campo_sensible(campo_sensible):
    regla = ReglaHost(
        nombre="R", prioridad=1, activa=True,
        condiciones=(CondicionRegla(CAMPO_MTI, "igual", "0200"),),
        respuesta=RespuestaRegla(de39="00", campos_adicionales={campo_sensible: "x"}),
    )
    with pytest.raises(ValueError, match="sensible"):
        validar_regla(regla, PERFIL_GENERICO)


def test_validar_regla_rechaza_campo_inexistente_en_el_perfil():
    regla = _regla(condiciones=(CondicionRegla("999", "igual", "x"),))
    with pytest.raises(ValueError, match="no existe"):
        validar_regla(regla, PERFIL_GENERICO)


def test_validar_regla_acepta_condicion_sobre_mti_sin_tocar_el_perfil():
    regla = _regla()
    validar_regla(regla, PERFIL_GENERICO)  # no debe lanzar


def test_validar_regla_rechaza_de39_de_longitud_incorrecta():
    regla = _regla(de39="0")
    with pytest.raises(ValueError, match="DE39"):
        validar_regla(regla, PERFIL_GENERICO)


def test_validar_regla_rechaza_generador_desconocido():
    regla = ReglaHost(
        nombre="R", prioridad=1, activa=True,
        condiciones=(CondicionRegla(CAMPO_MTI, "igual", "0200"),),
        respuesta=RespuestaRegla(de39="00", campos_adicionales={"41": "@no_existe"}),
    )
    with pytest.raises(ValueError, match="generador"):
        validar_regla(regla, PERFIL_GENERICO)


def test_mensaje_de_error_de_validacion_nunca_incluye_el_valor():
    pan = pan_sintetico("4242")
    regla = _regla(condiciones=(CondicionRegla("2", "igual", pan),))
    with pytest.raises(ValueError) as exc:
        validar_regla(regla, PERFIL_GENERICO)
    assert pan not in str(exc.value)

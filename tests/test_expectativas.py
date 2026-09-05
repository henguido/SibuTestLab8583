"""Bloque 3: expected vs actual, a nivel de dominio puro.

`evaluar_expectativas` no toca red, ni base de datos, ni el orquestador: solo
compara valores ya resueltos. Estas pruebas cubren los tres tipos de
expectativa de campo, la expectativa de estado, timeout/sin-respuesta,
sin-expectativas, y las dos funciones de politica (`campos_permitidos_expectativa`,
`incompatibilidades_expectativas`).
"""

from __future__ import annotations

import pytest

from sibutestlab8583.domain.expectativas import (
    TIPOS_EXPECTATIVA_CAMPO,
    campos_permitidos_expectativa,
    discrepancia_a_dict,
    evaluacion_a_dict,
    evaluar_expectativas,
    expectativas_a_dict,
    expectativas_desde_dict,
    incompatibilidades_expectativas,
    validar_expectativas,
)
from sibutestlab8583.domain.modelos import (
    CAMPOS_SENSIBLES,
    MTI_RESPUESTA_COMPRA,
    CampoInterpretado,
    EstadoEjecucion,
    EstadoEvaluacion,
    ExpectativaCampo,
    Expectativas,
    MensajeInterpretado,
)
from sibutestlab8583.profiles.generico import PERFIL_GENERICO


def _respuesta(**campos: str) -> MensajeInterpretado:
    return MensajeInterpretado(
        mti=MTI_RESPUESTA_COMPRA,
        campos={
            numero: CampoInterpretado(numero=numero, valor=valor, crudo=valor, descripcion="")
            for numero, valor in campos.items()
        },
    )


# ------------------------------------------------------- campos permitidos ---


def test_campos_permitidos_excluye_siempre_los_sensibles():
    permitidos = campos_permitidos_expectativa(PERFIL_GENERICO, MTI_RESPUESTA_COMPRA)
    assert permitidos.isdisjoint(CAMPOS_SENSIBLES)


def test_campos_permitidos_incluye_opcionales_no_solo_obligatorios():
    """DE39 no es obligatorio en todos los perfiles de solicitud, pero como
    campo de RESPUESTA debe poder usarse en una expectativa literal.
    """
    permitidos = campos_permitidos_expectativa(PERFIL_GENERICO, MTI_RESPUESTA_COMPRA)
    assert "39" in permitidos


def test_campos_permitidos_vacio_si_el_perfil_no_soporta_el_mti():
    class PerfilSinSoporte:
        def soporta(self, mti):
            return False

    assert campos_permitidos_expectativa(PerfilSinSoporte(), "9999") == frozenset()


# ------------------------------------------------------------- validacion ---


def test_validar_expectativas_rechaza_campo_sensible():
    campo_sensible = next(iter(CAMPOS_SENSIBLES))
    expectativas = Expectativas(campos={campo_sensible: ExpectativaCampo(tipo="presente")})
    with pytest.raises(ValueError):
        validar_expectativas(expectativas, PERFIL_GENERICO, MTI_RESPUESTA_COMPRA)


def test_validar_expectativas_rechaza_tipo_desconocido():
    expectativas = Expectativas(campos={"39": ExpectativaCampo(tipo="contains", valor="0")})
    with pytest.raises(ValueError):
        validar_expectativas(expectativas, PERFIL_GENERICO, MTI_RESPUESTA_COMPRA)


def test_validar_expectativas_igual_sin_valor_es_invalido():
    expectativas = Expectativas(campos={"39": ExpectativaCampo(tipo="igual", valor=None)})
    with pytest.raises(ValueError):
        validar_expectativas(expectativas, PERFIL_GENERICO, MTI_RESPUESTA_COMPRA)


def test_validar_expectativas_acepta_los_tres_tipos_en_un_campo_permitido():
    for tipo in TIPOS_EXPECTATIVA_CAMPO:
        valor = "00" if tipo == "igual" else None
        expectativas = Expectativas(campos={"39": ExpectativaCampo(tipo=tipo, valor=valor)})
        validar_expectativas(expectativas, PERFIL_GENERICO, MTI_RESPUESTA_COMPRA)  # no revienta


def test_incompatibilidades_detecta_un_campo_que_ya_no_esta_permitido():
    campo_sensible = next(iter(CAMPOS_SENSIBLES))
    expectativas = Expectativas(campos={campo_sensible: ExpectativaCampo(tipo="presente")})
    problemas = incompatibilidades_expectativas(expectativas, PERFIL_GENERICO, MTI_RESPUESTA_COMPRA)
    assert problemas
    assert campo_sensible in problemas[0]


def test_incompatibilidades_vacio_cuando_todo_es_valido():
    expectativas = Expectativas(campos={"39": ExpectativaCampo(tipo="igual", valor="00")})
    assert incompatibilidades_expectativas(expectativas, PERFIL_GENERICO, MTI_RESPUESTA_COMPRA) == ()


# ------------------------------------------------------- sin expectativas ---


def test_sin_expectativas_no_evalua_nada():
    resultado = evaluar_expectativas(None, EstadoEjecucion.APROBADA, _respuesta(**{"39": "00"}))
    assert resultado is None


# ------------------------------------------------------------------ estado ---


def test_estado_esperado_igual_al_real_es_pass():
    expectativas = Expectativas(estado=EstadoEjecucion.RECHAZADA)
    resultado = evaluar_expectativas(expectativas, EstadoEjecucion.RECHAZADA, _respuesta(**{"39": "05"}))
    assert resultado.estado is EstadoEvaluacion.PASS
    assert resultado.discrepancias == ()


def test_estado_esperado_distinto_del_real_es_fail_con_discrepancia_de_estado():
    expectativas = Expectativas(estado=EstadoEjecucion.APROBADA)
    resultado = evaluar_expectativas(expectativas, EstadoEjecucion.RECHAZADA, _respuesta(**{"39": "05"}))
    assert resultado.estado is EstadoEvaluacion.FAIL
    assert len(resultado.discrepancias) == 1
    discrepancia = resultado.discrepancias[0]
    assert discrepancia.criterio == "estado"
    assert discrepancia.esperado == "aprobada"
    assert discrepancia.recibido == "rechazada"


def test_estado_aprobada_no_se_traduce_a_de39_igual_00():
    """El catalogo podria aprobar un codigo distinto de 00: la expectativa de
    estado usa RN-1 (via `estado_real`), nunca compara el codigo a mano.
    """
    expectativas = Expectativas(estado=EstadoEjecucion.APROBADA)
    # DE39 = "05", pero el estado real ya resulto APROBADA (p.ej. un catalogo
    # que acepta "05"): la expectativa de estado debe pasar igual.
    resultado = evaluar_expectativas(expectativas, EstadoEjecucion.APROBADA, _respuesta(**{"39": "05"}))
    assert resultado.estado is EstadoEvaluacion.PASS


def test_estado_aprobada_y_de39_igual_00_pueden_discrepar_legitimamente():
    """Doble criterio: estado=aprobada (pasa, via catalogo) + DE39==00 (falla,
    literal). Es un FAIL global, no un falso negativo.
    """
    expectativas = Expectativas(
        estado=EstadoEjecucion.APROBADA,
        campos={"39": ExpectativaCampo(tipo="igual", valor="00")},
    )
    resultado = evaluar_expectativas(expectativas, EstadoEjecucion.APROBADA, _respuesta(**{"39": "05"}))
    assert resultado.estado is EstadoEvaluacion.FAIL
    assert len(resultado.discrepancias) == 1
    assert resultado.discrepancias[0].criterio == "campo"
    assert resultado.discrepancias[0].campo == "39"


# ------------------------------------------------------------- campo igual ---


def test_campo_igual_coincide_es_pass():
    expectativas = Expectativas(campos={"39": ExpectativaCampo(tipo="igual", valor="00")})
    resultado = evaluar_expectativas(expectativas, EstadoEjecucion.APROBADA, _respuesta(**{"39": "00"}))
    assert resultado.estado is EstadoEvaluacion.PASS


def test_campo_igual_no_coincide_es_fail():
    expectativas = Expectativas(campos={"39": ExpectativaCampo(tipo="igual", valor="00")})
    resultado = evaluar_expectativas(expectativas, EstadoEjecucion.RECHAZADA, _respuesta(**{"39": "05"}))
    assert resultado.estado is EstadoEvaluacion.FAIL
    assert resultado.discrepancias[0].esperado == "00"
    assert resultado.discrepancias[0].recibido == "05"


# --------------------------------------------------------- campo presente ---


def test_campo_presente_cuando_llega_es_pass():
    expectativas = Expectativas(campos={"41": ExpectativaCampo(tipo="presente")})
    resultado = evaluar_expectativas(
        expectativas, EstadoEjecucion.APROBADA, _respuesta(**{"39": "00", "41": "TERM0001"})
    )
    assert resultado.estado is EstadoEvaluacion.PASS


def test_campo_presente_cuando_falta_es_fail():
    expectativas = Expectativas(campos={"41": ExpectativaCampo(tipo="presente")})
    resultado = evaluar_expectativas(expectativas, EstadoEjecucion.APROBADA, _respuesta(**{"39": "00"}))
    assert resultado.estado is EstadoEvaluacion.FAIL
    assert resultado.discrepancias[0].tipo == "presente"


# ---------------------------------------------------------- campo ausente ---


def test_campo_ausente_cuando_no_llega_es_pass():
    expectativas = Expectativas(campos={"41": ExpectativaCampo(tipo="ausente")})
    resultado = evaluar_expectativas(expectativas, EstadoEjecucion.APROBADA, _respuesta(**{"39": "00"}))
    assert resultado.estado is EstadoEvaluacion.PASS


def test_campo_ausente_cuando_llega_es_fail():
    expectativas = Expectativas(campos={"41": ExpectativaCampo(tipo="ausente")})
    resultado = evaluar_expectativas(
        expectativas, EstadoEjecucion.APROBADA, _respuesta(**{"39": "00", "41": "TERM0001"})
    )
    assert resultado.estado is EstadoEvaluacion.FAIL
    assert resultado.discrepancias[0].recibido == "TERM0001"


# -------------------------------------------------------- timeout / error ---


def test_timeout_esperado_y_obtenido_es_pass_sin_respuesta():
    expectativas = Expectativas(estado=EstadoEjecucion.TIMEOUT)
    resultado = evaluar_expectativas(expectativas, EstadoEjecucion.TIMEOUT, None)
    assert resultado.estado is EstadoEvaluacion.PASS
    assert resultado.discrepancias == ()


def test_timeout_esperado_pero_ademas_se_esperaba_un_campo_presente_falla_esa_parte():
    expectativas = Expectativas(
        estado=EstadoEjecucion.TIMEOUT,
        campos={"39": ExpectativaCampo(tipo="presente")},
    )
    resultado = evaluar_expectativas(expectativas, EstadoEjecucion.TIMEOUT, None)
    assert resultado.estado is EstadoEvaluacion.FAIL
    assert len(resultado.discrepancias) == 1
    assert resultado.discrepancias[0].tipo == "presente"


def test_sin_respuesta_un_campo_ausente_pasa():
    expectativas = Expectativas(campos={"39": ExpectativaCampo(tipo="ausente")})
    resultado = evaluar_expectativas(expectativas, EstadoEjecucion.ERROR_CONEXION, None)
    assert resultado.estado is EstadoEvaluacion.PASS


# --------------------------------------------------------------- multiples ---


def test_multiples_discrepancias_se_acumulan_todas():
    expectativas = Expectativas(
        estado=EstadoEjecucion.APROBADA,
        campos={
            "39": ExpectativaCampo(tipo="igual", valor="00"),
            "41": ExpectativaCampo(tipo="presente"),
        },
    )
    resultado = evaluar_expectativas(expectativas, EstadoEjecucion.RECHAZADA, _respuesta(**{"39": "05"}))
    assert resultado.estado is EstadoEvaluacion.FAIL
    criterios = {(d.criterio, d.campo) for d in resultado.discrepancias}
    assert ("estado", None) in criterios
    assert ("campo", "39") in criterios
    assert ("campo", "41") in criterios


# ------------------------------------------------------------ serializacion ---


def test_expectativas_a_dict_y_de_vuelta_es_identidad():
    original = Expectativas(
        estado=EstadoEjecucion.APROBADA,
        campos={"39": ExpectativaCampo(tipo="igual", valor="00"), "41": ExpectativaCampo(tipo="presente")},
    )
    reconstruida = expectativas_desde_dict(expectativas_a_dict(original))
    assert reconstruida.estado == original.estado
    assert dict(reconstruida.campos) == dict(original.campos)


def test_expectativas_a_dict_sin_estado_serializa_none():
    datos = expectativas_a_dict(Expectativas(campos={"39": ExpectativaCampo(tipo="presente")}))
    assert datos["estado"] is None


def test_discrepancia_a_dict_conserva_todos_los_campos():
    expectativas = Expectativas(campos={"39": ExpectativaCampo(tipo="igual", valor="00")})
    resultado = evaluar_expectativas(expectativas, EstadoEjecucion.RECHAZADA, _respuesta(**{"39": "05"}))
    datos = discrepancia_a_dict(resultado.discrepancias[0])
    assert datos == {
        "criterio": "campo",
        "campo": "39",
        "tipo": "igual",
        "esperado": "00",
        "recibido": "05",
    }


def test_evaluacion_a_dict_arma_el_snapshot_completo():
    expectativas = Expectativas(
        estado=EstadoEjecucion.APROBADA,
        campos={"39": ExpectativaCampo(tipo="igual", valor="00")},
    )
    resultado = evaluar_expectativas(expectativas, EstadoEjecucion.APROBADA, _respuesta(**{"39": "05"}))
    datos = evaluacion_a_dict(expectativas, resultado)
    assert datos["resultado"] == "fail"
    assert datos["expectativas"]["estado"] == "aprobada"
    assert datos["expectativas"]["campos"]["39"] == {"tipo": "igual", "valor": "00"}
    assert len(datos["discrepancias"]) == 1
    assert datos["discrepancias"][0]["campo"] == "39"

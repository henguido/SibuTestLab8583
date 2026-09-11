"""Comparacion descriptiva Request vs Response (Bloque 8/9 del Isoscopio 2.0).

No confundir con Expected vs Actual (`tests/test_expectativas.py` y
`tests/test_reglas_negocio.py`): esa es la aserción de prueba de un escenario;
esta es puramente descriptiva de dos mensajes, sin juicio de correctitud.
"""

from __future__ import annotations

from sibutestlab8583.domain.comparacion_mensajes import (
    CampoComparado,
    EstadoComparacionCampo,
    comparar_campos,
)
from sibutestlab8583.domain.datos_sinteticos import monto_iso


def test_mismo_campo_mismo_valor_es_coincide():
    resultado = comparar_campos({"3": "000000"}, {"3": "000000"})
    assert resultado == [
        CampoComparado("3", "000000", "000000", EstadoComparacionCampo.COINCIDE)
    ]


def test_mismo_campo_distinto_valor_es_diferente():
    resultado = comparar_campos({"41": "TERM0001"}, {"41": "TERM0002"})
    assert resultado == [
        CampoComparado("41", "TERM0001", "TERM0002", EstadoComparacionCampo.DIFERENTE)
    ]


def test_un_campo_solo_en_request_es_solo_request():
    resultado = comparar_campos({"22": "011"}, {})
    assert resultado == [
        CampoComparado("22", "011", None, EstadoComparacionCampo.SOLO_REQUEST)
    ]


def test_un_campo_solo_en_response_es_solo_response():
    """DE39 (codigo de respuesta) es el caso real mas comun: por construccion
    del protocolo, solo viaja en la respuesta -nunca en la solicitud-.
    """
    resultado = comparar_campos({}, {"39": "00"})
    assert resultado == [
        CampoComparado("39", None, "00", EstadoComparacionCampo.SOLO_RESPONSE)
    ]


def test_solicitud_vacia_no_rompe_la_comparacion():
    resultado = comparar_campos({}, {"39": "00", "3": "000000"})
    assert {c.numero for c in resultado} == {"3", "39"}
    assert all(c.request is None for c in resultado)


def test_respuesta_vacia_o_ausente_no_rompe_la_comparacion():
    resultado = comparar_campos({"3": "000000", "4": monto_iso("15000")}, {})
    assert {c.numero for c in resultado} == {"3", "4"}
    assert all(c.response is None for c in resultado)
    assert all(c.estado == EstadoComparacionCampo.SOLO_REQUEST for c in resultado)


def test_dos_mensajes_vacios_da_una_lista_vacia():
    assert comparar_campos({}, {}) == []


def test_un_valor_sensible_ya_enmascarado_se_compara_como_cualquier_otro():
    """Esta funcion nunca ve el PAN en claro: solo compara los strings que ya
    llegaron enmascarados de `MensajeIso.enmascarado()`/`MensajeInterpretado.
    enmascarado()`. Dos representaciones enmascaradas iguales dan COINCIDE.
    """
    resultado = comparar_campos({"2": "************6666"}, {"2": "************6666"})
    assert resultado == [
        CampoComparado("2", "************6666", "************6666", EstadoComparacionCampo.COINCIDE)
    ]


def test_los_campos_quedan_ordenados_numericamente():
    resultado = comparar_campos({"41": "x", "3": "y", "128": "z"}, {})
    assert [c.numero for c in resultado] == ["3", "41", "128"]


def test_comparar_campos_no_pierde_ningun_campo_de_ninguno_de_los_dos_lados():
    resultado = comparar_campos({"3": "a", "4": "b"}, {"4": "b", "39": "c"})
    numeros = {c.numero for c in resultado}
    assert numeros == {"3", "4", "39"}

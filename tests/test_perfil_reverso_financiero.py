"""Perfil del reverso financiero (0400/0410, B7).

Un reverso no es un constructor libre (B7, punto 5): este modulo prueba que
la politica declarada lo refleja -sin editables ni opcionales-, que los
obligatorios describen exactamente lo que un 0400/0410 de este laboratorio
necesita, y que el perfil ahora SI soporta 0400/0410 (a diferencia de
`test_perfil_generico.py::test_solo_soporta_los_mti_del_alcance_aprobado`,
que confirma lo contrario para 0420/0430 -todavia fuera de alcance-).
"""

from __future__ import annotations

from sibutestlab8583.domain.modelos import (
    MTI_RESPUESTA_REVERSO_FINANCIERO,
    MTI_REVERSO_FINANCIERO,
)
from sibutestlab8583.profiles.generico import (
    OBLIGATORIOS_0400,
    OBLIGATORIOS_0410,
    PERFIL_GENERICO,
)


def test_el_perfil_soporta_0400_y_0410():
    assert PERFIL_GENERICO.soporta(MTI_REVERSO_FINANCIERO)
    assert PERFIL_GENERICO.soporta(MTI_RESPUESTA_REVERSO_FINANCIERO)


def test_obligatorios_del_reverso_describen_un_intercambio_valido():
    # Nuevo intercambio (proceso/fecha/STAN) + referencia al original (monto,
    # terminal, moneda). DE37 (RRN) NO es obligatorio: el original pudo no
    # haberlo tenido (ver profiles/generico.py, comentario de OBLIGATORIOS_0400).
    assert OBLIGATORIOS_0400 == frozenset({"3", "4", "7", "11", "41", "49"})
    assert "37" not in OBLIGATORIOS_0400


def test_obligatorios_de_la_respuesta_permiten_correlacion_rn3():
    assert OBLIGATORIOS_0410 == frozenset({"3", "4", "7", "11", "39", "41"})


def test_la_politica_no_declara_ningun_campo_editable_ni_opcional():
    politica = PERFIL_GENERICO.politica(MTI_REVERSO_FINANCIERO)
    assert politica.editables == frozenset()
    assert politica.opcionales == frozenset()


def test_de4_de41_de49_de37_son_derivados_no_texto_libre():
    politica = PERFIL_GENERICO.politica(MTI_REVERSO_FINANCIERO)
    for numero in ("4", "37", "41", "49"):
        assert politica.origen(numero) == "derivado"


def test_de3_de7_de11_son_automaticos_nunca_del_original():
    politica = PERFIL_GENERICO.politica(MTI_REVERSO_FINANCIERO)
    for numero in ("3", "7", "11"):
        assert politica.origen(numero) == "automatico"


def test_de90_no_esta_declarado_en_la_especificacion_generica():
    # B6 ya lo habia confirmado; B7 lo revisa de nuevo con la composicion
    # exacta en mano (ver docstring de profiles/generico.py, seccion
    # "Reverso financiero") y decide, con evidencia, no implementarlo.
    assert "90" not in PERFIL_GENERICO.especificacion

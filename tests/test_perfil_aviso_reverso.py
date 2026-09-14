"""Perfil del aviso de reverso (0420/0430, B8).

Espejo de `test_perfil_reverso_financiero.py`: la politica se declara de
cero para 0420/0430 (nunca referenciando la de 0400/0410, ver
`profiles/generico.py`), y el perfil ahora SI soporta 0420/0430 -a
diferencia de `test_perfil_generico.py::
test_solo_soporta_los_mti_del_alcance_aprobado`, que confirma que el resto
(retiro, consulta de saldo) sigue fuera de alcance-.
"""

from __future__ import annotations

from sibutestlab8583.domain.modelos import (
    MTI_AVISO_REVERSO,
    MTI_RESPUESTA_AVISO_REVERSO,
)
from sibutestlab8583.profiles.generico import (
    OBLIGATORIOS_0400,
    OBLIGATORIOS_0410,
    OBLIGATORIOS_0420,
    OBLIGATORIOS_0430,
    PERFIL_GENERICO,
)


def test_el_perfil_soporta_0420_y_0430():
    assert PERFIL_GENERICO.soporta(MTI_AVISO_REVERSO)
    assert PERFIL_GENERICO.soporta(MTI_RESPUESTA_AVISO_REVERSO)


def test_obligatorios_del_aviso_describen_un_intercambio_valido():
    assert OBLIGATORIOS_0420 == frozenset({"3", "4", "7", "11", "41", "49"})
    assert "37" not in OBLIGATORIOS_0420


def test_obligatorios_de_la_respuesta_permiten_correlacion_rn3():
    assert OBLIGATORIOS_0430 == frozenset({"3", "4", "7", "11", "39", "41"})


def test_la_politica_no_declara_ningun_campo_editable_ni_opcional():
    politica = PERFIL_GENERICO.politica(MTI_AVISO_REVERSO)
    assert politica.editables == frozenset()
    assert politica.opcionales == frozenset()


def test_de4_de41_de49_de37_son_derivados_no_texto_libre():
    politica = PERFIL_GENERICO.politica(MTI_AVISO_REVERSO)
    for numero in ("4", "37", "41", "49"):
        assert politica.origen(numero) == "derivado"


def test_de3_de7_de11_son_automaticos_nunca_del_original():
    politica = PERFIL_GENERICO.politica(MTI_AVISO_REVERSO)
    for numero in ("3", "7", "11"):
        assert politica.origen(numero) == "automatico"


def test_de90_no_esta_declarado_en_la_especificacion_generica():
    assert "90" not in PERFIL_GENERICO.especificacion


def test_los_obligatorios_de_0420_se_declaran_aparte_de_los_de_0400():
    """B8 punto 7: 0420 no referencia la politica/obligatorios de 0400 aunque
    hoy compartan forma -son constantes distintas, no un alias."""
    assert OBLIGATORIOS_0420 is not OBLIGATORIOS_0400
    assert OBLIGATORIOS_0430 is not OBLIGATORIOS_0410
    politica_0400 = PERFIL_GENERICO.politica("0400")
    politica_0420 = PERFIL_GENERICO.politica(MTI_AVISO_REVERSO)
    assert politica_0400 is not politica_0420

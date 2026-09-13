"""El perfil generico soporta 0800/0810 (Network Management/Echo, B2).

Mismo criterio que `test_perfil_generico.py` para 0100/0110: no basta con que
el objeto exista, hay que probarlo contra pyiso8583 de verdad. B2 (2026-09-12)
es la primera operacion distinta de compra que demuestra que el nucleo
generico (PerfilDeMarca/PoliticaCamposMti, ya genericos desde B1) soporta mas
de un MTI real sin ningun cambio de forma.
"""

from __future__ import annotations

import iso8583
import pytest

from sibutestlab8583.domain.modelos import MTI_ECHO, MTI_RESPUESTA_ECHO
from sibutestlab8583.profiles.generico import (
    METADATOS_CAMPOS_0800,
    PERFIL_GENERICO,
    VALOR_LABORATORIO_ECHO,
    perfil_activo,
)


def test_el_perfil_soporta_echo():
    perfil = perfil_activo()
    assert perfil.soporta(MTI_ECHO)
    assert perfil.soporta(MTI_RESPUESTA_ECHO)


def test_obligatorios_del_echo_no_incluyen_tarjeta_ni_monto():
    obligatorios = PERFIL_GENERICO.obligatorios(MTI_ECHO)
    assert obligatorios == frozenset({"7", "11", "70"})
    assert "2" not in obligatorios, "un echo no tiene tarjeta"
    assert "4" not in obligatorios, "un echo no tiene monto"


def test_obligatorios_de_la_respuesta_del_echo_incluyen_de39():
    """DE39 se incluye a proposito para que el echo reutilice RN-1/RN-3 sin
    ningun camino especial en domain/validacion.py -ver profiles/generico.py,
    docstring de OBLIGATORIOS_0810-."""
    obligatorios = PERFIL_GENERICO.obligatorios(MTI_RESPUESTA_ECHO)
    assert obligatorios == frozenset({"7", "11", "39", "70"})


def test_politica_del_echo_no_tiene_derivados():
    """Sin tarjeta involucrada: nada se deriva de un dato externo."""
    politica = PERFIL_GENERICO.politica(MTI_ECHO)
    assert politica.derivados == frozenset()


def test_de7_y_de11_son_automaticos_en_el_echo():
    politica = PERFIL_GENERICO.politica(MTI_ECHO)
    assert politica.origen("7") == "automatico"
    assert politica.origen("11") == "automatico"


def test_de70_es_editable_con_default_de_laboratorio():
    politica = PERFIL_GENERICO.politica(MTI_ECHO)
    assert politica.origen("70") == "editable"
    assert politica.valores_por_defecto["70"] == VALOR_LABORATORIO_ECHO


def test_ningun_campo_de_compra_es_valido_en_echo():
    """DE2/DE3/DE4/DE14/DE22/DE41/DE49 (tarjeta, monto, comercio) no son parte
    de este MTI en absoluto: no deben aparecer bajo ninguna categoria."""
    politica = PERFIL_GENERICO.politica(MTI_ECHO)
    gobernados = politica.derivados | politica.automaticos | politica.editables | politica.opcionales
    for numero in ("2", "3", "4", "14", "22", "41", "42", "43", "49"):
        assert numero not in gobernados
        assert politica.origen(numero) == "no_permitido"


def test_la_especificacion_codifica_y_decodifica_un_0800():
    perfil = perfil_activo()
    solicitud = {
        "t": MTI_ECHO,
        "7": "0912143000",
        "11": "000001",
        "70": VALOR_LABORATORIO_ECHO,
    }
    crudo, _ = iso8583.encode(dict(solicitud), perfil.especificacion)
    decodificado, _ = iso8583.decode(crudo, perfil.especificacion)

    assert decodificado["t"] == MTI_ECHO
    for numero, valor in solicitud.items():
        assert decodificado[numero] == valor


def test_la_especificacion_decodifica_un_0810_con_de39():
    perfil = perfil_activo()
    respuesta = {
        "t": MTI_RESPUESTA_ECHO,
        "7": "0912143000",
        "11": "000001",
        "39": "00",
        "70": VALOR_LABORATORIO_ECHO,
    }
    crudo, _ = iso8583.encode(dict(respuesta), perfil.especificacion)
    decodificado, _ = iso8583.decode(crudo, perfil.especificacion)

    assert decodificado["t"] == MTI_RESPUESTA_ECHO
    assert decodificado["39"] == "00"


def test_la_politica_del_echo_solo_referencia_campos_de_la_especificacion():
    politica = PERFIL_GENERICO.politica(MTI_ECHO)
    numeros_gobernados = politica.derivados | politica.automaticos | politica.editables
    numeros_de_la_especificacion = set(PERFIL_GENERICO.especificacion) - {"h", "t", "p"}
    assert numeros_gobernados <= numeros_de_la_especificacion


def test_la_politica_del_echo_cubre_todos_sus_obligatorios():
    politica = PERFIL_GENERICO.politica(MTI_ECHO)
    numeros_gobernados = politica.derivados | politica.automaticos | politica.editables
    assert PERFIL_GENERICO.obligatorios(MTI_ECHO) <= numeros_gobernados


def test_de70_tiene_metadata_consistente_con_la_especificacion():
    metadato = METADATOS_CAMPOS_0800["70"]
    definicion = PERFIL_GENERICO.especificacion["70"]
    assert metadato.longitud_maxima == definicion["max_len"]
    assert metadato.longitud_fija == (definicion["len_type"] == 0)
    assert metadato.descripcion == definicion["desc"]


def test_todo_editable_del_echo_tiene_metadata():
    politica = PERFIL_GENERICO.politica(MTI_ECHO)
    numeros_editables_u_opcionales = politica.editables | politica.opcionales
    assert numeros_editables_u_opcionales <= set(METADATOS_CAMPOS_0800)


def test_el_perfil_no_atribuye_echo_a_ninguna_marca_ni_red():
    """El valor de laboratorio de DE70 no debe presentarse como estandar de
    ninguna red real -ver VALOR_LABORATORIO_ECHO, documentado como
    convencion propia-."""
    ayuda = METADATOS_CAMPOS_0800["70"].ayuda.lower()
    assert "laboratorio" in ayuda or "convención" in ayuda or "convencion" in ayuda

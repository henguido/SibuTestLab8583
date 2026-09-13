"""El perfil generico soporta 0200/0210 (compra financiera, B4).

Mismo criterio que `test_perfil_echo.py` para 0800/0810: no basta con que el
objeto exista, hay que probarlo contra pyiso8583 de verdad. B4 (2026-09-13)
es la primera operacion Multi-MTI que vuelve a usar tarjeta y monto, y la
primera prueba real de que `operacion` y `mti` son conceptos separados -ver
`domain.modelos.OPERACION_COMPRA_FINANCIERA` vs `MTI_COMPRA_FINANCIERA`.
"""

from __future__ import annotations

import iso8583
import pytest

from sibutestlab8583.domain.datos_sinteticos import monto_iso, pan_sintetico
from sibutestlab8583.domain.modelos import (
    MTI_COMPRA,
    MTI_COMPRA_FINANCIERA,
    MTI_RESPUESTA_COMPRA_FINANCIERA,
    OPERACION_COMPRA,
    OPERACION_COMPRA_FINANCIERA,
    OPERACION_POR_MTI,
)
from sibutestlab8583.profiles.generico import (
    METADATOS_CAMPOS_0200,
    PERFIL_GENERICO,
    perfil_activo,
)


def test_el_perfil_soporta_compra_financiera():
    perfil = perfil_activo()
    assert perfil.soporta(MTI_COMPRA_FINANCIERA)
    assert perfil.soporta(MTI_RESPUESTA_COMPRA_FINANCIERA)


def test_obligatorios_de_la_compra_financiera_incluyen_tarjeta_y_monto():
    """A diferencia de echo, 0200 vuelve a exigir tarjeta y monto: es una
    operacion que mueve fondos, no una verificacion de conectividad."""
    obligatorios = PERFIL_GENERICO.obligatorios(MTI_COMPRA_FINANCIERA)
    assert "2" in obligatorios, "PAN"
    assert "4" in obligatorios, "monto"
    assert obligatorios == frozenset({"2", "3", "4", "7", "11", "14", "22", "41", "49"})


def test_obligatorios_de_la_respuesta_incluyen_de39():
    obligatorios = PERFIL_GENERICO.obligatorios(MTI_RESPUESTA_COMPRA_FINANCIERA)
    assert "39" in obligatorios


def test_la_operacion_es_distinta_de_compra_aunque_el_conjunto_de_campos_coincida():
    """Punto 3 de B4: no confundir MTI con operacion. 0100 y 0200 pueden
    auditarse con el mismo conjunto de campos (ver profiles/generico.py) sin
    que eso las vuelva la misma operacion."""
    assert OPERACION_POR_MTI[MTI_COMPRA] == OPERACION_COMPRA
    assert OPERACION_POR_MTI[MTI_COMPRA_FINANCIERA] == OPERACION_COMPRA_FINANCIERA
    assert OPERACION_COMPRA != OPERACION_COMPRA_FINANCIERA


def test_de38_no_es_editable_en_la_politica_de_compra_financiera():
    """Mismo motivo que en 0100: lo agrega el autorizador al aprobar."""
    politica = PERFIL_GENERICO.politica(MTI_COMPRA_FINANCIERA)
    assert politica.origen("38") == "no_permitido"


def test_metadatos_0200_conocen_los_mismos_campos_editables_que_la_politica():
    politica = PERFIL_GENERICO.politica(MTI_COMPRA_FINANCIERA)
    for numero in politica.editables:
        assert numero in METADATOS_CAMPOS_0200, numero


def test_especificacion_generica_ya_declara_los_campos_de_0200_para_pyiso8583():
    """0200/0210 no agregan ningun campo nuevo a `ESPECIFICACION_GENERICA`
    -reutilizan integramente el catalogo que 0100/0110 ya declaraba-: esta
    prueba lo confirma codificando/decodificando un 0200 real con pyiso8583."""
    documento = {
        "t": MTI_COMPRA_FINANCIERA,
        "2": pan_sintetico("6666"),
        "3": "000000",
        "4": monto_iso("5000"),
        "7": "0913120000",
        "11": "000001",
        "14": "3012",
        "22": "011",
        "41": "TERM0001",
        "49": "188",
    }
    crudo, _ = iso8583.encode(documento, PERFIL_GENERICO.especificacion)
    decodificado, _ = iso8583.decode(bytes(crudo), PERFIL_GENERICO.especificacion)
    assert decodificado["t"] == MTI_COMPRA_FINANCIERA
    assert decodificado["4"] == monto_iso("5000")

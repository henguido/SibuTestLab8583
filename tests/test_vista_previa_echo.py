"""Vista previa del 0800 (Network Management/Echo, B2).

Mismo criterio que `test_vista_previa.py` para compra: deriva del mismo
`armar_echo` real (nunca una segunda implementacion), DE7/DE11 quedan
marcados como no definitivos (automaticos), DE70 sí es definitivo salvo que
dependa de una variable no reproducible.
"""

from __future__ import annotations

from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.application.vista_previa import ServicioVistaPreviaEcho
from sibutestlab8583.domain.modelos import DatosEcho, MTI_ECHO
from sibutestlab8583.profiles.generico import PERFIL_GENERICO, VALOR_LABORATORIO_ECHO

CODEC = CodecIso8583()


def _servicio() -> ServicioVistaPreviaEcho:
    return ServicioVistaPreviaEcho(CODEC, PERFIL_GENERICO)


async def test_vista_previa_muestra_el_mti_0800():
    vista = await _servicio().construir(DatosEcho())
    assert vista.mti == MTI_ECHO


async def test_vista_previa_muestra_un_bitmap_valido():
    vista = await _servicio().construir(DatosEcho())
    assert vista.bitmap is not None
    assert vista.bitmap == vista.bitmap.upper()


async def test_de7_y_de11_quedan_marcados_como_no_definitivos():
    vista = await _servicio().construir(DatosEcho())
    por_numero = {c.numero: c for c in vista.campos}
    for numero in ("7", "11"):
        assert por_numero[numero].origen == "automatico"
        assert por_numero[numero].es_valor_definitivo is False


async def test_de70_es_definitivo_con_su_default():
    vista = await _servicio().construir(DatosEcho())
    por_numero = {c.numero: c for c in vista.campos}
    assert por_numero["70"].valor == VALOR_LABORATORIO_ECHO
    assert por_numero["70"].es_valor_definitivo is True


async def test_de70_con_variable_de_stan_no_es_definitivo():
    """{{stan}} en DE70 depende del STAN real: en preview usa el marcador, asi
    que no debe presentarse como el valor definitivo -mismo criterio que ya
    aplica a compra-."""
    vista = await _servicio().construir(DatosEcho(campos_manuales={"70": "{{stan}}"}))
    por_numero = {c.numero: c for c in vista.campos}
    assert por_numero["70"].es_valor_definitivo is False


async def test_ningun_campo_de_compra_aparece_en_la_vista_previa():
    vista = await _servicio().construir(DatosEcho())
    numeros = {c.numero for c in vista.campos}
    for numero in ("2", "3", "4", "14", "22", "41", "49"):
        assert numero not in numeros

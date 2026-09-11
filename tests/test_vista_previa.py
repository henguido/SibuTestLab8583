"""Vista previa del 0100 antes de transmitir (Bloque 7).

Cubre: que se derive del mismo `armar_compra` real (no una segunda
implementacion), que los automaticos queden marcados como no definitivos, que
un opcional agregado aparezca y uno no agregado no aparezca, que el PAN quede
enmascarado, y que una tarjeta inexistente/inactiva se rechace igual que en
la ejecucion real.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

import pytest

from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.application.vista_previa import (
    ServicioVistaPrevia,
    TarjetaNoDisponibleParaVistaPrevia,
)
from sibutestlab8583.domain.datos_sinteticos import pan_sintetico
from sibutestlab8583.domain.errores import CampoNoPermitido, CampoProtegido
from sibutestlab8583.domain.modelos import DatosCompra, TarjetaPrueba
from sibutestlab8583.profiles.generico import PERFIL_GENERICO

CODEC = CodecIso8583()


@dataclass
class _RepositorioTarjetasFalso:
    tarjetas: dict[str, TarjetaPrueba] = field(default_factory=dict)

    async def obtener(self, card_id: str) -> TarjetaPrueba | None:
        return self.tarjetas.get(card_id)


def _servicio(tarjetas: dict[str, TarjetaPrueba] | None = None) -> ServicioVistaPrevia:
    repo = _RepositorioTarjetasFalso(
        tarjetas
        or {"X": TarjetaPrueba(card_id="X", pan=pan_sintetico("6666"), expiracion="3012")}
    )
    return ServicioVistaPrevia(repo, CODEC, PERFIL_GENERICO)


async def test_vista_previa_muestra_el_mti():
    vista = await _servicio().construir(DatosCompra(card_id="X", monto=Decimal("10.00")))
    assert vista.mti == "0100"


async def test_vista_previa_muestra_un_bitmap_valido():
    vista = await _servicio().construir(DatosCompra(card_id="X", monto=Decimal("10.00")))
    assert vista.bitmap is not None
    assert vista.bitmap == vista.bitmap.upper()
    assert all(c in "0123456789ABCDEF" for c in vista.bitmap)


async def test_agregar_un_opcional_cambia_el_bitmap():
    sin_opcional = await _servicio().construir(DatosCompra(card_id="X", monto=Decimal("10.00")))
    con_opcional = await _servicio().construir(
        DatosCompra(card_id="X", monto=Decimal("10.00"), campos_manuales={"18": "5411"})
    )
    assert sin_opcional.bitmap != con_opcional.bitmap


async def test_los_automaticos_quedan_marcados_como_no_definitivos():
    vista = await _servicio().construir(DatosCompra(card_id="X", monto=Decimal("10.00")))
    por_numero = {c.numero: c for c in vista.campos}
    for numero in ("7", "11", "12", "13"):
        assert por_numero[numero].origen == "automatico"
        assert por_numero[numero].es_valor_definitivo is False


async def test_los_no_automaticos_quedan_marcados_como_definitivos():
    vista = await _servicio().construir(DatosCompra(card_id="X", monto=Decimal("10.00")))
    por_numero = {c.numero: c for c in vista.campos}
    for numero in ("2", "3", "4", "14", "22", "41", "49"):
        assert por_numero[numero].es_valor_definitivo is True


async def test_de4_estructural_no_se_rotula_no_permitido():
    """DE4 no esta en ninguna categoria de `PoliticaCamposMti` -es un campo
    estructural que `armar_compra` fija directo desde `DatosCompra.monto`-,
    asi que no debe aparecer como "no_permitido" (que significaria "esta
    prohibido"), sino como un origen propio que lo explique.
    """
    vista = await _servicio().construir(DatosCompra(card_id="X", monto=Decimal("10.00")))
    de4 = next(c for c in vista.campos if c.numero == "4")
    assert de4.origen == "estructural"


async def test_un_opcional_agregado_aparece_en_la_vista_previa():
    vista = await _servicio().construir(
        DatosCompra(card_id="X", monto=Decimal("10.00"), campos_manuales={"18": "5411"})
    )
    de18 = next((c for c in vista.campos if c.numero == "18"), None)
    assert de18 is not None
    assert de18.valor == "5411"
    assert de18.origen == "opcional"


async def test_un_opcional_no_agregado_no_aparece_en_la_vista_previa():
    vista = await _servicio().construir(DatosCompra(card_id="X", monto=Decimal("10.00")))
    assert not any(c.numero == "18" for c in vista.campos)


async def test_el_pan_aparece_enmascarado_en_la_vista_previa():
    vista = await _servicio().construir(DatosCompra(card_id="X", monto=Decimal("10.00")))
    de2 = next(c for c in vista.campos if c.numero == "2")
    assert de2.valor.startswith("*")
    assert de2.valor.endswith("6666")
    assert "*" * 4 in de2.valor


async def test_tarjeta_inexistente_se_rechaza():
    with pytest.raises(TarjetaNoDisponibleParaVistaPrevia):
        await _servicio().construir(DatosCompra(card_id="NO-EXISTE", monto=Decimal("10.00")))


async def test_tarjeta_inactiva_se_rechaza():
    inactiva = TarjetaPrueba(
        card_id="X", pan=pan_sintetico("6666"), expiracion="3012", activa=False
    )
    servicio = _servicio({"X": inactiva})
    with pytest.raises(TarjetaNoDisponibleParaVistaPrevia):
        await servicio.construir(DatosCompra(card_id="X", monto=Decimal("10.00")))


async def test_un_campo_derivado_forzado_a_mano_se_rechaza_igual_que_en_la_ejecucion_real():
    with pytest.raises(CampoProtegido):
        await _servicio().construir(
            DatosCompra(card_id="X", monto=Decimal("10.00"), campos_manuales={"2": "9" * 16})
        )


async def test_un_campo_no_permitido_forzado_a_mano_se_rechaza():
    with pytest.raises(CampoNoPermitido):
        await _servicio().construir(
            DatosCompra(card_id="X", monto=Decimal("10.00"), campos_manuales={"38": "000000"})
        )

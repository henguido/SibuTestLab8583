"""`armar_compra_financiera` (0200, B4): mismo principio de capas que
`armar_compra`, y de hecho comparte con ella la capa 3 estructural completa
(`domain.armado._campos_estructurales_transaccion_con_tarjeta`) -B4 confirmo
que esa capa es identica entre ambas operaciones, ver docstring del modulo.

Cubre MTI, campos, defensa en profundidad, y round-trip de bitmap contra el
codec real -- mismo patron que `test_armado_echo.py`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.domain.armado import armar_compra, armar_compra_financiera
from sibutestlab8583.domain.datos_sinteticos import monto_iso, pan_sintetico
from sibutestlab8583.domain.errores import CampoNoPermitido, CampoProtegido
from sibutestlab8583.domain.modelos import (
    DatosCompra,
    DatosCompraFinanciera,
    MTI_COMPRA_FINANCIERA,
    TarjetaPrueba,
)
from sibutestlab8583.profiles.generico import (
    CODIGO_PROCESO_COMPRA_FINANCIERA,
    MODO_CAPTURA_DEMOSTRACION,
    PERFIL_GENERICO,
    TERMINAL_DEMOSTRACION,
)

MOMENTO = datetime(2026, 9, 13, 14, 30, 45, tzinfo=timezone.utc)


def _tarjeta() -> TarjetaPrueba:
    return TarjetaPrueba(card_id="X", pan=pan_sintetico("6666"), expiracion="3012")


def test_armar_compra_financiera_produce_el_mti_0200():
    mensaje = armar_compra_financiera(
        DatosCompraFinanciera(card_id="X", monto=Decimal("50.00")),
        _tarjeta(), stan="000001", momento=MOMENTO, perfil=PERFIL_GENERICO,
    )
    assert mensaje.mti == MTI_COMPRA_FINANCIERA


def test_de2_de4_de14_se_derivan_de_tarjeta_y_monto():
    tarjeta = _tarjeta()
    mensaje = armar_compra_financiera(
        DatosCompraFinanciera(card_id="X", monto=Decimal("50.00")),
        tarjeta, stan="000001", momento=MOMENTO, perfil=PERFIL_GENERICO,
    )
    assert mensaje.campos["2"] == tarjeta.pan
    assert mensaje.campos["4"] == monto_iso("5000")
    assert mensaje.campos["14"] == tarjeta.expiracion


def test_de7_de11_de12_de13_son_automaticos_del_sistema():
    mensaje = armar_compra_financiera(
        DatosCompraFinanciera(card_id="X", monto=Decimal("50.00")),
        _tarjeta(), stan="000042", momento=MOMENTO, perfil=PERFIL_GENERICO,
    )
    assert mensaje.campos["11"] == "000042"
    assert mensaje.campos["7"] == "0913143045"
    assert mensaje.campos["12"] == "143045"
    assert mensaje.campos["13"] == "0913"


def test_sin_campos_manuales_se_usan_los_defaults_del_perfil():
    mensaje = armar_compra_financiera(
        DatosCompraFinanciera(card_id="X", monto=Decimal("10.00")),
        _tarjeta(), stan="000001", momento=MOMENTO, perfil=PERFIL_GENERICO,
    )
    assert mensaje.campos["3"] == CODIGO_PROCESO_COMPRA_FINANCIERA
    assert mensaje.campos["22"] == MODO_CAPTURA_DEMOSTRACION
    assert mensaje.campos["41"] == TERMINAL_DEMOSTRACION
    assert mensaje.campos["49"] == "188"


def test_un_editable_provisto_reemplaza_su_default():
    mensaje = armar_compra_financiera(
        DatosCompraFinanciera(
            card_id="X", monto=Decimal("10.00"), campos_manuales={"37": "REF-QA-01"}
        ),
        _tarjeta(), stan="000001", momento=MOMENTO, perfil=PERFIL_GENERICO,
    )
    assert mensaje.campos["37"] == "REF-QA-01"
    assert mensaje.campos["3"] == CODIGO_PROCESO_COMPRA_FINANCIERA


def test_un_campo_derivado_o_automatico_manual_se_rechaza():
    with pytest.raises(CampoProtegido):
        armar_compra_financiera(
            DatosCompraFinanciera(card_id="X", monto=Decimal("10.00"), campos_manuales={"2": "9" * 16}),
            _tarjeta(), stan="000001", momento=MOMENTO, perfil=PERFIL_GENERICO,
        )


def test_de38_no_puede_fijarse_a_mano():
    with pytest.raises(CampoNoPermitido):
        armar_compra_financiera(
            DatosCompraFinanciera(card_id="X", monto=Decimal("10.00"), campos_manuales={"38": "000001"}),
            _tarjeta(), stan="000001", momento=MOMENTO, perfil=PERFIL_GENERICO,
        )


def test_la_capa_estructural_es_identica_a_la_de_compra_salvo_el_mti():
    """Confirma la extraccion de B4: dado el mismo stan/momento/tarjeta/monto,
    0100 y 0200 derivan los mismos siete campos estructurales."""
    tarjeta = _tarjeta()
    compra = armar_compra(
        DatosCompra(card_id="X", monto=Decimal("50.00")),
        tarjeta, stan="000007", momento=MOMENTO, perfil=PERFIL_GENERICO,
    )
    financiera = armar_compra_financiera(
        DatosCompraFinanciera(card_id="X", monto=Decimal("50.00")),
        tarjeta, stan="000007", momento=MOMENTO, perfil=PERFIL_GENERICO,
    )
    for numero in ("2", "4", "7", "11", "12", "13", "14"):
        assert compra.campos[numero] == financiera.campos[numero], numero
    assert compra.mti != financiera.mti


def test_bitmap_y_round_trip_real_contra_el_codec():
    codec = CodecIso8583()
    mensaje = armar_compra_financiera(
        DatosCompraFinanciera(card_id="X", monto=Decimal("50.00")),
        _tarjeta(), stan="000007", momento=MOMENTO, perfil=PERFIL_GENERICO,
    )

    bitmap = codec.bitmap_hex(mensaje.enmascarado(), PERFIL_GENERICO)
    assert bitmap == bitmap.upper()
    assert all(c in "0123456789ABCDEF" for c in bitmap)

    crudo = codec.codificar(mensaje, PERFIL_GENERICO)
    decodificado = codec.decodificar(crudo, PERFIL_GENERICO).como_mensaje()
    assert decodificado.mti == MTI_COMPRA_FINANCIERA
    assert decodificado.campos["4"] == mensaje.campos["4"]
    assert decodificado.campos["11"] == mensaje.campos["11"]

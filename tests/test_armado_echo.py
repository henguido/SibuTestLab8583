"""`armar_echo` (0800, B2): mismo principio de capas que `armar_compra`, sin
tarjeta ni monto. Cubre MTI, campos, defensa en profundidad, y round-trip de
bitmap contra el codec real -DE7/DE11 automaticos, DE70 editable con default.

Ver `domain/armado.py`, docstring del modulo, para por que `armar_echo` NO
copia el cuerpo de `armar_compra`: ambas reutilizan `_componer_campos_base`
para las capas 1+2 (defaults + overrides), y cada una agrega solo su propia
capa 3 estructural.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.domain.armado import armar_echo
from sibutestlab8583.domain.errores import CampoNoPermitido, CampoProtegido
from sibutestlab8583.domain.modelos import MTI_ECHO
from sibutestlab8583.profiles.generico import PERFIL_GENERICO, VALOR_LABORATORIO_ECHO

MOMENTO = datetime(2026, 9, 12, 14, 30, 45, tzinfo=timezone.utc)


class _DatosEcho:
    def __init__(self, campos_manuales=None):
        self.campos_manuales = campos_manuales or {}


def test_armar_echo_produce_el_mti_0800():
    mensaje = armar_echo(_DatosEcho(), stan="000001", momento=MOMENTO, perfil=PERFIL_GENERICO)
    assert mensaje.mti == MTI_ECHO


def test_de7_y_de11_son_automaticos_del_sistema():
    mensaje = armar_echo(_DatosEcho(), stan="000042", momento=MOMENTO, perfil=PERFIL_GENERICO)
    assert mensaje.campos["11"] == "000042"
    assert mensaje.campos["7"] == "0912143045"


def test_de70_usa_el_default_de_laboratorio_si_no_se_informa():
    mensaje = armar_echo(_DatosEcho(), stan="000001", momento=MOMENTO, perfil=PERFIL_GENERICO)
    assert mensaje.campos["70"] == VALOR_LABORATORIO_ECHO


def test_de70_puede_sobreescribirse_por_el_usuario():
    mensaje = armar_echo(
        _DatosEcho({"70": "001"}), stan="000001", momento=MOMENTO, perfil=PERFIL_GENERICO
    )
    assert mensaje.campos["70"] == "001"


def test_ningun_campo_de_compra_aparece_en_el_mensaje_armado():
    mensaje = armar_echo(_DatosEcho(), stan="000001", momento=MOMENTO, perfil=PERFIL_GENERICO)
    for numero in ("2", "3", "4", "14", "22", "41", "49"):
        assert numero not in mensaje.campos


def test_un_campo_derivado_o_automatico_manual_se_rechaza():
    """Defensa en profundidad identica a armar_compra: intentar fijar a mano
    un campo automatico (DE11) revienta, nunca se acepta en silencio."""
    with pytest.raises(CampoProtegido):
        armar_echo(
            _DatosEcho({"11": "999999"}), stan="000001", momento=MOMENTO, perfil=PERFIL_GENERICO
        )


def test_un_campo_de_compra_no_permitido_en_echo_se_rechaza():
    with pytest.raises(CampoNoPermitido):
        armar_echo(
            _DatosEcho({"41": "TERM0001"}), stan="000001", momento=MOMENTO, perfil=PERFIL_GENERICO
        )


def test_bitmap_y_round_trip_real_contra_el_codec():
    codec = CodecIso8583()
    mensaje = armar_echo(_DatosEcho(), stan="000007", momento=MOMENTO, perfil=PERFIL_GENERICO)

    bitmap = codec.bitmap_hex(mensaje, PERFIL_GENERICO)
    assert bitmap == bitmap.upper()
    assert all(c in "0123456789ABCDEF" for c in bitmap)

    crudo = codec.codificar(mensaje, PERFIL_GENERICO)
    decodificado = codec.decodificar(crudo, PERFIL_GENERICO).como_mensaje()
    assert decodificado.mti == MTI_ECHO
    assert decodificado.campos["7"] == mensaje.campos["7"]
    assert decodificado.campos["11"] == mensaje.campos["11"]
    assert decodificado.campos["70"] == mensaje.campos["70"]

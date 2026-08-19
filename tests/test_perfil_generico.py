"""El perfil generico carga y su especificacion sirve de verdad para un 0100/0110.

Comprobar solo que el objeto existe no probaria nada: una especificacion mal
formada tambien se carga. Por eso se verifica contra pyiso8583 que un mensaje
puede codificarse y volver a leerse.
"""

from __future__ import annotations

import iso8583
import pytest

from sibutestlab8583.domain.datos_sinteticos import monto_iso, pan_sintetico
from sibutestlab8583.domain.modelos import MTI_COMPRA, MTI_RESPUESTA_COMPRA
from sibutestlab8583.profiles.generico import (
    CODIGO_PROCESO_COMPRA,
    PERFIL_GENERICO,
    perfil_activo,
)


def test_el_perfil_activo_es_el_generico():
    perfil = perfil_activo()
    assert perfil is PERFIL_GENERICO
    assert perfil.nombre == "generico"


def test_solo_soporta_los_mti_del_alcance_aprobado():
    perfil = perfil_activo()
    assert perfil.soporta(MTI_COMPRA)
    assert perfil.soporta(MTI_RESPUESTA_COMPRA)
    # Fuera de alcance: reverso, retiro, consulta de saldo.
    for mti in ("0200", "0400", "0800"):
        assert not perfil.soporta(mti)
        with pytest.raises(ValueError):
            perfil.obligatorios(mti)


def test_obligatorios_de_la_compra_identifican_la_transaccion():
    obligatorios = perfil_activo().obligatorios(MTI_COMPRA)
    # Que tarjeta, que operacion, cuanto, en que moneda y con que trazabilidad.
    for campo in ("2", "3", "4", "11", "49"):
        assert campo in obligatorios


def test_la_respuesta_exige_el_codigo_de_respuesta():
    obligatorios = perfil_activo().obligatorios(MTI_RESPUESTA_COMPRA)
    assert "39" in obligatorios, "sin campo 39 no se puede aplicar RN-1"


def test_la_especificacion_codifica_y_decodifica_un_0100():
    perfil = perfil_activo()
    solicitud = {
        "t": MTI_COMPRA,
        "2": pan_sintetico("6666"),
        "3": CODIGO_PROCESO_COMPRA,
        "4": monto_iso("15000"),
        "7": "0818120000",
        "11": "000001",
        "14": "3012",
        "22": "051",
        "41": "TERM0001",
        "49": "188",
    }
    crudo, _ = iso8583.encode(dict(solicitud), perfil.especificacion)
    decodificado, _ = iso8583.decode(crudo, perfil.especificacion)

    assert decodificado["t"] == MTI_COMPRA
    for numero, valor in solicitud.items():
        assert decodificado[numero] == valor


def test_la_especificacion_decodifica_un_0110_con_codigo_de_respuesta():
    perfil = perfil_activo()
    respuesta = {
        "t": MTI_RESPUESTA_COMPRA,
        "3": CODIGO_PROCESO_COMPRA,
        "4": monto_iso("15000"),
        "7": "0818120000",
        "11": "000001",
        "39": "00",
        "41": "TERM0001",
    }
    crudo, _ = iso8583.encode(dict(respuesta), perfil.especificacion)
    decodificado, _ = iso8583.decode(crudo, perfil.especificacion)

    assert decodificado["t"] == MTI_RESPUESTA_COMPRA
    assert decodificado["39"] == "00"


def test_el_perfil_no_se_atribuye_a_ninguna_marca():
    """No hay perfiles de marca hasta tener documentos autorizados."""
    texto = repr(PERFIL_GENERICO.nombre).lower()
    for marca in ("visa", "mastercard", "amex", "american"):
        assert marca not in texto

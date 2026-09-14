"""Caracterizacion (punto 18 del checkpoint D1): la regla sintetica de
rechazo por monto (B4, hardcodeada en `HostSimulado._construir_respuesta`)
EXPRESADA en el motor declarativo (`regla_migrada_rechazo_sintetico_
financiero`) debe producir el MISMO resultado externo que la version
hardcodeada, para varios montos alrededor del umbral -incluido el limite
exacto, donde el operador estricto (`>`) importa-.

E2E real: TCP real, host real (una vez con las reglas migradas, otra vez
sin ninguna -el camino hardcodeado de siempre-), Orquestador real.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import construir_orquestador
from sibutestlab8583.adapters.persistence.esquema import inicializar
from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.host_simulado.servidor import (
    UMBRAL_SINTETICO_RECHAZO_FINANCIERO,
    regla_migrada_rechazo_sintetico_financiero,
)
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.adapters.transporte.tcp import TransporteTcp
from sibutestlab8583.domain.modelos import DatosCompraFinanciera, DestinoTcp
from sibutestlab8583.profiles.generico import PERFIL_GENERICO


def _host(**kwargs) -> HostSimulado:
    return HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), **kwargs)


async def _ejecutar(ruta, host, monto: Decimal):
    base = await inicializar(ruta)
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        orquestador = construir_orquestador(
            base, transporte, destino=DestinoTcp(host=host.host, puerto=host.puerto),
            tiempo_limite=2.0,
        )
        return await orquestador.ejecutar_compra_financiera(
            DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=monto)
        )


@pytest.mark.parametrize(
    "monto",
    [
        Decimal("1.00"),
        Decimal("50000.00"),
        UMBRAL_SINTETICO_RECHAZO_FINANCIERO,  # exactamente en el limite: NO rechaza (operador estricto >)
        UMBRAL_SINTETICO_RECHAZO_FINANCIERO + Decimal("0.01"),
        Decimal("999999.99"),
    ],
)
async def test_la_regla_migrada_produce_el_mismo_resultado_que_el_camino_hardcodeado(monto, tmp_path):
    hardcodeado = await _ejecutar(tmp_path / "hard.db", _host(), monto)

    rechazo, aprobacion = regla_migrada_rechazo_sintetico_financiero()
    migrado = await _ejecutar(
        tmp_path / "migrado.db", _host(reglas=[rechazo, aprobacion]), monto
    )

    assert migrado.estado == hardcodeado.estado
    assert migrado.respuesta.valor("39") == hardcodeado.respuesta.valor("39")
    # DE38 (autorizacion) solo viaja cuando se aprueba, en ambos caminos por igual.
    assert migrado.respuesta.valor("38") == hardcodeado.respuesta.valor("38")

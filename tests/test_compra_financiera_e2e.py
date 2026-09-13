"""E2E real de compra financiera (0200/0210, B4): Orquestador real, TCP real,
host simulado real, codec real, SQLite real. Misma evidencia que ya exige
`test_integracion_end_to_end.py` para compra y `test_echo_e2e.py` para echo,
aplicada a la tercera operacion -la prueba de que el nucleo generico de B1
sirve para una operacion que vuelve a usar tarjeta y monto, no solo para
compra ni solo para operaciones sin tarjeta.

Cubre en particular el punto 21 de B4: DE39="51" (rechazo sintetico por
monto) es un resultado transaccional valido, no un ERROR tecnico -y un
escenario que esperaba justamente ese codigo debe seguir dando PASS-.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import construir_orquestador
from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.host_simulado.servidor import UMBRAL_SINTETICO_RECHAZO_FINANCIERO
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO
from sibutestlab8583.adapters.persistence.sqlite_repos import RepositorioEjecucionesSQLite
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.adapters.transporte.tcp import TransporteTcp
from sibutestlab8583.domain.modelos import (
    DatosCompraFinanciera,
    DestinoTcp,
    EstadoEjecucion,
    EstadoEvaluacion,
    Expectativas,
    ExpectativaCampo,
    MTI_COMPRA_FINANCIERA,
    MTI_RESPUESTA_COMPRA_FINANCIERA,
)
from sibutestlab8583.profiles.generico import PERFIL_GENERICO


def _host(**kwargs) -> HostSimulado:
    return HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), **kwargs)


async def _ejecutar_contra(host, base, datos, *, tiempo_limite=2.0, expectativas=None):
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=tiempo_limite)
        orquestador = construir_orquestador(
            base,
            transporte,
            destino=DestinoTcp(host=host.host, puerto=host.puerto),
            tiempo_limite=tiempo_limite,
        )
        return await orquestador.ejecutar_compra_financiera(datos, expectativas=expectativas)


async def test_compra_financiera_aprobada_real_por_tcp(base):
    host = _host()
    datos = DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=Decimal("50.00"))
    resultado = await _ejecutar_contra(host, base, datos)

    assert host.solicitudes_recibidas == 1
    assert resultado.estado is EstadoEjecucion.APROBADA
    assert resultado.solicitud.mti == MTI_COMPRA_FINANCIERA
    assert resultado.respuesta is not None
    assert resultado.respuesta.mti == MTI_RESPUESTA_COMPRA_FINANCIERA
    assert resultado.respuesta.valor("39") == "00"
    assert resultado.motivos == ()


async def test_compra_financiera_rechazada_por_monto_sintetico(base):
    """Punto 13 de B4: sin pasar `--codigo`, un monto que supera el umbral
    sintetico de laboratorio produce DE39="51" por si solo."""
    host = _host()
    monto_rechazado = UMBRAL_SINTETICO_RECHAZO_FINANCIERO + Decimal("1.00")
    datos = DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=monto_rechazado)
    resultado = await _ejecutar_contra(host, base, datos)

    assert resultado.respuesta.valor("39") == "51"
    # RECHAZADA, nunca ERROR: un DE39 de rechazo es una respuesta valida del
    # autorizador, no un fallo tecnico del laboratorio (punto 22 de B4).
    assert resultado.estado is EstadoEjecucion.RECHAZADA


async def test_un_monto_bajo_el_umbral_se_sigue_aprobando(base):
    host = _host()
    datos = DatosCompraFinanciera(
        card_id=CARD_ID_DEMO, monto=UMBRAL_SINTETICO_RECHAZO_FINANCIERO - Decimal("1.00")
    )
    resultado = await _ejecutar_contra(host, base, datos)
    assert resultado.respuesta.valor("39") == "00"
    assert resultado.estado is EstadoEjecucion.APROBADA


async def test_expected_de39_51_da_pass_cuando_el_rechazo_era_lo_esperado(base):
    """Punto 21/22 de B4: un escenario que esperaba el rechazo sintetico debe
    dar PASS, nunca FAIL ni ERROR -el motor no confunde 'rechazo financiero'
    con 'fallo tecnico de prueba'."""
    host = _host()
    monto_rechazado = UMBRAL_SINTETICO_RECHAZO_FINANCIERO + Decimal("1.00")
    datos = DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=monto_rechazado)
    expectativas = Expectativas(campos={"39": ExpectativaCampo(tipo="igual", valor="51")})
    resultado = await _ejecutar_contra(host, base, datos, expectativas=expectativas)

    assert resultado.respuesta.valor("39") == "51"
    assert resultado.ejecucion.evaluacion_json is not None
    import json

    evaluacion = json.loads(resultado.ejecucion.evaluacion_json)
    assert evaluacion["resultado"] == EstadoEvaluacion.PASS.value


async def test_expected_de39_00_da_fail_cuando_la_respuesta_fue_rechazo(base):
    host = _host()
    monto_rechazado = UMBRAL_SINTETICO_RECHAZO_FINANCIERO + Decimal("1.00")
    datos = DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=monto_rechazado)
    expectativas = Expectativas(campos={"39": ExpectativaCampo(tipo="igual", valor="00")})
    resultado = await _ejecutar_contra(host, base, datos, expectativas=expectativas)

    import json

    evaluacion = json.loads(resultado.ejecucion.evaluacion_json)
    assert evaluacion["resultado"] == EstadoEvaluacion.FAIL.value


async def test_compra_financiera_persiste_tarjeta_y_monto_en_el_historial(base):
    host = _host()
    datos = DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=Decimal("50.00"))
    resultado = await _ejecutar_contra(host, base, datos)

    guardadas = await RepositorioEjecucionesSQLite(base).listar()
    assert len(guardadas) == 1
    ejecucion = guardadas[0]
    assert ejecucion.card_id == CARD_ID_DEMO
    assert ejecucion.monto == Decimal("50.00")
    assert ejecucion.mti_solicitud == MTI_COMPRA_FINANCIERA
    assert ejecucion.mti_respuesta == MTI_RESPUESTA_COMPRA_FINANCIERA


async def test_compra_financiera_no_reponde_produce_timeout(base):
    """RN-2 aplica igual que a compra/echo: sin respuesta, TIMEOUT."""
    host = _host(responder=False)
    datos = DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=Decimal("50.00"))
    resultado = await _ejecutar_contra(host, base, datos, tiempo_limite=0.2)
    assert resultado.estado is EstadoEjecucion.TIMEOUT

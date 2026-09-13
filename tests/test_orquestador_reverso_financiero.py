"""`Orquestador.ejecutar_reverso_financiero` (0400/0410, B7).

E2E real: TCP real, codec real, SQLite real, host simulado real -mismo
estilo que `test_compra_financiera_e2e.py`/`test_referencia_ejecucion.py`-.
Cubre el recorrido completo exigido por el checkpoint (punto 26):

    0200 -> 0210/00 -> ejecucion_id = A
    crear reverso desde A -> 0400 -> 0410/00 -> ejecucion_origen_id = A

y la reautenticacion de elegibilidad server-side (puntos 15/16): un origen
inexistente o no elegible (0200 rechazada, 0100, echo, sin respuesta)
revienta ANTES de generar ningun STAN ni tocar la red.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO
from sibutestlab8583.adapters.persistence.sqlite_repos import RepositorioEjecucionesSQLite
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.adapters.transporte.tcp import TransporteTcp
from sibutestlab8583.domain.errores import EjecucionOrigenNoElegible, EjecucionOrigenNoEncontrada
from sibutestlab8583.domain.modelos import (
    DatosCompra,
    DatosCompraFinanciera,
    DatosEcho,
    DatosReversoFinanciero,
    DestinoTcp,
    EstadoEjecucion,
    MTI_RESPUESTA_REVERSO_FINANCIERO,
    MTI_REVERSO_FINANCIERO,
)
from sibutestlab8583.profiles.generico import PERFIL_GENERICO

from conftest import construir_orquestador


def _host(**kwargs) -> HostSimulado:
    return HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), **kwargs)


async def test_reverso_real_desde_una_financiera_aprobada(base):
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        destino = DestinoTcp(host=host.host, puerto=host.puerto)
        orquestador = construir_orquestador(base, transporte, destino=destino, tiempo_limite=2.0)

        original = await orquestador.ejecutar_compra_financiera(
            DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=Decimal("80.00"))
        )
        assert original.estado is EstadoEjecucion.APROBADA

        reverso = await orquestador.ejecutar_reverso_financiero(
            DatosReversoFinanciero(ejecucion_origen_id=original.ejecucion.id)
        )

    assert reverso.estado is EstadoEjecucion.APROBADA
    assert reverso.ejecucion.mti_solicitud == MTI_REVERSO_FINANCIERO
    assert reverso.ejecucion.mti_respuesta == MTI_RESPUESTA_REVERSO_FINANCIERO
    # El nucleo de la operacion derivada: la nueva ejecucion apunta a la
    # original por identidad de fila, nunca por STAN/RRN.
    assert reverso.ejecucion.ejecucion_origen_id == original.ejecucion.id
    # El STAN del reverso es SIEMPRE nuevo.
    assert reverso.ejecucion.stan != original.ejecucion.stan

    repo = RepositorioEjecucionesSQLite(base)
    original_relectura = await repo.obtener(original.ejecucion.id)
    assert original_relectura.estado is EstadoEjecucion.APROBADA
    assert original_relectura.ejecucion_origen_id is None
    assert original_relectura.stan == original.ejecucion.stan
    assert original_relectura.monto == original.ejecucion.monto

    derivadas = await repo.listar_derivadas(original.ejecucion.id)
    assert [d.id for d in derivadas] == [reverso.ejecucion.id]


async def test_un_origen_inexistente_revienta_antes_de_generar_stan(base):
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        destino = DestinoTcp(host=host.host, puerto=host.puerto)
        orquestador = construir_orquestador(base, transporte, destino=destino, tiempo_limite=2.0)

        with pytest.raises(EjecucionOrigenNoEncontrada):
            await orquestador.ejecutar_reverso_financiero(
                DatosReversoFinanciero(ejecucion_origen_id=999999)
            )

    repo = RepositorioEjecucionesSQLite(base)
    assert await repo.listar(limite=10) == []


async def test_una_financiera_rechazada_no_es_elegible(base):
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        destino = DestinoTcp(host=host.host, puerto=host.puerto)
        orquestador = construir_orquestador(base, transporte, destino=destino, tiempo_limite=2.0)

        # Monto por encima del umbral sintetico de rechazo (ver
        # adapters/host_simulado/servidor.py).
        rechazada = await orquestador.ejecutar_compra_financiera(
            DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=Decimal("500000.00"))
        )
        assert rechazada.estado is EstadoEjecucion.RECHAZADA

        with pytest.raises(EjecucionOrigenNoElegible):
            await orquestador.ejecutar_reverso_financiero(
                DatosReversoFinanciero(ejecucion_origen_id=rechazada.ejecucion.id)
            )


async def test_una_autorizacion_0100_no_es_elegible(base):
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        destino = DestinoTcp(host=host.host, puerto=host.puerto)
        orquestador = construir_orquestador(base, transporte, destino=destino, tiempo_limite=2.0)

        autorizacion = await orquestador.ejecutar_compra(
            DatosCompra(card_id=CARD_ID_DEMO, monto=Decimal("50.00"))
        )
        assert autorizacion.estado is EstadoEjecucion.APROBADA

        with pytest.raises(EjecucionOrigenNoElegible):
            await orquestador.ejecutar_reverso_financiero(
                DatosReversoFinanciero(ejecucion_origen_id=autorizacion.ejecucion.id)
            )


async def test_un_echo_no_es_elegible(base):
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        destino = DestinoTcp(host=host.host, puerto=host.puerto)
        orquestador = construir_orquestador(base, transporte, destino=destino, tiempo_limite=2.0)

        echo = await orquestador.ejecutar_network_echo(DatosEcho())
        assert echo.estado is EstadoEjecucion.APROBADA

        with pytest.raises(EjecucionOrigenNoElegible):
            await orquestador.ejecutar_reverso_financiero(
                DatosReversoFinanciero(ejecucion_origen_id=echo.ejecucion.id)
            )


async def test_una_financiera_sin_respuesta_no_es_elegible(base):
    host = _host(responder=False)
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=0.2)
        destino = DestinoTcp(host=host.host, puerto=host.puerto)
        orquestador = construir_orquestador(base, transporte, destino=destino, tiempo_limite=0.2)

        sin_respuesta = await orquestador.ejecutar_compra_financiera(
            DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=Decimal("40.00"))
        )
        assert sin_respuesta.estado is EstadoEjecucion.TIMEOUT

        with pytest.raises(EjecucionOrigenNoElegible):
            await orquestador.ejecutar_reverso_financiero(
                DatosReversoFinanciero(ejecucion_origen_id=sin_respuesta.ejecucion.id)
            )


async def test_un_origen_puede_tener_varios_reversos(base):
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        destino = DestinoTcp(host=host.host, puerto=host.puerto)
        orquestador = construir_orquestador(base, transporte, destino=destino, tiempo_limite=2.0)

        original = await orquestador.ejecutar_compra_financiera(
            DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=Decimal("90.00"))
        )
        reverso_1 = await orquestador.ejecutar_reverso_financiero(
            DatosReversoFinanciero(ejecucion_origen_id=original.ejecucion.id)
        )
        reverso_2 = await orquestador.ejecutar_reverso_financiero(
            DatosReversoFinanciero(ejecucion_origen_id=original.ejecucion.id)
        )

    assert reverso_1.ejecucion.id != reverso_2.ejecucion.id
    assert reverso_1.ejecucion.stan != reverso_2.ejecucion.stan

    repo = RepositorioEjecucionesSQLite(base)
    derivadas = await repo.listar_derivadas(original.ejecucion.id)
    assert {d.id for d in derivadas} == {reverso_1.ejecucion.id, reverso_2.ejecucion.id}

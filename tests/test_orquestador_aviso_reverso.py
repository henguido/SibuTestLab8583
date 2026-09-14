"""`Orquestador.ejecutar_aviso_reverso` (0420/0430, B8).

E2E real: TCP real, codec real, SQLite real, host simulado real -mismo
estilo que `test_orquestador_reverso_financiero.py`, que este archivo
espeja punto por punto-. Cubre el recorrido exigido por el checkpoint
(punto 24):

    0200 -> 0210/00 -> ejecucion_id = A
    crear aviso de reverso desde A -> 0420 -> 0430/00 -> ejecucion_origen_id = A

y la reautenticacion de elegibilidad server-side, identica a la de 0400
(punto 5 del checkpoint B8: investigada, no asumida -misma regla, mismo
origen elegible-).
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
    DatosAvisoReverso,
    DatosCompra,
    DatosCompraFinanciera,
    DatosEcho,
    DatosReversoFinanciero,
    DestinoTcp,
    EstadoEjecucion,
    MTI_AVISO_REVERSO,
    MTI_RESPUESTA_AVISO_REVERSO,
)
from sibutestlab8583.profiles.generico import PERFIL_GENERICO

from conftest import construir_orquestador


def _host(**kwargs) -> HostSimulado:
    return HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), **kwargs)


async def test_aviso_de_reverso_real_desde_una_financiera_aprobada(base):
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        destino = DestinoTcp(host=host.host, puerto=host.puerto)
        orquestador = construir_orquestador(base, transporte, destino=destino, tiempo_limite=2.0)

        original = await orquestador.ejecutar_compra_financiera(
            DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=Decimal("80.00"))
        )
        assert original.estado is EstadoEjecucion.APROBADA

        aviso = await orquestador.ejecutar_aviso_reverso(
            DatosAvisoReverso(ejecucion_origen_id=original.ejecucion.id)
        )

    assert aviso.estado is EstadoEjecucion.APROBADA
    assert aviso.ejecucion.mti_solicitud == MTI_AVISO_REVERSO
    assert aviso.ejecucion.mti_respuesta == MTI_RESPUESTA_AVISO_REVERSO
    assert aviso.ejecucion.ejecucion_origen_id == original.ejecucion.id
    assert aviso.ejecucion.stan != original.ejecucion.stan

    repo = RepositorioEjecucionesSQLite(base)
    original_relectura = await repo.obtener(original.ejecucion.id)
    assert original_relectura.estado is EstadoEjecucion.APROBADA
    assert original_relectura.ejecucion_origen_id is None

    derivadas = await repo.listar_derivadas(original.ejecucion.id)
    assert [d.id for d in derivadas] == [aviso.ejecucion.id]


async def test_un_origen_inexistente_revienta_antes_de_generar_stan(base):
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        destino = DestinoTcp(host=host.host, puerto=host.puerto)
        orquestador = construir_orquestador(base, transporte, destino=destino, tiempo_limite=2.0)

        with pytest.raises(EjecucionOrigenNoEncontrada):
            await orquestador.ejecutar_aviso_reverso(
                DatosAvisoReverso(ejecucion_origen_id=999999)
            )

    repo = RepositorioEjecucionesSQLite(base)
    assert await repo.listar(limite=10) == []


async def test_una_financiera_rechazada_no_es_elegible(base):
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        destino = DestinoTcp(host=host.host, puerto=host.puerto)
        orquestador = construir_orquestador(base, transporte, destino=destino, tiempo_limite=2.0)

        rechazada = await orquestador.ejecutar_compra_financiera(
            DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=Decimal("500000.00"))
        )
        assert rechazada.estado is EstadoEjecucion.RECHAZADA

        with pytest.raises(EjecucionOrigenNoElegible):
            await orquestador.ejecutar_aviso_reverso(
                DatosAvisoReverso(ejecucion_origen_id=rechazada.ejecucion.id)
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
            await orquestador.ejecutar_aviso_reverso(
                DatosAvisoReverso(ejecucion_origen_id=autorizacion.ejecucion.id)
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
            await orquestador.ejecutar_aviso_reverso(
                DatosAvisoReverso(ejecucion_origen_id=echo.ejecucion.id)
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
            await orquestador.ejecutar_aviso_reverso(
                DatosAvisoReverso(ejecucion_origen_id=sin_respuesta.ejecucion.id)
            )


async def test_un_origen_puede_tener_varios_avisos_de_reverso(base):
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        destino = DestinoTcp(host=host.host, puerto=host.puerto)
        orquestador = construir_orquestador(base, transporte, destino=destino, tiempo_limite=2.0)

        original = await orquestador.ejecutar_compra_financiera(
            DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=Decimal("90.00"))
        )
        aviso_1 = await orquestador.ejecutar_aviso_reverso(
            DatosAvisoReverso(ejecucion_origen_id=original.ejecucion.id)
        )
        aviso_2 = await orquestador.ejecutar_aviso_reverso(
            DatosAvisoReverso(ejecucion_origen_id=original.ejecucion.id)
        )

    assert aviso_1.ejecucion.id != aviso_2.ejecucion.id
    assert aviso_1.ejecucion.stan != aviso_2.ejecucion.stan

    repo = RepositorioEjecucionesSQLite(base)
    derivadas = await repo.listar_derivadas(original.ejecucion.id)
    assert {d.id for d in derivadas} == {aviso_1.ejecucion.id, aviso_2.ejecucion.id}


async def test_un_origen_puede_tener_un_reverso_y_un_aviso_de_reverso(base):
    """Punto 5 del checkpoint B8: este laboratorio no bloquea una operacion
    derivada solo porque otra ya exista para el mismo origen -0400 y 0420
    son operaciones distintas, y coexisten sobre la misma ejecucion origen
    sin ningun candado de exclusividad."""
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        destino = DestinoTcp(host=host.host, puerto=host.puerto)
        orquestador = construir_orquestador(base, transporte, destino=destino, tiempo_limite=2.0)

        original = await orquestador.ejecutar_compra_financiera(
            DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=Decimal("65.00"))
        )
        reverso = await orquestador.ejecutar_reverso_financiero(
            DatosReversoFinanciero(ejecucion_origen_id=original.ejecucion.id)
        )
        aviso = await orquestador.ejecutar_aviso_reverso(
            DatosAvisoReverso(ejecucion_origen_id=original.ejecucion.id)
        )

    assert reverso.ejecucion.mti_solicitud == "0400"
    assert aviso.ejecucion.mti_solicitud == MTI_AVISO_REVERSO
    assert reverso.ejecucion.id != aviso.ejecucion.id

    repo = RepositorioEjecucionesSQLite(base)
    derivadas = await repo.listar_derivadas(original.ejecucion.id)
    assert {d.id for d in derivadas} == {reverso.ejecucion.id, aviso.ejecucion.id}

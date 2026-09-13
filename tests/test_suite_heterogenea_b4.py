"""B4, punto 20: suite heterogenea real de cuatro items -

    1. Autorizacion 0100
    2. Echo 0800
    3. Financiera 0200 aprobada
    4. Financiera 0200 rechazada (DE39="51", rechazo sintetico por monto)

ejecutada por el mismo `CorredorDeSuites` -sin cambios-, contra un
`HostSimulado` real y TCP/codec/SQLite reales (no dobles): la demostracion
de que un rechazo financiero (DE39="51") es un resultado transaccional
valido dentro de una corrida mixta, no un caso especial, y que el motor no
lo confunde con un ERROR tecnico (puntos 21/22 de B4).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.host_simulado.servidor import UMBRAL_SINTETICO_RECHAZO_FINANCIERO
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, DESTINO_ID_DEMO
from sibutestlab8583.adapters.persistence.sqlite_repos import (
    RepositorioCorridasSuiteSQLite,
    RepositorioDestinosSQLite,
    RepositorioEscenariosSQLite,
    RepositorioSuitesSQLite,
    RepositorioTarjetasSQLite,
)
from conftest import construir_orquestador

from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.adapters.transporte.tcp import TransporteTcp
from sibutestlab8583.application.conexiones import ServicioConexiones
from sibutestlab8583.application.corredor_suites import CorredorDeSuites
from sibutestlab8583.application.ejecutor_escenarios import EjecutorDeEscenarios
from sibutestlab8583.application.escenarios import DatosNuevoEscenario, ServicioEscenarios
from sibutestlab8583.application.suites import DatosNuevaSuite, ServicioSuites
from sibutestlab8583.domain.modelos import (
    EstadoEjecucion,
    EstadoItemCorrida,
    ExpectativaCampo,
    Expectativas,
    MTI_COMPRA_FINANCIERA,
    MTI_ECHO,
    ResultadoGlobalSuite,
)
from sibutestlab8583.profiles.generico import PERFIL_GENERICO


def _servicios_reales(base):
    escenarios = ServicioEscenarios(
        RepositorioEscenariosSQLite(base), RepositorioTarjetasSQLite(base),
        RepositorioDestinosSQLite(base), PERFIL_GENERICO,
    )
    conexiones = ServicioConexiones(RepositorioDestinosSQLite(base))

    async def fabrica(destino, tiempo_limite):
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=tiempo_limite)
        return construir_orquestador(base, transporte, destino=destino, tiempo_limite=tiempo_limite)

    ejecutor = EjecutorDeEscenarios(escenarios, conexiones, fabrica)
    suites = ServicioSuites(RepositorioSuitesSQLite(base), RepositorioEscenariosSQLite(base))
    corridas = RepositorioCorridasSuiteSQLite(base)
    corredor = CorredorDeSuites(suites, escenarios, corridas, ejecutor)
    return suites, escenarios, corridas, corredor


async def test_suite_heterogenea_de_cuatro_items_compra_echo_financiera_aprobada_y_rechazada(base):
    host = HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion())
    async with host:
        conexion_destino = await RepositorioDestinosSQLite(base).obtener(DESTINO_ID_DEMO)
        # Redirige la conexion de demostracion al host efimero real de esta prueba.
        import dataclasses

        await RepositorioDestinosSQLite(base).guardar(
            dataclasses.replace(conexion_destino, host=host.host, puerto=host.puerto)
        )

        suites, escenarios, corridas, corredor = _servicios_reales(base)

        e1 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="1. Autorizacion 0100", card_id=CARD_ID_DEMO,
                conexion_id=DESTINO_ID_DEMO, monto=Decimal("10.00"),
                expectativas=Expectativas(estado=EstadoEjecucion.APROBADA),
            )
        )
        e2 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="2. Echo 0800", conexion_id=DESTINO_ID_DEMO, mti=MTI_ECHO,
                expectativas=Expectativas(estado=EstadoEjecucion.APROBADA),
            )
        )
        e3 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="3. Financiera 0200 aprobada", card_id=CARD_ID_DEMO,
                conexion_id=DESTINO_ID_DEMO,
                monto=UMBRAL_SINTETICO_RECHAZO_FINANCIERO - Decimal("1.00"),
                mti=MTI_COMPRA_FINANCIERA,
                expectativas=Expectativas(campos={"39": ExpectativaCampo(tipo="igual", valor="00")}),
            )
        )
        e4 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="4. Financiera 0200 rechazada", card_id=CARD_ID_DEMO,
                conexion_id=DESTINO_ID_DEMO,
                monto=UMBRAL_SINTETICO_RECHAZO_FINANCIERO + Decimal("1.00"),
                mti=MTI_COMPRA_FINANCIERA,
                expectativas=Expectativas(campos={"39": ExpectativaCampo(tipo="igual", valor="51")}),
            )
        )

        suite = await suites.crear(
            DatosNuevaSuite(
                nombre="Heterogenea B4",
                escenarios=[e1.escenario_id, e2.escenario_id, e3.escenario_id, e4.escenario_id],
            )
        )

        corrida = await corredor.ejecutar(suite.suite_id)
        items = await corridas.obtener_items(corrida.corrida_id)

    assert corrida.resultado_global == ResultadoGlobalSuite.PASS
    assert len(items) == 4

    por_orden = {item.orden: item for item in items}
    assert por_orden[1].resultado == EstadoItemCorrida.PASS
    assert por_orden[2].resultado == EstadoItemCorrida.PASS
    assert por_orden[3].resultado == EstadoItemCorrida.PASS
    # El item 4 esperaba EXACTAMENTE el rechazo -DE39="51"- que recibio: PASS,
    # no FAIL ni ERROR. Un rechazo financiero real no es un fallo tecnico.
    assert por_orden[4].resultado == EstadoItemCorrida.PASS

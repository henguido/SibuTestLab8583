"""B3: escenarios y suites realmente Multi-MTI (Compra + Echo).

Cubre el ciclo completo que el pedido de B3 exige, en el mismo sentido para
ambas operaciones -sin que `application/escenarios.py` ni `corredor_suites.py`
dependan estructuralmente de Compra-:

    crear -> guardar escenario -> reejecutar -> Expected vs Actual ->
    suite (heterogenea) -> corrida -> comparacion -> reintento

`comparacion_corridas.py`/`exportacion_corridas.py`/`cli.py` no se modificaron
en B3 porque ya eran agnosticos de MTI (verificado leyendo el codigo antes de
escribir estas pruebas): estas pruebas son la evidencia de que esa
generalidad ya existente realmente sostiene una suite mixta, no una
suposicion.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from conftest import TransporteFalso, construir_orquestador

from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, DESTINO_ID_DEMO
from sibutestlab8583.adapters.persistence.sqlite_repos import (
    RepositorioCorridasSuiteSQLite,
    RepositorioDestinosSQLite,
    RepositorioEscenariosSQLite,
    RepositorioSuitesSQLite,
    RepositorioTarjetasSQLite,
)
from sibutestlab8583.application.comparacion_corridas import ServicioComparacionCorridas
from sibutestlab8583.application.conexiones import ServicioConexiones
from sibutestlab8583.application.corredor_suites import CorredorDeSuites
from sibutestlab8583.application.ejecutor_escenarios import EjecutorDeEscenarios
from sibutestlab8583.application.escenarios import (
    DatosNuevoEscenario,
    ServicioEscenarios,
)
from sibutestlab8583.application.exportacion_corridas import reporte_a_csv, reporte_a_json
from sibutestlab8583.application.suites import DatosNuevaSuite, ServicioSuites
from sibutestlab8583.domain.modelos import (
    EstadoEjecucion,
    EstadoItemCorrida,
    ExpectativaCampo,
    Expectativas,
    MTI_ECHO,
    OPERACION_ECHO,
    ResultadoGlobalSuite,
)
from sibutestlab8583.profiles.generico import PERFIL_GENERICO, VALOR_LABORATORIO_ECHO

CODIGO_APROBADO = "00"


def _servicios(base, transporte):
    escenarios = ServicioEscenarios(
        RepositorioEscenariosSQLite(base), RepositorioTarjetasSQLite(base),
        RepositorioDestinosSQLite(base), PERFIL_GENERICO,
    )
    conexiones = ServicioConexiones(RepositorioDestinosSQLite(base))

    async def fabrica(destino, tiempo_limite):
        return construir_orquestador(base, transporte, destino=destino, tiempo_limite=tiempo_limite)

    ejecutor = EjecutorDeEscenarios(escenarios, conexiones, fabrica)
    suites = ServicioSuites(RepositorioSuitesSQLite(base), RepositorioEscenariosSQLite(base))
    corridas = RepositorioCorridasSuiteSQLite(base)
    corredor = CorredorDeSuites(suites, escenarios, corridas, ejecutor)
    comparador = ServicioComparacionCorridas(corridas)
    return suites, escenarios, corridas, corredor, comparador


async def _crear_compra(escenarios: ServicioEscenarios, nombre: str, *, expectativas=None):
    return await escenarios.crear(
        DatosNuevoEscenario(
            nombre=nombre, card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO,
            monto=Decimal("10.00"), expectativas=expectativas,
        )
    )


async def _crear_echo(escenarios: ServicioEscenarios, nombre: str, *, expectativas=None, campos=None):
    return await escenarios.crear(
        DatosNuevoEscenario(
            nombre=nombre, conexion_id=DESTINO_ID_DEMO, mti=MTI_ECHO,
            campos_manuales=campos or {}, expectativas=expectativas,
        )
    )


# ------------------------------------------------------- crear / reejecutar --


async def test_crear_un_escenario_echo_sin_tarjeta_ni_monto(base):
    _, escenarios, *_ = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    creado = await _crear_echo(escenarios, "Echo simple")
    assert creado.card_id is None
    assert creado.monto is None
    assert creado.mti == MTI_ECHO
    assert creado.operacion == OPERACION_ECHO


async def test_crear_una_compra_sin_tarjeta_sigue_fallando(base):
    """Regresion: la validacion condicional por perfil no debe volverse
    permisiva para la operacion que SI necesita tarjeta."""
    escenarios = ServicioEscenarios(
        RepositorioEscenariosSQLite(base), RepositorioTarjetasSQLite(base),
        RepositorioDestinosSQLite(base), PERFIL_GENERICO,
    )
    with pytest.raises(ValueError, match="tarjeta"):
        await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Compra sin tarjeta", card_id=None, conexion_id=DESTINO_ID_DEMO,
                monto=Decimal("10.00"),
            )
        )


async def test_reejecutar_un_escenario_echo_llama_ejecutar_network_echo(base):
    _, escenarios, *_ = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    creado = await _crear_echo(escenarios, "Echo reejecutable")

    conexiones = ServicioConexiones(RepositorioDestinosSQLite(base))
    transporte = TransporteFalso(codigo=CODIGO_APROBADO)

    async def fabrica(destino, tiempo_limite):
        return construir_orquestador(base, transporte, destino=destino, tiempo_limite=tiempo_limite)

    ejecutor = EjecutorDeEscenarios(escenarios, conexiones, fabrica)
    resultado = await ejecutor.ejecutar(creado.escenario_id)

    assert resultado.solicitud.mti == MTI_ECHO
    assert resultado.estado is EstadoEjecucion.APROBADA
    assert resultado.ejecucion.card_id is None
    assert resultado.ejecucion.monto is None


# --------------------------------------------------------- Expected/Actual --


async def test_expected_vs_actual_en_echo_evalua_de39_y_de70(base):
    _, escenarios, *_ = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    expectativas = Expectativas(
        estado=EstadoEjecucion.APROBADA,
        campos={
            "39": ExpectativaCampo(tipo="igual", valor="00"),
            "70": ExpectativaCampo(tipo="igual", valor=VALOR_LABORATORIO_ECHO),
        },
    )
    creado = await _crear_echo(escenarios, "Echo con expectativas", expectativas=expectativas)

    conexiones = ServicioConexiones(RepositorioDestinosSQLite(base))
    transporte = TransporteFalso(codigo=CODIGO_APROBADO)

    async def fabrica(destino, tiempo_limite):
        return construir_orquestador(base, transporte, destino=destino, tiempo_limite=tiempo_limite)

    ejecutor = EjecutorDeEscenarios(escenarios, conexiones, fabrica)
    resultado = await ejecutor.ejecutar(creado.escenario_id)

    assert resultado.ejecucion.evaluacion_estado == "pass"


async def test_expected_vs_actual_en_echo_detecta_fail_si_de70_no_coincide(base):
    _, escenarios, *_ = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    expectativas = Expectativas(
        campos={"70": ExpectativaCampo(tipo="igual", valor="999")},
    )
    creado = await _crear_echo(escenarios, "Echo expectativa incorrecta", expectativas=expectativas)

    conexiones = ServicioConexiones(RepositorioDestinosSQLite(base))
    transporte = TransporteFalso(codigo=CODIGO_APROBADO)

    async def fabrica(destino, tiempo_limite):
        return construir_orquestador(base, transporte, destino=destino, tiempo_limite=tiempo_limite)

    ejecutor = EjecutorDeEscenarios(escenarios, conexiones, fabrica)
    resultado = await ejecutor.ejecutar(creado.escenario_id)

    assert resultado.ejecucion.evaluacion_estado == "fail"


# -------------------------------------------------------- suite heterogenea --


async def test_suite_heterogenea_compra_echo_compra_ejecuta_las_tres(base):
    _, escenarios, _, corredor, _ = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    e1 = await _crear_compra(escenarios, "Compra 1", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    e2 = await _crear_echo(escenarios, "Echo", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    e3 = await _crear_compra(escenarios, "Compra 2", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    suite = await ServicioSuites(
        RepositorioSuitesSQLite(base), RepositorioEscenariosSQLite(base)
    ).crear(
        DatosNuevaSuite(nombre="Mixta", escenarios=(e1.escenario_id, e2.escenario_id, e3.escenario_id))
    )

    corrida = await corredor.ejecutar(suite.suite_id)

    assert corrida.total == 3
    assert corrida.resultado_global == ResultadoGlobalSuite.PASS
    assert corrida.cantidad_pass == 3

    items = await RepositorioCorridasSuiteSQLite(base).obtener_items(corrida.corrida_id)
    mtis_solicitud = [i.escenario_id for i in items]
    assert {e1.escenario_id, e2.escenario_id, e3.escenario_id} == set(mtis_solicitud)
    assert all(i.resultado == EstadoItemCorrida.PASS for i in items)


async def test_suite_heterogenea_con_echo_fallido_da_resultado_global_fail(base):
    _, escenarios, _, corredor, comparador = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    e1 = await _crear_compra(escenarios, "Compra OK", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    e2 = await _crear_echo(
        escenarios, "Echo con expectativa incorrecta",
        expectativas=Expectativas(campos={"70": ExpectativaCampo(tipo="igual", valor="999")}),
    )
    e3 = await _crear_compra(escenarios, "Compra OK 2", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    suite = await ServicioSuites(
        RepositorioSuitesSQLite(base), RepositorioEscenariosSQLite(base)
    ).crear(
        DatosNuevaSuite(nombre="Con echo fallido", escenarios=(e1.escenario_id, e2.escenario_id, e3.escenario_id))
    )

    corrida = await corredor.ejecutar(suite.suite_id)

    assert corrida.resultado_global == ResultadoGlobalSuite.FAIL
    assert corrida.cantidad_pass == 2
    assert corrida.cantidad_fail == 1


# ----------------------------------------------------- comparacion / reintento --


async def test_comparacion_de_corridas_heterogeneas_no_asume_compra(base):
    _, escenarios, corridas_repo, corredor, comparador = _servicios(
        base, TransporteFalso(codigo=CODIGO_APROBADO)
    )
    e1 = await _crear_compra(escenarios, "Compra", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    e2 = await _crear_echo(escenarios, "Echo", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    suite = await ServicioSuites(
        RepositorioSuitesSQLite(base), RepositorioEscenariosSQLite(base)
    ).crear(DatosNuevaSuite(nombre="Comparable", escenarios=(e1.escenario_id, e2.escenario_id)))

    corrida_a = await corredor.ejecutar(suite.suite_id)
    corrida_b = await corredor.ejecutar(suite.suite_id)

    comparacion = await comparador.comparar(corrida_a.corrida_id, corrida_b.corrida_id)
    assert len(comparacion.items) == 2
    # Ninguno de los dos items (uno compra, uno echo) cambio: ambos PASS en
    # ambas corridas.
    assert all(item.cambio.value in ("sin_cambio",) for item in comparacion.items)


async def test_reintento_selectivo_solo_reintenta_el_item_fallido_echo(base):
    _, escenarios, corridas_repo, corredor, _ = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    e1 = await _crear_compra(escenarios, "Compra OK", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    e2 = await _crear_echo(
        escenarios, "Echo fallido",
        expectativas=Expectativas(campos={"70": ExpectativaCampo(tipo="igual", valor="999")}),
    )
    suite = await ServicioSuites(
        RepositorioSuitesSQLite(base), RepositorioEscenariosSQLite(base)
    ).crear(DatosNuevaSuite(nombre="Para reintentar", escenarios=(e1.escenario_id, e2.escenario_id)))

    corrida_original = await corredor.ejecutar(suite.suite_id)
    assert corrida_original.cantidad_fail == 1

    corrida_reintento = await corredor.reintentar_fallidos(corrida_original.corrida_id)

    assert corrida_reintento.total == 1, "solo el item fallido (echo) se reintenta"
    items = await RepositorioCorridasSuiteSQLite(base).obtener_items(corrida_reintento.corrida_id)
    assert len(items) == 1
    assert items[0].escenario_id == e2.escenario_id


async def test_reintento_selectivo_al_reves_solo_reintenta_compra_fallida(base):
    """Simetria: si el FALLIDO es compra y el que pasa es echo, el reintento
    tampoco debe depender de card_id/monto para decidir que reejecutar."""
    _, escenarios, corridas_repo, corredor, _ = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    e1 = await _crear_compra(
        escenarios, "Compra fallida",
        expectativas=Expectativas(estado=EstadoEjecucion.RECHAZADA),
    )
    e2 = await _crear_echo(escenarios, "Echo OK", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    suite = await ServicioSuites(
        RepositorioSuitesSQLite(base), RepositorioEscenariosSQLite(base)
    ).crear(DatosNuevaSuite(nombre="Compra falla", escenarios=(e1.escenario_id, e2.escenario_id)))

    corrida_original = await corredor.ejecutar(suite.suite_id)
    assert corrida_original.cantidad_fail == 1

    corrida_reintento = await corredor.reintentar_fallidos(corrida_original.corrida_id)

    items = await RepositorioCorridasSuiteSQLite(base).obtener_items(corrida_reintento.corrida_id)
    assert len(items) == 1
    assert items[0].escenario_id == e1.escenario_id


# ------------------------------------------------------------------- export --


async def test_export_de_corrida_heterogenea_json_y_csv(base):
    _, escenarios, corridas_repo, corredor, _ = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    e1 = await _crear_compra(escenarios, "Compra", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    e2 = await _crear_echo(escenarios, "Echo", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    suite = await ServicioSuites(
        RepositorioSuitesSQLite(base), RepositorioEscenariosSQLite(base)
    ).crear(DatosNuevaSuite(nombre="Exportable", escenarios=(e1.escenario_id, e2.escenario_id)))

    corrida = await corredor.ejecutar(suite.suite_id)
    items = await corridas_repo.obtener_items(corrida.corrida_id)

    reporte_json = reporte_a_json(corrida, items)
    assert "Echo" in reporte_json

    reporte_csv = reporte_a_csv(corrida, items, {})
    assert "Echo" in reporte_csv
    assert "Compra" in reporte_csv


# ---------------------------------------------------------------- variables --


async def test_variable_dinamica_en_escenario_echo_se_congela_sin_resolver(base):
    """Mismo criterio ya verificado para compra en Fase A: guardar un
    escenario con {{stan}} en un campo editable debe conservar la expresion
    tal cual, nunca un STAN ya resuelto -y debe funcionar igual para Echo."""
    _, escenarios, *_ = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    creado = await _crear_echo(escenarios, "Echo con variable", campos={"70": "{{stan}}"})
    assert creado.campos_manuales["70"] == "{{stan}}"


async def test_variable_dinamica_en_escenario_echo_se_resuelve_al_reejecutar(base):
    _, escenarios, *_ = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    creado = await _crear_echo(escenarios, "Echo con variable", campos={"70": "{{stan}}"})

    conexiones = ServicioConexiones(RepositorioDestinosSQLite(base))
    transporte = TransporteFalso(codigo=CODIGO_APROBADO)

    async def fabrica(destino, tiempo_limite):
        return construir_orquestador(base, transporte, destino=destino, tiempo_limite=tiempo_limite)

    ejecutor = EjecutorDeEscenarios(escenarios, conexiones, fabrica)
    resultado = await ejecutor.ejecutar(creado.escenario_id)

    assert resultado.solicitud.campos["70"] == resultado.solicitud.campos["11"]

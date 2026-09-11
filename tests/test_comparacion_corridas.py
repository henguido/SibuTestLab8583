"""Comparacion historica de dos corridas de la misma suite.

Dos niveles de prueba: `clasificar_cambio` (dominio, pura, sin base de
datos) cubre la matriz completa MEJORO/EMPEORO/CAMBIO/SIN_CAMBIO;
`ServicioComparacionCorridas.comparar` (aplicacion, con corridas reales via
`CorredorDeSuites`) cubre el emparejamiento por escenario_id, los errores
controlados, y que la comparacion sea verdaderamente historica -no cambie
si se edita el escenario o la suite despues de ambas corridas.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from test_corredor_suites import TransporteFalso, _crear_escenario, _servicios

from sibutestlab8583.application.comparacion_corridas import (
    CorridaNoEncontrada,
    CorridasDeSuitesDistintas,
    ItemsHistoricosDuplicados,
    ServicioComparacionCorridas,
    _comparar_items,
)
from sibutestlab8583.application.escenarios import DatosEdicionEscenario
from sibutestlab8583.application.suites import DatosEdicionSuite, DatosNuevaSuite
from sibutestlab8583.domain.comparacion_corridas import CambioItem, clasificar_cambio
from sibutestlab8583.domain.modelos import (
    CorridaSuite,
    EstadoEjecucion,
    EstadoItemCorrida,
    Expectativas,
    ItemCorridaSuite,
)

PASS, FAIL, ERROR = EstadoItemCorrida.PASS, EstadoItemCorrida.FAIL, EstadoItemCorrida.ERROR
SIN_EXP, NO_EJEC = EstadoItemCorrida.SIN_EXPECTATIVAS, EstadoItemCorrida.NO_EJECUTADO

CODIGO_APROBADO = "00"
CODIGO_RECHAZADO = "05"


# ------------------------------------------------------------ dominio puro --


@pytest.mark.parametrize(
    "resultado_a,resultado_b,esperado",
    [
        (PASS, PASS, CambioItem.SIN_CAMBIO),  # 1
        (FAIL, PASS, CambioItem.MEJORO),  # 2
        (PASS, FAIL, CambioItem.EMPEORO),  # 3
        (ERROR, PASS, CambioItem.MEJORO),  # 4
        (ERROR, FAIL, CambioItem.MEJORO),
        (FAIL, ERROR, CambioItem.EMPEORO),
        (PASS, ERROR, CambioItem.EMPEORO),
    ],
)
def test_clasificar_cambio_resultados_evaluables(resultado_a, resultado_b, esperado):
    assert clasificar_cambio(resultado_a, resultado_b, None, None) == esperado


def test_clasificar_cambio_fail_a_fail_con_discrepancia_distinta_es_cambio():  # 5
    cambio = clasificar_cambio(FAIL, FAIL, [{"criterio": "estado"}], [{"criterio": "campo"}])
    assert cambio == CambioItem.CAMBIO


def test_clasificar_cambio_fail_a_fail_con_misma_discrepancia_es_sin_cambio():
    misma = [{"criterio": "estado", "esperado": "aprobada", "recibido": "rechazada"}]
    assert clasificar_cambio(FAIL, FAIL, misma, list(misma)) == CambioItem.SIN_CAMBIO


def test_clasificar_cambio_error_a_error_con_detalle_distinto_es_cambio():
    assert clasificar_cambio(ERROR, ERROR, "motivo viejo", "motivo nuevo") == CambioItem.CAMBIO


def test_clasificar_cambio_error_a_error_con_mismo_detalle_es_sin_cambio():
    assert clasificar_cambio(ERROR, ERROR, "mismo motivo", "mismo motivo") == CambioItem.SIN_CAMBIO


@pytest.mark.parametrize(
    "resultado_a,resultado_b",
    [
        (SIN_EXP, SIN_EXP),
        (NO_EJEC, NO_EJEC),
    ],
)
def test_clasificar_cambio_no_evaluables_iguales_es_sin_cambio(resultado_a, resultado_b):
    assert clasificar_cambio(resultado_a, resultado_b, None, None) == CambioItem.SIN_CAMBIO


@pytest.mark.parametrize(
    "resultado_a,resultado_b",
    [
        (SIN_EXP, PASS),
        (PASS, SIN_EXP),
        (SIN_EXP, FAIL),
        (NO_EJEC, PASS),
        (FAIL, SIN_EXP),
    ],
)
def test_clasificar_cambio_con_no_evaluable_de_por_medio_nunca_es_mejoro_ni_empeoro(
    resultado_a, resultado_b
):
    """No hay expectativa que perder ni ganar cuando uno de los dos lados no
    es evaluable: es un cambio real, pero nunca graduado como mejor/peor.
    """
    cambio = clasificar_cambio(resultado_a, resultado_b, None, None)
    assert cambio == CambioItem.CAMBIO


# ------------------------------------------------ aplicacion, con corridas --


async def _correr_suite_pass_fail(base):
    """Una suite de 2 escenarios: E1 siempre PASS, E2 siempre FAIL. Devuelve
    (suites, escenarios, corridas, corredor, suite, e1, e2).
    """
    suites, escenarios, corridas, corredor = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    e1 = await _crear_escenario(
        escenarios, "E1", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA)
    )
    e2 = await _crear_escenario(
        escenarios, "E2", expectativas=Expectativas(estado=EstadoEjecucion.RECHAZADA)
    )
    suite = await suites.crear(
        DatosNuevaSuite(nombre="Comparable", escenarios=(e1.escenario_id, e2.escenario_id))
    )
    return suites, escenarios, corridas, corredor, suite, e1, e2


async def test_comparar_detecta_mejoro_cuando_un_fail_pasa_a_pass(base):  # 2 (nivel aplicacion)
    suites, escenarios, corridas, corredor, suite, e1, e2 = await _correr_suite_pass_fail(base)
    corrida_a = await corredor.ejecutar(suite.suite_id)

    # Se corrige la expectativa de E2 para que ahora si cumpla -pero la
    # comparacion debe seguir leyendo el snapshot de la corrida A tal cual
    # quedo, nunca la expectativa actual.
    await escenarios.actualizar(
        e2.escenario_id,
        DatosEdicionEscenario(
            nombre="E2", card_id=e2.card_id, conexion_id=e2.conexion_id, monto=e2.monto,
            expectativas=Expectativas(estado=EstadoEjecucion.APROBADA),
        ),
    )
    corrida_b = await corredor.ejecutar(suite.suite_id)

    comparacion = await ServicioComparacionCorridas(corridas).comparar(
        corrida_a.corrida_id, corrida_b.corrida_id
    )
    por_escenario = {item.escenario_id: item for item in comparacion.items}
    assert por_escenario[e1.escenario_id].cambio == CambioItem.SIN_CAMBIO
    assert por_escenario[e2.escenario_id].cambio == CambioItem.MEJORO
    assert comparacion.resumen.mejoro == 1
    assert comparacion.resumen.sin_cambio == 1


async def test_comparar_item_solo_en_a(base):  # 6
    suites, escenarios, corridas, corredor, suite, e1, e2 = await _correr_suite_pass_fail(base)
    corrida_a = await corredor.ejecutar(suite.suite_id)

    # Se saca E2 de la suite antes de la segunda corrida.
    await suites.actualizar(
        suite.suite_id,
        DatosEdicionSuite(nombre="Comparable", escenarios=(e1.escenario_id,)),
    )
    corrida_b = await corredor.ejecutar(suite.suite_id)

    comparacion = await ServicioComparacionCorridas(corridas).comparar(
        corrida_a.corrida_id, corrida_b.corrida_id
    )
    por_escenario = {item.escenario_id: item for item in comparacion.items}
    assert por_escenario[e2.escenario_id].cambio == CambioItem.SOLO_EN_A
    assert por_escenario[e2.escenario_id].item_b is None
    assert comparacion.resumen.solo_en_a == 1


async def test_comparar_item_solo_en_b(base):  # 7
    suites, escenarios, corridas, corredor, suite, e1, e2 = await _correr_suite_pass_fail(base)
    # Primera corrida solo con E1.
    await suites.actualizar(
        suite.suite_id,
        DatosEdicionSuite(nombre="Comparable", escenarios=(e1.escenario_id,)),
    )
    corrida_a = await corredor.ejecutar(suite.suite_id)

    # Se agrega E2 antes de la segunda corrida.
    await suites.actualizar(
        suite.suite_id,
        DatosEdicionSuite(nombre="Comparable", escenarios=(e1.escenario_id, e2.escenario_id)),
    )
    corrida_b = await corredor.ejecutar(suite.suite_id)

    comparacion = await ServicioComparacionCorridas(corridas).comparar(
        corrida_a.corrida_id, corrida_b.corrida_id
    )
    por_escenario = {item.escenario_id: item for item in comparacion.items}
    assert por_escenario[e2.escenario_id].cambio == CambioItem.SOLO_EN_B
    assert por_escenario[e2.escenario_id].item_a is None
    assert comparacion.resumen.solo_en_b == 1


async def test_comparar_corridas_de_suites_distintas_da_error_controlado(base):  # 8
    suites, escenarios, corridas, corredor = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    e1 = await _crear_escenario(escenarios, "E1")
    suite_1 = await suites.crear(DatosNuevaSuite(nombre="Suite 1", escenarios=(e1.escenario_id,)))
    suite_2 = await suites.crear(DatosNuevaSuite(nombre="Suite 2", escenarios=(e1.escenario_id,)))
    corrida_1 = await corredor.ejecutar(suite_1.suite_id)
    corrida_2 = await corredor.ejecutar(suite_2.suite_id)

    with pytest.raises(CorridasDeSuitesDistintas):
        await ServicioComparacionCorridas(corridas).comparar(
            corrida_1.corrida_id, corrida_2.corrida_id
        )


async def test_comparar_corrida_inexistente_da_error_controlado(base):  # 9
    _, _, corridas, _ = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    with pytest.raises(CorridaNoEncontrada):
        await ServicioComparacionCorridas(corridas).comparar(9999, 9998)


async def test_comparar_no_cambia_si_se_edita_el_escenario_o_la_suite_despues(base):  # 10
    suites, escenarios, corridas, corredor, suite, e1, e2 = await _correr_suite_pass_fail(base)
    corrida_a = await corredor.ejecutar(suite.suite_id)
    corrida_b = await corredor.ejecutar(suite.suite_id)

    comparacion_antes = await ServicioComparacionCorridas(corridas).comparar(
        corrida_a.corrida_id, corrida_b.corrida_id
    )

    # Editar el escenario (nombre, tarjeta, monto, expectativa) y la suite
    # (nombre) DESPUES de ambas corridas no debe alterar ni un campo de la
    # comparacion ya hecha -esta lee unicamente los snapshots persistidos.
    await escenarios.actualizar(
        e1.escenario_id,
        DatosEdicionEscenario(
            nombre="E1 renombrado", card_id=e1.card_id, conexion_id=e1.conexion_id,
            monto=Decimal("999.99"), expectativas=Expectativas(estado=EstadoEjecucion.RECHAZADA),
        ),
    )
    await suites.actualizar(
        suite.suite_id,
        DatosEdicionSuite(nombre="Suite renombrada", escenarios=(e1.escenario_id, e2.escenario_id)),
    )

    comparacion_despues = await ServicioComparacionCorridas(corridas).comparar(
        corrida_a.corrida_id, corrida_b.corrida_id
    )
    assert comparacion_despues.resumen == comparacion_antes.resumen
    assert [item.cambio for item in comparacion_despues.items] == [
        item.cambio for item in comparacion_antes.items
    ]
    # El nombre historico del item sigue siendo el de cuando se corrio, no
    # el nombre nuevo del escenario.
    por_escenario = {item.escenario_id: item for item in comparacion_despues.items}
    assert por_escenario[e1.escenario_id].item_a.escenario_nombre == "E1"


# ------------------------------------- defensa ante datos historicos corruptos --
#
# `corrida_suite_items` no tiene UNIQUE sobre `escenario_id` (su PRIMARY KEY es
# `(corrida_id, orden)`); la aplicacion normal nunca produce un duplicado
# (`ServicioSuites._validar_escenarios` lo rechaza al guardar una suite), pero
# el comparador debe negarse a elegir uno en silencio si el dato ya esta
# corrupto. Se construye el estado corrupto a mano, con `ItemCorridaSuite`
# directos y `_comparar_items` (la funcion sin `await` ni repositorio) -no
# hace falta un repositorio falso ni forzar el flujo normal, que correctamente
# lo impide.


def _corrida(corrida_id: int, suite_id: str = "SUI-X") -> CorridaSuite:
    return CorridaSuite(suite_id=suite_id, suite_nombre="Suite", total=2, corrida_id=corrida_id)


def _item(escenario_id: str, orden: int, resultado=PASS) -> ItemCorridaSuite:
    return ItemCorridaSuite(
        corrida_id=1, escenario_id=escenario_id, escenario_nombre=escenario_id,
        orden=orden, resultado=resultado,
    )


def test_comparar_duplicado_en_corrida_a_da_error_controlado():  # duplicados, corrida A
    corrida_a = _corrida(corrida_id=7)
    corrida_b = _corrida(corrida_id=8)
    items_a = [_item("E1", 1), _item("E1", 2)]  # mismo escenario_id, dos ordenes
    items_b = [_item("E1", 1)]

    with pytest.raises(ItemsHistoricosDuplicados) as excinfo:
        _comparar_items(corrida_a, corrida_b, items_a, items_b)

    assert excinfo.value.corrida_id == 7
    assert excinfo.value.escenario_id == "E1"


def test_comparar_duplicado_en_corrida_b_da_error_controlado():  # duplicados, corrida B
    corrida_a = _corrida(corrida_id=7)
    corrida_b = _corrida(corrida_id=8)
    items_a = [_item("E1", 1)]
    items_b = [_item("E1", 1), _item("E1", 2)]  # mismo escenario_id, dos ordenes

    with pytest.raises(ItemsHistoricosDuplicados) as excinfo:
        _comparar_items(corrida_a, corrida_b, items_a, items_b)

    assert excinfo.value.corrida_id == 8
    assert excinfo.value.escenario_id == "E1"

"""Bloque 4: dominio y persistencia de suites de regresion.

SUITE = agrupacion reusable de escenarios. CORRIDA = ejecucion historica
concreta (`domain.corredor_suites`/`RepositorioCorridasSuite`). Este archivo
prueba el calculo puro de resultado global y la persistencia de las 4 tablas
nuevas: `suites`, `suite_escenarios`, `corridas_suite`, `corrida_suite_items`.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, DESTINO_ID_DEMO, inicializar
from sibutestlab8583.adapters.persistence.sqlite_repos import (
    RepositorioCorridasSuiteSQLite,
    RepositorioEscenariosSQLite,
    RepositorioSuitesSQLite,
)
from sibutestlab8583.domain.modelos import (
    CorridaSuite,
    Escenario,
    EstadoCorridaSuite,
    EstadoItemCorrida,
    ItemCorridaSuite,
    ResultadoGlobalSuite,
    Suite,
)
from sibutestlab8583.domain.suites import calcular_resultado_global


def _escenario(escenario_id: str, **overrides) -> Escenario:
    base = dict(
        escenario_id=escenario_id, nombre=f"Escenario {escenario_id}", perfil="generico",
        mti="0100", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO, monto=Decimal("10.00"),
    )
    base.update(overrides)
    return Escenario(**base)


# ------------------------------------------------ calcular_resultado_global --


def test_todos_pass_es_pass():
    conteos = {EstadoItemCorrida.PASS: 3}
    assert calcular_resultado_global(conteos) == ResultadoGlobalSuite.PASS


def test_algun_error_es_error_aunque_el_resto_sea_pass():
    conteos = {EstadoItemCorrida.PASS: 2, EstadoItemCorrida.ERROR: 1}
    assert calcular_resultado_global(conteos) == ResultadoGlobalSuite.ERROR


def test_algun_fail_es_fail_sin_error():
    conteos = {EstadoItemCorrida.PASS: 2, EstadoItemCorrida.FAIL: 1}
    assert calcular_resultado_global(conteos) == ResultadoGlobalSuite.FAIL


def test_error_tiene_prioridad_sobre_fail():
    conteos = {EstadoItemCorrida.FAIL: 1, EstadoItemCorrida.ERROR: 1}
    assert calcular_resultado_global(conteos) == ResultadoGlobalSuite.ERROR


def test_mezcla_pass_y_sin_expectativas_es_incompleta():
    """El caso central de la correccion: 1 PASS + N SIN_EXPECTATIVAS nunca es PASS."""
    conteos = {EstadoItemCorrida.PASS: 1, EstadoItemCorrida.SIN_EXPECTATIVAS: 19}
    assert calcular_resultado_global(conteos) == ResultadoGlobalSuite.INCOMPLETA


def test_todos_sin_expectativas_es_sin_expectativas():
    conteos = {EstadoItemCorrida.SIN_EXPECTATIVAS: 5}
    assert calcular_resultado_global(conteos) == ResultadoGlobalSuite.SIN_EXPECTATIVAS


def test_no_ejecutado_se_trata_como_inconsistencia_nunca_pass():
    """Una corrida FINALIZADA jamas deberia conservar un NO_EJECUTADO, pero si
    ocurriera, no debe poder colarse hacia PASS ni INCOMPLETA.
    """
    conteos = {EstadoItemCorrida.PASS: 2, EstadoItemCorrida.NO_EJECUTADO: 1}
    assert calcular_resultado_global(conteos) == ResultadoGlobalSuite.ERROR


def test_no_ejecutado_con_sin_expectativas_tambien_es_error():
    conteos = {EstadoItemCorrida.SIN_EXPECTATIVAS: 2, EstadoItemCorrida.NO_EJECUTADO: 1}
    assert calcular_resultado_global(conteos) == ResultadoGlobalSuite.ERROR


# ------------------------------------------------------------- persistencia --


async def test_la_inicializacion_crea_las_cuatro_tablas_de_suites(base):
    with sqlite3.connect(base) as conexion:
        tablas = {
            f[0] for f in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {"suites", "suite_escenarios", "corridas_suite", "corrida_suite_items"} <= tablas


async def test_inicializar_no_siembra_ninguna_suite(base):
    assert await RepositorioSuitesSQLite(base).listar() == []


async def test_guardar_y_recuperar_una_suite_nueva(base):
    repo_escenarios = RepositorioEscenariosSQLite(base)
    await repo_escenarios.guardar(_escenario("ESC-01"))
    await repo_escenarios.guardar(_escenario("ESC-02"))

    repo = RepositorioSuitesSQLite(base)
    await repo.guardar(
        Suite(suite_id="SUI-01", nombre="Regresion basica", escenarios=("ESC-01", "ESC-02"))
    )

    recuperada = await repo.obtener("SUI-01")
    assert recuperada is not None
    assert recuperada.nombre == "Regresion basica"
    assert recuperada.escenarios == ("ESC-01", "ESC-02")
    assert recuperada.activa


async def test_guardar_una_suite_persiste_el_orden(base):
    repo_escenarios = RepositorioEscenariosSQLite(base)
    for eid in ("ESC-A", "ESC-B", "ESC-C"):
        await repo_escenarios.guardar(_escenario(eid))

    repo = RepositorioSuitesSQLite(base)
    await repo.guardar(Suite(suite_id="SUI-02", nombre="X", escenarios=("ESC-C", "ESC-A", "ESC-B")))

    recuperada = await repo.obtener("SUI-02")
    assert recuperada.escenarios == ("ESC-C", "ESC-A", "ESC-B")


async def test_guardar_reemplaza_entera_la_membresia_no_la_fusiona(base):
    repo_escenarios = RepositorioEscenariosSQLite(base)
    for eid in ("ESC-X", "ESC-Y", "ESC-Z"):
        await repo_escenarios.guardar(_escenario(eid))

    repo = RepositorioSuitesSQLite(base)
    await repo.guardar(Suite(suite_id="SUI-03", nombre="X", escenarios=("ESC-X", "ESC-Y")))
    await repo.guardar(Suite(suite_id="SUI-03", nombre="X", escenarios=("ESC-Z",)))

    recuperada = await repo.obtener("SUI-03")
    assert recuperada.escenarios == ("ESC-Z",), "no debe conservar ESC-X/ESC-Y de antes"


async def test_guardar_es_un_upsert_por_suite_id(base):
    repo = RepositorioSuitesSQLite(base)
    await repo.guardar(Suite(suite_id="SUI-04", nombre="Original"))
    await repo.guardar(Suite(suite_id="SUI-04", nombre="Renombrada", activa=False))

    suites = await repo.listar()
    coincidencias = [s for s in suites if s.suite_id == "SUI-04"]
    assert len(coincidencias) == 1
    assert coincidencias[0].nombre == "Renombrada"
    assert not coincidencias[0].activa


async def test_una_suite_sin_escenarios_persiste_una_tupla_vacia(base):
    repo = RepositorioSuitesSQLite(base)
    await repo.guardar(Suite(suite_id="SUI-05", nombre="Vacia"))
    recuperada = await repo.obtener("SUI-05")
    assert recuperada.escenarios == ()


async def test_listar_ordena_por_nombre(base):
    repo = RepositorioSuitesSQLite(base)
    await repo.guardar(Suite(suite_id="SUI-Z", nombre="Z"))
    await repo.guardar(Suite(suite_id="SUI-A", nombre="A"))
    nombres = [s.nombre for s in await repo.listar()]
    assert nombres == sorted(nombres)


async def test_obtener_una_suite_inexistente_devuelve_none(base):
    assert await RepositorioSuitesSQLite(base).obtener("NO-EXISTE") is None


async def test_inicializar_es_idempotente_sobre_suites(tmp_path):
    ruta = tmp_path / "repetida.db"
    await inicializar(ruta)
    await inicializar(ruta)
    with sqlite3.connect(ruta) as conexion:
        tablas = {
            f[0] for f in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "suites" in tablas


# ------------------------------------------------------- corridas de suite --


async def test_crear_con_items_inserta_la_corrida_y_todos_los_items_presembrados(base):
    repo = RepositorioCorridasSuiteSQLite(base)
    await RepositorioSuitesSQLite(base).guardar(Suite(suite_id="SUI-10", nombre="X"))
    corrida = CorridaSuite(suite_id="SUI-10", suite_nombre="X", total=2)
    items = [
        ItemCorridaSuite(
            corrida_id=0, escenario_id="ESC-A", escenario_nombre="A", orden=1,
            resultado=EstadoItemCorrida.NO_EJECUTADO,
        ),
        ItemCorridaSuite(
            corrida_id=0, escenario_id="ESC-B", escenario_nombre="B", orden=2,
            resultado=EstadoItemCorrida.NO_EJECUTADO,
        ),
    ]
    corrida_id = await repo.crear_con_items(corrida, items)

    recuperada = await repo.obtener(corrida_id)
    assert recuperada.estado == EstadoCorridaSuite.EN_CURSO
    assert recuperada.resultado_global is None
    assert recuperada.total == 2

    items_guardados = await repo.obtener_items(corrida_id)
    assert [i.orden for i in items_guardados] == [1, 2]
    assert all(i.resultado == EstadoItemCorrida.NO_EJECUTADO for i in items_guardados)


async def test_actualizar_item_sobrescribe_solo_ese_item(base):
    repo = RepositorioCorridasSuiteSQLite(base)
    await RepositorioSuitesSQLite(base).guardar(Suite(suite_id="SUI-11", nombre="X"))
    corrida = CorridaSuite(suite_id="SUI-11", suite_nombre="X", total=2)
    items = [
        ItemCorridaSuite(
            corrida_id=0, escenario_id="ESC-A", escenario_nombre="A", orden=1,
            resultado=EstadoItemCorrida.NO_EJECUTADO,
        ),
        ItemCorridaSuite(
            corrida_id=0, escenario_id="ESC-B", escenario_nombre="B", orden=2,
            resultado=EstadoItemCorrida.NO_EJECUTADO,
        ),
    ]
    corrida_id = await repo.crear_con_items(corrida, items)

    await repo.actualizar_item(
        ItemCorridaSuite(
            corrida_id=corrida_id, escenario_id="ESC-A", escenario_nombre="A", orden=1,
            resultado=EstadoItemCorrida.PASS, ejecucion_id=42,
            evaluacion_json='{"version":1,"resultado":"pass"}',
        )
    )

    items_guardados = await repo.obtener_items(corrida_id)
    primero, segundo = items_guardados
    assert primero.resultado == EstadoItemCorrida.PASS
    assert primero.ejecucion_id == 42
    assert primero.evaluacion_json == '{"version":1,"resultado":"pass"}'
    assert segundo.resultado == EstadoItemCorrida.NO_EJECUTADO, "el otro item no debe tocarse"


async def test_cerrar_actualiza_estado_resultado_y_contadores(base):
    repo = RepositorioCorridasSuiteSQLite(base)
    await RepositorioSuitesSQLite(base).guardar(Suite(suite_id="SUI-12", nombre="X"))
    corrida = CorridaSuite(suite_id="SUI-12", suite_nombre="X", total=1)
    corrida_id = await repo.crear_con_items(
        corrida,
        [ItemCorridaSuite(corrida_id=0, escenario_id="ESC-A", escenario_nombre="A", orden=1,
                           resultado=EstadoItemCorrida.NO_EJECUTADO)],
    )
    corrida.estado = EstadoCorridaSuite.FINALIZADA
    corrida.resultado_global = ResultadoGlobalSuite.PASS
    corrida.cantidad_pass = 1
    from datetime import datetime, timezone

    corrida.finalizada_en = datetime.now(timezone.utc)
    await repo.cerrar(corrida)

    recuperada = await repo.obtener(corrida_id)
    assert recuperada.estado == EstadoCorridaSuite.FINALIZADA
    assert recuperada.resultado_global == ResultadoGlobalSuite.PASS
    assert recuperada.cantidad_pass == 1
    assert recuperada.finalizada_en is not None


async def test_listar_corridas_ordena_por_mas_reciente(base):
    repo = RepositorioCorridasSuiteSQLite(base)
    await RepositorioSuitesSQLite(base).guardar(Suite(suite_id="SUI-13", nombre="X"))
    primero = await repo.crear_con_items(CorridaSuite(suite_id="SUI-13", suite_nombre="X", total=0), [])
    segundo = await repo.crear_con_items(CorridaSuite(suite_id="SUI-13", suite_nombre="X", total=0), [])

    corridas = await repo.listar()
    assert corridas[0].corrida_id == segundo
    assert corridas[1].corrida_id == primero

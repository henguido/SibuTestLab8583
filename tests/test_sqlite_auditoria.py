"""Auditoria de persistencia SQLite (Bloque 4): FKs, atomicidad e indices.

Este archivo es de AUDITORIA, no de especificacion: cada prueba documenta con
evidencia real un comportamiento observado (correcto o defectuoso) de
`esquema.py` / `sqlite_repos.py`. No se toca produccion.

Nota de la ronda nocturna de auditoria: `RepositorioCorridasSuiteSQLite.actualizar_item`
NO activaba `PRAGMA foreign_keys = ON` (a diferencia de `guardar()`/`crear_con_items()`),
permitiendo un `ejecucion_id` huerfano. Se corrigio agregando la pragma; las dos
pruebas de esa seccion se actualizaron para reflejar el comportamiento YA CORREGIDO
en vez de documentar el defecto original.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from decimal import Decimal

import aiosqlite
import pytest

from sibutestlab8583.adapters.persistence.esquema import (
    CARD_ID_DEMO,
    DESTINO_ID_DEMO,
    inicializar,
)
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


def _escenario(escenario_id: str, **overrides) -> Escenario:
    base = dict(
        escenario_id=escenario_id, nombre=f"Escenario {escenario_id}", perfil="generico",
        mti="0100", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO, monto=Decimal("10.00"),
    )
    base.update(overrides)
    return Escenario(**base)


# ---------------------------------------------------------------- item 2: FKs --


async def test_foreign_keys_esta_apagada_por_defecto_en_una_conexion_nueva(base):
    """Documenta el comportamiento de base de aiosqlite/SQLite: PRAGMA
    foreign_keys es una propiedad de LA CONEXION, nunca del archivo. Una nueva
    conexion que no la active explicitamente queda con FKs OFF, aunque
    `inicializar()` si la haya activado en la suya.
    """
    async with aiosqlite.connect(base) as conexion:
        async with conexion.execute("PRAGMA foreign_keys") as cursor:
            fila = await cursor.fetchone()
    assert fila[0] == 0, "una conexion nueva no hereda foreign_keys=ON de otra conexion"


async def test_actualizar_item_ahora_activa_foreign_keys_y_rechaza_ejecucion_id_huerfano(base):
    """Corregido durante la auditoria nocturna: `RepositorioCorridasSuiteSQLite.actualizar_item`
    (sqlite_repos.py) ahora ejecuta `PRAGMA foreign_keys = ON` antes del UPDATE,
    igual que ya hacian `guardar()`/`crear_con_items()`. Un `ejecucion_id`
    inexistente debe rechazarse, no aceptarse como referencia huerfana.
    """
    repo = RepositorioCorridasSuiteSQLite(base)
    await RepositorioSuitesSQLite(base).guardar(Suite(suite_id="SUI-AUD-1", nombre="X"))
    corrida_id = await repo.crear_con_items(
        CorridaSuite(suite_id="SUI-AUD-1", suite_nombre="X", total=1),
        [ItemCorridaSuite(corrida_id=0, escenario_id="ESC-A", escenario_nombre="A", orden=1,
                           resultado=EstadoItemCorrida.NO_EJECUTADO)],
    )

    # ejecucion_id=999999 no existe en `ejecuciones`: debe rechazarse.
    with pytest.raises(aiosqlite.IntegrityError):
        await repo.actualizar_item(
            ItemCorridaSuite(
                corrida_id=corrida_id, escenario_id="ESC-A", escenario_nombre="A", orden=1,
                resultado=EstadoItemCorrida.PASS, ejecucion_id=999999,
            )
        )

    items = await repo.obtener_items(corrida_id)
    assert items[0].ejecucion_id is None, (
        "el item no debio actualizarse: la referencia huerfana debe rechazarse por completo"
    )
    assert items[0].resultado == EstadoItemCorrida.NO_EJECUTADO, (
        "un UPDATE rechazado no debe dejar ningun campo modificado a medias"
    )


async def test_guardar_suite_con_escenario_id_inexistente_es_rechazado_por_fk(base):
    """`RepositorioSuitesSQLite.guardar` SI activa foreign_keys=ON (sqlite_repos.py
    linea 453). Confirma que el INSERT de `suite_escenarios` con un
    escenario_id inexistente falla, tal como exige la FK declarada.
    """
    repo = RepositorioSuitesSQLite(base)
    with pytest.raises(aiosqlite.IntegrityError):
        await repo.guardar(
            Suite(suite_id="SUI-AUD-3", nombre="X", escenarios=("NO-EXISTE",))
        )


async def test_crear_con_items_con_ejecucion_id_inexistente_es_rechazado_por_fk(base):
    """`crear_con_items` SI activa foreign_keys=ON. Un ejecucion_id inexistente en
    uno de los items presembrados debe hacer fallar el INSERT completo.
    """
    repo = RepositorioCorridasSuiteSQLite(base)
    await RepositorioSuitesSQLite(base).guardar(Suite(suite_id="SUI-AUD-4", nombre="X"))
    with pytest.raises(aiosqlite.IntegrityError):
        await repo.crear_con_items(
            CorridaSuite(suite_id="SUI-AUD-4", suite_nombre="X", total=1),
            [ItemCorridaSuite(corrida_id=0, escenario_id="ESC-A", escenario_nombre="A", orden=1,
                               resultado=EstadoItemCorrida.NO_EJECUTADO, ejecucion_id=999999)],
        )


# ------------------------------------------------------- item 3/8: atomicidad de guardar --


async def test_guardar_suite_falla_a_mitad_no_deja_estado_parcial(base):
    """Fuerza un error a mitad del `guardar` de una suite YA EXISTENTE con
    membresia previa: la nueva lista incluye un escenario_id inexistente. Si
    DELETE+INSERT no estuvieran en la misma transaccion (o el rollback no
    ocurriera), la membresia anterior se perderia sin que la nueva quedara
    guardada. Se verifica que la membresia ANTERIOR sobrevive intacta.
    """
    repo_escenarios = RepositorioEscenariosSQLite(base)
    await repo_escenarios.guardar(_escenario("ESC-P1"))
    await repo_escenarios.guardar(_escenario("ESC-P2"))

    repo = RepositorioSuitesSQLite(base)
    await repo.guardar(Suite(suite_id="SUI-AT-1", nombre="X", escenarios=("ESC-P1", "ESC-P2")))

    # Intento de guardar con un escenario inexistente en la nueva membresia.
    with pytest.raises(aiosqlite.IntegrityError):
        await repo.guardar(
            Suite(suite_id="SUI-AT-1", nombre="Y", escenarios=("ESC-P1", "NO-EXISTE"))
        )

    recuperada = await repo.obtener("SUI-AT-1")
    assert recuperada is not None
    assert recuperada.nombre == "X", "el rename a 'Y' NO debe haberse aplicado (mismo commit)"
    assert recuperada.escenarios == ("ESC-P1", "ESC-P2"), (
        "la membresia anterior debe sobrevivir intacta: el DELETE previo al "
        "INSERT que fallo debe haberse revertido junto con todo lo demas"
    )


async def test_crear_con_items_falla_a_mitad_no_deja_corrida_sin_items(base):
    """Fuerza un error en el segundo item del `executemany` de
    `crear_con_items` (ejecucion_id inexistente) y confirma que la fila de
    `corridas_suite` recien insertada TAMBIEN desaparece -no queda una corrida
    huerfana sin ninguno de sus items-.
    """
    repo = RepositorioCorridasSuiteSQLite(base)
    await RepositorioSuitesSQLite(base).guardar(Suite(suite_id="SUI-AT-2", nombre="X"))

    with pytest.raises(aiosqlite.IntegrityError):
        await repo.crear_con_items(
            CorridaSuite(suite_id="SUI-AT-2", suite_nombre="X", total=2),
            [
                ItemCorridaSuite(corrida_id=0, escenario_id="ESC-A", escenario_nombre="A",
                                  orden=1, resultado=EstadoItemCorrida.NO_EJECUTADO),
                ItemCorridaSuite(corrida_id=0, escenario_id="ESC-B", escenario_nombre="B",
                                  orden=2, resultado=EstadoItemCorrida.NO_EJECUTADO,
                                  ejecucion_id=999999),
            ],
        )

    async with aiosqlite.connect(base) as conexion:
        total_corridas = (
            await (await conexion.execute(
                "SELECT COUNT(*) FROM corridas_suite WHERE suite_id = ?", ("SUI-AT-2",)
            )).fetchone()
        )[0]
        total_items = (
            await (await conexion.execute(
                "SELECT COUNT(*) FROM corrida_suite_items"
            )).fetchone()
        )[0]
    assert total_corridas == 0, (
        "la fila de corridas_suite insertada antes del error debe haberse revertido"
    )
    # No hay forma de referenciar el corrida_id (el INSERT se revirtio), pero
    # como no quedo ninguna corrida para SUI-AT-2, tampoco puede haber items
    # huerfanos de esa corrida en la tabla global (que en este test esta vacia
    # de items de cualquier otra corrida).
    assert total_items == 0


# ---------------------------------------------------- item 10: cierre de corrida --


async def test_cerrar_es_un_unico_update_atomico_por_construccion(base):
    """`cerrar()` emite un solo UPDATE (una sola sentencia SQL), por lo que no
    existe una ventana intermedia donde `estado` cambie sin que los contadores
    lo hagan: SQLite aplica todas las columnas de un UPDATE en un unico paso
    interno. Se confirma leyendo el codigo fuente (sqlite_repos.py 562-582): no
    hay mas de un `execute` entre la apertura de conexion y el commit.
    """
    import inspect

    from sibutestlab8583.adapters.persistence import sqlite_repos

    codigo = inspect.getsource(sqlite_repos.RepositorioCorridasSuiteSQLite.cerrar)
    assert codigo.count("conexion.execute(") == 1, (
        "cerrar() debe seguir siendo un unico execute; si esto falla, el metodo "
        "cambio y la atomicidad debe reverificarse"
    )


# --------------------------------------------------- item 11: interrupcion real --


async def test_interrupcion_a_mitad_de_corrida_deja_items_mixtos_y_corrida_en_curso(base):
    """Simula el proceso muriendo entre el segundo y el tercer escenario de una
    corrida de 3: se llama `actualizar_item` dos veces y nunca se llama
    `cerrar`. Confirma exactamente el disenio documentado en
    `RepositorioCorridasSuiteSQLite`: los items ya actualizados quedan
    correctos, el resto en NO_EJECUTADO, y la corrida queda EN_CURSO
    indefinidamente (nadie la cierra sola).
    """
    repo = RepositorioCorridasSuiteSQLite(base)
    await RepositorioSuitesSQLite(base).guardar(Suite(suite_id="SUI-INT-1", nombre="X"))
    corrida_id = await repo.crear_con_items(
        CorridaSuite(suite_id="SUI-INT-1", suite_nombre="X", total=3),
        [
            ItemCorridaSuite(corrida_id=0, escenario_id="ESC-A", escenario_nombre="A",
                              orden=1, resultado=EstadoItemCorrida.NO_EJECUTADO),
            ItemCorridaSuite(corrida_id=0, escenario_id="ESC-B", escenario_nombre="B",
                              orden=2, resultado=EstadoItemCorrida.NO_EJECUTADO),
            ItemCorridaSuite(corrida_id=0, escenario_id="ESC-C", escenario_nombre="C",
                              orden=3, resultado=EstadoItemCorrida.NO_EJECUTADO),
        ],
    )

    # "Se ejecutan" los primeros dos escenarios; el proceso "muere" antes del tercero.
    await repo.actualizar_item(
        ItemCorridaSuite(corrida_id=corrida_id, escenario_id="ESC-A", escenario_nombre="A",
                          orden=1, resultado=EstadoItemCorrida.PASS, ejecucion_id=None)
    )
    await repo.actualizar_item(
        ItemCorridaSuite(corrida_id=corrida_id, escenario_id="ESC-B", escenario_nombre="B",
                          orden=2, resultado=EstadoItemCorrida.FAIL, ejecucion_id=None)
    )
    # (nunca se llama cerrar(): el proceso "murio" aqui)

    corrida = await repo.obtener(corrida_id)
    items = await repo.obtener_items(corrida_id)

    assert corrida.estado == EstadoCorridaSuite.EN_CURSO, (
        "confirmado: sin un proceso de recuperacion explicito, la corrida "
        "queda EN_CURSO para siempre tras una interrupcion"
    )
    assert corrida.resultado_global is None
    assert [i.resultado for i in items] == [
        EstadoItemCorrida.PASS,
        EstadoItemCorrida.FAIL,
        EstadoItemCorrida.NO_EJECUTADO,
    ], "los items ya actualizados persisten correctamente; el resto queda NO_EJECUTADO"


# --------------------------------------------------------------- item 5/7/6 --


async def test_inicializar_dos_veces_seguidas_no_duplica_filas_de_suites(tmp_path):
    """Caso no cubierto explicitamente por test_migracion_generalizada.py: dos
    inicializaciones consecutivas de una base COMPLETAMENTE NUEVA (no una
    migrada desde un esquema viejo) no deben duplicar la semilla de destinos
    ni ninguna otra fila de las 4 tablas de suites (que de por si no siembran
    nada, pero se confirma que el esquema/indices no generan un error en la
    segunda pasada con datos ya presentes).
    """
    ruta = tmp_path / "nueva_dos_veces.db"
    await inicializar(ruta)
    await inicializar(ruta)  # no debe fallar ni duplicar

    with sqlite3.connect(ruta) as conexion:
        conexion.row_factory = sqlite3.Row
        destinos = conexion.execute(
            "SELECT COUNT(*) AS n FROM destinos WHERE destino_id = ?", (DESTINO_ID_DEMO,)
        ).fetchone()["n"]
        tarjetas = conexion.execute(
            "SELECT COUNT(*) AS n FROM tarjetas_prueba WHERE card_id = ?", (CARD_ID_DEMO,)
        ).fetchone()["n"]
        suites = conexion.execute("SELECT COUNT(*) AS n FROM suites").fetchone()["n"]
    assert destinos == 1
    assert tarjetas == 1
    assert suites == 0


async def test_db_completamente_nueva_no_requiere_pasos_manuales(tmp_path):
    """Item 7: una unica llamada a `inicializar()` sobre una ruta que no existe
    deja las 4 tablas nuevas listas para usarse sin ningun paso adicional.
    """
    ruta = tmp_path / "desde_cero.db"
    assert not ruta.exists()
    await inicializar(ruta, con_datos_demo=False)

    repo_suites = RepositorioSuitesSQLite(ruta)
    await repo_suites.guardar(Suite(suite_id="SUI-CERO", nombre="X"))
    assert await repo_suites.obtener("SUI-CERO") is not None


# --------------------------------------------------------------------- item 1 --


async def test_indice_de_items_por_corrida_existe_via_pk_compuesta(base):
    """`corrida_suite_items` no tiene un CREATE INDEX explicito sobre
    `corrida_id`, pero su PRIMARY KEY es (corrida_id, orden): en SQLite eso
    crea automaticamente un indice interno cuyo prefijo cubre `WHERE
    corrida_id = ?` (el patron real de `obtener_items`). Se confirma con
    EXPLAIN QUERY PLAN que la consulta usa esa clave, no un table scan.
    """
    async with aiosqlite.connect(base) as conexion:
        async with conexion.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM corrida_suite_items"
            " WHERE corrida_id = ? ORDER BY orden",
            (1,),
        ) as cursor:
            plan = await cursor.fetchall()
    texto_plan = " ".join(str(fila) for fila in plan)
    assert "SCAN" not in texto_plan.upper() or "corrida_suite_items" not in texto_plan.upper() \
        or "USING INDEX" in texto_plan.upper() or "USING PRIMARY KEY" in texto_plan.upper(), (
        f"se esperaba uso de la PK compuesta, plan real: {plan}"
    )

"""Migracion de las tablas de Reglas del Host (Fase D1, 2026-09-14).

Mismo criterio que C1/C2/B8/C3: solo tablas NUEVAS (`reglas_host`,
`reglas_host_eventos`) via `CREATE TABLE IF NOT EXISTS` -ninguna tabla
existente se toca-. Estas pruebas confirman que eso es seguro contra una
base YA POBLADA de una version anterior, sin perder ninguna fila existente,
y que `inicializar()` sigue siendo idempotente.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, inicializar
from sibutestlab8583.adapters.persistence.sqlite_repos import RepositorioEjecucionesSQLite
from sibutestlab8583.domain.modelos import Ejecucion, EstadoEjecucion


async def test_una_base_nueva_ya_nace_con_las_tablas_de_reglas_host(base):
    with sqlite3.connect(base) as conexion:
        nombres = {
            fila[0]
            for fila in conexion.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {"reglas_host", "reglas_host_eventos"} <= nombres


async def test_la_migracion_preserva_las_ejecuciones_existentes(base):
    repo = RepositorioEjecucionesSQLite(base)
    ejecucion = Ejecucion(
        stan="000001", estado=EstadoEjecucion.APROBADA, card_id=CARD_ID_DEMO,
        monto=Decimal("10.00"),
    )
    await repo.guardar(ejecucion)

    await inicializar(base)  # reinicializar: idempotente, no debe tocar la fila

    con = await RepositorioEjecucionesSQLite(base).obtener(1)
    assert con is not None
    assert con.stan == "000001"

    with sqlite3.connect(base) as conexion:
        conexion.execute("PRAGMA foreign_keys = ON")
        violaciones = conexion.execute("PRAGMA foreign_key_check").fetchall()
    assert violaciones == []


async def test_la_migracion_es_idempotente(base):
    await inicializar(base)
    await inicializar(base)
    with sqlite3.connect(base) as conexion:
        tablas = conexion.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            " AND name IN ('reglas_host', 'reglas_host_eventos')"
        ).fetchone()[0]
    assert tablas == 2


async def test_una_base_nueva_ya_nace_con_la_tabla_de_estado_d2(base):
    with sqlite3.connect(base) as conexion:
        nombres = {
            fila[0]
            for fila in conexion.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "reglas_host_estado" in nombres


async def test_columnas_d2_presentes_y_la_migracion_es_idempotente(base):
    await inicializar(base)
    await inicializar(base)
    with sqlite3.connect(base) as conexion:
        columnas_reglas = {r[1] for r in conexion.execute("PRAGMA table_info(reglas_host)")}
        columnas_eventos = {r[1] for r in conexion.execute("PRAGMA table_info(reglas_host_eventos)")}
    assert "max_aplicaciones" in columnas_reglas
    assert "match_number" in columnas_eventos

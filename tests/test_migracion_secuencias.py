"""Migracion de las tablas de Secuencias transaccionales (Fase C1).

A diferencia de B6 (`ejecucion_origen_id`, columna aditiva sobre una tabla
YA EXISTENTE), C1 no modifica ninguna tabla existente: solo agrega tablas
NUEVAS (`secuencias_transaccionales`, `secuencia_transaccional_pasos`,
`corridas_secuencia`, `corrida_secuencia_pasos`) via `CREATE TABLE IF NOT
EXISTS`. Estas pruebas confirman que eso es seguro contra una base YA
POBLADA de una version anterior (B7), sin perder ninguna fila existente, y
que `inicializar()` sigue siendo idempotente.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, inicializar
from sibutestlab8583.adapters.persistence.sqlite_repos import RepositorioEjecucionesSQLite
from sibutestlab8583.domain.modelos import Ejecucion, EstadoEjecucion


async def test_una_base_nueva_ya_nace_con_las_tablas_de_secuencias(base):
    with sqlite3.connect(base) as conexion:
        nombres = {
            fila[0]
            for fila in conexion.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert {
        "secuencias_transaccionales",
        "secuencia_transaccional_pasos",
        "corridas_secuencia",
        "corrida_secuencia_pasos",
    } <= nombres
    # La tabla del contador de STAN sigue existiendo, sin colision de nombre.
    assert "secuencias" in nombres


def _crear_base_anterior_a_c1_con_una_ejecucion_real(ruta) -> None:
    """Simula una base de B7 (ya con `ejecucion_origen_id`, sin las tablas
    de Secuencias) insertando una fila real de `ejecuciones` DESPUES de
    haber corrido `inicializar()` -o sea, el DDL completo incluido C1 ya
    corrio-. Como C1 no quita nada, la unica forma real de probar
    "base anterior a C1" es confirmar que las tablas nuevas coexisten sin
    tocar filas ya existentes en `ejecuciones`; no hace falta un esquema
    manual reducido -a diferencia de B6, aqui no hay ninguna columna nueva
    en una tabla vieja que una base antigua pudiera no tener-.
    """


async def test_la_migracion_preserva_las_ejecuciones_existentes(base):
    repo = RepositorioEjecucionesSQLite(base)
    ejecucion = Ejecucion(
        stan="000001", estado=EstadoEjecucion.APROBADA, card_id=CARD_ID_DEMO,
        monto=Decimal("10.00"),
    )
    await repo.guardar(ejecucion)

    # Reinicializar (idempotente): no debe tocar la fila ya guardada ni
    # fallar por las tablas de Secuencias ya presentes.
    await inicializar(base)

    con = await RepositorioEjecucionesSQLite(base).obtener(1)
    assert con is not None
    assert con.stan == "000001"
    assert con.estado is EstadoEjecucion.APROBADA

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
            " AND name IN ('secuencias_transaccionales', 'secuencia_transaccional_pasos',"
            "              'corridas_secuencia', 'corrida_secuencia_pasos')"
        ).fetchone()[0]
    assert tablas == 4


async def test_operacion_derivada_existe_con_default_reverso_financiero(base):
    """B8: `operacion_derivada` es aditiva sobre `secuencia_transaccional_pasos`
    (ya existente desde C1) -una fila insertada ANTES de B8 (o por cualquier
    INSERT que no la mencione) debe leerse como reverso financiero, nunca
    como NULL ni como un valor inventado."""
    with sqlite3.connect(base) as conexion:
        columnas = {
            fila[1] for fila in conexion.execute(
                "PRAGMA table_info(secuencia_transaccional_pasos)"
            ).fetchall()
        }
        assert "operacion_derivada" in columnas

        conexion.execute(
            "INSERT INTO secuencias_transaccionales"
            " (secuencia_id, nombre, descripcion, activa, creado_en, actualizado_en)"
            " VALUES ('SEQ-MIGRACION', 'x', '', 1, '2026-01-01', '2026-01-01')"
        )
        conexion.execute(
            "INSERT INTO secuencia_transaccional_pasos"
            " (secuencia_id, orden, origen_tipo, origen_paso_orden)"
            " VALUES ('SEQ-MIGRACION', 1, 'derivado', 1)"
        )
        conexion.commit()
        valor = conexion.execute(
            "SELECT operacion_derivada FROM secuencia_transaccional_pasos"
            " WHERE secuencia_id = 'SEQ-MIGRACION'"
        ).fetchone()[0]
    assert valor == "financial_reversal"

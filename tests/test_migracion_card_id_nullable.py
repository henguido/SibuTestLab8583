"""B2: `ejecuciones.card_id`/`monto`/`moneda` pasan a ser NULLABLE.

Necesario para persistir una operacion sin tarjeta ni monto (0800 Network
Management/Echo, primera operacion de B2 distinta de compra) a traves del
mismo esquema -sin inventar un sentinel falso ni una tabla paralela-.

SQLite no admite quitar `NOT NULL` con `ALTER TABLE`: el camino es
reconstruir la tabla (`_migrar_ejecuciones_card_id_nullable`). Estas pruebas
verifican que la reconstruccion es segura -ninguna fila existente pierde ni
cambia un valor-, idempotente, y que una base nueva ya nace con la columna
nullable sin necesitar el camino de migracion en absoluto.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from decimal import Decimal

from sibutestlab8583.adapters.persistence.esquema import inicializar
from sibutestlab8583.adapters.persistence.sqlite_repos import RepositorioEjecucionesSQLite
from sibutestlab8583.domain.datos_sinteticos import pan_sintetico
from sibutestlab8583.domain.modelos import EstadoEjecucion, Ejecucion, MTI_ECHO, MTI_RESPUESTA_ECHO


def _notnull_card_id(ruta) -> int:
    with sqlite3.connect(ruta) as conexion:
        fila = next(
            f for f in conexion.execute("PRAGMA table_info(ejecuciones)") if f[1] == "card_id"
        )
        return fila[3]  # (cid, name, type, notnull, dflt_value, pk)


async def test_una_base_nueva_ya_nace_con_card_id_nullable(tmp_path):
    ruta = tmp_path / "nueva.db"
    await inicializar(ruta, con_datos_demo=False)
    assert _notnull_card_id(ruta) == 0


def _crear_base_anterior_a_b2(ruta) -> None:
    """Reproduce `ejecuciones` tal como era justo antes de B2: todas las
    columnas modernas ya presentes, pero `card_id`/`monto`/`moneda` todavia
    `NOT NULL` (el esquema real anterior a este cambio)."""
    ddl_anterior = """
    CREATE TABLE tarjetas_prueba (
        card_id           TEXT PRIMARY KEY,
        pan               TEXT NOT NULL,
        pan_enmascarado   TEXT NOT NULL,
        expiracion        TEXT NOT NULL,
        descripcion       TEXT NOT NULL DEFAULT '',
        sintetica         INTEGER NOT NULL DEFAULT 1,
        activa            INTEGER NOT NULL DEFAULT 1,
        creada_en         TEXT NOT NULL
    );
    CREATE TABLE escenarios (
        escenario_id TEXT PRIMARY KEY,
        nombre       TEXT NOT NULL
    );
    CREATE TABLE ejecuciones (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        creada_en               TEXT    NOT NULL,
        card_id                 TEXT    NOT NULL REFERENCES tarjetas_prueba(card_id),
        mti_solicitud           TEXT    NOT NULL,
        mti_respuesta           TEXT,
        monto                   TEXT    NOT NULL,
        moneda                  TEXT    NOT NULL,
        stan                    TEXT    NOT NULL,
        destino_host            TEXT,
        destino_puerto          INTEGER,
        estado                  TEXT    NOT NULL,
        codigo_respuesta        TEXT,
        solicitud_enmascarada   TEXT,
        respuesta_enmascarada   TEXT,
        solicitud_json          TEXT,
        respuesta_json          TEXT,
        latencia_ms             INTEGER,
        escenario_id            TEXT,
        escenario_nombre        TEXT,
        evaluacion_estado       TEXT,
        evaluacion_json         TEXT,
        motivo_detalle          TEXT
    );
    """
    with sqlite3.connect(ruta) as conexion:
        conexion.executescript(ddl_anterior)
        pan = pan_sintetico("6666")
        conexion.execute(
            "INSERT INTO tarjetas_prueba"
            " (card_id, pan, pan_enmascarado, expiracion, creada_en)"
            " VALUES ('VIEJA-B2', ?, '************6666', '3012',"
            "         '2026-01-01T00:00:00+00:00')",
            (pan,),
        )
        conexion.execute(
            "INSERT INTO ejecuciones"
            " (creada_en, card_id, mti_solicitud, monto, moneda, stan, estado,"
            "  destino_host, destino_puerto, codigo_respuesta, latencia_ms)"
            " VALUES ('2026-01-01T00:00:00+00:00', 'VIEJA-B2', '0100', '10.00', '188',"
            "         '000001', 'aprobada', '127.0.0.1', 8583, '00', 42)"
        )


async def test_una_base_anterior_a_b2_se_reconstruye_sin_perder_filas(tmp_path):
    ruta = tmp_path / "anterior_b2.db"
    _crear_base_anterior_a_b2(ruta)
    assert _notnull_card_id(ruta) == 1  # confirma el punto de partida

    await inicializar(ruta, con_datos_demo=False)

    assert _notnull_card_id(ruta) == 0
    with sqlite3.connect(ruta) as conexion:
        conexion.row_factory = sqlite3.Row
        fila = conexion.execute(
            "SELECT * FROM ejecuciones WHERE card_id = 'VIEJA-B2'"
        ).fetchone()

    assert fila is not None, "la fila anterior se conserva"
    assert fila["monto"] == "10.00"
    assert fila["moneda"] == "188"
    assert fila["stan"] == "000001"
    assert fila["estado"] == "aprobada"
    assert fila["destino_host"] == "127.0.0.1"
    assert fila["destino_puerto"] == 8583
    assert fila["codigo_respuesta"] == "00"
    assert fila["latencia_ms"] == 42


async def test_la_migracion_de_card_id_nullable_es_idempotente(tmp_path):
    ruta = tmp_path / "idempotente.db"
    _crear_base_anterior_a_b2(ruta)

    await inicializar(ruta, con_datos_demo=False)
    await inicializar(ruta, con_datos_demo=False)  # segunda vez: no debe reventar

    assert _notnull_card_id(ruta) == 0
    with sqlite3.connect(ruta) as conexion:
        total = conexion.execute("SELECT COUNT(*) FROM ejecuciones").fetchone()[0]
    assert total == 1, "la reconstruccion no debe duplicar ni perder filas"


async def test_una_ejecucion_sin_tarjeta_ni_monto_se_persiste_y_se_lee_igual(base):
    """El caso real que motiva la migracion: una operacion tipo Echo (0800),
    sin card_id/monto/moneda, debe poder guardarse y recuperarse con esos
    tres campos en `None` -no con un sentinel inventado ("", 0)."""
    repo = RepositorioEjecucionesSQLite(base)
    ejecucion = Ejecucion(
        stan="000123",
        estado=EstadoEjecucion.APROBADA,
        mti_solicitud=MTI_ECHO,
        mti_respuesta=MTI_RESPUESTA_ECHO,
        codigo_respuesta="00",
        creada_en=datetime(2026, 9, 12, 10, 0, 0, tzinfo=timezone.utc),
    )
    id_ejecucion = await repo.guardar(ejecucion)

    recuperada = await repo.obtener(id_ejecucion)
    assert recuperada is not None
    assert recuperada.card_id is None
    assert recuperada.monto is None
    assert recuperada.moneda is None
    assert recuperada.mti_solicitud == MTI_ECHO
    assert recuperada.mti_respuesta == MTI_RESPUESTA_ECHO
    assert recuperada.stan == "000123"

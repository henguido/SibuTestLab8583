"""B3: `escenarios.card_id`/`monto` pasan a ser NULLABLE, y gana `operacion`.

Necesario para que un escenario Echo (sin tarjeta ni monto) se pueda guardar
con el MISMO esquema que un escenario de compra -sin tabla paralela, sin
sentinel inventado-, exactamente el mismo criterio que B2 ya aplico a
`ejecuciones`.

Este archivo reproduce la cadena real completa que motiva la migracion
(escenario -> suite -> suite_item -> corrida -> corrida_suite_item ->
ejecucion), simulando una base ANTERIOR a B3 con datos reales en cada tabla,
y verifica que la reconstruccion (mismo patron de rebuild que
`_migrar_ejecuciones_card_id_nullable` en B2, ver
`_migrar_escenarios_card_id_nullable`) preserva absolutamente todo: mismos
ids, mismo orden, mismas relaciones, `PRAGMA foreign_key_check` limpio.
"""

from __future__ import annotations

import sqlite3

from sibutestlab8583.adapters.persistence.esquema import inicializar
from sibutestlab8583.adapters.persistence.sqlite_repos import RepositorioEscenariosSQLite
from sibutestlab8583.domain.datos_sinteticos import pan_sintetico
from sibutestlab8583.domain.modelos import Escenario, OPERACION_COMPRA, OPERACION_ECHO


def _notnull_card_id_escenarios(ruta) -> int:
    with sqlite3.connect(ruta) as conexion:
        fila = next(
            f for f in conexion.execute("PRAGMA table_info(escenarios)") if f[1] == "card_id"
        )
        return fila[3]


async def test_una_base_nueva_ya_nace_con_escenarios_card_id_nullable_y_operacion(tmp_path):
    ruta = tmp_path / "nueva.db"
    await inicializar(ruta, con_datos_demo=False)
    assert _notnull_card_id_escenarios(ruta) == 0
    with sqlite3.connect(ruta) as conexion:
        columnas = {f[1] for f in conexion.execute("PRAGMA table_info(escenarios)")}
    assert "operacion" in columnas


def _crear_base_anterior_a_b3_con_cadena_completa(ruta) -> None:
    """Reproduce el esquema justo antes de B3 -escenarios.card_id/monto
    todavia NOT NULL, sin columna `operacion`- con una cadena real completa:
    un escenario, una suite que lo contiene, una corrida de esa suite con un
    item que referencia una ejecucion real. Es exactamente la forma de una
    base de desarrollo con historial real de uso, el caso que el fixture de
    B2 no cubria y que el pedido de B3 exige probar antes de tocar la base
    real.
    """
    ddl_anterior = """
    CREATE TABLE tarjetas_prueba (
        card_id           TEXT PRIMARY KEY,
        pan               TEXT NOT NULL,
        pan_enmascarado   TEXT NOT NULL,
        expiracion        TEXT NOT NULL,
        creada_en         TEXT NOT NULL
    );
    CREATE TABLE destinos (
        destino_id TEXT PRIMARY KEY,
        nombre     TEXT NOT NULL,
        host       TEXT NOT NULL,
        puerto     INTEGER NOT NULL,
        activo     INTEGER NOT NULL DEFAULT 1,
        creado_en  TEXT NOT NULL
    );
    CREATE TABLE escenarios (
        escenario_id   TEXT PRIMARY KEY,
        nombre         TEXT NOT NULL,
        perfil         TEXT NOT NULL,
        mti            TEXT NOT NULL DEFAULT '0100',
        card_id        TEXT NOT NULL REFERENCES tarjetas_prueba(card_id),
        conexion_id    TEXT NOT NULL REFERENCES destinos(destino_id),
        monto          TEXT NOT NULL,
        campos_json    TEXT NOT NULL DEFAULT '{}',
        expected_json  TEXT,
        activo         INTEGER NOT NULL DEFAULT 1,
        creado_en      TEXT NOT NULL,
        actualizado_en TEXT NOT NULL
    );
    CREATE TABLE ejecuciones (
        id                      INTEGER PRIMARY KEY AUTOINCREMENT,
        creada_en               TEXT    NOT NULL,
        card_id                 TEXT    REFERENCES tarjetas_prueba(card_id),
        mti_solicitud           TEXT    NOT NULL,
        mti_respuesta           TEXT,
        monto                   TEXT,
        moneda                  TEXT,
        stan                    TEXT    NOT NULL,
        destino_host            TEXT,
        destino_puerto          INTEGER,
        estado                  TEXT    NOT NULL,
        codigo_respuesta        TEXT,
        escenario_id            TEXT    REFERENCES escenarios(escenario_id),
        escenario_nombre        TEXT
    );
    CREATE TABLE suites (
        suite_id       TEXT PRIMARY KEY,
        nombre         TEXT NOT NULL,
        descripcion    TEXT NOT NULL DEFAULT '',
        activa         INTEGER NOT NULL DEFAULT 1,
        creado_en      TEXT NOT NULL,
        actualizado_en TEXT NOT NULL
    );
    CREATE TABLE suite_escenarios (
        suite_id     TEXT NOT NULL REFERENCES suites(suite_id),
        escenario_id TEXT NOT NULL REFERENCES escenarios(escenario_id),
        orden        INTEGER NOT NULL,
        PRIMARY KEY (suite_id, escenario_id)
    );
    CREATE TABLE corridas_suite (
        corrida_id   INTEGER PRIMARY KEY AUTOINCREMENT,
        suite_id     TEXT NOT NULL REFERENCES suites(suite_id),
        suite_nombre TEXT NOT NULL,
        estado       TEXT NOT NULL,
        resultado_global TEXT,
        total        INTEGER NOT NULL,
        iniciada_en  TEXT NOT NULL
    );
    CREATE TABLE corrida_suite_items (
        corrida_id       INTEGER NOT NULL REFERENCES corridas_suite(corrida_id),
        escenario_id     TEXT    NOT NULL,
        escenario_nombre TEXT    NOT NULL,
        orden            INTEGER NOT NULL,
        resultado        TEXT    NOT NULL,
        ejecucion_id     INTEGER REFERENCES ejecuciones(id),
        PRIMARY KEY (corrida_id, orden)
    );
    """
    with sqlite3.connect(ruta) as conexion:
        conexion.execute("PRAGMA foreign_keys = ON")
        conexion.executescript(ddl_anterior)
        pan = pan_sintetico("6666")
        conexion.execute(
            "INSERT INTO tarjetas_prueba (card_id, pan, pan_enmascarado, expiracion, creada_en)"
            " VALUES ('CARD-B3', ?, '************6666', '3012', '2026-01-01T00:00:00+00:00')",
            (pan,),
        )
        conexion.execute(
            "INSERT INTO destinos (destino_id, nombre, host, puerto, creado_en)"
            " VALUES ('DEST-B3', 'Destino', '127.0.0.1', 8583, '2026-01-01T00:00:00+00:00')"
        )
        conexion.execute(
            "INSERT INTO escenarios"
            " (escenario_id, nombre, perfil, mti, card_id, conexion_id, monto,"
            "  creado_en, actualizado_en)"
            " VALUES ('ESC-B3', 'Escenario viejo', 'generico', '0100', 'CARD-B3', 'DEST-B3',"
            "         '10.00', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
        )
        conexion.execute(
            "INSERT INTO ejecuciones"
            " (creada_en, card_id, mti_solicitud, mti_respuesta, monto, moneda, stan, estado,"
            "  escenario_id, escenario_nombre)"
            " VALUES ('2026-01-01T00:00:00+00:00', 'CARD-B3', '0100', '0110', '10.00', '188',"
            "         '000001', 'aprobada', 'ESC-B3', 'Escenario viejo')"
        )
        conexion.execute(
            "INSERT INTO suites (suite_id, nombre, creado_en, actualizado_en)"
            " VALUES ('SUITE-B3', 'Suite vieja', '2026-01-01T00:00:00+00:00',"
            "         '2026-01-01T00:00:00+00:00')"
        )
        conexion.execute(
            "INSERT INTO suite_escenarios (suite_id, escenario_id, orden)"
            " VALUES ('SUITE-B3', 'ESC-B3', 1)"
        )
        conexion.execute(
            "INSERT INTO corridas_suite"
            " (corrida_id, suite_id, suite_nombre, estado, total, iniciada_en)"
            " VALUES (1, 'SUITE-B3', 'Suite vieja', 'finalizada', 1, '2026-01-01T00:00:00+00:00')"
        )
        conexion.execute(
            "INSERT INTO corrida_suite_items"
            " (corrida_id, escenario_id, escenario_nombre, orden, resultado, ejecucion_id)"
            " VALUES (1, 'ESC-B3', 'Escenario viejo', 1, 'pass', 1)"
        )
        conexion.commit()


async def test_la_migracion_preserva_toda_la_cadena_real(tmp_path):
    ruta = tmp_path / "cadena_completa.db"
    _crear_base_anterior_a_b3_con_cadena_completa(ruta)
    assert _notnull_card_id_escenarios(ruta) == 1  # punto de partida

    await inicializar(ruta, con_datos_demo=False)

    assert _notnull_card_id_escenarios(ruta) == 0
    with sqlite3.connect(ruta) as conexion:
        conexion.execute("PRAGMA foreign_keys = ON")
        conexion.row_factory = sqlite3.Row

        # PRAGMA foreign_key_check vacio (criterio de aceptacion #13 de B3).
        violaciones = conexion.execute("PRAGMA foreign_key_check").fetchall()
        assert violaciones == [], f"quedaron referencias rotas: {violaciones}"

        escenario = conexion.execute(
            "SELECT * FROM escenarios WHERE escenario_id = 'ESC-B3'"
        ).fetchone()
        assert escenario is not None, "el escenario se conserva"
        assert escenario["nombre"] == "Escenario viejo"
        assert escenario["mti"] == "0100"
        assert escenario["operacion"] == OPERACION_COMPRA, (
            "toda fila anterior a B3 es una compra: unico MTI que escenarios.py sabia crear"
        )
        assert escenario["card_id"] == "CARD-B3"
        assert escenario["monto"] == "10.00"

        suite_item = conexion.execute(
            "SELECT * FROM suite_escenarios WHERE suite_id = 'SUITE-B3'"
        ).fetchone()
        assert suite_item["escenario_id"] == "ESC-B3"
        assert suite_item["orden"] == 1

        corrida = conexion.execute(
            "SELECT * FROM corridas_suite WHERE corrida_id = 1"
        ).fetchone()
        assert corrida["suite_id"] == "SUITE-B3"
        assert corrida["estado"] == "finalizada"

        item = conexion.execute(
            "SELECT * FROM corrida_suite_items WHERE corrida_id = 1"
        ).fetchone()
        assert item["escenario_id"] == "ESC-B3"
        assert item["resultado"] == "pass"
        assert item["ejecucion_id"] == 1

        ejecucion = conexion.execute("SELECT * FROM ejecuciones WHERE id = 1").fetchone()
        assert ejecucion["escenario_id"] == "ESC-B3"
        assert ejecucion["card_id"] == "CARD-B3"


async def test_la_migracion_de_escenarios_es_idempotente(tmp_path):
    ruta = tmp_path / "idempotente.db"
    _crear_base_anterior_a_b3_con_cadena_completa(ruta)

    await inicializar(ruta, con_datos_demo=False)
    await inicializar(ruta, con_datos_demo=False)  # segunda vez: no debe reventar

    assert _notnull_card_id_escenarios(ruta) == 0
    with sqlite3.connect(ruta) as conexion:
        conexion.execute("PRAGMA foreign_keys = ON")
        assert conexion.execute("PRAGMA foreign_key_check").fetchall() == []
        total_escenarios = conexion.execute("SELECT COUNT(*) FROM escenarios").fetchone()[0]
        total_items = conexion.execute("SELECT COUNT(*) FROM corrida_suite_items").fetchone()[0]
    assert total_escenarios == 1, "la reconstruccion no debe duplicar ni perder filas"
    assert total_items == 1


async def test_un_escenario_echo_sin_tarjeta_ni_monto_se_persiste_y_se_lee_igual(base):
    """El caso real que motiva la migracion: un escenario Echo, sin
    card_id/monto, debe guardarse y recuperarse con esos dos campos en
    `None` -no con un sentinel inventado ("", 0)-, y con
    `operacion=OPERACION_ECHO`."""
    repo = RepositorioEscenariosSQLite(base)
    escenario = Escenario(
        escenario_id="ESC-ECHO-1",
        nombre="Echo de prueba",
        perfil="generico",
        mti="0800",
        operacion=OPERACION_ECHO,
        conexion_id="LOCAL-DEMO",
        campos_manuales={"70": "301"},
    )
    await repo.guardar(escenario)

    recuperado = await repo.obtener("ESC-ECHO-1")
    assert recuperado is not None
    assert recuperado.card_id is None
    assert recuperado.monto is None
    assert recuperado.operacion == OPERACION_ECHO
    assert recuperado.mti == "0800"
    assert recuperado.campos_manuales == {"70": "301"}

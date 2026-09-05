"""Sub-bloque 2: la migracion aditiva generalizada, probada sobre una base anterior.

`test_persistencia_json.py` ya prueba la migracion de las columnas JSON de
`ejecuciones` contra `_migrar_ejecuciones`, que ahora es un envoltorio de
compatibilidad sobre `_migrar`. Aqui se prueba la funcion generalizada en si
misma -sobre dos tablas distintas- y la migracion de `tarjetas_prueba.activa`
sobre una base creada antes de que esa columna existiera.
"""

from __future__ import annotations

import sqlite3

import aiosqlite
import pytest

from sibutestlab8583.adapters.persistence.esquema import (
    COLUMNAS_AGREGADAS_DESTINOS,
    COLUMNAS_AGREGADAS_EJECUCIONES_ESCENARIO,
    COLUMNAS_AGREGADAS_EJECUCIONES_EVALUACION,
    COLUMNAS_AGREGADAS_ESCENARIOS,
    COLUMNAS_AGREGADAS_TARJETAS,
    inicializar,
)


def _crear_base_sin_columnas_de_escenario(ruta) -> None:
    """Reproduce `ejecuciones` tal como era antes del Bloque 2 (sin escenarios)."""
    ddl_anterior = """
    CREATE TABLE tarjetas_prueba (
        card_id   TEXT PRIMARY KEY,
        creada_en TEXT NOT NULL
    );
    CREATE TABLE ejecuciones (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        creada_en     TEXT    NOT NULL,
        card_id       TEXT    NOT NULL REFERENCES tarjetas_prueba(card_id),
        mti_solicitud TEXT    NOT NULL,
        monto         TEXT    NOT NULL,
        moneda        TEXT    NOT NULL,
        stan          TEXT    NOT NULL,
        estado        TEXT    NOT NULL
    );
    """
    with sqlite3.connect(ruta) as conexion:
        conexion.executescript(ddl_anterior)
        conexion.execute(
            "INSERT INTO tarjetas_prueba (card_id, creada_en)"
            " VALUES ('VIEJA-1', '2026-01-01T00:00:00+00:00')"
        )
        conexion.execute(
            "INSERT INTO ejecuciones"
            " (creada_en, card_id, mti_solicitud, monto, moneda, stan, estado)"
            " VALUES ('2026-01-01T00:00:00+00:00', 'VIEJA-1', '0100', '10.00', '188',"
            "         '000001', 'aprobada')"
        )


async def test_una_base_anterior_sin_columnas_de_escenario_las_recibe_migrada(tmp_path):
    ruta = tmp_path / "sin_escenario.db"
    _crear_base_sin_columnas_de_escenario(ruta)

    await inicializar(ruta, con_datos_demo=False)

    with sqlite3.connect(ruta) as conexion:
        conexion.row_factory = sqlite3.Row
        columnas = {f[1] for f in conexion.execute("PRAGMA table_info(ejecuciones)")}
        fila = conexion.execute(
            "SELECT * FROM ejecuciones WHERE card_id = 'VIEJA-1'"
        ).fetchone()

    assert {"escenario_id", "escenario_nombre"} <= columnas
    assert fila is not None, "la fila anterior se conserva"
    assert fila["escenario_id"] is None, "una fila migrada no inventa un escenario"
    assert fila["estado"] == "aprobada", "ninguna otra columna se modifica"


async def test_la_migracion_de_columnas_de_escenario_es_idempotente(tmp_path):
    ruta = tmp_path / "sin_escenario_repetida.db"
    _crear_base_sin_columnas_de_escenario(ruta)

    await inicializar(ruta, con_datos_demo=False)
    await inicializar(ruta, con_datos_demo=False)  # segunda vez: no debe duplicar la columna

    with sqlite3.connect(ruta) as conexion:
        columnas = [f[1] for f in conexion.execute("PRAGMA table_info(ejecuciones)")]
    assert columnas.count("escenario_id") == 1
    assert columnas.count("escenario_nombre") == 1


async def test_una_base_nueva_no_necesita_migrar_columnas_de_escenario(base):
    """El DDL ya trae las columnas: `_migrar` sobre una base nueva no agrega nada."""
    from sibutestlab8583.adapters.persistence.esquema import _migrar

    async with aiosqlite.connect(base) as conexion:
        agregadas = await _migrar(
            conexion, "ejecuciones", COLUMNAS_AGREGADAS_EJECUCIONES_ESCENARIO
        )
    assert agregadas == ()


# --------------------------------- Bloque 3: expected vs actual (evaluacion) --


def _crear_base_sin_columnas_de_evaluacion(ruta) -> None:
    """Reproduce `ejecuciones`/`escenarios` tal como eran justo antes del
    Bloque 3: con las columnas de escenario (Bloque 2), pero sin
    `evaluacion_estado`/`evaluacion_json` en `ejecuciones` ni `expected_json`
    en `escenarios`.
    """
    ddl_anterior = """
    CREATE TABLE tarjetas_prueba (
        card_id   TEXT PRIMARY KEY,
        creada_en TEXT NOT NULL
    );
    CREATE TABLE escenarios (
        escenario_id  TEXT PRIMARY KEY,
        nombre        TEXT NOT NULL,
        creado_en     TEXT NOT NULL
    );
    CREATE TABLE ejecuciones (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        creada_en       TEXT    NOT NULL,
        card_id         TEXT    NOT NULL REFERENCES tarjetas_prueba(card_id),
        mti_solicitud   TEXT    NOT NULL,
        monto           TEXT    NOT NULL,
        moneda          TEXT    NOT NULL,
        stan            TEXT    NOT NULL,
        estado          TEXT    NOT NULL,
        escenario_id    TEXT,
        escenario_nombre TEXT
    );
    """
    with sqlite3.connect(ruta) as conexion:
        conexion.executescript(ddl_anterior)
        conexion.execute(
            "INSERT INTO tarjetas_prueba (card_id, creada_en)"
            " VALUES ('VIEJA-EVAL', '2026-01-01T00:00:00+00:00')"
        )
        conexion.execute(
            "INSERT INTO escenarios (escenario_id, nombre, creado_en)"
            " VALUES ('ESC-VIEJO', 'Escenario previo', '2026-01-01T00:00:00+00:00')"
        )
        conexion.execute(
            "INSERT INTO ejecuciones"
            " (creada_en, card_id, mti_solicitud, monto, moneda, stan, estado,"
            "  escenario_id, escenario_nombre)"
            " VALUES ('2026-01-01T00:00:00+00:00', 'VIEJA-EVAL', '0100', '10.00', '188',"
            "         '000001', 'aprobada', 'ESC-VIEJO', 'Escenario previo')"
        )


async def test_una_base_anterior_sin_columnas_de_evaluacion_las_recibe_migrada(tmp_path):
    ruta = tmp_path / "sin_evaluacion.db"
    _crear_base_sin_columnas_de_evaluacion(ruta)

    await inicializar(ruta, con_datos_demo=False)

    with sqlite3.connect(ruta) as conexion:
        conexion.row_factory = sqlite3.Row
        columnas_ejecuciones = {f[1] for f in conexion.execute("PRAGMA table_info(ejecuciones)")}
        columnas_escenarios = {f[1] for f in conexion.execute("PRAGMA table_info(escenarios)")}
        fila = conexion.execute(
            "SELECT * FROM ejecuciones WHERE card_id = 'VIEJA-EVAL'"
        ).fetchone()

    assert {"evaluacion_estado", "evaluacion_json"} <= columnas_ejecuciones
    assert "expected_json" in columnas_escenarios
    assert fila is not None, "la fila anterior se conserva"
    assert fila["evaluacion_estado"] is None, "una fila migrada no inventa una evaluacion"
    assert fila["escenario_nombre"] == "Escenario previo", "ninguna otra columna se modifica"


async def test_la_migracion_de_columnas_de_evaluacion_es_idempotente(tmp_path):
    ruta = tmp_path / "sin_evaluacion_repetida.db"
    _crear_base_sin_columnas_de_evaluacion(ruta)

    await inicializar(ruta, con_datos_demo=False)
    await inicializar(ruta, con_datos_demo=False)  # segunda vez: no debe duplicar la columna

    with sqlite3.connect(ruta) as conexion:
        columnas_ejecuciones = [f[1] for f in conexion.execute("PRAGMA table_info(ejecuciones)")]
        columnas_escenarios = [f[1] for f in conexion.execute("PRAGMA table_info(escenarios)")]
    assert columnas_ejecuciones.count("evaluacion_estado") == 1
    assert columnas_ejecuciones.count("evaluacion_json") == 1
    assert columnas_escenarios.count("expected_json") == 1


async def test_una_base_nueva_no_necesita_migrar_columnas_de_evaluacion(base):
    """El DDL ya trae las columnas: `_migrar` sobre una base nueva no agrega nada."""
    from sibutestlab8583.adapters.persistence.esquema import _migrar

    async with aiosqlite.connect(base) as conexion:
        agregadas_ejecuciones = await _migrar(
            conexion, "ejecuciones", COLUMNAS_AGREGADAS_EJECUCIONES_EVALUACION
        )
        agregadas_escenarios = await _migrar(
            conexion, "escenarios", COLUMNAS_AGREGADAS_ESCENARIOS
        )
    assert agregadas_ejecuciones == ()
    assert agregadas_escenarios == ()


def _crear_base_sin_columna_timeout(ruta) -> None:
    """Reproduce el esquema de `destinos` tal como era antes de `timeout`."""
    ddl_anterior = """
    CREATE TABLE destinos (
        destino_id  TEXT    PRIMARY KEY,
        nombre      TEXT    NOT NULL,
        host        TEXT    NOT NULL,
        puerto      INTEGER NOT NULL,
        activo      INTEGER NOT NULL DEFAULT 1,
        creado_en   TEXT    NOT NULL
    );
    """
    with sqlite3.connect(ruta) as conexion:
        conexion.executescript(ddl_anterior)
        conexion.execute(
            "INSERT INTO destinos (destino_id, nombre, host, puerto, activo, creado_en)"
            " VALUES ('VIEJO-1', 'previo', '10.0.0.1', 9000, 1, '2026-01-01T00:00:00+00:00')"
        )


async def test_una_base_anterior_sin_timeout_la_recibe_migrada(tmp_path):
    ruta = tmp_path / "sin_timeout.db"
    _crear_base_sin_columna_timeout(ruta)

    await inicializar(ruta)

    with sqlite3.connect(ruta) as conexion:
        conexion.row_factory = sqlite3.Row
        columnas = {f[1] for f in conexion.execute("PRAGMA table_info(destinos)")}
        fila = conexion.execute(
            "SELECT * FROM destinos WHERE destino_id = 'VIEJO-1'"
        ).fetchone()

    assert "timeout" in columnas
    assert fila is not None, "la fila anterior se conserva"
    assert fila["timeout"] == 10.0, "una fila migrada recibe el default de la columna"
    assert fila["host"] == "10.0.0.1", "ninguna otra columna se modifica"


async def test_la_migracion_de_timeout_es_idempotente(tmp_path):
    ruta = tmp_path / "sin_timeout_repetida.db"
    _crear_base_sin_columna_timeout(ruta)

    await inicializar(ruta)
    await inicializar(ruta)  # segunda vez: no debe fallar ni duplicar la columna

    with sqlite3.connect(ruta) as conexion:
        columnas = [f[1] for f in conexion.execute("PRAGMA table_info(destinos)")]
    assert columnas.count("timeout") == 1


async def test_una_base_nueva_no_necesita_migrar_timeout(base):
    """El DDL ya trae la columna: `_migrar` sobre una base nueva no agrega nada."""
    from sibutestlab8583.adapters.persistence.esquema import _migrar

    async with aiosqlite.connect(base) as conexion:
        agregadas = await _migrar(conexion, "destinos", COLUMNAS_AGREGADAS_DESTINOS)
    assert agregadas == ()


def _crear_base_sin_columna_activa(ruta) -> None:
    """Reproduce el esquema de `tarjetas_prueba` tal como era antes de `activa`."""
    ddl_anterior = """
    CREATE TABLE tarjetas_prueba (
        card_id          TEXT    PRIMARY KEY,
        pan              TEXT    NOT NULL,
        pan_enmascarado  TEXT    NOT NULL,
        expiracion       TEXT    NOT NULL,
        descripcion      TEXT    NOT NULL DEFAULT '',
        sintetica        INTEGER NOT NULL DEFAULT 1,
        creada_en        TEXT    NOT NULL
    );
    """
    with sqlite3.connect(ruta) as conexion:
        conexion.executescript(ddl_anterior)
        conexion.execute(
            "INSERT INTO tarjetas_prueba"
            " (card_id, pan, pan_enmascarado, expiracion, descripcion, sintetica, creada_en)"
            " VALUES ('VIEJA-1', '0', '****', '3012', 'previa', 1, '2026-01-01T00:00:00+00:00')"
        )


async def test_una_base_anterior_sin_activa_la_recibe_migrada(tmp_path):
    ruta = tmp_path / "anterior.db"
    _crear_base_sin_columna_activa(ruta)

    await inicializar(ruta)

    with sqlite3.connect(ruta) as conexion:
        conexion.row_factory = sqlite3.Row
        columnas = {f[1] for f in conexion.execute("PRAGMA table_info(tarjetas_prueba)")}
        fila = conexion.execute(
            "SELECT * FROM tarjetas_prueba WHERE card_id = 'VIEJA-1'"
        ).fetchone()

    assert "activa" in columnas
    assert fila is not None, "la fila anterior se conserva"
    assert fila["activa"] == 1, "una fila migrada queda activa por defecto"
    assert fila["descripcion"] == "previa", "ninguna otra columna se modifica"


async def test_la_migracion_de_activa_es_idempotente(tmp_path):
    ruta = tmp_path / "anterior_repetida.db"
    _crear_base_sin_columna_activa(ruta)

    await inicializar(ruta)
    await inicializar(ruta)  # segunda vez: no debe fallar ni duplicar la columna

    with sqlite3.connect(ruta) as conexion:
        columnas = [f[1] for f in conexion.execute("PRAGMA table_info(tarjetas_prueba)")]
    assert columnas.count("activa") == 1


async def test_una_base_nueva_no_necesita_migrar_activa(base):
    """El DDL ya trae la columna: `_migrar` sobre una base nueva no agrega nada."""
    from sibutestlab8583.adapters.persistence.esquema import _migrar

    async with aiosqlite.connect(base) as conexion:
        agregadas = await _migrar(conexion, "tarjetas_prueba", COLUMNAS_AGREGADAS_TARJETAS)
    assert agregadas == ()


async def test_migrar_es_generico_y_funciona_sobre_otra_tabla(tmp_path):
    """`_migrar` no esta atado a `ejecuciones` ni a `tarjetas_prueba`: prueba con una tercera."""
    from sibutestlab8583.adapters.persistence.esquema import _migrar

    ruta = tmp_path / "generica.db"
    with sqlite3.connect(ruta) as conexion:
        conexion.execute("CREATE TABLE otra (id INTEGER PRIMARY KEY)")

    async with aiosqlite.connect(ruta) as conexion:
        agregadas = await _migrar(conexion, "otra", (("nueva_columna", "TEXT"),))
        await conexion.commit()
    assert agregadas == ("nueva_columna",)

    with sqlite3.connect(ruta) as conexion:
        columnas = {f[1] for f in conexion.execute("PRAGMA table_info(otra)")}
    assert "nueva_columna" in columnas


# ------------------------------------------------- compatibilidad real completa ----


def _crear_base_anterior_real(ruta) -> None:
    """Reproduce una base real de ANTES de este sub-bloque: sin `activa`, sin
    `destinos`, y con `ejecuciones` en su forma anterior a las columnas JSON
    (P0-1/persistencia estructurada). Trae una tarjeta, una ejecucion que la
    referencia y una secuencia STAN ya avanzada -exactamente lo que existiria
    en un clon usado antes de este cambio-.

    No incluye PAN de largo real: el valor de `pan` es un literal corto
    deliberadamente invalido, para no disparar la guardia de PAN de la suite.
    """
    ddl_anterior = """
    CREATE TABLE tarjetas_prueba (
        card_id          TEXT    PRIMARY KEY,
        pan              TEXT    NOT NULL,
        pan_enmascarado  TEXT    NOT NULL,
        expiracion       TEXT    NOT NULL,
        descripcion      TEXT    NOT NULL DEFAULT '',
        sintetica        INTEGER NOT NULL DEFAULT 1,
        creada_en        TEXT    NOT NULL
    );

    CREATE TABLE codigos_respuesta (
        catalogo     TEXT    NOT NULL,
        codigo       TEXT    NOT NULL,
        descripcion  TEXT    NOT NULL,
        aprobado     INTEGER NOT NULL,
        PRIMARY KEY (catalogo, codigo)
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
        latencia_ms             INTEGER
    );

    CREATE TABLE secuencias (
        nombre  TEXT    PRIMARY KEY,
        valor   INTEGER NOT NULL
    );
    """
    with sqlite3.connect(ruta) as conexion:
        conexion.executescript(ddl_anterior)
        conexion.execute(
            "INSERT INTO tarjetas_prueba"
            " (card_id, pan, pan_enmascarado, expiracion, descripcion, sintetica, creada_en)"
            " VALUES ('VIEJA-REAL', '0', '****9999', '3012', 'previa real',"
            "         1, '2026-01-01T00:00:00+00:00')"
        )
        conexion.execute(
            "INSERT INTO ejecuciones"
            " (creada_en, card_id, mti_solicitud, mti_respuesta, monto, moneda, stan,"
            "  destino_host, destino_puerto, estado, codigo_respuesta,"
            "  solicitud_enmascarada, respuesta_enmascarada, latencia_ms)"
            " VALUES ('2026-01-02T00:00:00+00:00', 'VIEJA-REAL', '0100', '0110',"
            "         '150.00', '188', '000123', '127.0.0.1', 8583, 'aprobada', '00',"
            "         'MTI=0100 | 2=****9999', 'MTI=0110 | 39=00', 42)"
        )
        conexion.execute("INSERT INTO secuencias (nombre, valor) VALUES ('stan', 123)")


def _fila_tarjeta(ruta):
    with sqlite3.connect(ruta) as conexion:
        conexion.row_factory = sqlite3.Row
        return conexion.execute(
            "SELECT * FROM tarjetas_prueba WHERE card_id = 'VIEJA-REAL'"
        ).fetchone()


def _fila_ejecucion(ruta):
    with sqlite3.connect(ruta) as conexion:
        conexion.row_factory = sqlite3.Row
        return conexion.execute(
            "SELECT * FROM ejecuciones WHERE card_id = 'VIEJA-REAL'"
        ).fetchone()


def _valor_secuencia_stan(ruta) -> int:
    with sqlite3.connect(ruta) as conexion:
        return conexion.execute(
            "SELECT valor FROM secuencias WHERE nombre = 'stan'"
        ).fetchone()[0]


def _contar_destinos_local_demo(ruta) -> int:
    with sqlite3.connect(ruta) as conexion:
        return conexion.execute(
            "SELECT COUNT(*) FROM destinos WHERE destino_id = 'LOCAL-DEMO'"
        ).fetchone()[0]


async def test_compatibilidad_completa_de_una_base_anterior_real(tmp_path):
    """El criterio de aceptacion completo: tarjeta, ejecucion, STAN y esquema
    anterior de `ejecuciones`, todos presentes en la misma base, todos
    verificados explicitamente despues de migrar -y otra vez despues de una
    segunda inicializacion, para probar que no hay efectos de una segunda
    corrida.
    """
    ruta = tmp_path / "anterior_real.db"
    _crear_base_anterior_real(ruta)

    await inicializar(ruta)

    # 1. tarjetas_prueba.activa existe
    with sqlite3.connect(ruta) as conexion:
        columnas_tarjetas = {f[1] for f in conexion.execute("PRAGMA table_info(tarjetas_prueba)")}
    assert "activa" in columnas_tarjetas

    # 2. la tarjeta anterior queda activa = 1
    tarjeta = _fila_tarjeta(ruta)
    assert tarjeta is not None
    assert tarjeta["activa"] == 1
    assert tarjeta["descripcion"] == "previa real", "ninguna otra columna se reescribe"

    # 3. aparece destinos
    with sqlite3.connect(ruta) as conexion:
        tablas = {f[0] for f in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "destinos" in tablas

    # 4. aparece exactamente una semilla LOCAL-DEMO
    assert _contar_destinos_local_demo(ruta) == 1

    # 5. la ejecucion anterior conserva sus valores
    ejecucion = _fila_ejecucion(ruta)
    assert ejecucion is not None
    assert ejecucion["monto"] == "150.00"
    assert ejecucion["estado"] == "aprobada"
    assert ejecucion["codigo_respuesta"] == "00"
    assert ejecucion["stan"] == "000123"
    assert ejecucion["destino_host"] == "127.0.0.1"
    assert ejecucion["destino_puerto"] == 8583
    assert ejecucion["solicitud_enmascarada"] == "MTI=0100 | 2=****9999"
    assert ejecucion["respuesta_enmascarada"] == "MTI=0110 | 39=00"
    assert ejecucion["latencia_ms"] == 42
    # las columnas JSON se agregan, pero no se inventa contenido para una fila
    # que nunca las tuvo: reconstruirlo seria inventar datos historicos.
    assert ejecucion["solicitud_json"] is None
    assert ejecucion["respuesta_json"] is None

    # 6. el STAN/secuencia conserva su valor
    assert _valor_secuencia_stan(ruta) == 123

    # 7. las columnas JSON de ejecuciones se migran, como antes
    with sqlite3.connect(ruta) as conexion:
        columnas_ejecuciones = {f[1] for f in conexion.execute("PRAGMA table_info(ejecuciones)")}
    assert {"solicitud_json", "respuesta_json"} <= columnas_ejecuciones

    # --- segunda inicializacion: nada de lo anterior debe cambiar ---
    await inicializar(ruta)

    # 8a. no duplica LOCAL-DEMO
    assert _contar_destinos_local_demo(ruta) == 1
    # 8b. no modifica la tarjeta
    tarjeta_tras_segunda = _fila_tarjeta(ruta)
    assert dict(tarjeta_tras_segunda) == dict(tarjeta)
    # 8c. no modifica la ejecucion
    ejecucion_tras_segunda = _fila_ejecucion(ruta)
    assert dict(ejecucion_tras_segunda) == dict(ejecucion)
    # 8d. no modifica la secuencia
    assert _valor_secuencia_stan(ruta) == 123


# ------------------------------------- compatibilidad con el esquema previo al sub-bloque 5 ----


def _crear_base_anterior_a_laboratorio(ruta) -> None:
    """Reproduce el esquema EXACTO de justo antes de este sub-bloque: con
    `activa`, con `destinos` ya poblada, con las columnas JSON de `ejecuciones`
    -todo lo que ya existia-, pero SIN los ocho campos de laboratorio nuevos
    (`titular` en adelante) en `tarjetas_prueba`.

    Trae una tarjeta preexistente, una ejecucion historica que la referencia,
    una secuencia STAN ya avanzada, y un destino ya sembrado ademas de
    LOCAL-DEMO -exactamente lo que existiria en un clon usado antes de esta
    iteracion-.
    """
    ddl_anterior = """
    CREATE TABLE tarjetas_prueba (
        card_id          TEXT    PRIMARY KEY,
        pan              TEXT    NOT NULL,
        pan_enmascarado  TEXT    NOT NULL,
        expiracion       TEXT    NOT NULL,
        descripcion      TEXT    NOT NULL DEFAULT '',
        sintetica        INTEGER NOT NULL DEFAULT 1,
        activa           INTEGER NOT NULL DEFAULT 1,
        creada_en        TEXT    NOT NULL
    );

    CREATE TABLE codigos_respuesta (
        catalogo     TEXT    NOT NULL,
        codigo       TEXT    NOT NULL,
        descripcion  TEXT    NOT NULL,
        aprobado     INTEGER NOT NULL,
        PRIMARY KEY (catalogo, codigo)
    );

    CREATE TABLE destinos (
        destino_id  TEXT    PRIMARY KEY,
        nombre      TEXT    NOT NULL,
        host        TEXT    NOT NULL,
        puerto      INTEGER NOT NULL,
        activo      INTEGER NOT NULL DEFAULT 1,
        creado_en   TEXT    NOT NULL
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
        latencia_ms             INTEGER
    );

    CREATE TABLE secuencias (
        nombre  TEXT    PRIMARY KEY,
        valor   INTEGER NOT NULL
    );
    """
    with sqlite3.connect(ruta) as conexion:
        conexion.executescript(ddl_anterior)
        conexion.execute(
            "INSERT INTO tarjetas_prueba"
            " (card_id, pan, pan_enmascarado, expiracion, descripcion, sintetica, activa,"
            "  creada_en)"
            " VALUES ('VIEJA-LAB', '0', '****8888', '3012', 'previa laboratorio',"
            "         1, 1, '2026-01-01T00:00:00+00:00')"
        )
        conexion.execute(
            "INSERT INTO ejecuciones"
            " (creada_en, card_id, mti_solicitud, mti_respuesta, monto, moneda, stan,"
            "  destino_host, destino_puerto, estado, codigo_respuesta,"
            "  solicitud_enmascarada, respuesta_enmascarada, solicitud_json, respuesta_json,"
            "  latencia_ms)"
            " VALUES ('2026-01-02T00:00:00+00:00', 'VIEJA-LAB', '0100', '0110',"
            "         '150.00', '188', '000456', '127.0.0.1', 8583, 'aprobada', '00',"
            "         'MTI=0100 | 2=****8888', 'MTI=0110 | 39=00', NULL, NULL, 55)"
        )
        conexion.execute("INSERT INTO secuencias (nombre, valor) VALUES ('stan', 456)")
        conexion.execute(
            "INSERT INTO destinos (destino_id, nombre, host, puerto, activo, creado_en)"
            " VALUES ('LOCAL-DEMO', 'Host simulado local', '127.0.0.1', 8583, 1,"
            "         '2026-01-01T00:00:00+00:00')"
        )
        conexion.execute(
            "INSERT INTO destinos (destino_id, nombre, host, puerto, activo, creado_en)"
            " VALUES ('QA-EXISTENTE', 'Switch QA', '192.0.2.10', 9583, 1,"
            "         '2026-01-01T00:00:00+00:00')"
        )


def _fila_tarjeta_lab(ruta):
    with sqlite3.connect(ruta) as conexion:
        conexion.row_factory = sqlite3.Row
        return conexion.execute(
            "SELECT * FROM tarjetas_prueba WHERE card_id = 'VIEJA-LAB'"
        ).fetchone()


def _fila_ejecucion_lab(ruta):
    with sqlite3.connect(ruta) as conexion:
        conexion.row_factory = sqlite3.Row
        return conexion.execute(
            "SELECT * FROM ejecuciones WHERE card_id = 'VIEJA-LAB'"
        ).fetchone()


def _valor_secuencia_stan_lab(ruta) -> int:
    with sqlite3.connect(ruta) as conexion:
        return conexion.execute(
            "SELECT valor FROM secuencias WHERE nombre = 'stan'"
        ).fetchone()[0]


def _destinos_lab(ruta):
    with sqlite3.connect(ruta) as conexion:
        conexion.row_factory = sqlite3.Row
        return [
            dict(f)
            for f in conexion.execute("SELECT * FROM destinos ORDER BY destino_id").fetchall()
        ]


#: Independiente de `COLUMNAS_AGREGADAS_TARJETAS`, a proposito: si la lista
#: de produccion se mutara o se rompiera, esta prueba debe notarlo, no
#: heredar el mismo error.
COLUMNAS_LABORATORIO = (
    "titular", "service_code", "discretionary_data", "cvv", "cvv2", "icvv",
    "card_sequence_number", "pin_block_laboratorio",
)


async def test_compatibilidad_con_esquema_anterior_a_las_columnas_de_laboratorio(tmp_path):
    """Criterio de aceptacion del sub-bloque 5: una base con el esquema completo
    de justo antes de esta iteracion -tarjeta, ejecucion, STAN y destinos ya
    poblados- migra sin perder ni modificar nada, y las ocho columnas nuevas
    quedan en `''` para la fila preexistente.
    """
    ruta = tmp_path / "anterior_laboratorio.db"
    _crear_base_anterior_a_laboratorio(ruta)

    await inicializar(ruta)

    # 1. existen las 8 columnas nuevas
    with sqlite3.connect(ruta) as conexion:
        columnas = {f[1] for f in conexion.execute("PRAGMA table_info(tarjetas_prueba)")}
    assert set(COLUMNAS_LABORATORIO) <= columnas

    tarjeta = _fila_tarjeta_lab(ruta)
    assert tarjeta is not None
    # 2. las 8 columnas nuevas valen '' para la fila anterior
    for columna in COLUMNAS_LABORATORIO:
        assert tarjeta[columna] == "", f"{columna} deberia quedar vacio, no {tarjeta[columna]!r}"
    # 3-8. el resto de la tarjeta no cambia
    assert tarjeta["pan"] == "0"
    assert tarjeta["pan_enmascarado"] == "****8888"
    assert tarjeta["expiracion"] == "3012"
    assert tarjeta["descripcion"] == "previa laboratorio"
    assert tarjeta["sintetica"] == 1
    assert tarjeta["activa"] == 1

    # 9. la ejecucion historica no cambia
    ejecucion = _fila_ejecucion_lab(ruta)
    assert ejecucion is not None
    assert ejecucion["stan"] == "000456"
    assert ejecucion["monto"] == "150.00"
    assert ejecucion["estado"] == "aprobada"
    assert ejecucion["latencia_ms"] == 55

    # 10. el STAN no cambia
    assert _valor_secuencia_stan_lab(ruta) == 456

    # 11. los destinos existentes no cambian, y no se duplica la semilla
    destinos = _destinos_lab(ruta)
    assert [d["destino_id"] for d in destinos] == ["LOCAL-DEMO", "QA-EXISTENTE"]

    # 12. ninguna fila duplicada (la propia, y la ejecucion que la referencia;
    # `inicializar()` tambien siembra su propia tarjeta de demostracion, que
    # es una fila distinta y no cuenta como duplicado de VIEJA-LAB)
    with sqlite3.connect(ruta) as conexion:
        assert conexion.execute(
            "SELECT COUNT(*) FROM tarjetas_prueba WHERE card_id = 'VIEJA-LAB'"
        ).fetchone()[0] == 1
        assert conexion.execute(
            "SELECT COUNT(*) FROM ejecuciones WHERE card_id = 'VIEJA-LAB'"
        ).fetchone()[0] == 1

    # --- segunda inicializacion: nada de lo anterior debe cambiar ---
    await inicializar(ruta)

    with sqlite3.connect(ruta) as conexion:
        columnas_tras_segunda = {f[1] for f in conexion.execute("PRAGMA table_info(tarjetas_prueba)")}
    assert set(COLUMNAS_LABORATORIO) <= columnas_tras_segunda

    tarjeta_tras_segunda = _fila_tarjeta_lab(ruta)
    assert dict(tarjeta_tras_segunda) == dict(tarjeta)
    for columna in COLUMNAS_LABORATORIO:
        assert tarjeta_tras_segunda[columna] == ""

    ejecucion_tras_segunda = _fila_ejecucion_lab(ruta)
    assert dict(ejecucion_tras_segunda) == dict(ejecucion)

    assert _valor_secuencia_stan_lab(ruta) == 456
    assert _destinos_lab(ruta) == destinos

    with sqlite3.connect(ruta) as conexion:
        assert conexion.execute(
            "SELECT COUNT(*) FROM tarjetas_prueba WHERE card_id = 'VIEJA-LAB'"
        ).fetchone()[0] == 1
        assert conexion.execute(
            "SELECT COUNT(*) FROM ejecuciones WHERE card_id = 'VIEJA-LAB'"
        ).fetchone()[0] == 1
        assert conexion.execute("SELECT COUNT(*) FROM destinos").fetchone()[0] == 2


# --------------------------------------- Bloque 4: tablas nuevas de suites ----


def _crear_base_anterior_a_suites(ruta) -> None:
    """Reproduce el esquema completo de justo antes del Bloque 4: con todo lo
    de Bloques 1-3, pero sin ninguna de las 4 tablas de suites/corridas.
    """
    ddl_anterior = """
    CREATE TABLE tarjetas_prueba (
        card_id   TEXT PRIMARY KEY,
        creada_en TEXT NOT NULL
    );
    CREATE TABLE destinos (
        destino_id TEXT PRIMARY KEY,
        nombre     TEXT NOT NULL,
        host       TEXT NOT NULL,
        puerto     INTEGER NOT NULL,
        activo     INTEGER NOT NULL DEFAULT 1,
        timeout    REAL NOT NULL DEFAULT 10.0,
        creado_en  TEXT NOT NULL
    );
    CREATE TABLE escenarios (
        escenario_id TEXT PRIMARY KEY,
        nombre       TEXT NOT NULL,
        creado_en    TEXT NOT NULL,
        actualizado_en TEXT NOT NULL
    );
    CREATE TABLE ejecuciones (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        creada_en TEXT NOT NULL,
        card_id   TEXT NOT NULL REFERENCES tarjetas_prueba(card_id),
        mti_solicitud TEXT NOT NULL,
        monto     TEXT NOT NULL,
        moneda    TEXT NOT NULL,
        stan      TEXT NOT NULL,
        estado    TEXT NOT NULL
    );
    """
    with sqlite3.connect(ruta) as conexion:
        conexion.executescript(ddl_anterior)
        conexion.execute(
            "INSERT INTO tarjetas_prueba (card_id, creada_en)"
            " VALUES ('VIEJA-SUITE', '2026-01-01T00:00:00+00:00')"
        )


async def test_una_base_anterior_a_suites_recibe_las_cuatro_tablas_nuevas(tmp_path):
    ruta = tmp_path / "sin_suites.db"
    _crear_base_anterior_a_suites(ruta)

    await inicializar(ruta, con_datos_demo=False)

    with sqlite3.connect(ruta) as conexion:
        tablas = {
            f[0] for f in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {"suites", "suite_escenarios", "corridas_suite", "corrida_suite_items"} <= tablas

    # La fila anterior (de una tabla que SI existia) se conserva intacta.
    with sqlite3.connect(ruta) as conexion:
        conexion.row_factory = sqlite3.Row
        fila = conexion.execute(
            "SELECT * FROM tarjetas_prueba WHERE card_id = 'VIEJA-SUITE'"
        ).fetchone()
    assert fila is not None


async def test_la_migracion_de_tablas_de_suites_es_idempotente(tmp_path):
    ruta = tmp_path / "sin_suites_repetida.db"
    _crear_base_anterior_a_suites(ruta)

    await inicializar(ruta, con_datos_demo=False)
    await inicializar(ruta, con_datos_demo=False)  # segunda vez: no debe fallar

    with sqlite3.connect(ruta) as conexion:
        tablas = {
            f[0] for f in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {"suites", "suite_escenarios", "corridas_suite", "corrida_suite_items"} <= tablas

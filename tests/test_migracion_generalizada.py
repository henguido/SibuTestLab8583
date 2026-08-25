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
    COLUMNAS_AGREGADAS_TARJETAS,
    inicializar,
)


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

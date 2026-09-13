"""B6: `ejecuciones.ejecucion_origen_id` -modelo de operacion derivada
(preparacion para un futuro reverso 0400/0410, todavia sin implementar).

A diferencia de `card_id`/`monto` (B2) -que exigieron reconstruir la tabla
porque relajaban un `NOT NULL` ya existente-, esta es una columna NUEVA,
nullable desde el principio: el camino liviano `_migrar()` (`ALTER TABLE ...
ADD COLUMN`) alcanza, sin reconstruccion. Estas pruebas verifican: que una
base nueva ya nace con la columna; que una base anterior a B6 la recibe sin
perder ni modificar ninguna fila existente; que la migracion es idempotente;
y que el mecanismo real (guardar una fila con `ejecucion_origen_id` y
consultar sus derivadas) funciona con FKs reales -incluyendo el caso
1 origen -> N derivadas, nunca 1:1-.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from decimal import Decimal

from sibutestlab8583.adapters.persistence.esquema import inicializar
from sibutestlab8583.adapters.persistence.sqlite_repos import RepositorioEjecucionesSQLite
from sibutestlab8583.domain.datos_sinteticos import pan_sintetico
from sibutestlab8583.domain.modelos import (
    EstadoEjecucion,
    Ejecucion,
    MTI_COMPRA,
    MTI_COMPRA_FINANCIERA,
    MTI_RESPUESTA_COMPRA_FINANCIERA,
)


def _columnas_ejecuciones(ruta) -> set[str]:
    with sqlite3.connect(ruta) as conexion:
        return {f[1] for f in conexion.execute("PRAGMA table_info(ejecuciones)")}


async def test_una_base_nueva_ya_nace_con_la_columna_origen(tmp_path):
    ruta = tmp_path / "nueva.db"
    await inicializar(ruta, con_datos_demo=False)
    assert "ejecucion_origen_id" in _columnas_ejecuciones(ruta)


def _crear_base_anterior_a_b6_con_cadena_real(ruta) -> None:
    """Reproduce el esquema justo antes de B6: todas las columnas modernas
    presentes (post B2-B5), pero SIN `ejecucion_origen_id`. Incluye una
    cadena real -tarjeta, destino, dos ejecuciones ya persistidas- para
    confirmar que la migracion no toca ninguna fila existente.
    """
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
        conexion.execute(
            "INSERT INTO tarjetas_prueba"
            " (card_id, pan, pan_enmascarado, expiracion, descripcion, sintetica, activa, creada_en)"
            " VALUES (?, ?, ?, ?, ?, 1, 1, ?)",
            (
                "VIEJA-B6", pan_sintetico("1234"), "************1234", "3012",
                "previa a B6", datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
            ),
        )
        conexion.execute(
            "INSERT INTO ejecuciones"
            " (creada_en, card_id, mti_solicitud, mti_respuesta, monto, moneda, stan,"
            "  destino_host, destino_puerto, estado, codigo_respuesta)"
            " VALUES ('2026-01-02T00:00:00+00:00', 'VIEJA-B6', '0200', '0210',"
            "         '50.00', '188', '000700', '127.0.0.1', 8583, 'aprobada', '00')"
        )
        conexion.execute(
            "INSERT INTO ejecuciones"
            " (creada_en, card_id, mti_solicitud, mti_respuesta, monto, moneda, stan,"
            "  destino_host, destino_puerto, estado, codigo_respuesta)"
            " VALUES ('2026-01-02T00:05:00+00:00', 'VIEJA-B6', '0200', '0210',"
            "         '75.00', '188', '000701', '127.0.0.1', 8583, 'rechazada', '51')"
        )
        conexion.commit()


async def test_la_migracion_preserva_las_ejecuciones_existentes(tmp_path):
    ruta = tmp_path / "anterior_b6.db"
    _crear_base_anterior_a_b6_con_cadena_real(ruta)

    await inicializar(ruta)

    assert "ejecucion_origen_id" in _columnas_ejecuciones(ruta)

    with sqlite3.connect(ruta) as conexion:
        assert conexion.execute("PRAGMA foreign_key_check").fetchall() == []
        conexion.row_factory = sqlite3.Row
        filas = conexion.execute(
            "SELECT * FROM ejecuciones WHERE card_id = 'VIEJA-B6' ORDER BY id"
        ).fetchall()

    assert len(filas) == 2
    # Ninguna fila existente cambia de valor, y la columna nueva queda NULL
    # -nunca un sentinel inventado- para filas anteriores a B6.
    assert filas[0]["stan"] == "000700"
    assert filas[0]["ejecucion_origen_id"] is None
    assert filas[1]["stan"] == "000701"
    assert filas[1]["ejecucion_origen_id"] is None


async def test_la_migracion_es_idempotente(tmp_path):
    ruta = tmp_path / "anterior_b6_repetida.db"
    _crear_base_anterior_a_b6_con_cadena_real(ruta)

    await inicializar(ruta)
    with sqlite3.connect(ruta) as conexion:
        conexion.row_factory = sqlite3.Row
        filas_primera = [dict(f) for f in conexion.execute(
            "SELECT * FROM ejecuciones WHERE card_id = 'VIEJA-B6' ORDER BY id"
        ).fetchall()]

    await inicializar(ruta)  # segunda vez: no debe duplicar ni tocar nada
    with sqlite3.connect(ruta) as conexion:
        columnas = [f[1] for f in conexion.execute("PRAGMA table_info(ejecuciones)")]
        conexion.row_factory = sqlite3.Row
        filas_segunda = [dict(f) for f in conexion.execute(
            "SELECT * FROM ejecuciones WHERE card_id = 'VIEJA-B6' ORDER BY id"
        ).fetchall()]

    assert columnas.count("ejecucion_origen_id") == 1
    assert filas_segunda == filas_primera


async def test_un_origen_puede_tener_varias_derivadas(base):
    """El mecanismo real -no solo el esquema-: 1 ejecucion origen con 3
    derivadas, consultadas via `listar_derivadas`. Nunca 1:1."""
    repo = RepositorioEjecucionesSQLite(base)

    origen = Ejecucion(
        stan="000801", estado=EstadoEjecucion.APROBADA, mti_solicitud=MTI_COMPRA_FINANCIERA,
        mti_respuesta=MTI_RESPUESTA_COMPRA_FINANCIERA, monto=Decimal("100.00"), moneda="188",
        codigo_respuesta="00",
    )
    origen_id = await repo.guardar(origen)

    for i in range(3):
        derivada = Ejecucion(
            stan=f"00090{i}", estado=EstadoEjecucion.APROBADA, mti_solicitud=MTI_COMPRA,
            ejecucion_origen_id=origen_id,
        )
        await repo.guardar(derivada)

    # Una ejecucion sin relacion, para confirmar que no aparece como derivada.
    independiente = Ejecucion(stan="000999", estado=EstadoEjecucion.APROBADA, mti_solicitud=MTI_COMPRA)
    await repo.guardar(independiente)

    derivadas = await repo.listar_derivadas(origen_id)
    assert len(derivadas) == 3
    assert {d.stan for d in derivadas} == {"000900", "000901", "000902"}
    assert all(d.ejecucion_origen_id == origen_id for d in derivadas)


async def test_una_ejecucion_sin_derivadas_devuelve_lista_vacia(base):
    repo = RepositorioEjecucionesSQLite(base)
    origen = Ejecucion(stan="001000", estado=EstadoEjecucion.APROBADA, mti_solicitud=MTI_COMPRA_FINANCIERA)
    origen_id = await repo.guardar(origen)

    assert await repo.listar_derivadas(origen_id) == []


async def test_reconstruir_una_ejecucion_con_origen_devuelve_el_id_correcto(base):
    repo = RepositorioEjecucionesSQLite(base)
    origen = Ejecucion(stan="001100", estado=EstadoEjecucion.APROBADA, mti_solicitud=MTI_COMPRA_FINANCIERA)
    origen_id = await repo.guardar(origen)

    derivada = Ejecucion(
        stan="001101", estado=EstadoEjecucion.APROBADA, mti_solicitud=MTI_COMPRA,
        ejecucion_origen_id=origen_id,
    )
    derivada_id = await repo.guardar(derivada)

    leida = await repo.obtener(derivada_id)
    assert leida.ejecucion_origen_id == origen_id

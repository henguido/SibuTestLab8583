"""Esquema SQLite e inicializacion reproducible.

La inicializacion es idempotente: ejecutarla dos veces no falla ni destruye
datos. Por eso todo es ``CREATE TABLE IF NOT EXISTS`` y ``INSERT OR IGNORE``.

No se usa Alembic: para tres tablas seria sobreingenieria en este alcance.

Politica de datos aplicada desde el esquema:
- El PAN completo vive unicamente en ``tarjetas_prueba``.
- ``ejecuciones`` NO tiene columna para el PAN: referencia ``card_id`` y guarda
  los mensajes ya enmascarados.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from ...domain.catalogo import CATALOGO_GENERICO, CatalogoDeRespuestas
from ...domain.datos_sinteticos import pan_sintetico
from ...domain.enmascarado import enmascarar_pan

VARIABLE_RUTA = "SIBU_DB_PATH"
RUTA_POR_DEFECTO = Path("sibutestlab8583.db")

DDL = """
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS tarjetas_prueba (
    card_id          TEXT    PRIMARY KEY,
    pan              TEXT    NOT NULL,
    pan_enmascarado  TEXT    NOT NULL,
    expiracion       TEXT    NOT NULL,
    descripcion      TEXT    NOT NULL DEFAULT '',
    sintetica        INTEGER NOT NULL DEFAULT 1,
    creada_en        TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS codigos_respuesta (
    catalogo     TEXT    NOT NULL,
    codigo       TEXT    NOT NULL,
    descripcion  TEXT    NOT NULL,
    aprobado     INTEGER NOT NULL,
    PRIMARY KEY (catalogo, codigo)
);

-- Sin columna de PAN a proposito: una ejecucion referencia la tarjeta por
-- card_id y guarda los mensajes ya enmascarados.
CREATE TABLE IF NOT EXISTS ejecuciones (
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

CREATE INDEX IF NOT EXISTS idx_ejecuciones_creada_en ON ejecuciones(creada_en);
CREATE INDEX IF NOT EXISTS idx_ejecuciones_card_id   ON ejecuciones(card_id);
"""

# Tarjeta de demostracion SINTETICA.
#
# Su numero se GENERA en ejecucion con pan_sintetico(): el repositorio no
# contiene PAN completos, ni reales ni sinteticos. El numero resultante no supera
# la verificacion de Luhn, de modo que ningun sistema que valide el digito
# verificador lo aceptaria como tarjeta. Existe unicamente para que un clon
# limpio tenga con que ejecutar la demostracion contra el host simulado; no
# representa una tarjeta de pago utilizable ni pertenece a ninguna marca.
CARD_ID_DEMO = "DEMO-0001"
SUFIJO_DEMO = "6666"
PAN_DEMO = pan_sintetico(SUFIJO_DEMO)
EXPIRACION_DEMO = "3012"
DESCRIPCION_DEMO = "Tarjeta sintetica de demostracion. No es una tarjeta real."


def ruta_base_datos() -> Path:
    """Ruta del archivo SQLite. Configurable por variable de entorno."""
    return Path(os.environ.get(VARIABLE_RUTA, RUTA_POR_DEFECTO))


async def _sembrar_catalogo(conexion: aiosqlite.Connection, catalogo: CatalogoDeRespuestas) -> None:
    await conexion.executemany(
        "INSERT OR IGNORE INTO codigos_respuesta (catalogo, codigo, descripcion, aprobado)"
        " VALUES (?, ?, ?, ?)",
        [
            (catalogo.nombre, c.codigo, c.descripcion, int(c.aprobado))
            for c in catalogo.codigos.values()
        ],
    )


async def _sembrar_tarjeta_demo(conexion: aiosqlite.Connection) -> None:
    await conexion.execute(
        "INSERT OR IGNORE INTO tarjetas_prueba"
        " (card_id, pan, pan_enmascarado, expiracion, descripcion, sintetica, creada_en)"
        " VALUES (?, ?, ?, ?, ?, 1, ?)",
        (
            CARD_ID_DEMO,
            PAN_DEMO,
            enmascarar_pan(PAN_DEMO),
            EXPIRACION_DEMO,
            DESCRIPCION_DEMO,
            datetime.now(timezone.utc).isoformat(),
        ),
    )


async def inicializar(ruta: Path | str | None = None, *, con_datos_demo: bool = True) -> Path:
    """Crea el esquema y siembra los datos base. Idempotente.

    Devuelve la ruta del archivo creado o ya existente.
    """
    destino = Path(ruta) if ruta is not None else ruta_base_datos()
    if destino.parent != Path("") and not destino.parent.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(destino) as conexion:
        await conexion.execute("PRAGMA foreign_keys = ON")
        await conexion.executescript(DDL)
        await _sembrar_catalogo(conexion, CATALOGO_GENERICO)
        if con_datos_demo:
            await _sembrar_tarjeta_demo(conexion)
        await conexion.commit()
    return destino


def main() -> None:
    """Punto de entrada de la consola: ``sibu-init-db``."""
    destino = asyncio.run(inicializar())
    print(f"Base de datos lista en: {destino.resolve()}")


if __name__ == "__main__":
    main()

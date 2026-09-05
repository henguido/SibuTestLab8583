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

-- Los ocho campos de laboratorio (titular en adelante) son datos propios de la
-- tarjeta, todavia sin validar y sin transmitirse por ISO: ver el docstring de
-- TarjetaPrueba en domain/modelos.py. pin_block_laboratorio es un valor con
-- forma de PIN Block, nunca un PIN en claro.
CREATE TABLE IF NOT EXISTS tarjetas_prueba (
    card_id                TEXT    PRIMARY KEY,
    pan                    TEXT    NOT NULL,
    pan_enmascarado        TEXT    NOT NULL,
    expiracion             TEXT    NOT NULL,
    descripcion            TEXT    NOT NULL DEFAULT '',
    sintetica              INTEGER NOT NULL DEFAULT 1,
    activa                 INTEGER NOT NULL DEFAULT 1,
    titular                TEXT    NOT NULL DEFAULT '',
    service_code           TEXT    NOT NULL DEFAULT '',
    discretionary_data     TEXT    NOT NULL DEFAULT '',
    cvv                    TEXT    NOT NULL DEFAULT '',
    cvv2                   TEXT    NOT NULL DEFAULT '',
    icvv                   TEXT    NOT NULL DEFAULT '',
    card_sequence_number   TEXT    NOT NULL DEFAULT '',
    pin_block_laboratorio  TEXT    NOT NULL DEFAULT '',
    creada_en              TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS codigos_respuesta (
    catalogo     TEXT    NOT NULL,
    codigo       TEXT    NOT NULL,
    descripcion  TEXT    NOT NULL,
    aprobado     INTEGER NOT NULL,
    PRIMARY KEY (catalogo, codigo)
);

-- Destinos de prueba administrados. LOCAL-DEMO se siembra abajo y apunta al
-- host simulado local; el puerto sembrado es el mismo valor por defecto que
-- composicion.PUERTO_POR_DEFECTO (8583). Una ejecucion NO referencia esta
-- tabla: guarda destino_host/destino_puerto como valores propios, para que
-- editar o desactivar un destino no altere el historial ya registrado.
CREATE TABLE IF NOT EXISTS destinos (
    destino_id  TEXT    PRIMARY KEY,
    nombre      TEXT    NOT NULL,
    host        TEXT    NOT NULL,
    puerto      INTEGER NOT NULL,
    activo      INTEGER NOT NULL DEFAULT 1,
    timeout     REAL    NOT NULL DEFAULT 10.0,
    creado_en   TEXT    NOT NULL
);

-- Escenarios: transacciones reutilizables. Congelan los valores EFECTIVOS de
-- los campos editables (defaults del perfil + overrides del usuario) al
-- momento de guardar -nunca los derivados/automaticos, que se regeneran en
-- cada ejecucion-. Referencia tarjeta y conexion por id, nunca PAN ni
-- host/puerto/timeout, igual que el resto del esquema.
-- expected_json es NULL a proposito -no '{}'-: un escenario sin expectativas
-- no es lo mismo que uno con una expectativa vacia, y NULL deja esa distincion
-- explicita en la propia fila en vez de depender de convencion.
CREATE TABLE IF NOT EXISTS escenarios (
    escenario_id   TEXT    PRIMARY KEY,
    nombre         TEXT    NOT NULL,
    perfil         TEXT    NOT NULL,
    mti            TEXT    NOT NULL DEFAULT '0100',
    card_id        TEXT    NOT NULL REFERENCES tarjetas_prueba(card_id),
    conexion_id    TEXT    NOT NULL REFERENCES destinos(destino_id),
    monto          TEXT    NOT NULL,
    campos_json    TEXT    NOT NULL DEFAULT '{}',
    expected_json  TEXT,
    activo         INTEGER NOT NULL DEFAULT 1,
    creado_en      TEXT    NOT NULL,
    actualizado_en TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_escenarios_nombre ON escenarios(nombre);

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
    -- Representacion estructurada de los mismos mensajes, ya enmascarados. Las
    -- dos columnas de texto se conservan por compatibilidad; estas permiten
    -- recuperar campo por campo sin depender de un separador sin escape.
    -- Nullable a proposito: las filas anteriores no se rellenan con datos
    -- reconstruidos, porque reconstruirlos seria inventarlos.
    solicitud_json          TEXT,
    respuesta_json          TEXT,
    latencia_ms             INTEGER,
    -- Si esta ejecucion partio de un escenario guardado: su id y su nombre en
    -- ese momento, copiado y no resuelto con un join -renombrar el escenario
    -- despues no debe alterar como luce una ejecucion ya registrada-.
    escenario_id            TEXT    REFERENCES escenarios(escenario_id),
    escenario_nombre        TEXT,
    -- Snapshot expected-vs-actual, congelado al ejecutar. `evaluacion_estado`
    -- NULL significa "el escenario no tenia expectativas" -nunca "aprobado
    -- por omision"-. `evaluacion_json` guarda la expectativa ORIGINAL usada,
    -- no una referencia al escenario: editarlo despues no altera esta fila.
    evaluacion_estado       TEXT,
    evaluacion_json         TEXT
);

CREATE INDEX IF NOT EXISTS idx_ejecuciones_creada_en ON ejecuciones(creada_en);
CREATE INDEX IF NOT EXISTS idx_ejecuciones_card_id   ON ejecuciones(card_id);

-- Bloque 4: suites de regresion. Una suite es una agrupacion reutilizable de
-- escenarios, en un orden fijo -no una corrida-. Igual que escenarios, nunca
-- contiene PAN ni host/puerto/timeout.
CREATE TABLE IF NOT EXISTS suites (
    suite_id       TEXT    PRIMARY KEY,
    nombre         TEXT    NOT NULL,
    descripcion    TEXT    NOT NULL DEFAULT '',
    activa         INTEGER NOT NULL DEFAULT 1,
    creado_en      TEXT    NOT NULL,
    actualizado_en TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_suites_nombre ON suites(nombre);

-- Membresia + orden. Se reemplaza entera (DELETE + INSERT en una sola
-- transaccion) al editar una suite, nunca se fusiona con lo anterior.
CREATE TABLE IF NOT EXISTS suite_escenarios (
    suite_id     TEXT    NOT NULL REFERENCES suites(suite_id),
    escenario_id TEXT    NOT NULL REFERENCES escenarios(escenario_id),
    orden        INTEGER NOT NULL,
    PRIMARY KEY (suite_id, escenario_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_suite_escenarios_orden ON suite_escenarios(suite_id, orden);

-- Corrida = ejecucion historica concreta de una suite. suite_nombre se copia
-- -no se resuelve con join- por el mismo motivo que ejecuciones.escenario_nombre:
-- renombrar la suite despues no debe alterar como luce una corrida ya registrada.
-- estado es el ciclo de vida (en_curso/finalizada); resultado_global es el
-- desenlace agregado, separado a proposito -ver domain/modelos.py- y NULL
-- mientras la corrida esta en curso.
CREATE TABLE IF NOT EXISTS corridas_suite (
    corrida_id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    suite_id                   TEXT    NOT NULL REFERENCES suites(suite_id),
    suite_nombre               TEXT    NOT NULL,
    estado                     TEXT    NOT NULL,
    resultado_global           TEXT,
    total                      INTEGER NOT NULL,
    cantidad_pass              INTEGER NOT NULL DEFAULT 0,
    cantidad_fail              INTEGER NOT NULL DEFAULT 0,
    cantidad_error             INTEGER NOT NULL DEFAULT 0,
    cantidad_sin_expectativas  INTEGER NOT NULL DEFAULT 0,
    cantidad_no_ejecutado      INTEGER NOT NULL DEFAULT 0,
    iniciada_en                TEXT    NOT NULL,
    finalizada_en              TEXT
);

CREATE INDEX IF NOT EXISTS idx_corridas_suite_iniciada_en ON corridas_suite(iniciada_en);

-- Item = resultado historico de UN escenario dentro de una corrida.
-- escenario_nombre y orden se copian al presembrar el item, antes de
-- ejecutarlo -editar la suite o el escenario despues no altera esta fila-.
-- evaluacion_json es una copia LITERAL del snapshot ya inmutable de la
-- Ejecucion (solo para pass/fail; NULL en cualquier otro caso): el detalle
-- de una corrida explica por si mismo que se esperaba, que se obtuvo y las
-- discrepancias, sin volver a consultar el escenario ni recalcular nada.
-- ejecucion_id sigue existiendo, aparte, como enlace de navegacion hacia el
-- detalle ISO completo.
CREATE TABLE IF NOT EXISTS corrida_suite_items (
    corrida_id       INTEGER NOT NULL REFERENCES corridas_suite(corrida_id),
    escenario_id     TEXT    NOT NULL,
    escenario_nombre TEXT    NOT NULL,
    orden            INTEGER NOT NULL,
    resultado        TEXT    NOT NULL,
    ejecucion_id     INTEGER REFERENCES ejecuciones(id),
    detalle          TEXT,
    evaluacion_json  TEXT,
    PRIMARY KEY (corrida_id, orden)
);

-- Secuencias persistentes. Existe para que el numero de trazabilidad sobreviva
-- a los reinicios y sea unico entre peticiones concurrentes. NO se deriva de
-- MAX(id) de ejecuciones: dos peticiones simultaneas leerian el mismo maximo.
CREATE TABLE IF NOT EXISTS secuencias (
    nombre  TEXT    PRIMARY KEY,
    valor   INTEGER NOT NULL
);
"""

#: Nombre de la secuencia del numero de trazabilidad.
SECUENCIA_STAN = "stan"

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
DESCRIPCION_DEMO = "Tarjeta de demostración"

# Destino de demostracion, sembrado en `destinos`. El puerto coincide con
# composicion.PUERTO_POR_DEFECTO (8583); esquema.py no importa composicion.py
# para evitar un ciclo, asi que el valor se repite aqui a proposito.
DESTINO_ID_DEMO = "LOCAL-DEMO"
DESTINO_NOMBRE_DEMO = "Host simulado local"
DESTINO_HOST_DEMO = "127.0.0.1"
DESTINO_PUERTO_DEMO = 8583


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


async def _sembrar_secuencias(conexion: aiosqlite.Connection) -> None:
    """Crea la secuencia del STAN si no existe.

    `INSERT OR IGNORE` es lo que hace idempotente la inicializacion: si la
    secuencia ya avanzo, volver a ejecutar `sibu-init-db` no la reinicia.
    """
    await conexion.execute(
        "INSERT OR IGNORE INTO secuencias (nombre, valor) VALUES (?, 0)",
        (SECUENCIA_STAN,),
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


#: Columnas agregadas despues de que la tabla `ejecuciones` ya existiera en
#: bases locales. El DDL de arriba las crea en una base nueva; en una existente
#: las agrega `_migrar`.
COLUMNAS_AGREGADAS: tuple[tuple[str, str], ...] = (
    ("solicitud_json", "TEXT"),
    ("respuesta_json", "TEXT"),
)

#: Lo mismo para `destinos`: `timeout` es posterior a bases ya creadas por un
#: clon anterior de este repositorio (la conexion pasa a llevar su propio
#: limite de tiempo, en vez de depender solo de la variable de entorno global).
COLUMNAS_AGREGADAS_DESTINOS: tuple[tuple[str, str], ...] = (
    ("timeout", "REAL NOT NULL DEFAULT 10.0"),
)

#: Lo mismo para `ejecuciones`: `escenario_id`/`escenario_nombre` son
#: posteriores a bases ya creadas por un clon anterior de este repositorio (el
#: Bloque 2 de escenarios agrega trazabilidad opcional hacia un escenario).
COLUMNAS_AGREGADAS_EJECUCIONES_ESCENARIO: tuple[tuple[str, str], ...] = (
    ("escenario_id", "TEXT"),
    ("escenario_nombre", "TEXT"),
)

#: Lo mismo para `ejecuciones`: `evaluacion_estado`/`evaluacion_json` son
#: posteriores (Bloque 3, expected vs actual).
COLUMNAS_AGREGADAS_EJECUCIONES_EVALUACION: tuple[tuple[str, str], ...] = (
    ("evaluacion_estado", "TEXT"),
    ("evaluacion_json", "TEXT"),
)

#: Lo mismo para `escenarios`: `expected_json` es posterior (Bloque 3).
COLUMNAS_AGREGADAS_ESCENARIOS: tuple[tuple[str, str], ...] = (
    ("expected_json", "TEXT"),
)

#: Lo mismo para `tarjetas_prueba`: `activa` y los ocho campos de laboratorio
#: (titular en adelante) son posteriores a bases ya creadas por un clon
#: anterior de este repositorio.
COLUMNAS_AGREGADAS_TARJETAS: tuple[tuple[str, str], ...] = (
    ("activa", "INTEGER NOT NULL DEFAULT 1"),
    ("titular", "TEXT NOT NULL DEFAULT ''"),
    ("service_code", "TEXT NOT NULL DEFAULT ''"),
    ("discretionary_data", "TEXT NOT NULL DEFAULT ''"),
    ("cvv", "TEXT NOT NULL DEFAULT ''"),
    ("cvv2", "TEXT NOT NULL DEFAULT ''"),
    ("icvv", "TEXT NOT NULL DEFAULT ''"),
    ("card_sequence_number", "TEXT NOT NULL DEFAULT ''"),
    ("pin_block_laboratorio", "TEXT NOT NULL DEFAULT ''"),
)


async def _columnas_de(conexion: aiosqlite.Connection, tabla: str) -> set[str]:
    async with conexion.execute(f"PRAGMA table_info({tabla})") as cursor:
        return {fila[1] for fila in await cursor.fetchall()}


async def _migrar(
    conexion: aiosqlite.Connection, tabla: str, columnas: tuple[tuple[str, str], ...]
) -> tuple[str, ...]:
    """Agrega a `tabla` las columnas de `columnas` que una base anterior no tenga.

    El proyecto no usa Alembic: para este alcance, comprobar y agregar es mas
    simple de leer y de auditar que una herramienta de migraciones.

    `CREATE TABLE IF NOT EXISTS` no altera una tabla que ya existe, asi que sin
    esto una base creada antes de estas columnas se quedaria sin ellas y las
    consultas fallarian. Es idempotente: si la columna esta, no se toca nada, y
    **ninguna fila existente se modifica**.

    Los nombres de tabla y columna se interpolan porque `ALTER TABLE` no admite
    parametros; provienen siempre de las constantes de arriba, nunca de
    entrada externa.

    Corre despues del DDL, asi que la tabla siempre existe: en una base nueva ya
    trae las columnas y este bucle no hace nada; en una anterior las agrega.
    Devuelve los nombres que agrego, para que una prueba pueda comprobarlo.
    """
    existentes = await _columnas_de(conexion, tabla)
    agregadas: list[str] = []
    for columna, tipo in columnas:
        if columna not in existentes:
            await conexion.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {tipo}")
            agregadas.append(columna)
    return tuple(agregadas)


async def _migrar_ejecuciones(conexion: aiosqlite.Connection) -> tuple[str, ...]:
    """Compatibilidad: `ejecuciones` migrada con el `_migrar` generalizado."""
    return await _migrar(conexion, "ejecuciones", COLUMNAS_AGREGADAS)


async def _sembrar_destinos(conexion: aiosqlite.Connection) -> None:
    await conexion.execute(
        "INSERT OR IGNORE INTO destinos (destino_id, nombre, host, puerto, activo, creado_en)"
        " VALUES (?, ?, ?, ?, 1, ?)",
        (
            DESTINO_ID_DEMO,
            DESTINO_NOMBRE_DEMO,
            DESTINO_HOST_DEMO,
            DESTINO_PUERTO_DEMO,
            datetime.now(timezone.utc).isoformat(),
        ),
    )


async def inicializar(ruta: Path | str | None = None, *, con_datos_demo: bool = True) -> Path:
    """Crea el esquema, migra lo que falte y siembra los datos base. Idempotente.

    Devuelve la ruta del archivo creado o ya existente.
    """
    destino = Path(ruta) if ruta is not None else ruta_base_datos()
    if destino.parent != Path("") and not destino.parent.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(destino) as conexion:
        await conexion.execute("PRAGMA foreign_keys = ON")
        await conexion.executescript(DDL)
        await _migrar(conexion, "ejecuciones", COLUMNAS_AGREGADAS)
        await _migrar(conexion, "ejecuciones", COLUMNAS_AGREGADAS_EJECUCIONES_ESCENARIO)
        await _migrar(conexion, "ejecuciones", COLUMNAS_AGREGADAS_EJECUCIONES_EVALUACION)
        await _migrar(conexion, "escenarios", COLUMNAS_AGREGADAS_ESCENARIOS)
        await _migrar(conexion, "tarjetas_prueba", COLUMNAS_AGREGADAS_TARJETAS)
        await _migrar(conexion, "destinos", COLUMNAS_AGREGADAS_DESTINOS)
        await _sembrar_secuencias(conexion)
        await _sembrar_catalogo(conexion, CATALOGO_GENERICO)
        await _sembrar_destinos(conexion)
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

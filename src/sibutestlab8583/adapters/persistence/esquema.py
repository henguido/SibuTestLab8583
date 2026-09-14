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
--
-- card_id/monto son NULLABLE desde B3 (2026-09-13): una operacion sin
-- tarjeta ni monto (Echo) no tiene forma de rellenarlos con un valor real -
-- mismo criterio ya aplicado a `ejecuciones` en B2-. conexion_id sigue
-- NOT NULL: toda operacion, con o sin tarjeta, se transmite a un destino.
-- operacion (nueva) es la intencion funcional (ver domain.modelos.
-- OPERACION_POR_MTI), redundante con `mti` hoy -exactamente un MTI por
-- operacion-, pero ya lista para cuando un MTI futuro represente mas de una.
CREATE TABLE IF NOT EXISTS escenarios (
    escenario_id   TEXT    PRIMARY KEY,
    nombre         TEXT    NOT NULL,
    perfil         TEXT    NOT NULL,
    mti            TEXT    NOT NULL DEFAULT '0100',
    operacion      TEXT    NOT NULL DEFAULT 'purchase',
    card_id        TEXT    REFERENCES tarjetas_prueba(card_id),
    conexion_id    TEXT    NOT NULL REFERENCES destinos(destino_id),
    monto          TEXT,
    campos_json    TEXT    NOT NULL DEFAULT '{}',
    expected_json  TEXT,
    activo         INTEGER NOT NULL DEFAULT 1,
    creado_en      TEXT    NOT NULL,
    actualizado_en TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_escenarios_nombre ON escenarios(nombre);

-- Sin columna de PAN a proposito: una ejecucion referencia la tarjeta por
-- card_id y guarda los mensajes ya enmascarados.
--
-- card_id/monto/moneda son NULLABLE desde B2 (2026-09-12): una operacion sin
-- tarjeta ni monto (ej. 0800 Network Management/Echo) no tiene forma de
-- rellenarlos con un valor real, y un sentinel inventado ("", 0) seria un dato
-- falso en el historial. NULL es honesto: "no aplica", no "vacio". La FK hacia
-- tarjetas_prueba se mantiene -NULL la deja sin efecto automaticamente, es
-- comportamiento estandar de SQL, no una relajacion de la garantia para las
-- filas que SI tienen tarjeta-. Ver `_migrar_ejecuciones_card_id_nullable`
-- para el camino de una base existente creada antes de este cambio.
CREATE TABLE IF NOT EXISTS ejecuciones (
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
    evaluacion_json         TEXT,
    -- Causa concreta y segura del desenlace (ver Ejecucion.motivo_detalle en
    -- domain/modelos.py). NULL para una APROBADA (no aplica) y para filas
    -- anteriores a que este campo existiera (no se reconstruye).
    motivo_detalle          TEXT,
    -- Referencia a la ejecucion de la que ESTA se deriva (B6, modelo de
    -- reversos, 2026-09-13): FK auto-referencial, nullable -NULL para
    -- cualquier ejecucion independiente, la inmensa mayoria hoy. Un mismo
    -- origen puede tener varias derivadas (1->N): nada aqui impone
    -- unicidad. Nunca se resuelve con join en cada lectura -ver
    -- Ejecucion.ejecucion_origen_id en domain/modelos.py-: es un puntero de
    -- navegacion, los datos seguros de la ejecucion origen viajan aparte en
    -- `ReferenciaEjecucion` (application/referencia_ejecucion.py).
    ejecucion_origen_id     INTEGER REFERENCES ejecuciones(id)
);

CREATE INDEX IF NOT EXISTS idx_ejecuciones_creada_en ON ejecuciones(creada_en);
CREATE INDEX IF NOT EXISTS idx_ejecuciones_card_id   ON ejecuciones(card_id);
-- Sin indice para ejecucion_origen_id a proposito: es una columna migrada
-- (ADD COLUMN), y este DDL corre integro -incluidas las CREATE INDEX- ANTES
-- de que las migraciones de columnas se apliquen (ver inicializar() mas
-- abajo); un indice aqui fallaria con "no such column" contra una base
-- existente que todavia no la tenga. Ningun otro campo agregado por
-- migracion (escenario_id, evaluacion_estado, motivo_detalle) tiene indice
-- propio tampoco -mismo motivo-. El volumen esperado de derivadas no lo
-- justifica todavia; se puede agregar despues con su propia migracion si
-- hiciera falta.

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

-- Fase C1: Secuencias transaccionales -pasos DEPENDIENTES (el paso 2 usa la
-- ejecucion producida por el paso 1), a diferencia de una Suite (escenarios
-- INDEPENDIENTES). Nombradas "secuencias_transaccionales"/"secuencia_
-- transaccional_pasos" -NUNCA "secuencias" a secas- para no chocar con la
-- tabla de arriba, que es el contador de STAN y no tiene relacion alguna
-- con este concepto.
--
-- origen_tipo distingue, por paso, de donde salen sus datos:
--   'independiente' -> arma su propio DatosX desde escenario_id, igual que
--                      cualquier item de una suite hoy.
--   'derivado'      -> NO tiene escenario_id (nada que armar libremente):
--                      se construye enteramente desde la ejecucion que
--                      produjo el paso `origen_paso_orden` de ESTA MISMA
--                      secuencia (ver application/referencia_ejecucion.py,
--                      B6/B7 -reusado tal cual, nunca un segundo sistema de
--                      referencias).
CREATE TABLE IF NOT EXISTS secuencias_transaccionales (
    secuencia_id   TEXT    PRIMARY KEY,
    nombre         TEXT    NOT NULL,
    descripcion    TEXT    NOT NULL DEFAULT '',
    activa         INTEGER NOT NULL DEFAULT 1,
    creado_en      TEXT    NOT NULL,
    actualizado_en TEXT    NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_secuencias_transaccionales_nombre
    ON secuencias_transaccionales(nombre);

-- Pasos de la DEFINICION, en orden. escenario_id es NULL para un paso
-- derivado -a proposito, no tiene sentido "que escenario arma un reverso
-- derivado"-; origen_paso_orden es NULL para un paso independiente.
-- expectativas_json solo aplica a un paso derivado (uno independiente ya
-- trae sus propias expectativas en el escenario referenciado -no se
-- duplican aqui, para no tener dos fuentes de la misma expectativa-).
CREATE TABLE IF NOT EXISTS secuencia_transaccional_pasos (
    secuencia_id      TEXT    NOT NULL REFERENCES secuencias_transaccionales(secuencia_id),
    orden             INTEGER NOT NULL,
    origen_tipo       TEXT    NOT NULL,
    escenario_id      TEXT    REFERENCES escenarios(escenario_id),
    origen_paso_orden INTEGER,
    expectativas_json TEXT,
    PRIMARY KEY (secuencia_id, orden)
);

-- Corrida = ejecucion historica concreta de una secuencia. Mismo criterio de
-- "copiar, nunca join" que corridas_suite. cantidad_bloqueado es el unico
-- contador nuevo respecto de corridas_suite: un paso derivado cuyo origen no
-- produjo una ejecucion elegible NO es lo mismo que FAIL (no se intento) ni
-- que ERROR (no fue un fallo tecnico) -ver domain/secuencias.py.
CREATE TABLE IF NOT EXISTS corridas_secuencia (
    corrida_id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    secuencia_id               TEXT    NOT NULL REFERENCES secuencias_transaccionales(secuencia_id),
    secuencia_nombre           TEXT    NOT NULL,
    estado                     TEXT    NOT NULL,
    resultado_global           TEXT,
    total                      INTEGER NOT NULL,
    cantidad_pass              INTEGER NOT NULL DEFAULT 0,
    cantidad_fail              INTEGER NOT NULL DEFAULT 0,
    cantidad_error             INTEGER NOT NULL DEFAULT 0,
    cantidad_sin_expectativas  INTEGER NOT NULL DEFAULT 0,
    cantidad_bloqueado         INTEGER NOT NULL DEFAULT 0,
    cantidad_no_ejecutado      INTEGER NOT NULL DEFAULT 0,
    iniciada_en                TEXT    NOT NULL,
    finalizada_en              TEXT
);

CREATE INDEX IF NOT EXISTS idx_corridas_secuencia_iniciada_en ON corridas_secuencia(iniciada_en);

-- Paso = resultado historico de UN paso dentro de una corrida de secuencia.
-- origen_tipo/origen_paso_orden se copian de la definicion al presembrar
-- -editar la secuencia despues no altera una corrida ya registrada-.
-- ejecucion_id es el enlace de navegacion hacia el detalle ISO completo,
-- igual que en corrida_suite_items; NULL si el paso quedo BLOQUEADO (nunca
-- se genero ninguna ejecucion para el).
CREATE TABLE IF NOT EXISTS corrida_secuencia_pasos (
    corrida_id        INTEGER NOT NULL REFERENCES corridas_secuencia(corrida_id),
    orden             INTEGER NOT NULL,
    escenario_id      TEXT,
    escenario_nombre  TEXT,
    origen_tipo       TEXT    NOT NULL,
    origen_paso_orden INTEGER,
    resultado         TEXT    NOT NULL,
    ejecucion_id      INTEGER REFERENCES ejecuciones(id),
    detalle           TEXT,
    evaluacion_json   TEXT,
    PRIMARY KEY (corrida_id, orden)
);

-- Intentos de UN paso con retry (C3, 2026-09-14). Tabla NUEVA -no una fila
-- por intento en corrida_secuencia_pasos, que seguiria representando SOLO
-- el desenlace final/autoritativo de cada paso (misma fila, mismo
-- significado que antes de C3)-: cada intento real (solo ocurre cuando
-- `PasoSecuencia.max_retries > 0`, hoy exclusivo de un escenario Echo, ver
-- domain/modelos.py) se guarda aqui, en su propio orden, sin sobrescribir
-- al anterior. `corrida_secuencia_pasos.ejecucion_id`/`resultado` siguen
-- siendo la fuente de verdad de "que paso al final"; esta tabla es el
-- detalle de auditoria de COMO se llego ahi.
CREATE TABLE IF NOT EXISTS corrida_secuencia_paso_intentos (
    corrida_id      INTEGER NOT NULL,
    orden           INTEGER NOT NULL,
    numero_intento  INTEGER NOT NULL,
    resultado       TEXT    NOT NULL,
    ejecucion_id    INTEGER REFERENCES ejecuciones(id),
    detalle         TEXT,
    creado_en       TEXT    NOT NULL,
    PRIMARY KEY (corrida_id, orden, numero_intento),
    FOREIGN KEY (corrida_id, orden) REFERENCES corrida_secuencia_pasos(corrida_id, orden)
);

-- Secuencias persistentes. Existe para que el numero de trazabilidad sobreviva
-- a los reinicios y sea unico entre peticiones concurrentes. NO se deriva de
-- MAX(id) de ejecuciones: dos peticiones simultaneas leerian el mismo maximo.
CREATE TABLE IF NOT EXISTS secuencias (
    nombre  TEXT    PRIMARY KEY,
    valor   INTEGER NOT NULL
);

-- Reglas del Host Simulado (Fase D1, 2026-09-14). LA REGLA ES CONFIGURACION
-- -esta tabla nunca se mezcla con el EVENTO de que una regla coincidio con
-- un mensaje real (eso vive en reglas_host_eventos, mas abajo; punto 20 del
-- checkpoint: "no guardar ambas cosas en la misma tabla"). `condiciones_json`
-- y `campos_adicionales_json` siguen el mismo criterio ya establecido para
-- estructuras anidadas en este proyecto (`expectativas_json` en
-- secuencia_transaccional_pasos): JSON en una columna, nunca una tabla hija
-- por condicion -no hay necesidad de consultar condiciones individualmente
-- fuera de cargar la regla completa-.
CREATE TABLE IF NOT EXISTS reglas_host (
    regla_id                TEXT    PRIMARY KEY,
    nombre                  TEXT    NOT NULL,
    prioridad               INTEGER NOT NULL,
    activa                  INTEGER NOT NULL,
    condiciones_json        TEXT    NOT NULL,
    de39                    TEXT    NOT NULL,
    campos_adicionales_json TEXT    NOT NULL,
    comportamiento_tipo     TEXT    NOT NULL,
    comportamiento_delay_ms INTEGER NOT NULL,
    creado_en               TEXT    NOT NULL,
    actualizado_en          TEXT    NOT NULL
);

-- Evidencia, del lado del SIMULADOR, de que una regla (o ninguna) goberno
-- una respuesta real (punto 21 del checkpoint). Deliberadamente SIN FK hacia
-- `ejecuciones` (esa es la tabla del CLIENTE -Orquestador/EjecutorDeSecuencia-
-- ; conectar ambos lados complicaria D1 sin necesidad real todavia, punto 21
-- lo autoriza explicitamente: "no hace falta conectar aun con Ejecucion
-- cliente si complica D1"). `regla_id` es NULL cuando NINGUNA regla coincidio
-- (comportamiento default, punto 7) -tambien es evidencia valiosa. Nunca
-- guarda el VALOR de ningun campo del mensaje que causo la coincidencia
-- (punto 21/35: solo que regla goberno, con que prioridad, y que
-- respondio) -ver `application/reglas_host.py::registrar_evento`.
CREATE TABLE IF NOT EXISTS reglas_host_eventos (
    evento_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    regla_id        TEXT,
    regla_nombre    TEXT,
    prioridad       INTEGER,
    mti_solicitud   TEXT    NOT NULL,
    de39_respuesta  TEXT,
    comportamiento  TEXT    NOT NULL,
    delay_ms        INTEGER NOT NULL DEFAULT 0,
    creado_en       TEXT    NOT NULL
);

-- ESTADO OPERACIONAL de una regla con `max_aplicaciones` (Fase D2,
-- 2026-09-14): deliberadamente SEPARADA de `reglas_host` -mismo principio
-- que ya separa configuracion (reglas_host) de auditoria
-- (reglas_host_eventos): duplicar una regla (INSERT en reglas_host) nunca
-- toca esta tabla -la copia arranca sin fila aqui, equivalente a contador
-- en 0-; reiniciar el contador es un UPDATE de una sola fila que nunca
-- toca la configuracion. `regla_id` es PK Y FK 1:1 hacia `reglas_host`: una
-- regla sin `max_aplicaciones` nunca necesita fila aqui (investigado:
-- `es_agotada`/`evaluar_reglas` ya tratan "sin fila" como "0 consumidas",
-- ver `domain/reglas_host.py`).
CREATE TABLE IF NOT EXISTS reglas_host_estado (
    regla_id                TEXT    PRIMARY KEY REFERENCES reglas_host(regla_id),
    aplicaciones_consumidas INTEGER NOT NULL DEFAULT 0,
    actualizado_en          TEXT    NOT NULL
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

#: Lo mismo para `ejecuciones`: `ejecucion_origen_id` es posterior (B6,
#: modelo de reversos). Aditiva y nullable -sin conflicto de default ni de
#: constraint existente-, asi que basta el camino liviano de `_migrar()`
#: (`ALTER TABLE ... ADD COLUMN`): a diferencia de `card_id`/`monto`
#: (`_migrar_ejecuciones_card_id_nullable`), aqui no se relaja ningun
#: `NOT NULL` previo, se agrega una columna nueva desde cero.
COLUMNAS_AGREGADAS_EJECUCIONES_ORIGEN: tuple[tuple[str, str], ...] = (
    ("ejecucion_origen_id", "INTEGER REFERENCES ejecuciones(id)"),
)

#: Lo mismo para `ejecuciones`: `motivo_detalle` es posterior (diagnostico
#: historico de fallos, mejora funcional posterior al cierre).
COLUMNAS_AGREGADAS_EJECUCIONES_MOTIVO: tuple[tuple[str, str], ...] = (
    ("motivo_detalle", "TEXT"),
)

#: Lo mismo para `escenarios`: `expected_json` es posterior (Bloque 3);
#: `operacion` es posterior (B3, 2026-09-13) -default 'purchase' porque toda
#: fila anterior a B3 es, por definicion, una compra: es el unico MTI que
#: `escenarios.py` sabia crear antes de B3-.
COLUMNAS_AGREGADAS_ESCENARIOS: tuple[tuple[str, str], ...] = (
    ("expected_json", "TEXT"),
    ("operacion", "TEXT NOT NULL DEFAULT 'purchase'"),
)

#: C2 (2026-09-14): `paso_id` -identificador estable de paso, distinto de
#: `orden`- es posterior a C1, que nunca lo necesito. Aditiva y nullable:
#: una secuencia guardada antes de C2 simplemente no tiene id estable en
#: sus pasos hasta que se vuelva a guardar (`ServicioSecuencias` lo genera
#: si falta, ver domain/modelos.py::PasoSecuencia).
#:
#: B8 (2026-09-14): `operacion_derivada` -cual operacion derivada ejecuta un
#: paso DERIVADO (reverso financiero o aviso de reverso)- es posterior a C1,
#: que solo conocia una. Aditiva, con el mismo default que
#: `PasoSecuencia.operacion_derivada` ("financial_reversal"): una secuencia
#: guardada antes de B8 significa exactamente lo mismo que antes (su unico
#: paso derivado posible ya era un reverso financiero), sin necesitar
#: migrar datos.
#:
#: C3 (2026-09-14): `on_error`/`on_qa_fail` -politica de continuacion de la
#: SECUENCIA cuando ESTE paso termina en ERROR/FAIL- y `max_retries` -
#: reintentos automaticos permitidos, solo aplicable hoy a un paso Echo- son
#: posteriores a C1/C2/B8, que no conocian ningun control de flujo. Aditivas,
#: con el mismo default que `PasoSecuencia` (`domain/modelos.py`,
#: `PoliticaContinuacion.CONTINUAR`/`0`): una secuencia guardada antes de C3
#: preserva su comportamiento observable exacto -el motor NUNCA se detenia
#: por si solo antes de C3 (auditado explicitamente, ver docstring de
#: `PoliticaContinuacion`), asi que CONTINUAR es la unica retro-asignacion
#: que no cambia nada para una definicion existente.
COLUMNAS_AGREGADAS_SECUENCIA_TRANSACCIONAL_PASOS: tuple[tuple[str, str], ...] = (
    ("paso_id", "TEXT"),
    ("operacion_derivada", "TEXT NOT NULL DEFAULT 'financial_reversal'"),
    ("on_error", "TEXT NOT NULL DEFAULT 'continuar'"),
    ("on_qa_fail", "TEXT NOT NULL DEFAULT 'continuar'"),
    ("max_retries", "INTEGER NOT NULL DEFAULT 0"),
)

#: Lo mismo para `corrida_secuencia_pasos`: copia historica del `paso_id`
#: vigente al presembrar el paso (mismo criterio que `escenario_nombre`).
COLUMNAS_AGREGADAS_CORRIDA_SECUENCIA_PASOS: tuple[tuple[str, str], ...] = (
    ("paso_id", "TEXT"),
)

#: D2 (2026-09-14): `max_aplicaciones` es posterior a D1, que no conocia
#: ningun limite. Aditiva, nullable -sin default numerico-: una regla
#: guardada antes de D2 significa "ilimitada" exactamente igual que antes,
#: sin necesitar backfill (NULL ya es "ilimitada" para `es_agotada`).
COLUMNAS_AGREGADAS_REGLAS_HOST: tuple[tuple[str, str], ...] = (
    ("max_aplicaciones", "INTEGER"),
)

#: D2: `match_number` es posterior a D1. Aditiva, nullable: un evento
#: registrado antes de D2 nunca tuvo un limite que contar, asi que `NULL`
#: es el unico valor coherente para esas filas historicas.
COLUMNAS_AGREGADAS_REGLAS_HOST_EVENTOS: tuple[tuple[str, str], ...] = (
    ("match_number", "INTEGER"),
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


#: Columnas de `ejecuciones`, en el orden exacto del DDL -usado para copiar
#: fila por fila durante el rebuild de `_migrar_ejecuciones_card_id_nullable`,
#: nunca para adivinar el orden con `SELECT *`.
_COLUMNAS_EJECUCIONES = (
    "id", "creada_en", "card_id", "mti_solicitud", "mti_respuesta", "monto",
    "moneda", "stan", "destino_host", "destino_puerto", "estado",
    "codigo_respuesta", "solicitud_enmascarada", "respuesta_enmascarada",
    "solicitud_json", "respuesta_json", "latencia_ms", "escenario_id",
    "escenario_nombre", "evaluacion_estado", "evaluacion_json", "motivo_detalle",
    "ejecucion_origen_id",
)


async def _migrar_ejecuciones_card_id_nullable(conexion: aiosqlite.Connection) -> bool:
    """Relaja `card_id`/`monto`/`moneda` de `NOT NULL` a `NULL` en una base
    creada ANTES de B2 (2026-09-12).

    SQLite no admite `ALTER TABLE ... ALTER COLUMN` para quitar `NOT NULL`: el
    unico camino estandar es reconstruir la tabla (crear con el esquema
    nuevo, copiar todas las filas explicitamente por nombre de columna,
    borrar la vieja, renombrar la nueva) - el mismo patron documentado en la
    propia documentacion de SQLite para este tipo de cambio. Es **aditivo y
    seguro**: solo AMPLIA que valores acepta la columna, ninguna fila
    existente cambia de valor, y el DDL de mas arriba ya crea la tabla nueva
    con el esquema correcto -esta funcion solo corre para una base existente
    que todavia tenga la restriccion vieja-.

    Idempotente por diseno: si `card_id` ya admite `NULL` (base nueva, o ya
    migrada), no hace nada y devuelve `False`. El `DROP TABLE IF EXISTS
    ejecuciones_nueva_b2` inicial existe porque un intento anterior
    interrumpido a mitad de camino (verificado en la practica: una version
    previa de esta funcion fallaba por la FK de abajo, dejando la tabla
    temporal creada pero `ejecuciones` intacta) no debe bloquear el reintento
    con "the table already exists" -limpiar el residuo es seguro porque esa
    tabla temporal nunca es la fuente de verdad mientras no se haya
    renombrado.

    `corrida_suite_items.ejecucion_id` referencia `ejecuciones(id)`: mientras
    existan filas de suites ya corridas, `DROP TABLE ejecuciones` viola esa
    FK si `PRAGMA foreign_keys` esta ON durante el rebuild -aunque la tabla
    reaparezca con el mismo nombre e ids un instante despues-. Se apaga el
    chequeo solo durante esta operacion (nunca se borra ni se recrea ninguna
    fila de otra tabla, asi que no hay ninguna referencia real que se
    rompa) y se restaura antes de devolver el control. `PRAGMA foreign_keys`
    no se puede cambiar dentro de una transaccion abierta, por eso el commit
    explicito antes de tocarlo.
    """
    async with conexion.execute("PRAGMA table_info(ejecuciones)") as cursor:
        columnas_info = await cursor.fetchall()
    # PRAGMA table_info: (cid, name, type, notnull, dflt_value, pk)
    notnull_card_id = next((fila[3] for fila in columnas_info if fila[1] == "card_id"), None)
    if not notnull_card_id:
        return False  # ya nullable (base nueva o ya migrada): nada que hacer

    # Una base MUY anterior (de antes de que existieran mti_respuesta,
    # destino_host/puerto, codigo_respuesta, etc.) puede no tener todavia
    # alguna de estas columnas -esas migraciones nunca las agregaron porque
    # nunca hizo falta para lo que probaban-. Copiar solo lo que existe de
    # verdad evita "no such column"; lo que falte queda NULL en la tabla
    # nueva, exactamente como quedaria si nunca se hubiera escrito.
    existentes = {fila[1] for fila in columnas_info}
    columnas_a_copiar = tuple(c for c in _COLUMNAS_EJECUCIONES if c in existentes)
    columnas_sql = ", ".join(columnas_a_copiar)
    await conexion.commit()
    await conexion.execute("PRAGMA foreign_keys = OFF")
    await conexion.executescript(
        f"""
        DROP TABLE IF EXISTS ejecuciones_nueva_b2;
        CREATE TABLE ejecuciones_nueva_b2 (
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
            escenario_id            TEXT    REFERENCES escenarios(escenario_id),
            escenario_nombre        TEXT,
            evaluacion_estado       TEXT,
            evaluacion_json         TEXT,
            motivo_detalle          TEXT,
            ejecucion_origen_id     INTEGER REFERENCES ejecuciones(id)
        );
        INSERT INTO ejecuciones_nueva_b2 ({columnas_sql})
            SELECT {columnas_sql} FROM ejecuciones;
        DROP TABLE ejecuciones;
        ALTER TABLE ejecuciones_nueva_b2 RENAME TO ejecuciones;
        CREATE INDEX IF NOT EXISTS idx_ejecuciones_creada_en ON ejecuciones(creada_en);
        CREATE INDEX IF NOT EXISTS idx_ejecuciones_card_id   ON ejecuciones(card_id);
        """
    )
    await conexion.commit()
    await conexion.execute("PRAGMA foreign_keys = ON")
    return True


#: Columnas de `escenarios`, en el orden exacto del DDL -mismo proposito que
#: `_COLUMNAS_EJECUCIONES`: copiar por nombre explicito, nunca con `SELECT *`.
_COLUMNAS_ESCENARIOS = (
    "escenario_id", "nombre", "perfil", "mti", "operacion", "card_id",
    "conexion_id", "monto", "campos_json", "expected_json", "activo",
    "creado_en", "actualizado_en",
)


async def _migrar_escenarios_card_id_nullable(conexion: aiosqlite.Connection) -> bool:
    """Relaja `escenarios.card_id`/`monto` de `NOT NULL` a `NULL` en una base
    creada ANTES de B3 (2026-09-13) -mismo patron y mismo motivo que
    `_migrar_ejecuciones_card_id_nullable` (B2): una operacion sin tarjeta ni
    monto (Echo) no puede guardarse como escenario con el esquema viejo.

    Debe correr DESPUES de que `operacion` ya exista (agregada por
    `COLUMNAS_AGREGADAS_ESCENARIOS` en `_migrar`, antes de esta llamada en
    `inicializar`), por la misma razon que `_migrar_ejecuciones_card_id_nullable`
    corre al final: copiar por nombre de columna exige que la columna ya
    exista.

    `ejecuciones.escenario_id` y `suite_escenarios.escenario_id` referencian
    `escenarios(escenario_id)`: se apaga `PRAGMA foreign_keys` durante el
    rebuild por el mismo motivo documentado ahi (dropear la tabla mientras
    esas filas la referencian violaria la FK aunque reaparezca con el mismo
    nombre e ids un instante despues).
    """
    async with conexion.execute("PRAGMA table_info(escenarios)") as cursor:
        columnas_info = await cursor.fetchall()
    notnull_card_id = next((fila[3] for fila in columnas_info if fila[1] == "card_id"), None)
    if not notnull_card_id:
        return False  # ya nullable (base nueva o ya migrada): nada que hacer

    existentes = {fila[1] for fila in columnas_info}
    columnas_a_copiar = tuple(c for c in _COLUMNAS_ESCENARIOS if c in existentes)
    columnas_sql = ", ".join(columnas_a_copiar)
    await conexion.commit()
    await conexion.execute("PRAGMA foreign_keys = OFF")
    await conexion.executescript(
        f"""
        DROP TABLE IF EXISTS escenarios_nueva_b3;
        CREATE TABLE escenarios_nueva_b3 (
            escenario_id   TEXT    PRIMARY KEY,
            nombre         TEXT    NOT NULL,
            perfil         TEXT    NOT NULL,
            mti            TEXT    NOT NULL DEFAULT '0100',
            operacion      TEXT    NOT NULL DEFAULT 'purchase',
            card_id        TEXT    REFERENCES tarjetas_prueba(card_id),
            conexion_id    TEXT    NOT NULL REFERENCES destinos(destino_id),
            monto          TEXT,
            campos_json    TEXT    NOT NULL DEFAULT '{{}}',
            expected_json  TEXT,
            activo         INTEGER NOT NULL DEFAULT 1,
            creado_en      TEXT    NOT NULL,
            actualizado_en TEXT    NOT NULL
        );
        INSERT INTO escenarios_nueva_b3 ({columnas_sql})
            SELECT {columnas_sql} FROM escenarios;
        DROP TABLE escenarios;
        ALTER TABLE escenarios_nueva_b3 RENAME TO escenarios;
        CREATE INDEX IF NOT EXISTS idx_escenarios_nombre ON escenarios(nombre);
        """
    )
    await conexion.commit()
    await conexion.execute("PRAGMA foreign_keys = ON")
    return True


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
        await _migrar(conexion, "ejecuciones", COLUMNAS_AGREGADAS_EJECUCIONES_MOTIVO)
        await _migrar(conexion, "ejecuciones", COLUMNAS_AGREGADAS_EJECUCIONES_ORIGEN)
        await _migrar(conexion, "escenarios", COLUMNAS_AGREGADAS_ESCENARIOS)
        await _migrar(conexion, "tarjetas_prueba", COLUMNAS_AGREGADAS_TARJETAS)
        await _migrar(conexion, "destinos", COLUMNAS_AGREGADAS_DESTINOS)
        await _migrar(
            conexion, "secuencia_transaccional_pasos",
            COLUMNAS_AGREGADAS_SECUENCIA_TRANSACCIONAL_PASOS,
        )
        await _migrar(
            conexion, "corrida_secuencia_pasos", COLUMNAS_AGREGADAS_CORRIDA_SECUENCIA_PASOS
        )
        await _migrar(conexion, "reglas_host", COLUMNAS_AGREGADAS_REGLAS_HOST)
        await _migrar(conexion, "reglas_host_eventos", COLUMNAS_AGREGADAS_REGLAS_HOST_EVENTOS)
        # Corre AL FINAL de las migraciones de columnas: reconstruye la tabla
        # completa (ver docstring), asi que necesita que todas las columnas
        # modernas ya existan -si una base historica todavia no tenia
        # mti_respuesta/escenario_id/etc., esas migraciones ya corrieron arriba.
        await _migrar_ejecuciones_card_id_nullable(conexion)
        # Mismo motivo: necesita que "operacion" ya exista (linea 619).
        await _migrar_escenarios_card_id_nullable(conexion)
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

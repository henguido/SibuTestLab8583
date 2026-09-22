"""Repositorios SQLite sobre aiosqlite.

Implementan los puertos declarados en ``domain.puertos``. Es el unico lugar del
proyecto que sabe que la persistencia es SQLite: el dominio no lo conoce, y por
eso PostgreSQL podria sustituirlo sin tocar la logica de negocio.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Sequence

import aiosqlite

from ...domain.catalogo import CatalogoDeRespuestas, CodigoRespuesta
from ...domain.expectativas import expectativas_a_dict, expectativas_desde_dict
from ...domain.modelos import (
    LARGO_STAN,
    STAN_MAXIMO,
    CorridaSecuencia,
    CorridaSuite,
    DestinoGuardado,
    Ejecucion,
    Escenario,
    EstadoCorridaSuite,
    EstadoEjecucion,
    EstadoItemCorrida,
    EstadoPasoSecuencia,
    FiltroHistorial,
    IntentoPasoSecuencia,
    ItemCorridaSuite,
    MAX_RETRIES_MINIMO,
    OPERACION_COMPRA,
    OPERACION_REVERSO_FINANCIERO,
    PasoCorridaSecuencia,
    PoliticaContinuacion,
    PasoSecuencia,
    ResultadoGlobalSuite,
    Secuencia,
    Suite,
    TarjetaPrueba,
)
from ...domain.proxy import (
    DireccionMensajeProxy,
    EstadoSesionProxy,
    MensajeProxyCapturado,
    MotivoCierreProxy,
    OrigenCapturaEscenario,
    SesionProxy,
)
from ...domain.reglas_host import (
    ComportamientoRegla,
    CondicionRegla,
    EstadoReglaHost,
    EventoReglaHost,
    ReglaHost,
    RespuestaRegla,
)
from .esquema import SECUENCIA_STAN, ruta_base_datos

#: Version del formato de `campos_json` en `escenarios`. Separado de
#: `application.serializacion.VERSION_FORMATO`: ese versiona un mensaje ISO ya
#: armado y enmascarado; este versiona una plantilla de campos editables sin
#: armar. Son formatos distintos y evolucionan por separado.
VERSION_CAMPOS_ESCENARIO = 1


class _RepositorioSQLite:
    """Base comun: guarda la ruta y abre conexiones con las mismas pragmas."""

    def __init__(self, ruta: Path | str | None = None) -> None:
        self._ruta = Path(ruta) if ruta is not None else ruta_base_datos()

    @property
    def ruta(self) -> Path:
        return self._ruta

    def _conectar(self) -> aiosqlite.Connection:
        return aiosqlite.connect(self._ruta)


class GeneradorStanSQLite(_RepositorioSQLite):
    """Secuencia persistente del numero de trazabilidad.

    ATOMICIDAD
    ==========
    Todo ocurre en **una sola sentencia**:

        UPDATE secuencias SET valor = (valor % :maximo) + 1
         WHERE nombre = 'stan'
        RETURNING valor

    SQLite ejecuta esa sentencia manteniendo el bloqueo de escritura de la base
    durante toda su duracion, de modo que la lectura del valor, su incremento y
    su escritura son indivisibles. Una segunda conexion que intente lo mismo al
    mismo tiempo **espera** al bloqueo (hasta el `busy timeout` del driver) y
    despues vuelve a leer el valor ya incrementado. Por eso dos compradores
    concurrentes no pueden obtener el mismo STAN.

    Lo que NO se hace, y es justamente el error que esto evita: un `SELECT valor`
    seguido de un `UPDATE` en sentencias separadas. Ahi ambas conexiones podrian
    leer el mismo valor antes de que ninguna escriba, y las dos entregarian el
    mismo STAN. Tampoco se usa `MAX(id)` de `ejecuciones`, que tiene el mismo
    defecto y ademas cuenta filas, no trazas.

    CICLO
    =====
    El modulo `%` hace que tras `999999` la secuencia vuelva a `000001`. Seis
    digitos no alcanzan para ser unicos indefinidamente: eso es propio del campo
    11 de ISO 8583, no de esta implementacion. Por la misma razon `ejecuciones`
    no lleva una restriccion `UNIQUE` sobre `stan`.
    """

    async def siguiente(self) -> str:
        async with self._conectar() as conexion:
            async with conexion.execute(
                "UPDATE secuencias SET valor = (valor % ?) + 1"
                " WHERE nombre = ? RETURNING valor",
                (STAN_MAXIMO, SECUENCIA_STAN),
            ) as cursor:
                fila = await cursor.fetchone()
            if fila is None:
                raise SecuenciaNoInicializada(
                    f"no existe la secuencia {SECUENCIA_STAN!r}: ejecute sibu-init-db"
                )
            await conexion.commit()
        return str(fila[0]).rjust(LARGO_STAN, "0")


class SecuenciaNoInicializada(RuntimeError):
    """La base existe pero le falta la fila de la secuencia."""


class RepositorioTarjetasSQLite(_RepositorioSQLite):
    """Catalogo de tarjetas de prueba.

    Unico repositorio que devuelve el PAN completo, porque sin el no se puede
    armar la transaccion. Los consumidores fuera del mantenimiento de tarjetas
    deben usar ``TarjetaPrueba.referencia()``.
    """

    async def obtener(self, card_id: str) -> TarjetaPrueba | None:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT card_id, pan, expiracion, descripcion, sintetica, activa,"
                "       titular, service_code, discretionary_data, cvv, cvv2, icvv,"
                "       card_sequence_number, pin_block_laboratorio"
                " FROM tarjetas_prueba WHERE card_id = ?",
                (card_id,),
            ) as cursor:
                fila = await cursor.fetchone()
        return _a_tarjeta(fila) if fila else None

    async def listar(self) -> Sequence[TarjetaPrueba]:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT card_id, pan, expiracion, descripcion, sintetica, activa,"
                "       titular, service_code, discretionary_data, cvv, cvv2, icvv,"
                "       card_sequence_number, pin_block_laboratorio"
                " FROM tarjetas_prueba ORDER BY card_id"
            ) as cursor:
                filas = await cursor.fetchall()
        return [_a_tarjeta(f) for f in filas]

    async def guardar(self, tarjeta: TarjetaPrueba) -> None:
        async with self._conectar() as conexion:
            await conexion.execute(
                "INSERT INTO tarjetas_prueba"
                " (card_id, pan, pan_enmascarado, expiracion, descripcion, sintetica, activa,"
                "  titular, service_code, discretionary_data, cvv, cvv2, icvv,"
                "  card_sequence_number, pin_block_laboratorio, creada_en)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(card_id) DO UPDATE SET"
                "   pan = excluded.pan,"
                "   pan_enmascarado = excluded.pan_enmascarado,"
                "   expiracion = excluded.expiracion,"
                "   descripcion = excluded.descripcion,"
                "   sintetica = excluded.sintetica,"
                "   activa = excluded.activa,"
                "   titular = excluded.titular,"
                "   service_code = excluded.service_code,"
                "   discretionary_data = excluded.discretionary_data,"
                "   cvv = excluded.cvv,"
                "   cvv2 = excluded.cvv2,"
                "   icvv = excluded.icvv,"
                "   card_sequence_number = excluded.card_sequence_number,"
                "   pin_block_laboratorio = excluded.pin_block_laboratorio",
                (
                    tarjeta.card_id,
                    tarjeta.pan,
                    tarjeta.pan_enmascarado,
                    tarjeta.expiracion,
                    tarjeta.descripcion,
                    int(tarjeta.sintetica),
                    int(tarjeta.activa),
                    tarjeta.titular,
                    tarjeta.service_code,
                    tarjeta.discretionary_data,
                    tarjeta.cvv,
                    tarjeta.cvv2,
                    tarjeta.icvv,
                    tarjeta.card_sequence_number,
                    tarjeta.pin_block_laboratorio,
                    datetime.now().astimezone().isoformat(),
                ),
            )
            await conexion.commit()


class RepositorioCatalogosSQLite(_RepositorioSQLite):
    async def catalogo_respuestas(self, nombre: str) -> CatalogoDeRespuestas:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT codigo, descripcion, aprobado FROM codigos_respuesta"
                " WHERE catalogo = ? ORDER BY codigo",
                (nombre,),
            ) as cursor:
                filas = await cursor.fetchall()
        return CatalogoDeRespuestas.desde(
            nombre,
            [
                CodigoRespuesta(f["codigo"], f["descripcion"], bool(f["aprobado"]))
                for f in filas
            ],
        )


class RepositorioEjecucionesSQLite(_RepositorioSQLite):
    """Historial de ejecuciones.

    Nunca escribe el PAN: la tarjeta se referencia por ``card_id`` y los mensajes
    llegan aqui ya enmascarados.
    """

    async def guardar(self, ejecucion: Ejecucion) -> int:
        async with self._conectar() as conexion:
            await conexion.execute("PRAGMA foreign_keys = ON")
            cursor = await conexion.execute(
                "INSERT INTO ejecuciones"
                " (creada_en, card_id, mti_solicitud, mti_respuesta, monto, moneda, stan,"
                "  destino_host, destino_puerto, estado, codigo_respuesta,"
                "  solicitud_enmascarada, respuesta_enmascarada,"
                "  solicitud_json, respuesta_json, latencia_ms,"
                "  escenario_id, escenario_nombre, evaluacion_estado, evaluacion_json,"
                "  motivo_detalle, ejecucion_origen_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ejecucion.creada_en.isoformat(),
                    ejecucion.card_id,
                    ejecucion.mti_solicitud,
                    ejecucion.mti_respuesta,
                    str(ejecucion.monto) if ejecucion.monto is not None else None,
                    ejecucion.moneda,
                    ejecucion.stan,
                    ejecucion.destino_host,
                    ejecucion.destino_puerto,
                    ejecucion.estado.value,
                    ejecucion.codigo_respuesta,
                    ejecucion.solicitud_enmascarada,
                    ejecucion.respuesta_enmascarada,
                    ejecucion.solicitud_json,
                    ejecucion.respuesta_json,
                    ejecucion.latencia_ms,
                    ejecucion.escenario_id,
                    ejecucion.escenario_nombre,
                    ejecucion.evaluacion_estado,
                    ejecucion.evaluacion_json,
                    ejecucion.motivo_detalle,
                    ejecucion.ejecucion_origen_id,
                ),
            )
            await conexion.commit()
            nuevo_id = cursor.lastrowid
        ejecucion.id = nuevo_id
        return nuevo_id

    async def obtener(self, id_ejecucion: int) -> Ejecucion | None:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT * FROM ejecuciones WHERE id = ?", (id_ejecucion,)
            ) as cursor:
                fila = await cursor.fetchone()
        return _a_ejecucion(fila) if fila else None

    async def listar(self, limite: int = 50) -> Sequence[Ejecucion]:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT * FROM ejecuciones ORDER BY id DESC LIMIT ?", (limite,)
            ) as cursor:
                filas = await cursor.fetchall()
        return [_a_ejecucion(f) for f in filas]

    async def listar_derivadas(self, ejecucion_origen_id: int) -> Sequence[Ejecucion]:
        """Todas las ejecuciones cuyo `ejecucion_origen_id` apunta a esta
        (B6, modelo de reversos): 1 origen -> N derivadas, nunca 1:1. Sin
        JOIN -cada fila ya es una `Ejecucion` completa por si misma, igual
        que cualquier otra lectura de este repositorio.
        """
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT * FROM ejecuciones WHERE ejecucion_origen_id = ? ORDER BY id ASC",
                (ejecucion_origen_id,),
            ) as cursor:
                filas = await cursor.fetchall()
        return [_a_ejecucion(f) for f in filas]

    async def buscar(
        self, filtro: FiltroHistorial, pagina: int, tam_pagina: int
    ) -> tuple[Sequence[Ejecucion], int]:
        """Filtra y pagina sobre `ejecuciones`. Ver `RepositorioEjecuciones.buscar`.

        El WHERE se arma con fragmentos fijos (nunca interpola el valor del
        usuario en el texto SQL: todo valor viaja como parametro) segun que
        criterios de `filtro` esten presentes -mismo principio que ya aplica
        `_leer_escenarios_de_suite` en la web: nunca se reinterpreta en
        silencio, y aqui nunca se concatena una entrada sin parametrizar.
        """
        condiciones: list[str] = []
        parametros: list[object] = []

        if filtro.desde:
            condiciones.append("date(creada_en) >= date(?)")
            parametros.append(filtro.desde)
        if filtro.hasta:
            condiciones.append("date(creada_en) <= date(?)")
            parametros.append(filtro.hasta)
        if filtro.estado is not None:
            condiciones.append("estado = ?")
            parametros.append(filtro.estado.value)
        if filtro.evaluacion == "sin_expectativas":
            condiciones.append("evaluacion_estado IS NULL")
        elif filtro.evaluacion in ("pass", "fail"):
            condiciones.append("evaluacion_estado = ?")
            parametros.append(filtro.evaluacion)
        if filtro.card_id:
            condiciones.append("card_id = ?")
            parametros.append(filtro.card_id)
        if filtro.destino:
            condiciones.append("(destino_host || ':' || COALESCE(destino_puerto, '')) LIKE ?")
            parametros.append(f"%{filtro.destino}%")
        if filtro.stan:
            condiciones.append("stan LIKE ?")
            parametros.append(f"%{filtro.stan}%")

        where = f" WHERE {' AND '.join(condiciones)}" if condiciones else ""

        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                f"SELECT COUNT(*) AS total FROM ejecuciones{where}", parametros
            ) as cursor:
                total = (await cursor.fetchone())["total"]

            desplazamiento = (pagina - 1) * tam_pagina
            async with conexion.execute(
                f"SELECT * FROM ejecuciones{where} ORDER BY id DESC LIMIT ? OFFSET ?",
                (*parametros, tam_pagina, desplazamiento),
            ) as cursor:
                filas = await cursor.fetchall()
        return [_a_ejecucion(f) for f in filas], total


class RepositorioDestinosSQLite(_RepositorioSQLite):
    """Catalogo de destinos de prueba administrados.

    Una ejecucion no referencia esta tabla: `Ejecucion.destino_host` y
    `destino_puerto` son valores propios, para que editar o desactivar un
    destino aqui no altere el historial ya registrado.
    """

    async def obtener(self, destino_id: str) -> DestinoGuardado | None:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT destino_id, nombre, host, puerto, activo, timeout, creado_en"
                " FROM destinos WHERE destino_id = ?",
                (destino_id,),
            ) as cursor:
                fila = await cursor.fetchone()
        return _a_destino(fila) if fila else None

    async def listar(self) -> Sequence[DestinoGuardado]:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT destino_id, nombre, host, puerto, activo, timeout, creado_en"
                " FROM destinos ORDER BY destino_id"
            ) as cursor:
                filas = await cursor.fetchall()
        return [_a_destino(f) for f in filas]

    async def guardar(self, destino: DestinoGuardado) -> None:
        async with self._conectar() as conexion:
            await conexion.execute(
                "INSERT INTO destinos (destino_id, nombre, host, puerto, activo, timeout, creado_en)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(destino_id) DO UPDATE SET"
                "   nombre = excluded.nombre,"
                "   host = excluded.host,"
                "   puerto = excluded.puerto,"
                "   activo = excluded.activo,"
                "   timeout = excluded.timeout",
                (
                    destino.destino_id,
                    destino.nombre,
                    destino.host,
                    destino.puerto,
                    int(destino.activo),
                    destino.timeout,
                    destino.creado_en.isoformat(),
                ),
            )
            await conexion.commit()


class RepositorioEscenariosSQLite(_RepositorioSQLite):
    """Catalogo de escenarios guardados: transacciones reutilizables.

    `campos_json` guarda la version propia de este repositorio (ver
    `VERSION_CAMPOS_ESCENARIO`), distinta de la de `application.serializacion`:
    una plantilla de campos editables sin armar, no un mensaje ISO transmitido.
    """

    async def obtener(self, escenario_id: str) -> Escenario | None:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT escenario_id, nombre, perfil, mti, operacion, card_id, conexion_id, monto,"
                "       campos_json, expected_json, activo, creado_en, actualizado_en"
                " FROM escenarios WHERE escenario_id = ?",
                (escenario_id,),
            ) as cursor:
                fila = await cursor.fetchone()
        return _a_escenario(fila) if fila else None

    async def listar(self) -> Sequence[Escenario]:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT escenario_id, nombre, perfil, mti, operacion, card_id, conexion_id, monto,"
                "       campos_json, expected_json, activo, creado_en, actualizado_en"
                " FROM escenarios ORDER BY nombre"
            ) as cursor:
                filas = await cursor.fetchall()
        return [_a_escenario(f) for f in filas]

    async def guardar(self, escenario: Escenario) -> None:
        async with self._conectar() as conexion:
            await conexion.execute("PRAGMA foreign_keys = ON")
            await conexion.execute(
                "INSERT INTO escenarios"
                " (escenario_id, nombre, perfil, mti, operacion, card_id, conexion_id, monto,"
                "  campos_json, expected_json, activo, creado_en, actualizado_en)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(escenario_id) DO UPDATE SET"
                "   nombre = excluded.nombre,"
                "   perfil = excluded.perfil,"
                "   mti = excluded.mti,"
                "   operacion = excluded.operacion,"
                "   card_id = excluded.card_id,"
                "   conexion_id = excluded.conexion_id,"
                "   monto = excluded.monto,"
                "   campos_json = excluded.campos_json,"
                "   expected_json = excluded.expected_json,"
                "   activo = excluded.activo,"
                "   actualizado_en = excluded.actualizado_en",
                (
                    escenario.escenario_id,
                    escenario.nombre,
                    escenario.perfil,
                    escenario.mti,
                    escenario.operacion,
                    escenario.card_id,
                    escenario.conexion_id,
                    str(escenario.monto) if escenario.monto is not None else None,
                    json.dumps(
                        {"version": VERSION_CAMPOS_ESCENARIO, "campos": dict(escenario.campos_manuales)},
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    (
                        json.dumps(
                            expectativas_a_dict(escenario.expectativas),
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        if escenario.expectativas is not None
                        else None
                    ),
                    int(escenario.activo),
                    escenario.creado_en.isoformat(),
                    escenario.actualizado_en.isoformat(),
                ),
            )
            await conexion.commit()


class RepositorioSuitesSQLite(_RepositorioSQLite):
    """Catalogo de suites: agrupaciones reutilizables de escenarios, en orden.

    `guardar` reemplaza entera la membresia (`suite_escenarios`) en la MISMA
    transaccion que el upsert de la fila de `suites` -DELETE + INSERT, nunca
    fusion con lo que ya estaba guardado-, igual criterio que ya aplica
    `ServicioEscenarios.actualizar` a `campos_manuales`/`expectativas`.
    """

    async def obtener(self, suite_id: str) -> Suite | None:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT suite_id, nombre, descripcion, activa, creado_en, actualizado_en"
                " FROM suites WHERE suite_id = ?",
                (suite_id,),
            ) as cursor:
                fila = await cursor.fetchone()
            if fila is None:
                return None
            escenarios = await self._escenarios_de(conexion, suite_id)
        return _a_suite(fila, escenarios)

    async def listar(self) -> Sequence[Suite]:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT suite_id, nombre, descripcion, activa, creado_en, actualizado_en"
                " FROM suites ORDER BY nombre"
            ) as cursor:
                filas = await cursor.fetchall()
            resultado = [
                _a_suite(fila, await self._escenarios_de(conexion, fila["suite_id"]))
                for fila in filas
            ]
        return resultado

    async def _escenarios_de(self, conexion: aiosqlite.Connection, suite_id: str) -> tuple[str, ...]:
        conexion.row_factory = aiosqlite.Row
        async with conexion.execute(
            "SELECT escenario_id FROM suite_escenarios WHERE suite_id = ? ORDER BY orden",
            (suite_id,),
        ) as cursor:
            filas = await cursor.fetchall()
        return tuple(f["escenario_id"] for f in filas)

    async def guardar(self, suite: Suite) -> None:
        async with self._conectar() as conexion:
            await conexion.execute("PRAGMA foreign_keys = ON")
            await conexion.execute(
                "INSERT INTO suites (suite_id, nombre, descripcion, activa, creado_en, actualizado_en)"
                " VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(suite_id) DO UPDATE SET"
                "   nombre = excluded.nombre,"
                "   descripcion = excluded.descripcion,"
                "   activa = excluded.activa,"
                "   actualizado_en = excluded.actualizado_en",
                (
                    suite.suite_id,
                    suite.nombre,
                    suite.descripcion,
                    int(suite.activa),
                    suite.creado_en.isoformat(),
                    suite.actualizado_en.isoformat(),
                ),
            )
            await conexion.execute(
                "DELETE FROM suite_escenarios WHERE suite_id = ?", (suite.suite_id,)
            )
            if suite.escenarios:
                await conexion.executemany(
                    "INSERT INTO suite_escenarios (suite_id, escenario_id, orden) VALUES (?, ?, ?)",
                    [
                        (suite.suite_id, escenario_id, orden)
                        for orden, escenario_id in enumerate(suite.escenarios, start=1)
                    ],
                )
            await conexion.commit()


class RepositorioCorridasSuiteSQLite(_RepositorioSQLite):
    """Historial de corridas de suite.

    Tres momentos de escritura, cada uno con su propia atomicidad: abrir con
    todos los items presembrados (una transaccion), actualizar un item a la
    vez segun se ejecuta su escenario (un commit por item, deliberadamente
    aislado del resto), y cerrar con los contadores finales (un UPDATE
    atomico). Ver `application.corredor_suites`.
    """

    async def crear_con_items(
        self, corrida: CorridaSuite, items: Sequence[ItemCorridaSuite]
    ) -> int:
        async with self._conectar() as conexion:
            await conexion.execute("PRAGMA foreign_keys = ON")
            cursor = await conexion.execute(
                "INSERT INTO corridas_suite"
                " (suite_id, suite_nombre, estado, resultado_global, total,"
                "  cantidad_pass, cantidad_fail, cantidad_error, cantidad_sin_expectativas,"
                "  cantidad_no_ejecutado, iniciada_en, finalizada_en)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    corrida.suite_id,
                    corrida.suite_nombre,
                    corrida.estado.value,
                    corrida.resultado_global.value if corrida.resultado_global else None,
                    corrida.total,
                    corrida.cantidad_pass,
                    corrida.cantidad_fail,
                    corrida.cantidad_error,
                    corrida.cantidad_sin_expectativas,
                    corrida.cantidad_no_ejecutado,
                    corrida.iniciada_en.isoformat(),
                    corrida.finalizada_en.isoformat() if corrida.finalizada_en else None,
                ),
            )
            corrida_id = cursor.lastrowid
            await conexion.executemany(
                "INSERT INTO corrida_suite_items"
                " (corrida_id, escenario_id, escenario_nombre, orden, resultado,"
                "  ejecucion_id, detalle, evaluacion_json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        corrida_id,
                        item.escenario_id,
                        item.escenario_nombre,
                        item.orden,
                        item.resultado.value,
                        item.ejecucion_id,
                        item.detalle,
                        item.evaluacion_json,
                    )
                    for item in items
                ],
            )
            await conexion.commit()
        corrida.corrida_id = corrida_id
        return corrida_id

    async def actualizar_item(self, item: ItemCorridaSuite) -> None:
        async with self._conectar() as conexion:
            # Este UPDATE puede escribir `ejecucion_id` (FK hacia `ejecuciones`):
            # sin esta pragma, una conexion nueva no hereda `foreign_keys=ON` de
            # ninguna otra conexion (es una propiedad por conexion, no del
            # archivo), y un id inexistente quedaria aceptado como referencia
            # huerfana. Mismo criterio que ya aplican `guardar()`/`crear_con_items()`.
            await conexion.execute("PRAGMA foreign_keys = ON")
            await conexion.execute(
                "UPDATE corrida_suite_items"
                " SET resultado = ?, ejecucion_id = ?, detalle = ?, evaluacion_json = ?"
                " WHERE corrida_id = ? AND orden = ?",
                (
                    item.resultado.value,
                    item.ejecucion_id,
                    item.detalle,
                    item.evaluacion_json,
                    item.corrida_id,
                    item.orden,
                ),
            )
            await conexion.commit()

    async def cerrar(self, corrida: CorridaSuite) -> None:
        async with self._conectar() as conexion:
            await conexion.execute(
                "UPDATE corridas_suite SET"
                "   estado = ?, resultado_global = ?, cantidad_pass = ?, cantidad_fail = ?,"
                "   cantidad_error = ?, cantidad_sin_expectativas = ?, cantidad_no_ejecutado = ?,"
                "   finalizada_en = ?"
                " WHERE corrida_id = ?",
                (
                    corrida.estado.value,
                    corrida.resultado_global.value if corrida.resultado_global else None,
                    corrida.cantidad_pass,
                    corrida.cantidad_fail,
                    corrida.cantidad_error,
                    corrida.cantidad_sin_expectativas,
                    corrida.cantidad_no_ejecutado,
                    corrida.finalizada_en.isoformat() if corrida.finalizada_en else None,
                    corrida.corrida_id,
                ),
            )
            await conexion.commit()

    async def obtener(self, corrida_id: int) -> CorridaSuite | None:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT * FROM corridas_suite WHERE corrida_id = ?", (corrida_id,)
            ) as cursor:
                fila = await cursor.fetchone()
        return _a_corrida(fila) if fila else None

    async def listar(self, limite: int = 50) -> Sequence[CorridaSuite]:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT * FROM corridas_suite ORDER BY corrida_id DESC LIMIT ?", (limite,)
            ) as cursor:
                filas = await cursor.fetchall()
        return [_a_corrida(f) for f in filas]

    async def listar_por_suite(self, suite_id: str, limite: int = 50) -> Sequence[CorridaSuite]:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT * FROM corridas_suite WHERE suite_id = ? ORDER BY corrida_id DESC LIMIT ?",
                (suite_id, limite),
            ) as cursor:
                filas = await cursor.fetchall()
        return [_a_corrida(f) for f in filas]

    async def obtener_items(self, corrida_id: int) -> Sequence[ItemCorridaSuite]:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT * FROM corrida_suite_items WHERE corrida_id = ? ORDER BY orden",
                (corrida_id,),
            ) as cursor:
                filas = await cursor.fetchall()
        return [_a_item(f) for f in filas]


class RepositorioSecuenciasSQLite(_RepositorioSQLite):
    """Catalogo de secuencias: pasos DEPENDIENTES, en orden (Fase C1).

    `guardar` reemplaza entera la lista de pasos (`secuencia_transaccional_
    pasos`) en la MISMA transaccion que el upsert de la fila de
    `secuencias_transaccionales` -DELETE + INSERT, nunca fusion-, mismo
    criterio que `RepositorioSuitesSQLite.guardar`.
    """

    async def obtener(self, secuencia_id: str) -> Secuencia | None:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT secuencia_id, nombre, descripcion, activa, creado_en, actualizado_en"
                " FROM secuencias_transaccionales WHERE secuencia_id = ?",
                (secuencia_id,),
            ) as cursor:
                fila = await cursor.fetchone()
            if fila is None:
                return None
            pasos = await self._pasos_de(conexion, secuencia_id)
        return _a_secuencia(fila, pasos)

    async def listar(self) -> Sequence[Secuencia]:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT secuencia_id, nombre, descripcion, activa, creado_en, actualizado_en"
                " FROM secuencias_transaccionales ORDER BY nombre"
            ) as cursor:
                filas = await cursor.fetchall()
            resultado = [
                _a_secuencia(fila, await self._pasos_de(conexion, fila["secuencia_id"]))
                for fila in filas
            ]
        return resultado

    async def _pasos_de(
        self, conexion: aiosqlite.Connection, secuencia_id: str
    ) -> tuple[PasoSecuencia, ...]:
        conexion.row_factory = aiosqlite.Row
        async with conexion.execute(
            "SELECT * FROM secuencia_transaccional_pasos WHERE secuencia_id = ? ORDER BY orden",
            (secuencia_id,),
        ) as cursor:
            filas = await cursor.fetchall()
        return tuple(_a_paso_secuencia(f) for f in filas)

    async def guardar(self, secuencia: Secuencia) -> None:
        async with self._conectar() as conexion:
            await conexion.execute("PRAGMA foreign_keys = ON")
            await conexion.execute(
                "INSERT INTO secuencias_transaccionales"
                " (secuencia_id, nombre, descripcion, activa, creado_en, actualizado_en)"
                " VALUES (?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(secuencia_id) DO UPDATE SET"
                "   nombre = excluded.nombre,"
                "   descripcion = excluded.descripcion,"
                "   activa = excluded.activa,"
                "   actualizado_en = excluded.actualizado_en",
                (
                    secuencia.secuencia_id,
                    secuencia.nombre,
                    secuencia.descripcion,
                    int(secuencia.activa),
                    secuencia.creado_en.isoformat(),
                    secuencia.actualizado_en.isoformat(),
                ),
            )
            await conexion.execute(
                "DELETE FROM secuencia_transaccional_pasos WHERE secuencia_id = ?",
                (secuencia.secuencia_id,),
            )
            if secuencia.pasos:
                await conexion.executemany(
                    "INSERT INTO secuencia_transaccional_pasos"
                    " (secuencia_id, orden, origen_tipo, escenario_id, origen_paso_orden,"
                    "  expectativas_json, paso_id, operacion_derivada, on_error, on_qa_fail,"
                    "  max_retries)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [
                        (
                            secuencia.secuencia_id,
                            paso.orden,
                            paso.origen_tipo,
                            paso.escenario_id,
                            paso.origen_paso_orden,
                            (
                                json.dumps(expectativas_a_dict(paso.expectativas))
                                if paso.expectativas
                                else None
                            ),
                            paso.paso_id,
                            paso.operacion_derivada,
                            paso.on_error,
                            paso.on_qa_fail,
                            paso.max_retries,
                        )
                        for paso in secuencia.pasos
                    ],
                )
            await conexion.commit()


class RepositorioCorridasSecuenciaSQLite(_RepositorioSQLite):
    """Historial de corridas de secuencia (Fase C1). Mismo patron de tres
    momentos de escritura que `RepositorioCorridasSuiteSQLite`. Ver
    `application.ejecutor_secuencia`.
    """

    async def crear_con_pasos(
        self, corrida: CorridaSecuencia, pasos: Sequence[PasoCorridaSecuencia]
    ) -> int:
        async with self._conectar() as conexion:
            await conexion.execute("PRAGMA foreign_keys = ON")
            cursor = await conexion.execute(
                "INSERT INTO corridas_secuencia"
                " (secuencia_id, secuencia_nombre, estado, resultado_global, total,"
                "  cantidad_pass, cantidad_fail, cantidad_error, cantidad_sin_expectativas,"
                "  cantidad_bloqueado, cantidad_no_ejecutado, iniciada_en, finalizada_en)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    corrida.secuencia_id,
                    corrida.secuencia_nombre,
                    corrida.estado.value,
                    corrida.resultado_global.value if corrida.resultado_global else None,
                    corrida.total,
                    corrida.cantidad_pass,
                    corrida.cantidad_fail,
                    corrida.cantidad_error,
                    corrida.cantidad_sin_expectativas,
                    corrida.cantidad_bloqueado,
                    corrida.cantidad_no_ejecutado,
                    corrida.iniciada_en.isoformat(),
                    corrida.finalizada_en.isoformat() if corrida.finalizada_en else None,
                ),
            )
            corrida_id = cursor.lastrowid
            await conexion.executemany(
                "INSERT INTO corrida_secuencia_pasos"
                " (corrida_id, orden, escenario_id, escenario_nombre, origen_tipo,"
                "  origen_paso_orden, resultado, ejecucion_id, detalle, evaluacion_json, paso_id)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        corrida_id,
                        paso.orden,
                        paso.escenario_id,
                        paso.escenario_nombre,
                        paso.origen_tipo,
                        paso.origen_paso_orden,
                        paso.resultado.value,
                        paso.ejecucion_id,
                        paso.detalle,
                        paso.evaluacion_json,
                        paso.paso_id,
                    )
                    for paso in pasos
                ],
            )
            await conexion.commit()
        corrida.corrida_id = corrida_id
        return corrida_id

    async def actualizar_paso(self, paso: PasoCorridaSecuencia) -> None:
        async with self._conectar() as conexion:
            # Este UPDATE puede escribir `ejecucion_id` (FK hacia `ejecuciones`):
            # mismo criterio que `RepositorioCorridasSuiteSQLite.actualizar_item`.
            await conexion.execute("PRAGMA foreign_keys = ON")
            await conexion.execute(
                "UPDATE corrida_secuencia_pasos"
                " SET resultado = ?, ejecucion_id = ?, detalle = ?, evaluacion_json = ?"
                " WHERE corrida_id = ? AND orden = ?",
                (
                    paso.resultado.value,
                    paso.ejecucion_id,
                    paso.detalle,
                    paso.evaluacion_json,
                    paso.corrida_id,
                    paso.orden,
                ),
            )
            await conexion.commit()

    async def cerrar(self, corrida: CorridaSecuencia) -> None:
        async with self._conectar() as conexion:
            await conexion.execute(
                "UPDATE corridas_secuencia SET"
                "   estado = ?, resultado_global = ?, cantidad_pass = ?, cantidad_fail = ?,"
                "   cantidad_error = ?, cantidad_sin_expectativas = ?, cantidad_bloqueado = ?,"
                "   cantidad_no_ejecutado = ?, finalizada_en = ?"
                " WHERE corrida_id = ?",
                (
                    corrida.estado.value,
                    corrida.resultado_global.value if corrida.resultado_global else None,
                    corrida.cantidad_pass,
                    corrida.cantidad_fail,
                    corrida.cantidad_error,
                    corrida.cantidad_sin_expectativas,
                    corrida.cantidad_bloqueado,
                    corrida.cantidad_no_ejecutado,
                    corrida.finalizada_en.isoformat() if corrida.finalizada_en else None,
                    corrida.corrida_id,
                ),
            )
            await conexion.commit()

    async def obtener(self, corrida_id: int) -> CorridaSecuencia | None:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT * FROM corridas_secuencia WHERE corrida_id = ?", (corrida_id,)
            ) as cursor:
                fila = await cursor.fetchone()
        return _a_corrida_secuencia(fila) if fila else None

    async def listar(self, limite: int = 50) -> Sequence[CorridaSecuencia]:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT * FROM corridas_secuencia ORDER BY corrida_id DESC LIMIT ?", (limite,)
            ) as cursor:
                filas = await cursor.fetchall()
        return [_a_corrida_secuencia(f) for f in filas]

    async def listar_por_secuencia(
        self, secuencia_id: str, limite: int = 50
    ) -> Sequence[CorridaSecuencia]:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT * FROM corridas_secuencia WHERE secuencia_id = ?"
                " ORDER BY corrida_id DESC LIMIT ?",
                (secuencia_id, limite),
            ) as cursor:
                filas = await cursor.fetchall()
        return [_a_corrida_secuencia(f) for f in filas]

    async def obtener_pasos(self, corrida_id: int) -> Sequence[PasoCorridaSecuencia]:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT * FROM corrida_secuencia_pasos WHERE corrida_id = ? ORDER BY orden",
                (corrida_id,),
            ) as cursor:
                filas = await cursor.fetchall()
        return [_a_paso_corrida_secuencia(f) for f in filas]

    async def registrar_intento(self, intento: IntentoPasoSecuencia) -> None:
        async with self._conectar() as conexion:
            await conexion.execute("PRAGMA foreign_keys = ON")
            await conexion.execute(
                "INSERT INTO corrida_secuencia_paso_intentos"
                " (corrida_id, orden, numero_intento, resultado, ejecucion_id, detalle, creado_en)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    intento.corrida_id,
                    intento.orden,
                    intento.numero_intento,
                    intento.resultado.value,
                    intento.ejecucion_id,
                    intento.detalle,
                    intento.creado_en.isoformat(),
                ),
            )
            await conexion.commit()

    async def obtener_intentos(self, corrida_id: int, orden: int) -> Sequence[IntentoPasoSecuencia]:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT * FROM corrida_secuencia_paso_intentos"
                " WHERE corrida_id = ? AND orden = ? ORDER BY numero_intento",
                (corrida_id, orden),
            ) as cursor:
                filas = await cursor.fetchall()
        return [_a_intento_paso_secuencia(f) for f in filas]


def _a_secuencia(fila: aiosqlite.Row, pasos: tuple[PasoSecuencia, ...]) -> Secuencia:
    return Secuencia(
        secuencia_id=fila["secuencia_id"],
        nombre=fila["nombre"],
        descripcion=fila["descripcion"],
        pasos=pasos,
        activa=bool(fila["activa"]),
        creado_en=datetime.fromisoformat(fila["creado_en"]),
        actualizado_en=datetime.fromisoformat(fila["actualizado_en"]),
    )


def _a_paso_secuencia(fila: aiosqlite.Row) -> PasoSecuencia:
    expectativas_json = _opcional(fila, "expectativas_json")
    # `operacion_derivada` (B8): la migracion siempre agrega la columna con
    # DEFAULT 'financial_reversal', asi que una fila real nunca la trae en
    # None -pero `_opcional` si puede devolver None contra una base que no
    # paso por `inicializar()` (mismo caso limite de las demas columnas
    # opcionales), y `PasoSecuencia` no acepta None para este campo.
    operacion_derivada = _opcional(fila, "operacion_derivada") or OPERACION_REVERSO_FINANCIERO
    # `on_error`/`on_qa_fail`/`max_retries` (C3): mismo caso limite que
    # `operacion_derivada` arriba -la migracion las agrega con DEFAULT, pero
    # `_opcional` puede devolver `None` contra una base que no paso por
    # `inicializar()`.
    on_error = _opcional(fila, "on_error") or PoliticaContinuacion.CONTINUAR.value
    on_qa_fail = _opcional(fila, "on_qa_fail") or PoliticaContinuacion.CONTINUAR.value
    max_retries = _opcional(fila, "max_retries")
    max_retries = max_retries if max_retries is not None else MAX_RETRIES_MINIMO
    return PasoSecuencia(
        orden=fila["orden"],
        origen_tipo=fila["origen_tipo"],
        escenario_id=_opcional(fila, "escenario_id"),
        origen_paso_orden=_opcional(fila, "origen_paso_orden"),
        expectativas=(
            expectativas_desde_dict(json.loads(expectativas_json)) if expectativas_json else None
        ),
        paso_id=_opcional(fila, "paso_id"),
        operacion_derivada=operacion_derivada,
        on_error=on_error,
        on_qa_fail=on_qa_fail,
        max_retries=max_retries,
    )


def _a_corrida_secuencia(fila: aiosqlite.Row) -> CorridaSecuencia:
    return CorridaSecuencia(
        corrida_id=fila["corrida_id"],
        secuencia_id=fila["secuencia_id"],
        secuencia_nombre=fila["secuencia_nombre"],
        total=fila["total"],
        estado=EstadoCorridaSuite(fila["estado"]),
        resultado_global=(
            ResultadoGlobalSuite(fila["resultado_global"]) if fila["resultado_global"] else None
        ),
        cantidad_pass=fila["cantidad_pass"],
        cantidad_fail=fila["cantidad_fail"],
        cantidad_error=fila["cantidad_error"],
        cantidad_sin_expectativas=fila["cantidad_sin_expectativas"],
        cantidad_bloqueado=fila["cantidad_bloqueado"],
        cantidad_no_ejecutado=fila["cantidad_no_ejecutado"],
        iniciada_en=datetime.fromisoformat(fila["iniciada_en"]),
        finalizada_en=(
            datetime.fromisoformat(fila["finalizada_en"]) if fila["finalizada_en"] else None
        ),
    )


def _a_paso_corrida_secuencia(fila: aiosqlite.Row) -> PasoCorridaSecuencia:
    return PasoCorridaSecuencia(
        corrida_id=fila["corrida_id"],
        orden=fila["orden"],
        origen_tipo=fila["origen_tipo"],
        resultado=EstadoPasoSecuencia(fila["resultado"]),
        escenario_id=_opcional(fila, "escenario_id"),
        escenario_nombre=_opcional(fila, "escenario_nombre"),
        origen_paso_orden=_opcional(fila, "origen_paso_orden"),
        ejecucion_id=fila["ejecucion_id"],
        detalle=fila["detalle"],
        evaluacion_json=fila["evaluacion_json"],
        paso_id=_opcional(fila, "paso_id"),
    )


def _a_intento_paso_secuencia(fila: aiosqlite.Row) -> IntentoPasoSecuencia:
    return IntentoPasoSecuencia(
        corrida_id=fila["corrida_id"],
        orden=fila["orden"],
        numero_intento=fila["numero_intento"],
        resultado=EstadoPasoSecuencia(fila["resultado"]),
        ejecucion_id=fila["ejecucion_id"],
        detalle=fila["detalle"],
        creado_en=datetime.fromisoformat(fila["creado_en"]),
    )


def _a_suite(fila: aiosqlite.Row, escenarios: tuple[str, ...]) -> Suite:
    return Suite(
        suite_id=fila["suite_id"],
        nombre=fila["nombre"],
        descripcion=fila["descripcion"],
        escenarios=escenarios,
        activa=bool(fila["activa"]),
        creado_en=datetime.fromisoformat(fila["creado_en"]),
        actualizado_en=datetime.fromisoformat(fila["actualizado_en"]),
    )


def _a_corrida(fila: aiosqlite.Row) -> CorridaSuite:
    return CorridaSuite(
        corrida_id=fila["corrida_id"],
        suite_id=fila["suite_id"],
        suite_nombre=fila["suite_nombre"],
        total=fila["total"],
        estado=EstadoCorridaSuite(fila["estado"]),
        resultado_global=(
            ResultadoGlobalSuite(fila["resultado_global"]) if fila["resultado_global"] else None
        ),
        cantidad_pass=fila["cantidad_pass"],
        cantidad_fail=fila["cantidad_fail"],
        cantidad_error=fila["cantidad_error"],
        cantidad_sin_expectativas=fila["cantidad_sin_expectativas"],
        cantidad_no_ejecutado=fila["cantidad_no_ejecutado"],
        iniciada_en=datetime.fromisoformat(fila["iniciada_en"]),
        finalizada_en=(
            datetime.fromisoformat(fila["finalizada_en"]) if fila["finalizada_en"] else None
        ),
    )


def _a_item(fila: aiosqlite.Row) -> ItemCorridaSuite:
    return ItemCorridaSuite(
        corrida_id=fila["corrida_id"],
        escenario_id=fila["escenario_id"],
        escenario_nombre=fila["escenario_nombre"],
        orden=fila["orden"],
        resultado=EstadoItemCorrida(fila["resultado"]),
        ejecucion_id=fila["ejecucion_id"],
        detalle=fila["detalle"],
        evaluacion_json=fila["evaluacion_json"],
    )


def _a_escenario(fila: aiosqlite.Row) -> Escenario:
    bruto = json.loads(fila["campos_json"]) if fila["campos_json"] else {}
    campos = bruto.get("campos", {}) if isinstance(bruto, dict) else {}
    expected_bruto = _opcional(fila, "expected_json")
    expectativas = expectativas_desde_dict(json.loads(expected_bruto)) if expected_bruto else None
    return Escenario(
        escenario_id=fila["escenario_id"],
        nombre=fila["nombre"],
        perfil=fila["perfil"],
        mti=fila["mti"],
        operacion=_opcional(fila, "operacion") or OPERACION_COMPRA,
        card_id=fila["card_id"],
        conexion_id=fila["conexion_id"],
        monto=Decimal(fila["monto"]) if fila["monto"] is not None else None,
        campos_manuales=campos,
        expectativas=expectativas,
        activo=bool(fila["activo"]),
        creado_en=datetime.fromisoformat(fila["creado_en"]),
        actualizado_en=datetime.fromisoformat(fila["actualizado_en"]),
    )


def _a_destino(fila: aiosqlite.Row) -> DestinoGuardado:
    return DestinoGuardado(
        destino_id=fila["destino_id"],
        nombre=fila["nombre"],
        host=fila["host"],
        puerto=fila["puerto"],
        activo=bool(fila["activo"]),
        timeout=fila["timeout"],
        creado_en=datetime.fromisoformat(fila["creado_en"]),
    )


def _a_tarjeta(fila: aiosqlite.Row) -> TarjetaPrueba:
    return TarjetaPrueba(
        card_id=fila["card_id"],
        pan=fila["pan"],
        expiracion=fila["expiracion"],
        descripcion=fila["descripcion"],
        sintetica=bool(fila["sintetica"]),
        activa=bool(fila["activa"]),
        titular=fila["titular"],
        service_code=fila["service_code"],
        discretionary_data=fila["discretionary_data"],
        cvv=fila["cvv"],
        cvv2=fila["cvv2"],
        icvv=fila["icvv"],
        card_sequence_number=fila["card_sequence_number"],
        pin_block_laboratorio=fila["pin_block_laboratorio"],
    )


def _opcional(fila: aiosqlite.Row, columna: str):
    """Lee una columna que puede no existir todavia en la base.

    Las columnas JSON se agregan por migracion. Si alguien ejecuta este codigo
    contra una base que no paso por `inicializar()`, la columna no esta y
    `fila[columna]` lanzaria. Devolver `None` deja la fila legible en lugar de
    convertir un historial antiguo en un error del servidor.
    """
    return fila[columna] if columna in fila.keys() else None


def _a_ejecucion(fila: aiosqlite.Row) -> Ejecucion:
    return Ejecucion(
        id=fila["id"],
        creada_en=datetime.fromisoformat(fila["creada_en"]),
        card_id=fila["card_id"],
        mti_solicitud=fila["mti_solicitud"],
        mti_respuesta=fila["mti_respuesta"],
        # None para una operacion sin monto (ej. 0800 Echo) -no un sentinel
        # inventado-: ver el comentario de la columna en esquema.py (DDL).
        monto=Decimal(fila["monto"]) if fila["monto"] is not None else None,
        moneda=fila["moneda"],
        stan=fila["stan"],
        destino_host=fila["destino_host"],
        destino_puerto=fila["destino_puerto"],
        estado=EstadoEjecucion(fila["estado"]),
        codigo_respuesta=fila["codigo_respuesta"],
        solicitud_enmascarada=fila["solicitud_enmascarada"],
        respuesta_enmascarada=fila["respuesta_enmascarada"],
        solicitud_json=_opcional(fila, "solicitud_json"),
        respuesta_json=_opcional(fila, "respuesta_json"),
        latencia_ms=fila["latencia_ms"],
        escenario_id=_opcional(fila, "escenario_id"),
        escenario_nombre=_opcional(fila, "escenario_nombre"),
        evaluacion_estado=_opcional(fila, "evaluacion_estado"),
        evaluacion_json=_opcional(fila, "evaluacion_json"),
        motivo_detalle=_opcional(fila, "motivo_detalle"),
        ejecucion_origen_id=_opcional(fila, "ejecucion_origen_id"),
    )


class RepositorioReglasHostSQLite(_RepositorioSQLite):
    """Catalogo de Reglas del Host Simulado (Fase D1). `condiciones_json`/
    `campos_adicionales_json` siguen el mismo criterio ya usado para
    `expectativas_json` en `secuencia_transaccional_pasos`: JSON en una
    columna para una estructura anidada que nunca se consulta por partes
    fuera de cargar la regla completa.
    """

    async def obtener(self, regla_id: str) -> ReglaHost | None:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT * FROM reglas_host WHERE regla_id = ?", (regla_id,)
            ) as cursor:
                fila = await cursor.fetchone()
        return _a_regla_host(fila) if fila else None

    async def listar(self) -> Sequence[ReglaHost]:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT * FROM reglas_host ORDER BY prioridad, nombre"
            ) as cursor:
                filas = await cursor.fetchall()
        return [_a_regla_host(f) for f in filas]

    async def guardar(self, regla: ReglaHost) -> None:
        ahora = datetime.now(timezone.utc).isoformat()
        async with self._conectar() as conexion:
            await conexion.execute(
                "INSERT INTO reglas_host"
                " (regla_id, nombre, prioridad, activa, condiciones_json, de39,"
                "  campos_adicionales_json, comportamiento_tipo, comportamiento_delay_ms,"
                "  max_aplicaciones, creado_en, actualizado_en)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(regla_id) DO UPDATE SET"
                "   nombre = excluded.nombre,"
                "   prioridad = excluded.prioridad,"
                "   activa = excluded.activa,"
                "   condiciones_json = excluded.condiciones_json,"
                "   de39 = excluded.de39,"
                "   campos_adicionales_json = excluded.campos_adicionales_json,"
                "   comportamiento_tipo = excluded.comportamiento_tipo,"
                "   comportamiento_delay_ms = excluded.comportamiento_delay_ms,"
                "   max_aplicaciones = excluded.max_aplicaciones,"
                "   actualizado_en = excluded.actualizado_en",
                (
                    regla.regla_id,
                    regla.nombre,
                    regla.prioridad,
                    int(regla.activa),
                    json.dumps([
                        {"campo": c.campo, "operador": c.operador, "valor": c.valor}
                        for c in regla.condiciones
                    ]),
                    regla.respuesta.de39,
                    json.dumps(dict(regla.respuesta.campos_adicionales)),
                    regla.comportamiento.tipo,
                    regla.comportamiento.delay_ms,
                    regla.max_aplicaciones,
                    ahora,
                    ahora,
                ),
            )
            await conexion.commit()


def _a_regla_host(fila: aiosqlite.Row) -> ReglaHost:
    condiciones = tuple(
        CondicionRegla(campo=c["campo"], operador=c["operador"], valor=c.get("valor"))
        for c in json.loads(fila["condiciones_json"])
    )
    return ReglaHost(
        regla_id=fila["regla_id"],
        nombre=fila["nombre"],
        prioridad=fila["prioridad"],
        activa=bool(fila["activa"]),
        condiciones=condiciones,
        respuesta=RespuestaRegla(
            de39=fila["de39"],
            campos_adicionales=json.loads(fila["campos_adicionales_json"]),
        ),
        comportamiento=ComportamientoRegla(
            tipo=fila["comportamiento_tipo"],
            delay_ms=fila["comportamiento_delay_ms"],
        ),
        max_aplicaciones=_opcional(fila, "max_aplicaciones"),
    )


class RepositorioEventosReglasHostSQLite(_RepositorioSQLite):
    """Evidencia, del lado del simulador, de que regla (o ninguna) goberno
    una respuesta real. Nunca guarda el valor de un campo del mensaje -solo
    que regla goberno, con que prioridad, y que respondio."""

    async def registrar(self, evento: EventoReglaHost) -> None:
        async with self._conectar() as conexion:
            await conexion.execute(
                "INSERT INTO reglas_host_eventos"
                " (regla_id, regla_nombre, prioridad, mti_solicitud, de39_respuesta,"
                "  comportamiento, delay_ms, match_number, creado_en)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    evento.regla_id,
                    evento.regla_nombre,
                    evento.prioridad,
                    evento.mti_solicitud,
                    evento.de39_respuesta,
                    evento.comportamiento,
                    evento.delay_ms,
                    evento.match_number,
                    evento.creado_en.isoformat(),
                ),
            )
            await conexion.commit()

    async def listar(self, limite: int = 50) -> Sequence[EventoReglaHost]:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT * FROM reglas_host_eventos ORDER BY evento_id DESC LIMIT ?", (limite,)
            ) as cursor:
                filas = await cursor.fetchall()
        return [_a_evento_regla_host(f) for f in filas]


def _a_evento_regla_host(fila: aiosqlite.Row) -> EventoReglaHost:
    return EventoReglaHost(
        evento_id=fila["evento_id"],
        regla_id=fila["regla_id"],
        regla_nombre=fila["regla_nombre"],
        prioridad=fila["prioridad"],
        mti_solicitud=fila["mti_solicitud"],
        de39_respuesta=fila["de39_respuesta"],
        comportamiento=fila["comportamiento"],
        delay_ms=fila["delay_ms"],
        match_number=_opcional(fila, "match_number"),
        creado_en=datetime.fromisoformat(fila["creado_en"]),
    )


class RepositorioEstadoReglasHostSQLite(_RepositorioSQLite):
    """Estado OPERACIONAL de una regla con `max_aplicaciones` (Fase D2):
    cuantas veces ya goberno. Deliberadamente separado del catalogo de
    reglas -ver docstring de `esquema.py::reglas_host_estado`.
    """

    async def obtener(self, regla_id: str) -> EstadoReglaHost | None:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT * FROM reglas_host_estado WHERE regla_id = ?", (regla_id,)
            ) as cursor:
                fila = await cursor.fetchone()
        return _a_estado_regla_host(fila) if fila else None

    async def incrementar_si_no_agotada(self, regla_id: str, max_aplicaciones: int) -> int | None:
        """Intenta consumir UNA aplicacion de la regla, respetando su
        limite, en UNA SOLA sentencia atomica -mismo espiritu que
        `GeneradorStanSQLite.siguiente()`: SQLite mantiene el bloqueo de
        escritura durante toda la sentencia, asi que dos conexiones
        concurrentes que compitan por la MISMA regla se serializan; nunca
        se hace un `SELECT` seguido de un `UPDATE` en pasos separados
        -ese es exactamente el error que este patron evita (punto 6 del
        checkpoint D2)-.

        Devuelve el nuevo `aplicaciones_consumidas` si esta invocacion
        consumio un cupo, o `None` si la regla ya estaba agotada -`None`
        NUNCA es un error, es la señal de "ya no es candidata".

        `INSERT ... ON CONFLICT DO UPDATE ... WHERE` cubre en una sola
        sentencia tanto la primera aplicacion (fila inexistente, se crea
        con `aplicaciones_consumidas=1`) como las siguientes (fila
        existente, se incrementa solo si `aplicaciones_consumidas <
        max_aplicaciones`); si la condicion del `WHERE` del `DO UPDATE`
        falla, SQLite no actualiza nada y `RETURNING` no devuelve fila.
        """
        ahora = datetime.now(timezone.utc).isoformat()
        async with self._conectar() as conexion:
            await conexion.execute("PRAGMA foreign_keys = ON")
            async with conexion.execute(
                "INSERT INTO reglas_host_estado (regla_id, aplicaciones_consumidas, actualizado_en)"
                " VALUES (?, 1, ?)"
                " ON CONFLICT(regla_id) DO UPDATE SET"
                "   aplicaciones_consumidas = aplicaciones_consumidas + 1,"
                "   actualizado_en = excluded.actualizado_en"
                " WHERE aplicaciones_consumidas < ?"
                " RETURNING aplicaciones_consumidas",
                (regla_id, ahora, max_aplicaciones),
            ) as cursor:
                fila = await cursor.fetchone()
            await conexion.commit()
        return fila[0] if fila else None

    async def reiniciar(self, regla_id: str) -> None:
        """Pone el contador en 0 -nunca borra la fila (para no perder
        `actualizado_en` como evidencia de que hubo un reset), nunca toca
        `reglas_host` (configuracion) ni `reglas_host_eventos` (auditoria
        historica, punto 8 del checkpoint D2)."""
        ahora = datetime.now(timezone.utc).isoformat()
        async with self._conectar() as conexion:
            await conexion.execute(
                "INSERT INTO reglas_host_estado (regla_id, aplicaciones_consumidas, actualizado_en)"
                " VALUES (?, 0, ?)"
                " ON CONFLICT(regla_id) DO UPDATE SET"
                "   aplicaciones_consumidas = 0,"
                "   actualizado_en = excluded.actualizado_en",
                (regla_id, ahora),
            )
            await conexion.commit()


def _a_estado_regla_host(fila: aiosqlite.Row) -> EstadoReglaHost:
    return EstadoReglaHost(
        regla_id=fila["regla_id"],
        aplicaciones_consumidas=fila["aplicaciones_consumidas"],
        actualizado_en=datetime.fromisoformat(fila["actualizado_en"]),
    )


class RepositorioSesionesProxySQLite(_RepositorioSQLite):
    """Sesiones del Proxy ISO 8583 (Fase E1). `crear` inserta la fila una
    sola vez (session_id como PK); `actualizar` es siempre un UPDATE de esa
    misma fila -una sesion nunca produce mas de una fila, sin importar
    cuantas veces cambie de estado."""

    async def crear(self, sesion: SesionProxy) -> None:
        async with self._conectar() as conexion:
            await conexion.execute(
                "INSERT INTO proxy_sesiones"
                " (session_id, cliente_host, cliente_puerto, upstream_host,"
                "  upstream_puerto, estado, motivo_cierre, inicio, fin)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    sesion.session_id,
                    sesion.cliente_host,
                    sesion.cliente_puerto,
                    sesion.upstream_host,
                    sesion.upstream_puerto,
                    sesion.estado.value,
                    sesion.motivo_cierre.value if sesion.motivo_cierre else None,
                    sesion.inicio.isoformat(),
                    sesion.fin.isoformat() if sesion.fin else None,
                ),
            )
            await conexion.commit()

    async def actualizar(self, sesion: SesionProxy) -> None:
        async with self._conectar() as conexion:
            await conexion.execute(
                "UPDATE proxy_sesiones SET estado = ?, motivo_cierre = ?, fin = ?"
                " WHERE session_id = ?",
                (
                    sesion.estado.value,
                    sesion.motivo_cierre.value if sesion.motivo_cierre else None,
                    sesion.fin.isoformat() if sesion.fin else None,
                    sesion.session_id,
                ),
            )
            await conexion.commit()

    async def obtener(self, session_id: str) -> SesionProxy | None:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT * FROM proxy_sesiones WHERE session_id = ?", (session_id,)
            ) as cursor:
                fila = await cursor.fetchone()
        return _a_sesion_proxy(fila) if fila else None

    async def listar(self, limite: int = 50) -> Sequence[SesionProxy]:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT * FROM proxy_sesiones ORDER BY inicio DESC LIMIT ?", (limite,)
            ) as cursor:
                filas = await cursor.fetchall()
        return [_a_sesion_proxy(f) for f in filas]


def _a_sesion_proxy(fila: aiosqlite.Row) -> SesionProxy:
    return SesionProxy(
        session_id=fila["session_id"],
        cliente_host=fila["cliente_host"],
        cliente_puerto=fila["cliente_puerto"],
        upstream_host=fila["upstream_host"],
        upstream_puerto=fila["upstream_puerto"],
        estado=EstadoSesionProxy(fila["estado"]),
        motivo_cierre=MotivoCierreProxy(fila["motivo_cierre"]) if fila["motivo_cierre"] else None,
        inicio=datetime.fromisoformat(fila["inicio"]),
        fin=datetime.fromisoformat(fila["fin"]) if fila["fin"] else None,
    )


class RepositorioMensajesProxySQLite(_RepositorioSQLite):
    """Metadata segura de los frames capturados por una sesion -nunca el
    payload (ver `domain.proxy.MensajeProxyCapturado`)."""

    async def registrar(self, mensaje: MensajeProxyCapturado) -> None:
        async with self._conectar() as conexion:
            await conexion.execute(
                "INSERT INTO proxy_mensajes"
                " (session_id, direccion, orden, longitud, mti, interpretable, creado_en,"
                "  stan, rrn)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    mensaje.session_id,
                    mensaje.direccion.value,
                    mensaje.orden,
                    mensaje.longitud,
                    mensaje.mti,
                    int(mensaje.interpretable),
                    mensaje.creado_en.isoformat(),
                    mensaje.stan,
                    mensaje.rrn,
                ),
            )
            await conexion.commit()

    async def listar_por_sesion(self, session_id: str) -> Sequence[MensajeProxyCapturado]:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT * FROM proxy_mensajes WHERE session_id = ? ORDER BY orden",
                (session_id,),
            ) as cursor:
                filas = await cursor.fetchall()
        return [_a_mensaje_proxy(f) for f in filas]


def _a_mensaje_proxy(fila: aiosqlite.Row) -> MensajeProxyCapturado:
    return MensajeProxyCapturado(
        mensaje_id=fila["mensaje_id"],
        session_id=fila["session_id"],
        direccion=DireccionMensajeProxy(fila["direccion"]),
        orden=fila["orden"],
        longitud=fila["longitud"],
        mti=fila["mti"],
        interpretable=bool(fila["interpretable"]),
        creado_en=datetime.fromisoformat(fila["creado_en"]),
        stan=_opcional(fila, "stan"),
        rrn=_opcional(fila, "rrn"),
    )


class RepositorioOrigenCapturaEscenarioSQLite(_RepositorioSQLite):
    """Trazabilidad de procedencia (Fase E2): de que sesion/mensaje del
    Proxy nacio un Escenario -tabla separada de `escenarios`."""

    async def registrar(self, origen: OrigenCapturaEscenario) -> None:
        async with self._conectar() as conexion:
            await conexion.execute(
                "INSERT INTO escenarios_origen_captura"
                " (escenario_id, session_id, mensaje_id_solicitud, mensaje_id_respuesta, creado_en)"
                " VALUES (?, ?, ?, ?, ?)",
                (
                    origen.escenario_id,
                    origen.session_id,
                    origen.mensaje_id_solicitud,
                    origen.mensaje_id_respuesta,
                    origen.creado_en.isoformat(),
                ),
            )
            await conexion.commit()

    async def obtener_por_escenario(self, escenario_id: str) -> OrigenCapturaEscenario | None:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT * FROM escenarios_origen_captura WHERE escenario_id = ?", (escenario_id,)
            ) as cursor:
                fila = await cursor.fetchone()
        if fila is None:
            return None
        return OrigenCapturaEscenario(
            escenario_id=fila["escenario_id"],
            session_id=fila["session_id"],
            mensaje_id_solicitud=fila["mensaje_id_solicitud"],
            mensaje_id_respuesta=_opcional(fila, "mensaje_id_respuesta"),
            creado_en=datetime.fromisoformat(fila["creado_en"]),
        )

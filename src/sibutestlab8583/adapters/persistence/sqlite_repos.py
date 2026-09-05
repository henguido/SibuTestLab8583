"""Repositorios SQLite sobre aiosqlite.

Implementan los puertos declarados en ``domain.puertos``. Es el unico lugar del
proyecto que sabe que la persistencia es SQLite: el dominio no lo conoce, y por
eso PostgreSQL podria sustituirlo sin tocar la logica de negocio.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Sequence

import aiosqlite

from ...domain.catalogo import CatalogoDeRespuestas, CodigoRespuesta
from ...domain.expectativas import expectativas_a_dict, expectativas_desde_dict
from ...domain.modelos import (
    LARGO_STAN,
    STAN_MAXIMO,
    DestinoGuardado,
    Ejecucion,
    Escenario,
    EstadoEjecucion,
    TarjetaPrueba,
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
                "  escenario_id, escenario_nombre, evaluacion_estado, evaluacion_json)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ejecucion.creada_en.isoformat(),
                    ejecucion.card_id,
                    ejecucion.mti_solicitud,
                    ejecucion.mti_respuesta,
                    str(ejecucion.monto),
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
                "SELECT escenario_id, nombre, perfil, mti, card_id, conexion_id, monto,"
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
                "SELECT escenario_id, nombre, perfil, mti, card_id, conexion_id, monto,"
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
                " (escenario_id, nombre, perfil, mti, card_id, conexion_id, monto,"
                "  campos_json, expected_json, activo, creado_en, actualizado_en)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(escenario_id) DO UPDATE SET"
                "   nombre = excluded.nombre,"
                "   perfil = excluded.perfil,"
                "   mti = excluded.mti,"
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
                    escenario.card_id,
                    escenario.conexion_id,
                    str(escenario.monto),
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
        card_id=fila["card_id"],
        conexion_id=fila["conexion_id"],
        monto=Decimal(fila["monto"]),
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
        monto=Decimal(fila["monto"]),
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
    )

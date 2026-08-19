"""Repositorios SQLite sobre aiosqlite.

Implementan los puertos declarados en ``domain.puertos``. Es el unico lugar del
proyecto que sabe que la persistencia es SQLite: el dominio no lo conoce, y por
eso PostgreSQL podria sustituirlo sin tocar la logica de negocio.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Sequence

import aiosqlite

from ...domain.catalogo import CatalogoDeRespuestas, CodigoRespuesta
from ...domain.modelos import (
    LARGO_STAN,
    STAN_MAXIMO,
    Ejecucion,
    EstadoEjecucion,
    TarjetaPrueba,
)
from .esquema import SECUENCIA_STAN, ruta_base_datos


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
                "SELECT card_id, pan, expiracion, descripcion, sintetica"
                " FROM tarjetas_prueba WHERE card_id = ?",
                (card_id,),
            ) as cursor:
                fila = await cursor.fetchone()
        return _a_tarjeta(fila) if fila else None

    async def listar(self) -> Sequence[TarjetaPrueba]:
        async with self._conectar() as conexion:
            conexion.row_factory = aiosqlite.Row
            async with conexion.execute(
                "SELECT card_id, pan, expiracion, descripcion, sintetica"
                " FROM tarjetas_prueba ORDER BY card_id"
            ) as cursor:
                filas = await cursor.fetchall()
        return [_a_tarjeta(f) for f in filas]

    async def guardar(self, tarjeta: TarjetaPrueba) -> None:
        async with self._conectar() as conexion:
            await conexion.execute(
                "INSERT INTO tarjetas_prueba"
                " (card_id, pan, pan_enmascarado, expiracion, descripcion, sintetica, creada_en)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(card_id) DO UPDATE SET"
                "   pan = excluded.pan,"
                "   pan_enmascarado = excluded.pan_enmascarado,"
                "   expiracion = excluded.expiracion,"
                "   descripcion = excluded.descripcion,"
                "   sintetica = excluded.sintetica",
                (
                    tarjeta.card_id,
                    tarjeta.pan,
                    tarjeta.pan_enmascarado,
                    tarjeta.expiracion,
                    tarjeta.descripcion,
                    int(tarjeta.sintetica),
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
                "  solicitud_enmascarada, respuesta_enmascarada, latencia_ms)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
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
                    ejecucion.latencia_ms,
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


def _a_tarjeta(fila: aiosqlite.Row) -> TarjetaPrueba:
    return TarjetaPrueba(
        card_id=fila["card_id"],
        pan=fila["pan"],
        expiracion=fila["expiracion"],
        descripcion=fila["descripcion"],
        sintetica=bool(fila["sintetica"]),
    )


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
        latencia_ms=fila["latencia_ms"],
    )

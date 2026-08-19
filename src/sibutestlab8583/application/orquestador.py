"""Orquestador del recorrido de compra 0100/0110.

Es la unica pieza que conoce a todas las demas, y las conoce **solo por sus
contratos**: no importa `aiosqlite`, ni `pyiso8583`, ni `asyncio.open_connection`.
Eso es lo que permitira que el motor de pruebas de carga reutilice transporte,
validacion y persistencia sin modificarlos.

Orden del recorrido, que no se altera:

    DatosCompra -> armar 0100 -> RN-4 -> codificar -> transporte
                -> TiempoAgotado?  -> RN-2: persistir timeout
                -> bytes?          -> decodificar -> RN-3 y RN-1 -> persistir
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from itertools import count
from typing import Callable

from ..domain.armado import armar_compra
from ..domain.catalogo import CatalogoDeRespuestas
from ..domain.errores import ErrorDeCodec
from ..domain.modelos import (
    CAMPOS_SENSIBLES,
    DatosCompra,
    DestinoTcp,
    Ejecucion,
    EstadoEjecucion,
    MensajeInterpretado,
    MensajeIso,
    ResultadoCompra,
    TiempoAgotado,
)
from ..domain.puertos import RepositorioEjecuciones, RepositorioTarjetas, Transporte
from ..domain.validacion import CAMPO_CODIGO_RESPUESTA, evaluar_respuesta, validar_envio

LARGO_STAN = 6


class TarjetaDesconocida(Exception):
    """El `card_id` no existe en el catalogo de tarjetas de prueba."""


class Orquestador:
    def __init__(
        self,
        *,
        codec,
        perfil,
        catalogo: CatalogoDeRespuestas,
        transporte: Transporte,
        repositorio_ejecuciones: RepositorioEjecuciones,
        repositorio_tarjetas: RepositorioTarjetas,
        destino: DestinoTcp,
        codigo_proceso: str,
        tiempo_limite: float | None = None,
        generador_stan: Callable[[], str] | None = None,
        reloj: Callable[[], datetime] | None = None,
    ) -> None:
        self._codec = codec
        self._perfil = perfil
        self._catalogo = catalogo
        self._transporte = transporte
        self._ejecuciones = repositorio_ejecuciones
        self._tarjetas = repositorio_tarjetas
        self._destino = destino
        self._codigo_proceso = codigo_proceso
        self._tiempo_limite = tiempo_limite
        self._stan = generador_stan or _contador_de_stan()
        self._reloj = reloj or (lambda: datetime.now(timezone.utc))

    async def ejecutar_compra(self, datos: DatosCompra) -> ResultadoCompra:
        tarjeta = await self._tarjetas.obtener(datos.card_id)
        if tarjeta is None:
            raise TarjetaDesconocida(f"no existe la tarjeta {datos.card_id!r}")

        momento = self._reloj()
        stan = self._stan()
        solicitud = armar_compra(
            datos,
            tarjeta,
            stan=stan,
            momento=momento,
            codigo_proceso=self._codigo_proceso,
        )

        # --- RN-4: si falta un obligatorio, no se codifica ni se envia ---
        validacion = validar_envio(solicitud, self._perfil)
        if not validacion:
            return await self._registrar(
                solicitud,
                stan,
                datos,
                EstadoEjecucion.NO_ENVIADA,
                motivos=validacion.motivos,
            )

        payload = self._codec.codificar(solicitud, self._perfil)

        inicio = time.monotonic()
        respuesta_cruda = await self._transporte.enviar(
            payload, self._destino, self._tiempo_limite
        )
        latencia_ms = int((time.monotonic() - inicio) * 1000)

        # --- RN-2: sin respuesta no hay nada que evaluar ---
        if isinstance(respuesta_cruda, TiempoAgotado):
            return await self._registrar(
                solicitud,
                stan,
                datos,
                EstadoEjecucion.TIMEOUT,
                motivos=(
                    f"sin respuesta en {respuesta_cruda.limite_segundos:g} s",
                ),
                latencia_ms=latencia_ms,
            )

        try:
            interpretada = self._codec.decodificar(respuesta_cruda, self._perfil)
        except ErrorDeCodec as error:
            return await self._registrar(
                solicitud,
                stan,
                datos,
                EstadoEjecucion.INVALIDA,
                motivos=(str(error),),
                latencia_ms=latencia_ms,
            )

        # --- RN-3 primero, luego RN-1 ---
        estado, motivos = evaluar_respuesta(
            solicitud, interpretada.como_mensaje(), self._catalogo, self._perfil
        )
        return await self._registrar(
            solicitud,
            stan,
            datos,
            estado,
            motivos=motivos,
            respuesta=interpretada,
            latencia_ms=latencia_ms,
        )

    async def _registrar(
        self,
        solicitud: MensajeIso,
        stan: str,
        datos: DatosCompra,
        estado: EstadoEjecucion,
        *,
        motivos: tuple[str, ...] = (),
        respuesta: MensajeInterpretado | None = None,
        latencia_ms: int | None = None,
    ) -> ResultadoCompra:
        """Construye la Ejecucion, la persiste enmascarada y devuelve el resultado."""
        enviado = estado is not EstadoEjecucion.NO_ENVIADA
        ejecucion = Ejecucion(
            card_id=datos.card_id,
            monto=datos.monto,
            moneda=datos.moneda,
            stan=stan,
            estado=estado,
            mti_solicitud=solicitud.mti,
            mti_respuesta=respuesta.mti if respuesta else None,
            codigo_respuesta=respuesta.valor(CAMPO_CODIGO_RESPUESTA) if respuesta else None,
            destino_host=self._destino.host if enviado else None,
            destino_puerto=self._destino.puerto if enviado else None,
            solicitud_enmascarada=_serializar(solicitud.enmascarado()),
            respuesta_enmascarada=(
                _serializar(respuesta.enmascarado().como_mensaje()) if respuesta else None
            ),
            latencia_ms=latencia_ms,
            creada_en=self._reloj(),
        )
        await self._ejecuciones.guardar(ejecucion)
        return ResultadoCompra(
            ejecucion=ejecucion,
            solicitud=solicitud.enmascarado(),
            respuesta=respuesta.enmascarado() if respuesta else None,
            motivos=tuple(motivos),
        )


def _serializar(mensaje: MensajeIso) -> str:
    """Texto legible de un mensaje YA enmascarado, para persistir y mostrar.

    Recibe siempre la version enmascarada; la comprobacion de abajo existe para
    que un cambio futuro no cuele un PAN completo a la base de datos.
    """
    partes = [f"MTI={mensaje.mti}"]
    for numero in sorted(mensaje.campos, key=int):
        valor = mensaje.campos[numero]
        if numero in CAMPOS_SENSIBLES and valor.isdigit():
            raise AssertionError(f"el campo {numero} llego sin enmascarar a la persistencia")
        partes.append(f"{numero}={valor}")
    return " | ".join(partes)


def _contador_de_stan() -> Callable[[], str]:
    """STAN incremental de seis digitos, unico dentro de una corrida."""
    secuencia = count(1)
    return lambda: str(next(secuencia) % 10**LARGO_STAN).rjust(LARGO_STAN, "0")

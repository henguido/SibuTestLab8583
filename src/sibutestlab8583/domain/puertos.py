"""Puertos del dominio.

El dominio define estos contratos; los adaptadores los implementan. La direccion
de dependencia va en un solo sentido: ningun modulo de dominio importa un
adaptador. Son asincronos por la decision registrada en ARQUITECTURA.md, para no
bloquear el event loop y para que el motor de carga los reutilice sin reescritura.
"""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from .catalogo import CatalogoDeRespuestas
from .modelos import (
    DestinoTcp,
    Ejecucion,
    FalloDeConexion,
    FalloDeTransmision,
    TarjetaPrueba,
    TiempoAgotado,
)


@runtime_checkable
class LectorDeStream(Protocol):
    """Lo minimo que el framing necesita de un stream para leer un mensaje.

    Se declara asi, y no como `asyncio.StreamReader`, para que el dominio no
    dependa de `asyncio`.
    """

    async def readexactly(self, n: int) -> bytes: ...


@runtime_checkable
class FramingStrategy(Protocol):
    """Delimita mensajes dentro de un stream.

    Su unico consumidor es el transporte. No interpreta ISO 8583: solo sabe
    donde empieza y donde termina un mensaje.
    """

    def preparar(self, payload: bytes) -> bytes:
        """Envuelve un payload opaco para transmitirlo."""
        ...

    async def leer_mensaje_completo(self, lector: LectorDeStream) -> bytes:
        """Lee del stream exactamente un mensaje y devuelve su payload."""
        ...


@runtime_checkable
class Transporte(Protocol):
    """Envia bytes opacos a un destino y espera una respuesta.

    No conoce ISO 8583. **Las condiciones de red no se propagan como excepciones**:
    se devuelven como resultado, para que el orquestador las registre igual que
    cualquier otro desenlace. Ninguna excepcion de `asyncio` ni ningun `OSError`
    cruza este contrato.

    CUATRO RESULTADOS
    =================
    Se distinguen por lo que cada uno permite **demostrar** sobre lo que llego al
    destino, no por la excepcion que los origino:

    - ``bytes``              llego una respuesta completa
    - ``TiempoAgotado``      la conexion se establecio, el drenaje del envio
                             termino, y no llego respuesta dentro del limite.
                             Esto, y solo esto, es RN-2
    - ``FalloDeConexion``    no se establecio la sesion TCP. Demostrable que nada
                             se transmitio, porque no hubo canal
    - ``FalloDeTransmision`` hubo sesion TCP y el intercambio quedo indeterminado.
                             **No** es demostrable que nada se transmitiera

    UNICA EXCEPCION QUE SI PUEDE SALIR
    ==================================
    `ErrorDeFraming` desde `FramingStrategy.preparar()`, que se ejecuta **antes**
    de abrir la conexion. No es una condicion de red: es un payload que no se
    puede enmarcar, y por eso ahi si es demostrable que nada se intento
    transmitir. El orquestador lo registra como un mensaje que no se envio.
    """

    async def enviar(
        self,
        payload: bytes,
        destino: DestinoTcp,
        tiempo_limite: float | None = None,
    ) -> bytes | TiempoAgotado | FalloDeConexion | FalloDeTransmision: ...


@runtime_checkable
class GeneradorStan(Protocol):
    """Entrega el siguiente numero de trazabilidad (campo 11).

    Es un puerto y no una funcion suelta porque la unicidad exige estado
    compartido y duradero: entre peticiones, entre peticiones concurrentes y
    entre reinicios. Un contador en memoria no puede darla, y el dominio no debe
    saber donde vive ese estado.
    """

    async def siguiente(self) -> str:
        """Devuelve un STAN de seis digitos, distinto del anterior."""
        ...


@runtime_checkable
class RepositorioTarjetas(Protocol):
    """Catalogo de tarjetas de prueba. Unico lugar que devuelve el PAN completo."""

    async def obtener(self, card_id: str) -> TarjetaPrueba | None: ...

    async def listar(self) -> Sequence[TarjetaPrueba]: ...

    async def guardar(self, tarjeta: TarjetaPrueba) -> None: ...


@runtime_checkable
class RepositorioCatalogos(Protocol):
    async def catalogo_respuestas(self, nombre: str) -> CatalogoDeRespuestas: ...


@runtime_checkable
class RepositorioEjecuciones(Protocol):
    async def guardar(self, ejecucion: Ejecucion) -> int: ...

    async def obtener(self, id_ejecucion: int) -> Ejecucion | None: ...

    async def listar(self, limite: int = 50) -> Sequence[Ejecucion]: ...

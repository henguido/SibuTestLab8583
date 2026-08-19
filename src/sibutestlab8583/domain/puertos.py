"""Puertos del dominio.

El dominio define estos contratos; los adaptadores los implementan. La direccion
de dependencia va en un solo sentido: ningun modulo de dominio importa un
adaptador. Son asincronos por la decision registrada en ARQUITECTURA.md, para no
bloquear el event loop y para que el motor de carga los reutilice sin reescritura.
"""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from .catalogo import CatalogoDeRespuestas
from .modelos import DestinoTcp, Ejecucion, TarjetaPrueba, TiempoAgotado


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

    No conoce ISO 8583. Devuelve `TiempoAgotado` en lugar de lanzar cuando el
    destino no responde: RN-2 lo trata como resultado, no como error.
    """

    async def enviar(
        self,
        payload: bytes,
        destino: DestinoTcp,
        tiempo_limite: float | None = None,
    ) -> bytes | TiempoAgotado: ...


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

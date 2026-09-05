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
    CorridaSuite,
    DestinoGuardado,
    DestinoTcp,
    Ejecucion,
    Escenario,
    FalloDeConexion,
    FalloDeTransmision,
    ItemCorridaSuite,
    Suite,
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


@runtime_checkable
class RepositorioDestinos(Protocol):
    """Catalogo de destinos de prueba administrados."""

    async def obtener(self, destino_id: str) -> DestinoGuardado | None: ...

    async def listar(self) -> Sequence[DestinoGuardado]: ...

    async def guardar(self, destino: DestinoGuardado) -> None: ...


@runtime_checkable
class RepositorioEscenarios(Protocol):
    """Catalogo de escenarios guardados: transacciones reutilizables."""

    async def obtener(self, escenario_id: str) -> Escenario | None: ...

    async def listar(self) -> Sequence[Escenario]: ...

    async def guardar(self, escenario: Escenario) -> None: ...


@runtime_checkable
class RepositorioSuites(Protocol):
    """Catalogo de suites guardadas: agrupaciones reutilizables de escenarios."""

    async def obtener(self, suite_id: str) -> Suite | None: ...

    async def listar(self) -> Sequence[Suite]: ...

    async def guardar(self, suite: Suite) -> None:
        """Reemplaza entera la suite y su membresia (`suite_escenarios`), en
        una sola transaccion: nunca fusiona con lo que ya estaba guardado.
        """
        ...


@runtime_checkable
class RepositorioCorridasSuite(Protocol):
    """Historial de corridas de suite. Escritura en tres momentos separados,
    cada uno su propia atomicidad (ver `application.corredor_suites`):
    abrir con todos los items presembrados, actualizar un item a la vez segun
    se ejecuta su escenario, y cerrar con los contadores y el resultado final.
    """

    async def crear_con_items(
        self, corrida: CorridaSuite, items: Sequence[ItemCorridaSuite]
    ) -> int:
        """Inserta la corrida y TODOS sus items (en NO_EJECUTADO) en una sola
        transaccion. Devuelve el `corrida_id` asignado.
        """
        ...

    async def actualizar_item(self, item: ItemCorridaSuite) -> None:
        """Sobrescribe el item `(corrida_id, orden)` con su resultado real.
        Se persiste de inmediato, item por item -no se agrupa con los demas-,
        para que un item ya corrido sobreviva aunque el proceso muera despues.
        """
        ...

    async def cerrar(self, corrida: CorridaSuite) -> None:
        """Un unico UPDATE atomico: estado, resultado_global, contadores y
        finalizada_en. Se llama una sola vez, al final.
        """
        ...

    async def obtener(self, corrida_id: int) -> CorridaSuite | None: ...

    async def listar(self, limite: int = 50) -> Sequence[CorridaSuite]: ...

    async def obtener_items(self, corrida_id: int) -> Sequence[ItemCorridaSuite]: ...


@runtime_checkable
class VerificadorDeConexion(Protocol):
    """Comprobacion TCP puntual de "Probar conexion", ajena al recorrido de compra.

    Deliberadamente mas angosto que `Transporte`: no envia bytes, no conoce
    framing ni ISO 8583, y no participa de ninguna regla de negocio. Un `bool`
    alcanza porque lo unico que hay que demostrar es si se pudo abrir un socket
    dentro del limite dado.
    """

    async def probar(self, host: str, puerto: int, tiempo_limite: float) -> bool: ...

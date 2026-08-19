"""Puertos del dominio.

El dominio define estos contratos; los adaptadores los implementan. La direccion
de dependencia va en un solo sentido: ningun modulo de dominio importa un
adaptador. Son asincronos por la decision registrada en ARQUITECTURA.md, para no
bloquear el event loop y para que el motor de carga los reutilice sin reescritura.
"""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from .catalogo import CatalogoDeRespuestas
from .modelos import Ejecucion, TarjetaPrueba


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

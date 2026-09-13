"""Administracion de secuencias: agrupaciones reutilizables de pasos
DEPENDIENTES, en orden (Fase C1).

SECUENCIA = agrupacion reusable de pasos (esta clase). CORRIDA DE SECUENCIA =
una ejecucion historica concreta de esa agrupacion (`application.
ejecutor_secuencia`). Este modulo administra la primera; la segunda es
responsabilidad exclusiva del ejecutor, que solo necesita `Secuencia.pasos`
para saber que ejecutar y en que orden.

`secuencia_id` es autogenerado y opaco, igual que `suite_id`/`escenario_id`.

C1 es deliberadamente minimo (punto 19 del checkpoint): solo `crear`/
`obtener`/`obtener_activa`/`listar`. Sin editar, duplicar ni desactivar
todavia -no hay evidencia de que haga falta antes de validar el motor con
la primera secuencia real (compra financiera -> reverso)-.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field
from typing import Sequence

from ..domain.modelos import (
    ORIGEN_PASO_DERIVADO,
    ORIGEN_PASO_INDEPENDIENTE,
    Expectativas,
    PasoSecuencia,
    Secuencia,
)
from ..domain.puertos import RepositorioEscenarios, RepositorioSecuencias

#: Prefijo legible del id autogenerado, igual criterio que `PREFIJO_SUITE_ID`.
PREFIJO_SECUENCIA_ID = "SEQ"


@dataclass(frozen=True)
class DatosPaso:
    """Lo que la pantalla de creacion de secuencias necesita por paso -antes
    de convertirse en `PasoSecuencia` (que ya exige la validacion completa
    de mutua exclusion entre `escenario_id`/`origen_paso_orden`)."""

    origen_tipo: str
    escenario_id: str | None = None
    origen_paso_orden: int | None = None
    expectativas: Expectativas | None = None


@dataclass(frozen=True)
class DatosNuevaSecuencia:
    nombre: str
    descripcion: str = ""
    pasos: Sequence[DatosPaso] = field(default_factory=tuple)


def _validar_nombre(nombre: str) -> str:
    nombre = (nombre or "").strip()
    if not nombre:
        raise ValueError("Indique un nombre para la secuencia.")
    return nombre


def _generar_secuencia_id() -> str:
    return f"{PREFIJO_SECUENCIA_ID}-{secrets.token_hex(4)}"


async def _validar_pasos(
    pasos: Sequence[DatosPaso], repositorio_escenarios: RepositorioEscenarios
) -> tuple[PasoSecuencia, ...]:
    """Cada paso se numera por su posicion (1-indexado) y se valida contra
    el catalogo real de escenarios -un paso independiente debe apuntar a un
    escenario que existe; un paso derivado debe apuntar a un `orden` ANTERIOR
    dentro de esta misma lista (nunca hacia adelante, nunca hacia si mismo:
    ambas reglas ya las exige `PasoSecuencia.__post_init__`, mas la de
    "anterior" se verifica aqui porque necesita ver la lista completa).
    """
    if not pasos:
        raise ValueError("Una secuencia necesita al menos un paso.")

    construidos: list[PasoSecuencia] = []
    for orden, datos in enumerate(pasos, start=1):
        if datos.origen_tipo == ORIGEN_PASO_INDEPENDIENTE:
            if not datos.escenario_id:
                raise ValueError(f"paso {orden}: indique un escenario.")
            if await repositorio_escenarios.obtener(datos.escenario_id) is None:
                raise ValueError(f"paso {orden}: no existe el escenario {datos.escenario_id!r}.")
        elif datos.origen_tipo == ORIGEN_PASO_DERIVADO:
            if datos.origen_paso_orden is None:
                raise ValueError(f"paso {orden}: indique de qué paso anterior deriva.")
            if not (1 <= datos.origen_paso_orden < orden):
                raise ValueError(
                    f"paso {orden}: solo puede derivar de un paso ANTERIOR de esta secuencia "
                    f"(1..{orden - 1})."
                )
        else:
            raise ValueError(f"paso {orden}: tipo de origen desconocido {datos.origen_tipo!r}.")

        construidos.append(
            PasoSecuencia(
                orden=orden,
                origen_tipo=datos.origen_tipo,
                escenario_id=datos.escenario_id if datos.origen_tipo == ORIGEN_PASO_INDEPENDIENTE else None,
                origen_paso_orden=(
                    datos.origen_paso_orden if datos.origen_tipo == ORIGEN_PASO_DERIVADO else None
                ),
                expectativas=datos.expectativas,
            )
        )
    return tuple(construidos)


class ServicioSecuencias:
    """Administracion de secuencias: listar, obtener, crear."""

    def __init__(
        self, repositorio: RepositorioSecuencias, repositorio_escenarios: RepositorioEscenarios
    ) -> None:
        self._secuencias = repositorio
        self._escenarios = repositorio_escenarios

    async def listar(self) -> Sequence[Secuencia]:
        return await self._secuencias.listar()

    async def obtener(self, secuencia_id: str) -> Secuencia | None:
        return await self._secuencias.obtener(secuencia_id)

    async def obtener_activa(self, secuencia_id: str) -> Secuencia | None:
        """Una secuencia, solo si existe y esta activa -mismo criterio que
        `ServicioSuites.obtener_activa`."""
        secuencia = await self._secuencias.obtener(secuencia_id)
        if secuencia is None or not secuencia.activa:
            return None
        return secuencia

    async def crear(self, datos: DatosNuevaSecuencia) -> Secuencia:
        nombre = _validar_nombre(datos.nombre)
        pasos = await _validar_pasos(datos.pasos, self._escenarios)
        secuencia = Secuencia(
            secuencia_id=_generar_secuencia_id(),
            nombre=nombre,
            descripcion=datos.descripcion,
            pasos=pasos,
        )
        await self._secuencias.guardar(secuencia)
        return secuencia

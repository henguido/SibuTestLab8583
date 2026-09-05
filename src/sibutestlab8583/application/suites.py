"""Administracion de suites: agrupaciones reutilizables de escenarios, en orden.

SUITE = agrupacion reusable de escenarios (esta clase). CORRIDA DE SUITE =
una ejecucion historica concreta de esa agrupacion (`application.corredor_suites`).
Este modulo administra la primera; la segunda es responsabilidad exclusiva del
corredor, que solo necesita `Suite.escenarios` para saber que ejecutar y en
que orden -no conoce nada de como se administran las suites.

`suite_id` es autogenerado y opaco, igual que `escenario_id`: el QA solo
escribe nombre y descripcion, nunca inventa un identificador tecnico.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field, replace
from typing import Sequence

from ..domain.modelos import Suite
from ..domain.puertos import RepositorioEscenarios, RepositorioSuites

#: Prefijo legible del id autogenerado, igual criterio que `PREFIJO_ESCENARIO_ID`.
PREFIJO_SUITE_ID = "SUI"


class SuiteNoEncontrada(Exception):
    """No existe una suite con el `suite_id` indicado."""


@dataclass(frozen=True)
class SuiteAdministrada:
    """Lo que la pantalla de suites y el constructor de suites necesitan."""

    suite_id: str
    nombre: str
    descripcion: str = ""
    escenarios: tuple[str, ...] = ()
    activa: bool = True


@dataclass(frozen=True)
class DatosNuevaSuite:
    nombre: str
    descripcion: str = ""
    escenarios: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class DatosEdicionSuite:
    nombre: str
    descripcion: str = ""
    escenarios: Sequence[str] = field(default_factory=tuple)


def _validar_nombre(nombre: str) -> str:
    nombre = (nombre or "").strip()
    if not nombre:
        raise ValueError("Indique un nombre para la suite.")
    return nombre


def _generar_suite_id() -> str:
    return f"{PREFIJO_SUITE_ID}-{secrets.token_hex(4)}"


async def _validar_escenarios(
    escenarios: Sequence[str], repositorio_escenarios: RepositorioEscenarios
) -> tuple[str, ...]:
    """Cada `escenario_id` referenciado debe existir. No exige que este activo
    -una suite puede guardar un escenario hoy inactivo; eso solo bloquea su
    ejecucion (`ERROR` en la corrida), no el guardado de la suite, mismo
    criterio que ya aplica un escenario con tarjeta inactiva.
    """
    vistos: set[str] = set()
    normalizados: list[str] = []
    for escenario_id in escenarios:
        if escenario_id in vistos:
            raise ValueError(f"el escenario {escenario_id!r} está repetido en la suite")
        vistos.add(escenario_id)
        if await repositorio_escenarios.obtener(escenario_id) is None:
            raise ValueError(f"no existe el escenario {escenario_id!r}")
        normalizados.append(escenario_id)
    return tuple(normalizados)


class ServicioSuites:
    """Administracion de suites: listar, buscar, crear, editar, duplicar, estado."""

    def __init__(
        self, repositorio: RepositorioSuites, repositorio_escenarios: RepositorioEscenarios
    ) -> None:
        self._suites = repositorio
        self._escenarios = repositorio_escenarios

    async def listar(self, *, buscar: str = "") -> Sequence[SuiteAdministrada]:
        suites = [_a_administrada(s) for s in await self._suites.listar()]
        if not buscar.strip():
            return suites
        objetivo = buscar.strip().lower()
        return [s for s in suites if objetivo in s.nombre.lower()]

    async def obtener(self, suite_id: str) -> SuiteAdministrada | None:
        suite = await self._suites.obtener(suite_id)
        return _a_administrada(suite) if suite else None

    async def obtener_activa(self, suite_id: str) -> SuiteAdministrada | None:
        """Una suite, solo si existe y esta activa. Mismo criterio que
        `ServicioEscenarios.obtener_activo`: una suite desactivada no debe
        poder dispararse con un click.
        """
        suite = await self._suites.obtener(suite_id)
        if suite is None or not suite.activa:
            return None
        return _a_administrada(suite)

    async def crear(self, datos: DatosNuevaSuite) -> SuiteAdministrada:
        nombre = _validar_nombre(datos.nombre)
        escenarios = await _validar_escenarios(datos.escenarios, self._escenarios)
        suite = Suite(
            suite_id=_generar_suite_id(),
            nombre=nombre,
            descripcion=datos.descripcion,
            escenarios=escenarios,
        )
        await self._suites.guardar(suite)
        return _a_administrada(suite)

    async def actualizar(self, suite_id: str, datos: DatosEdicionSuite) -> SuiteAdministrada:
        actual = await self._suites.obtener(suite_id)
        if actual is None:
            raise SuiteNoEncontrada(suite_id)

        nombre = _validar_nombre(datos.nombre)
        escenarios = await _validar_escenarios(datos.escenarios, self._escenarios)

        # "Guardar cambios" reemplaza entera la membresia -no la fusiona con
        # la anterior-, mismo criterio que ya aplica ServicioEscenarios.
        actualizado = replace(
            actual, nombre=nombre, descripcion=datos.descripcion, escenarios=escenarios
        )
        await self._suites.guardar(actualizado)
        return _a_administrada(actualizado)

    async def duplicar(self, suite_id: str) -> SuiteAdministrada:
        actual = await self._suites.obtener(suite_id)
        if actual is None:
            raise SuiteNoEncontrada(suite_id)
        copia = replace(
            actual,
            suite_id=_generar_suite_id(),
            nombre=f"{actual.nombre} (copia)",
            activa=True,
        )
        await self._suites.guardar(copia)
        return _a_administrada(copia)

    async def cambiar_estado(self, suite_id: str, *, activa: bool) -> SuiteAdministrada:
        actual = await self._suites.obtener(suite_id)
        if actual is None:
            raise SuiteNoEncontrada(suite_id)
        actualizada = replace(actual, activa=activa)
        await self._suites.guardar(actualizada)
        return _a_administrada(actualizada)


def _a_administrada(suite) -> SuiteAdministrada:
    return SuiteAdministrada(
        suite_id=suite.suite_id,
        nombre=suite.nombre,
        descripcion=suite.descripcion,
        escenarios=suite.escenarios,
        activa=suite.activa,
    )

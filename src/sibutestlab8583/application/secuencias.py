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
    OPERACION_REVERSO_FINANCIERO,
    Expectativas,
    PasoSecuencia,
    Secuencia,
)
from ..domain.puertos import RepositorioEscenarios, RepositorioSecuencias
from .variables_secuencia import paso_id_referenciado as _paso_id_referenciado

#: Prefijo legible del id autogenerado, igual criterio que `PREFIJO_SUITE_ID`.
PREFIJO_SECUENCIA_ID = "SEQ"


@dataclass(frozen=True)
class DatosPaso:
    """Lo que la pantalla de creacion de secuencias necesita por paso -antes
    de convertirse en `PasoSecuencia` (que ya exige la validacion completa
    de mutua exclusion entre `escenario_id`/`origen_paso_orden`).

    `paso_id` (C2) es opcional: si no se indica, `ServicioSecuencias` genera
    uno estable (`paso{N}`) -nunca lo deja vacio en lo que persiste-.

    `operacion_derivada` (B8) solo aplica a un paso derivado -ver
    `domain.modelos.PasoSecuencia`-, mismo default que alla
    (`OPERACION_REVERSO_FINANCIERO`) para no romper C1.
    """

    origen_tipo: str
    escenario_id: str | None = None
    origen_paso_orden: int | None = None
    expectativas: Expectativas | None = None
    paso_id: str | None = None
    operacion_derivada: str = OPERACION_REVERSO_FINANCIERO


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

    C2: ademas asigna/valida `paso_id` -unico dentro de la secuencia, y
    generado (`paso{N}`) si no se indico-, y valida CUALQUIER referencia de
    paso (`{{step.<id>...}}`, `application.variables_secuencia`) que el
    escenario de un paso independiente tenga guardada: el `paso_id`
    mencionado debe existir en esta secuencia y ser ESTRICTAMENTE ANTERIOR
    (punto 10/11 del checkpoint: rechazar referencias hacia adelante o
    circulares al GUARDAR la definicion, no en ejecucion).
    """
    if not pasos:
        raise ValueError("Una secuencia necesita al menos un paso.")

    ids_vistos: set[str] = set()
    paso_ids_por_orden: dict[int, str] = {}
    for orden, datos in enumerate(pasos, start=1):
        paso_id = datos.paso_id or f"paso{orden}"
        if paso_id in ids_vistos:
            raise ValueError(f"paso {orden}: el identificador {paso_id!r} ya se usó en esta secuencia.")
        ids_vistos.add(paso_id)
        paso_ids_por_orden[orden] = paso_id

    construidos: list[PasoSecuencia] = []
    for orden, datos in enumerate(pasos, start=1):
        if datos.origen_tipo == ORIGEN_PASO_INDEPENDIENTE:
            if not datos.escenario_id:
                raise ValueError(f"paso {orden}: indique un escenario.")
            escenario = await repositorio_escenarios.obtener(datos.escenario_id)
            if escenario is None:
                raise ValueError(f"paso {orden}: no existe el escenario {datos.escenario_id!r}.")
            _validar_referencias_de_paso(
                orden, escenario.campos_manuales, paso_ids_por_orden
            )
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
                paso_id=paso_ids_por_orden[orden],
                operacion_derivada=datos.operacion_derivada,
            )
        )
    return tuple(construidos)


def _validar_referencias_de_paso(
    orden_actual: int, campos_manuales, paso_ids_por_orden: dict[int, str]
) -> None:
    ordenes_por_paso_id = {v: k for k, v in paso_ids_por_orden.items()}
    for numero, valor in campos_manuales.items():
        referencia = _paso_id_referenciado(valor)
        if referencia is None:
            continue
        orden_origen = ordenes_por_paso_id.get(referencia)
        if orden_origen is None:
            raise ValueError(
                f"paso {orden_actual}: el campo {numero} referencia el paso "
                f"{referencia!r}, que no existe en esta secuencia."
            )
        if orden_origen >= orden_actual:
            raise ValueError(
                f"paso {orden_actual}: el campo {numero} referencia el paso "
                f"{referencia!r}, que no es un paso ANTERIOR."
            )


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

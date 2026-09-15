"""Administracion de Reglas del Host Simulado (Fase D1, 2026-09-14).

Mismo patron ya establecido por `application.escenarios`/`application.
secuencias`: `regla_id` autogenerado y opaco, `crear`/`actualizar`/
`duplicar`/`cambiar_estado`/`obtener`/`listar`. La validacion de dominio
(`domain.reglas_host.validar_regla`, campos sensibles prohibidos, DE39 con
la longitud correcta) se aplica SIEMPRE al crear/actualizar -nunca se
persiste una regla invalida, nunca se valida solo "a veces".
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from typing import Mapping, Sequence

from ..domain.reglas_host import (
    ComportamientoRegla,
    CondicionRegla,
    EstadoReglaHost,
    ReglaHost,
    RespuestaRegla,
    es_agotada,
    validar_regla,
)
from ..domain.puertos import RepositorioEstadoReglasHost, RepositorioReglasHost

PREFIJO_REGLA_ID = "RULE"


def _generar_regla_id() -> str:
    return f"{PREFIJO_REGLA_ID}-{secrets.token_hex(4)}"


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class DatosNuevaRegla:
    """Lo que la pantalla de creacion/edicion de una regla necesita -antes
    de convertirse en `ReglaHost` (que ya exige la validacion completa de
    forma; `validar_regla` exige ademas la validacion contra el perfil)."""

    nombre: str
    prioridad: int
    condiciones: Sequence[CondicionRegla]
    de39: str
    activa: bool = True
    campos_adicionales: Mapping[str, str] = field(default_factory=dict)
    comportamiento: ComportamientoRegla = field(default_factory=ComportamientoRegla)
    max_aplicaciones: int | None = None


class ReglaHostNoEncontrada(Exception):
    """No existe ninguna regla con ese `regla_id`."""


class ServicioReglasHost:
    """Administracion de Reglas del Host: listar, obtener, crear, editar,
    duplicar, activar/desactivar. Nunca evalua reglas contra un mensaje real
    -eso es `domain.reglas_host.evaluar_reglas`, invocado por
    `adapters.host_simulado.servidor.HostSimulado`, que solo necesita
    `listar()` para tener el conjunto vigente."""

    def __init__(
        self,
        repositorio: RepositorioReglasHost,
        perfil,
        repositorio_estado: RepositorioEstadoReglasHost | None = None,
    ) -> None:
        self._reglas = repositorio
        self._perfil = perfil
        self._estado = repositorio_estado

    async def listar(self) -> Sequence[ReglaHost]:
        return await self._reglas.listar()

    async def obtener(self, regla_id: str) -> ReglaHost | None:
        return await self._reglas.obtener(regla_id)

    async def crear(self, datos: DatosNuevaRegla) -> ReglaHost:
        regla = ReglaHost(
            nombre=_validar_nombre(datos.nombre),
            prioridad=datos.prioridad,
            activa=datos.activa,
            condiciones=tuple(datos.condiciones),
            respuesta=RespuestaRegla(de39=datos.de39, campos_adicionales=datos.campos_adicionales),
            comportamiento=datos.comportamiento,
            regla_id=_generar_regla_id(),
            max_aplicaciones=datos.max_aplicaciones,
        )
        validar_regla(regla, self._perfil)
        await self._reglas.guardar(regla)
        return regla

    async def actualizar(self, regla_id: str, datos: DatosNuevaRegla) -> ReglaHost:
        """Edita la configuracion de una regla existente. El CONTADOR
        operacional (si existe) se conserva siempre -editar nunca lo
        resetea, ni siquiera si el nuevo `max_aplicaciones` vuelve a la
        regla inmediatamente "agotada" con el contador ya acumulado: eso es
        una consecuencia legitima de la edicion, nunca una decision
        silenciosa (punto 11 del checkpoint D2) -el llamador (la ruta web)
        es quien decide si avisarlo, consultando `esta_agotada` despues de
        guardar."""
        actual = await self._reglas.obtener(regla_id)
        if actual is None:
            raise ReglaHostNoEncontrada(regla_id)
        actualizada = ReglaHost(
            nombre=_validar_nombre(datos.nombre),
            prioridad=datos.prioridad,
            activa=datos.activa,
            condiciones=tuple(datos.condiciones),
            respuesta=RespuestaRegla(de39=datos.de39, campos_adicionales=datos.campos_adicionales),
            comportamiento=datos.comportamiento,
            regla_id=regla_id,
            max_aplicaciones=datos.max_aplicaciones,
        )
        validar_regla(actualizada, self._perfil)
        await self._reglas.guardar(actualizada)
        return actualizada

    async def duplicar(self, regla_id: str) -> ReglaHost:
        """Copia la CONFIGURACION -incluido `max_aplicaciones`- pero NUNCA
        el estado operacional (punto 10 del checkpoint D2): la copia recibe
        un `regla_id` nuevo, que nunca tuvo fila en el repositorio de
        estado, asi que arranca en 0 consumidas sin necesitar ninguna
        llamada explicita al repositorio de estado."""
        actual = await self._reglas.obtener(regla_id)
        if actual is None:
            raise ReglaHostNoEncontrada(regla_id)
        copia = replace(actual, regla_id=_generar_regla_id(), nombre=f"{actual.nombre} (copia)")
        await self._reglas.guardar(copia)
        return copia

    async def cambiar_estado(self, regla_id: str, *, activa: bool) -> ReglaHost:
        """Activar/desactivar NUNCA toca el contador (punto 9 del
        checkpoint D2): son ortogonales -una regla desactivada simplemente
        deja de ser candidata (no consume matches), reactivarla la devuelve
        exactamente a donde estaba, contador incluido."""
        actual = await self._reglas.obtener(regla_id)
        if actual is None:
            raise ReglaHostNoEncontrada(regla_id)
        actualizada = replace(actual, activa=activa)
        await self._reglas.guardar(actualizada)
        return actualizada

    async def obtener_estado(self, regla_id: str) -> EstadoReglaHost | None:
        if self._estado is None:
            return None
        return await self._estado.obtener(regla_id)

    async def esta_agotada(self, regla: ReglaHost) -> bool:
        return es_agotada(regla, await self.obtener_estado(regla.regla_id) if regla.regla_id else None)

    async def reiniciar_contador(self, regla_id: str) -> ReglaHost:
        """Pone el contador de la regla en 0 -accion EXPLICITA, nunca
        implicita en un guardado o en activar/desactivar (punto 8 del
        checkpoint D2). Nunca borra auditoria historica (`reglas_host_
        eventos` no se toca)."""
        actual = await self._reglas.obtener(regla_id)
        if actual is None:
            raise ReglaHostNoEncontrada(regla_id)
        if self._estado is not None:
            await self._estado.reiniciar(regla_id)
        return actual


def _validar_nombre(nombre: str) -> str:
    nombre = (nombre or "").strip()
    if not nombre:
        raise ValueError("Indique un nombre para la regla.")
    return nombre

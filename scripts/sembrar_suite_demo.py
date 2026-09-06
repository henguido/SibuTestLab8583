"""Siembra (o reutiliza) UN escenario y UNA suite de nombre fijo, reservados
para demostraciones de CI, sobre una base ya inicializada con `sibu-init-db`
(que ya sembro `CARD_ID_DEMO`/`DESTINO_ID_DEMO`).

Idempotente por diseno: correrlo dos veces contra la MISMA base no duplica
nada -busca primero por nombre EXACTO y reutiliza si ya existe-. Si encuentra
mas de una coincidencia con un nombre reservado, se detiene con un mensaje
claro en vez de elegir una al azar: esa ambiguedad significa que algo ajeno ya
esta usando el nombre reservado, y tocarlo sin avisar violaria "no tocar
escenarios/suites ajenos".

No reimplementa nada de `ServicioEscenarios`/`ServicioSuites`: solo los llama,
igual que lo haria la interfaz web.

Salida: EXACTAMENTE una linea a stdout, `SUITE_ID=<id>`, para que un pipeline
la capture con una asignacion de variable simple, sin parsing adicional.
Cualquier progreso o error va a stderr.
"""

from __future__ import annotations

import asyncio
import sys
from decimal import Decimal

from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, DESTINO_ID_DEMO
from sibutestlab8583.application.escenarios import DatosNuevoEscenario, ServicioEscenarios
from sibutestlab8583.application.suites import DatosNuevaSuite, ServicioSuites
from sibutestlab8583.composicion import Composicion, Configuracion
from sibutestlab8583.domain.modelos import EstadoEjecucion, Expectativas

#: Nombres reservados de CI. Fijos a proposito -la idempotencia depende de
#: que sean siempre los mismos-: cualquier coincidencia se asume producida por
#: este mismo script en una corrida anterior, nunca por una persona.
NOMBRE_ESCENARIO_DEMO = "[CI] Escenario demo"
NOMBRE_SUITE_DEMO = "[CI] Suite demo"

#: Expectativa minima para que la suite sea una verificacion real, no un
#: SIN_EXPECTATIVAS: coincide con la politica de CI de "solo PASS = exito"
#: documentada en docs/ci/INTEGRACION_CI.md.
_EXPECTATIVA_DEMO = Expectativas(estado=EstadoEjecucion.APROBADA)


class AmbiguedadDeSiembra(Exception):
    """Existe mas de una coincidencia exacta con un nombre reservado de CI.

    Nunca se resuelve eligiendo una al azar: quien vea este error debe revisar
    el catalogo antes de reintentar -puede ser evidencia de que alguien creo
    manualmente algo con el mismo nombre reservado.
    """


async def _escenario_demo(servicio: ServicioEscenarios) -> str:
    coincidencias = [e for e in await servicio.listar() if e.nombre == NOMBRE_ESCENARIO_DEMO]
    if len(coincidencias) > 1:
        raise AmbiguedadDeSiembra(
            f"hay {len(coincidencias)} escenarios llamados {NOMBRE_ESCENARIO_DEMO!r}; "
            "no se elige ninguno al azar. Revise el catálogo antes de reintentar."
        )
    if coincidencias:
        return coincidencias[0].escenario_id

    creado = await servicio.crear(
        DatosNuevoEscenario(
            nombre=NOMBRE_ESCENARIO_DEMO,
            card_id=CARD_ID_DEMO,
            conexion_id=DESTINO_ID_DEMO,
            monto=Decimal("10.00"),
            expectativas=_EXPECTATIVA_DEMO,
        )
    )
    return creado.escenario_id


async def _suite_demo(servicio: ServicioSuites, escenario_id: str) -> str:
    coincidencias = [s for s in await servicio.listar() if s.nombre == NOMBRE_SUITE_DEMO]
    if len(coincidencias) > 1:
        raise AmbiguedadDeSiembra(
            f"hay {len(coincidencias)} suites llamadas {NOMBRE_SUITE_DEMO!r}; "
            "no se elige ninguna al azar. Revise el catálogo antes de reintentar."
        )
    if coincidencias:
        return coincidencias[0].suite_id

    creada = await servicio.crear(
        DatosNuevaSuite(nombre=NOMBRE_SUITE_DEMO, escenarios=(escenario_id,))
    )
    return creada.suite_id


async def sembrar(composicion: Composicion) -> str:
    """Devuelve el `suite_id` de la suite demo, reutilizada o recien creada."""
    escenario_id = await _escenario_demo(composicion.administracion_escenarios)
    return await _suite_demo(composicion.administracion_suites, escenario_id)


def main() -> int:
    composicion = Composicion(Configuracion.desde_entorno())
    try:
        suite_id = asyncio.run(sembrar(composicion))
    except (AmbiguedadDeSiembra, ValueError) as error:
        # ValueError: p.ej. no existe CARD_ID_DEMO/DESTINO_ID_DEMO porque la
        # base no se inicializo con `sibu-init-db` antes de correr este script.
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"SUITE_ID={suite_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

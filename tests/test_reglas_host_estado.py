"""Persistencia del estado operacional de una regla con `max_aplicaciones`
(Fase D2, 2026-09-14): incremento atomico, reset, y concurrencia real.
"""

from __future__ import annotations

import asyncio

from sibutestlab8583.adapters.persistence.sqlite_repos import (
    RepositorioEstadoReglasHostSQLite,
    RepositorioReglasHostSQLite,
)
from sibutestlab8583.application.reglas_host import DatosNuevaRegla, ServicioReglasHost
from sibutestlab8583.domain.reglas_host import CAMPO_MTI, CondicionRegla
from sibutestlab8583.profiles.generico import PERFIL_GENERICO


async def _crear_regla(base, *, max_aplicaciones=None):
    servicio = ServicioReglasHost(RepositorioReglasHostSQLite(base), PERFIL_GENERICO)
    return await servicio.crear(DatosNuevaRegla(
        nombre="R", prioridad=1,
        condiciones=[CondicionRegla(CAMPO_MTI, "igual", "0800")],
        de39="00", max_aplicaciones=max_aplicaciones,
    ))


async def test_incrementar_si_no_agotada_sin_fila_previa_crea_con_uno(base):
    regla = await _crear_regla(base, max_aplicaciones=3)
    estado_repo = RepositorioEstadoReglasHostSQLite(base)
    assert await estado_repo.obtener(regla.regla_id) is None
    resultado = await estado_repo.incrementar_si_no_agotada(regla.regla_id, 3)
    assert resultado == 1
    estado = await estado_repo.obtener(regla.regla_id)
    assert estado.aplicaciones_consumidas == 1


async def test_incrementar_si_no_agotada_respeta_el_limite(base):
    regla = await _crear_regla(base, max_aplicaciones=2)
    estado_repo = RepositorioEstadoReglasHostSQLite(base)
    assert await estado_repo.incrementar_si_no_agotada(regla.regla_id, 2) == 1
    assert await estado_repo.incrementar_si_no_agotada(regla.regla_id, 2) == 2
    # Tercer intento: ya agotada -> None, nunca supera el limite.
    assert await estado_repo.incrementar_si_no_agotada(regla.regla_id, 2) is None
    estado = await estado_repo.obtener(regla.regla_id)
    assert estado.aplicaciones_consumidas == 2


async def test_reiniciar_pone_el_contador_en_cero_sin_borrar_la_fila(base):
    regla = await _crear_regla(base, max_aplicaciones=1)
    estado_repo = RepositorioEstadoReglasHostSQLite(base)
    await estado_repo.incrementar_si_no_agotada(regla.regla_id, 1)
    assert (await estado_repo.obtener(regla.regla_id)).aplicaciones_consumidas == 1

    await estado_repo.reiniciar(regla.regla_id)
    estado = await estado_repo.obtener(regla.regla_id)
    assert estado.aplicaciones_consumidas == 0

    # Tras el reset, vuelve a poder consumir su cupo desde cero.
    assert await estado_repo.incrementar_si_no_agotada(regla.regla_id, 1) == 1


async def test_reiniciar_una_regla_sin_fila_previa_no_falla(base):
    regla = await _crear_regla(base, max_aplicaciones=1)
    estado_repo = RepositorioEstadoReglasHostSQLite(base)
    await estado_repo.reiniciar(regla.regla_id)  # nunca aplico, no debe lanzar
    estado = await estado_repo.obtener(regla.regla_id)
    assert estado.aplicaciones_consumidas == 0


async def test_concurrencia_real_solo_uno_consume_una_regla_de_limite_uno(base):
    """Punto 25 del checkpoint D2, el mas critico: N corrutinas concurrentes
    compitiendo por una regla con `max_aplicaciones=1` -SOLO UNA debe
    obtener un resultado distinto de `None`."""
    regla = await _crear_regla(base, max_aplicaciones=1)
    estado_repo = RepositorioEstadoReglasHostSQLite(base)

    resultados = await asyncio.gather(
        *[estado_repo.incrementar_si_no_agotada(regla.regla_id, 1) for _ in range(20)]
    )
    exitosos = [r for r in resultados if r is not None]
    assert len(exitosos) == 1
    assert exitosos[0] == 1
    estado = await estado_repo.obtener(regla.regla_id)
    assert estado.aplicaciones_consumidas == 1

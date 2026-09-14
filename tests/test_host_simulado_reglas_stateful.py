"""`HostSimulado` con reglas STATEFUL (`max_aplicaciones`, Fase D2,
2026-09-14). E2E real: TCP real, codec real, SQLite real, Orquestador
real -mismo estilo que `test_host_simulado_reglas.py` (D1).

Cubre los casos exigidos por el checkpoint: la prueba de fuego principal
(0800 timeout la primera vez, normal despues -totalmente automatico, sin
alternar nada desde la prueba-), agotamiento tras N coincidencias, reset,
concurrencia real, y compatibilidad D1 (una regla ilimitada nunca toca el
repositorio de estado).

Las reglas se persisten via `ServicioReglasHost.crear()` -nunca
construidas ad-hoc en memoria- porque `reglas_host_estado.regla_id` tiene
FK hacia `reglas_host`: el flujo real siempre lee reglas ya guardadas.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

from conftest import construir_orquestador
from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.sqlite_repos import (
    RepositorioEstadoReglasHostSQLite,
    RepositorioEventosReglasHostSQLite,
    RepositorioReglasHostSQLite,
)
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.adapters.transporte.tcp import TransporteTcp
from sibutestlab8583.application.reglas_host import DatosNuevaRegla, ServicioReglasHost
from sibutestlab8583.domain.modelos import DatosEcho, DestinoTcp, EstadoEjecucion
from sibutestlab8583.domain.reglas_host import (
    CAMPO_MTI,
    ComportamientoRegla,
    CondicionRegla,
    TipoComportamiento,
)
from sibutestlab8583.profiles.generico import PERFIL_GENERICO


def _host(**kwargs) -> HostSimulado:
    return HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), **kwargs)


async def _crear_regla(base, **kw):
    servicio = ServicioReglasHost(RepositorioReglasHostSQLite(base), PERFIL_GENERICO)
    return await servicio.crear(DatosNuevaRegla(
        condiciones=[CondicionRegla(CAMPO_MTI, "igual", "0800")],
        de39=kw.pop("de39", "00"), **kw,
    ))


async def _echo(host, base, tiempo_limite=2.0):
    transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=tiempo_limite)
    orquestador = construir_orquestador(
        base, transporte, destino=DestinoTcp(host=host.host, puerto=host.puerto),
        tiempo_limite=tiempo_limite,
    )
    return await orquestador.ejecutar_network_echo(DatosEcho())


async def test_primer_intento_timeout_segundo_intento_normal_totalmente_automatico(base):
    """La prueba de fuego del checkpoint D2: SIN alternar nada desde la
    prueba (a diferencia de C3/D1, que usaban `host._responder`/`activa`
    manualmente) -el propio motor de reglas, con `max_aplicaciones=1`,
    decide que la PRIMERA vez es TIMEOUT y la segunda cae al fallback
    NORMAL, automaticamente."""
    regla_timeout = await _crear_regla(
        base, nombre="Timeout primer intento", prioridad=10,
        comportamiento=ComportamientoRegla(tipo=TipoComportamiento.TIMEOUT.value),
        max_aplicaciones=1,
    )
    regla_fallback = await _crear_regla(base, nombre="Normal despues", prioridad=20)

    estado_repo = RepositorioEstadoReglasHostSQLite(base)
    eventos_repo = RepositorioEventosReglasHostSQLite(base)
    host = _host(
        reglas=[regla_timeout, regla_fallback],
        repositorio_estado=estado_repo,
        repositorio_eventos=eventos_repo,
    )
    async with host:
        r1 = await _echo(host, base, tiempo_limite=0.3)
        assert r1.estado is EstadoEjecucion.TIMEOUT

        r2 = await _echo(host, base, tiempo_limite=2.0)
        assert r2.estado is EstadoEjecucion.APROBADA

    eventos = sorted(await eventos_repo.listar(), key=lambda e: e.evento_id)
    assert eventos[0].regla_nombre == "Timeout primer intento"
    assert eventos[0].match_number == 1
    assert eventos[1].regla_nombre == "Normal despues"
    assert eventos[1].match_number is None  # regla ilimitada


async def test_agotamiento_tras_dos_coincidencias_cae_al_fallback(base):
    """Punto 23: max_aplicaciones=2, 3 mensajes -> 51, 51, fallback."""
    regla_rechazo = await _crear_regla(
        base, nombre="Rechazo limitado", prioridad=10, de39="51", max_aplicaciones=2,
    )
    regla_fallback = await _crear_regla(base, nombre="Fallback", prioridad=20)

    estado_repo = RepositorioEstadoReglasHostSQLite(base)
    host = _host(reglas=[regla_rechazo, regla_fallback], repositorio_estado=estado_repo)
    async with host:
        r1 = await _echo(host, base)
        r2 = await _echo(host, base)
        r3 = await _echo(host, base)
    assert r1.respuesta.valor("39") == "51"
    assert r2.respuesta.valor("39") == "51"
    assert r3.respuesta.valor("39") == "00"

    estado = await estado_repo.obtener(regla_rechazo.regla_id)
    assert estado.aplicaciones_consumidas == 2


async def test_reset_permite_que_la_regla_vuelva_a_aplicar_como_match_1(base):
    """Punto 24: tras agotar y resetear, el siguiente mensaje vuelve a
    contar como match #1."""
    regla = await _crear_regla(
        base, nombre="Rechazo con reset", prioridad=10, de39="51", max_aplicaciones=1,
    )
    estado_repo = RepositorioEstadoReglasHostSQLite(base)
    eventos_repo = RepositorioEventosReglasHostSQLite(base)
    host = _host(
        reglas=[regla], repositorio_estado=estado_repo, repositorio_eventos=eventos_repo
    )
    async with host:
        r1 = await _echo(host, base)
        assert r1.respuesta.valor("39") == "51"

        # Agotada: el fallback del HOST (sin otra regla) es el
        # comportamiento default -Echo siempre aprueba.
        r2 = await _echo(host, base)
        assert r2.respuesta.valor("39") == "00"

        await estado_repo.reiniciar(regla.regla_id)

        r3 = await _echo(host, base)
        assert r3.respuesta.valor("39") == "51"

    eventos = sorted(await eventos_repo.listar(), key=lambda e: e.evento_id)
    assert eventos[0].match_number == 1
    assert eventos[1].regla_nombre is None  # agotada, cayo al default
    assert eventos[2].match_number == 1  # tras el reset, vuelve a ser el primero


async def test_regla_ilimitada_nunca_toca_el_repositorio_de_estado(base):
    """Compatibilidad D1 (punto 18/33): una regla SIN `max_aplicaciones`
    nunca pasa por el repositorio de estado, ni siquiera si uno esta
    configurado."""
    regla = await _crear_regla(base, nombre="Ilimitada", prioridad=10)
    estado_repo = RepositorioEstadoReglasHostSQLite(base)
    host = _host(reglas=[regla], repositorio_estado=estado_repo)
    async with host:
        for _ in range(5):
            resultado = await _echo(host, base)
            assert resultado.estado is EstadoEjecucion.APROBADA
    assert await estado_repo.obtener(regla.regla_id) is None


async def test_concurrencia_real_contra_el_host_solo_un_echo_recibe_el_rechazo(base):
    """Punto 25, contra el HOST REAL (no solo el repositorio aislado, ver
    `test_reglas_host_estado.py`): 10 echos concurrentes reales contra una
    regla `max_aplicaciones=1` -exactamente UNO debe recibir DE39=51, los
    demas deben caer al fallback (echo siempre aprueba)."""
    regla = await _crear_regla(
        base, nombre="Rechazo unico", prioridad=10, de39="51", max_aplicaciones=1,
    )
    estado_repo = RepositorioEstadoReglasHostSQLite(base)
    host = _host(reglas=[regla], repositorio_estado=estado_repo)
    async with host:
        resultados = await asyncio.gather(*[_echo(host, base) for _ in range(10)])
    codigos = [r.respuesta.valor("39") for r in resultados]
    assert codigos.count("51") == 1
    assert codigos.count("00") == 9

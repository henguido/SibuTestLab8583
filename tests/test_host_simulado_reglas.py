"""`HostSimulado` con reglas declarativas (Fase D1, 2026-09-14). E2E real:
TCP real, codec real, SQLite real, Orquestador real -mismo estilo que
`test_compra_financiera_e2e.py`/`test_echo_e2e.py`.

Cubre: comportamiento default preservado sin reglas (punto 33), una regla
que gana produce la respuesta declarada, ninguna regla coincidente cae al
comportamiento default (fallback, punto 7), y los cuatro comportamientos
tecnicos (normal/delay/timeout/disconnect, puntos 12-14).
"""

from __future__ import annotations

import time
from decimal import Decimal

from conftest import construir_orquestador
from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO
from sibutestlab8583.adapters.persistence.sqlite_repos import RepositorioEventosReglasHostSQLite
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.adapters.transporte.tcp import TransporteTcp
from sibutestlab8583.domain.modelos import (
    DatosCompraFinanciera,
    DatosEcho,
    DestinoTcp,
    EstadoEjecucion,
    MTI_COMPRA_FINANCIERA,
)
from sibutestlab8583.domain.reglas_host import (
    CAMPO_MTI,
    ComportamientoRegla,
    CondicionRegla,
    ReglaHost,
    RespuestaRegla,
    TipoComportamiento,
)
from sibutestlab8583.profiles.generico import PERFIL_GENERICO


def _host(**kwargs) -> HostSimulado:
    return HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), **kwargs)


def _regla_rechazo_0200(prioridad=1, de39="51"):
    # DE4 viaja en UNIDADES MINIMAS (centavos, ver `domain.armado.
    # formatear_monto`): "50000" representa $500.00, nunca un literal de
    # dolares -un condicional "mayor_que" compara Decimal contra Decimal, y
    # el campo real siempre esta en centavos.
    return ReglaHost(
        nombre="Rechazo dinamico", prioridad=prioridad, activa=True,
        condiciones=(
            CondicionRegla(CAMPO_MTI, "igual", "0200"),
            CondicionRegla("4", "mayor_que", "50000"),
        ),
        respuesta=RespuestaRegla(de39=de39),
    )


async def test_sin_reglas_el_host_se_comporta_exactamente_igual_que_antes(base):
    """Punto 33: sin reglas personalizadas, la compra financiera sigue
    aprobando bajo el umbral sintetico, sin ningun cambio de codigo."""
    host = _host(reglas=None)
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        orquestador = construir_orquestador(
            base, transporte, destino=DestinoTcp(host=host.host, puerto=host.puerto),
            tiempo_limite=2.0,
        )
        resultado = await orquestador.ejecutar_compra_financiera(
            DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=Decimal("50.00"))
        )
    assert resultado.estado is EstadoEjecucion.APROBADA
    assert resultado.respuesta.valor("39") == "00"


async def test_una_regla_ganadora_gobierna_la_respuesta(base):
    """Punto 29 (E2E 1 - rechazo dinamico): una regla real, evaluada por el
    host real, decide un rechazo que el motor sintetico NO habria dado a
    este monto (por debajo del umbral hardcodeado, por encima del umbral de
    la regla)."""
    regla = _regla_rechazo_0200()
    host = _host(reglas=[regla])
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        orquestador = construir_orquestador(
            base, transporte, destino=DestinoTcp(host=host.host, puerto=host.puerto),
            tiempo_limite=2.0,
        )
        resultado = await orquestador.ejecutar_compra_financiera(
            DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=Decimal("600.00"))
        )
    assert resultado.estado is EstadoEjecucion.RECHAZADA
    assert resultado.respuesta.valor("39") == "51"


async def test_ninguna_regla_coincidente_cae_al_comportamiento_default(base):
    """Punto 7: con reglas configuradas pero NINGUNA coincide, el host
    responde con el comportamiento actual (fallback), nunca un error."""
    regla_echo = ReglaHost(
        nombre="Solo para echo", prioridad=1, activa=True,
        condiciones=(CondicionRegla(CAMPO_MTI, "igual", "0800"),),
        respuesta=RespuestaRegla(de39="00"),
    )
    host = _host(reglas=[regla_echo])
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        orquestador = construir_orquestador(
            base, transporte, destino=DestinoTcp(host=host.host, puerto=host.puerto),
            tiempo_limite=2.0,
        )
        resultado = await orquestador.ejecutar_compra_financiera(
            DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=Decimal("50.00"))
        )
    assert resultado.estado is EstadoEjecucion.APROBADA  # fallback: umbral sintetico de siempre


async def test_regla_inactiva_nunca_gana(base):
    regla_inactiva = _regla_rechazo_0200(prioridad=1)
    regla_inactiva = ReglaHost(
        nombre=regla_inactiva.nombre, prioridad=regla_inactiva.prioridad, activa=False,
        condiciones=regla_inactiva.condiciones, respuesta=regla_inactiva.respuesta,
    )
    host = _host(reglas=[regla_inactiva])
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        orquestador = construir_orquestador(
            base, transporte, destino=DestinoTcp(host=host.host, puerto=host.puerto),
            tiempo_limite=2.0,
        )
        resultado = await orquestador.ejecutar_compra_financiera(
            DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=Decimal("600.00"))
        )
    assert resultado.estado is EstadoEjecucion.APROBADA  # regla inactiva ignorada, cae al default


async def test_delay_real_produce_latencia_observable(base):
    """Punto 31 (E2E 3): no exige precision de milisegundos exacta, solo
    latencia observada coherente con lo declarado."""
    regla = ReglaHost(
        nombre="Echo lento", prioridad=1, activa=True,
        condiciones=(CondicionRegla(CAMPO_MTI, "igual", "0800"),),
        respuesta=RespuestaRegla(de39="00"),
        comportamiento=ComportamientoRegla(tipo=TipoComportamiento.DELAY.value, delay_ms=300),
    )
    host = _host(reglas=[regla])
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        orquestador = construir_orquestador(
            base, transporte, destino=DestinoTcp(host=host.host, puerto=host.puerto),
            tiempo_limite=2.0,
        )
        inicio = time.monotonic()
        resultado = await orquestador.ejecutar_network_echo(DatosEcho())
        duracion = time.monotonic() - inicio
    assert resultado.estado is EstadoEjecucion.APROBADA
    assert duracion >= 0.25  # tolerancia bajo 300ms declarados, sin exigir precision exacta


async def test_timeout_por_regla_produce_el_mismo_error_tecnico_que_responder_false(base):
    """Punto 30/32: TIMEOUT reutiliza el mecanismo YA EXISTENTE
    (`responder=False`/`_apagado`), asi que el cliente experimenta
    exactamente el mismo `TiempoAgotado` (RN-2)."""
    regla = ReglaHost(
        nombre="Echo timeout", prioridad=1, activa=True,
        condiciones=(CondicionRegla(CAMPO_MTI, "igual", "0800"),),
        respuesta=RespuestaRegla(de39="00"),
        comportamiento=ComportamientoRegla(tipo=TipoComportamiento.TIMEOUT.value),
    )
    host = _host(reglas=[regla])
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=0.2)
        orquestador = construir_orquestador(
            base, transporte, destino=DestinoTcp(host=host.host, puerto=host.puerto),
            tiempo_limite=0.2,
        )
        resultado = await orquestador.ejecutar_network_echo(DatosEcho())
    assert resultado.estado is EstadoEjecucion.TIMEOUT


async def test_disconnect_por_regla_es_distinto_de_timeout(base):
    """Punto 32/14: DISCONNECT cierra el socket de inmediato -el cliente ve
    la conexion cerrarse, un error tecnico DISTINTO de un timeout, si el
    transporte actual permite distinguirlo (si no, ambos caen igual en
    `TiempoAgotado`/`FalloDeTransmision`, pero nunca deben confundirse en el
    HOST: aqui se confirma que el host SI distingue el comportamiento)."""
    regla = ReglaHost(
        nombre="Echo disconnect", prioridad=1, activa=True,
        condiciones=(CondicionRegla(CAMPO_MTI, "igual", "0800"),),
        respuesta=RespuestaRegla(de39="00"),
        comportamiento=ComportamientoRegla(tipo=TipoComportamiento.DISCONNECT.value),
    )
    host = _host(reglas=[regla])
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=0.5)
        orquestador = construir_orquestador(
            base, transporte, destino=DestinoTcp(host=host.host, puerto=host.puerto),
            tiempo_limite=0.5,
        )
        resultado = await orquestador.ejecutar_network_echo(DatosEcho())
    # El socket se cierra antes de escribir nada: el cliente lo ve como una
    # falla de transmision/lectura -nunca un TIMEOUT (RN-2 exige que el envio
    # se haya completado Y no llegue nada dentro del plazo; aqui el cierre
    # es INMEDIATO, no un agotamiento de plazo).
    assert resultado.estado is not EstadoEjecucion.APROBADA
    assert resultado.estado is not EstadoEjecucion.TIMEOUT


async def test_los_eventos_de_reglas_quedan_auditables(base):
    """Punto 21: cada mensaje -con regla ganadora o sin ella- queda
    registrado del lado del simulador."""
    repo_eventos = RepositorioEventosReglasHostSQLite(base)
    regla = _regla_rechazo_0200()
    host = _host(reglas=[regla], repositorio_eventos=repo_eventos)
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        orquestador = construir_orquestador(
            base, transporte, destino=DestinoTcp(host=host.host, puerto=host.puerto),
            tiempo_limite=2.0,
        )
        await orquestador.ejecutar_compra_financiera(
            DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=Decimal("600.00"))
        )
        await orquestador.ejecutar_compra_financiera(
            DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=Decimal("10.00"))
        )
    eventos = await repo_eventos.listar()
    assert len(eventos) == 2
    con_regla = next(e for e in eventos if e.regla_nombre is not None)
    sin_regla = next(e for e in eventos if e.regla_nombre is None)
    assert con_regla.regla_nombre == "Rechazo dinamico"
    assert con_regla.de39_respuesta == "51"
    assert sin_regla.mti_solicitud == MTI_COMPRA_FINANCIERA

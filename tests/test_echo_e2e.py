"""E2E real de Network Management/Echo (0800/0810, B2): Orquestador real, TCP
real, host simulado real, codec real, SQLite real. Misma evidencia que ya
exige `test_integracion_end_to_end.py` para compra, aplicada a la segunda
operacion -la prueba de que el nucleo generico de B1 realmente sirve para
algo distinto de compra, no solo en el papel-.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import construir_orquestador
from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.sqlite_repos import RepositorioEjecucionesSQLite
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.adapters.transporte.tcp import TransporteTcp
from sibutestlab8583.domain.modelos import DatosEcho, DestinoTcp, EstadoEjecucion, MTI_ECHO, MTI_RESPUESTA_ECHO
from sibutestlab8583.profiles.generico import PERFIL_GENERICO, VALOR_LABORATORIO_ECHO


def _host(**kwargs) -> HostSimulado:
    return HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), **kwargs)


async def _ejecutar_echo_contra(host, base, datos_echo, *, tiempo_limite=2.0):
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=tiempo_limite)
        orquestador = construir_orquestador(
            base,
            transporte,
            destino=DestinoTcp(host=host.host, puerto=host.puerto),
            tiempo_limite=tiempo_limite,
        )
        return await orquestador.ejecutar_network_echo(datos_echo)


async def test_echo_completo_real_por_tcp(base):
    host = _host()
    resultado = await _ejecutar_echo_contra(host, base, DatosEcho())

    assert host.solicitudes_recibidas == 1, "el host simulado debio recibir el 0800"
    assert resultado.estado is EstadoEjecucion.APROBADA
    assert resultado.solicitud.mti == MTI_ECHO
    assert resultado.respuesta is not None
    assert resultado.respuesta.mti == MTI_RESPUESTA_ECHO
    assert resultado.respuesta.valor("39") == "00"
    assert resultado.motivos == ()


async def test_echo_correlaciona_stan_y_de70_entre_solicitud_y_respuesta(base):
    host = _host()
    resultado = await _ejecutar_echo_contra(host, base, DatosEcho())

    de11_solicitud = resultado.solicitud.campos.get("11")
    de11_respuesta = resultado.respuesta.valor("11")
    assert de11_solicitud == de11_respuesta
    assert resultado.respuesta.valor("70") == VALOR_LABORATORIO_ECHO


async def test_echo_persiste_sin_tarjeta_ni_monto_en_el_historial(base):
    host = _host()
    resultado = await _ejecutar_echo_contra(host, base, DatosEcho())

    guardadas = await RepositorioEjecucionesSQLite(base).listar()
    assert len(guardadas) == 1
    ejecucion = guardadas[0]
    assert ejecucion.card_id is None
    assert ejecucion.monto is None
    assert ejecucion.mti_solicitud == MTI_ECHO
    assert ejecucion.mti_respuesta == MTI_RESPUESTA_ECHO
    assert ejecucion.stan == resultado.ejecucion.stan
    assert ejecucion.latencia_ms is not None


async def test_echo_con_de70_personalizado_via_campos_manuales(base):
    host = _host()
    resultado = await _ejecutar_echo_contra(
        host, base, DatosEcho(campos_manuales={"70": "001"})
    )
    assert resultado.solicitud.campos.get("70") == "001"
    assert resultado.respuesta.valor("70") == "001"


async def test_echo_con_variable_dinamica_en_de70(base):
    """Demuestra que el mecanismo de variables (Fase A) es generico: no esta
    atado a compra, funciona igual para echo."""
    host = _host()
    resultado = await _ejecutar_echo_contra(
        host, base, DatosEcho(campos_manuales={"70": "{{stan}}"})
    )
    assert resultado.solicitud.campos.get("70") == resultado.solicitud.campos.get("11")


async def test_echo_no_reponde_produce_timeout(base):
    """RN-2 aplica igual que a compra: sin respuesta dentro del limite, el
    estado es TIMEOUT, no un estado inventado para echo."""
    host = _host(responder=False)
    resultado = await _ejecutar_echo_contra(host, base, DatosEcho(), tiempo_limite=0.2)
    assert resultado.estado is EstadoEjecucion.TIMEOUT

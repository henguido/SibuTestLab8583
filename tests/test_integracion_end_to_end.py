"""Recorrido completo, sin dobles de prueba.

Evidencia tecnica principal de esta iteracion: levanta el host simulado en un
puerto efimero y ejecuta la compra con codec real, framing real, transporte TCP
real y SQLite real, terminando en una ejecucion persistida.
"""

from __future__ import annotations

import sqlite3

import pytest

from conftest import construir_orquestador
from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.esquema import PAN_DEMO
from sibutestlab8583.adapters.persistence.sqlite_repos import RepositorioEjecucionesSQLite
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.adapters.transporte.tcp import TransporteTcp
from sibutestlab8583.domain.modelos import (
    MTI_RESPUESTA_COMPRA,
    DestinoTcp,
    EstadoEjecucion,
)
from sibutestlab8583.profiles.generico import PERFIL_GENERICO


async def _ejecutar_contra(host: HostSimulado, base, datos_compra, *, tiempo_limite=2.0):
    """Levanta el host, ejecuta una compra real por TCP y devuelve el resultado."""
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=tiempo_limite)
        orquestador = construir_orquestador(
            base,
            transporte,
            destino=DestinoTcp(host=host.host, puerto=host.puerto),
            tiempo_limite=tiempo_limite,
        )
        return await orquestador.ejecutar_compra(datos_compra)


def _host(**kwargs) -> HostSimulado:
    return HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), **kwargs)


async def test_recorrido_completo_aprobado(base, datos_compra):
    host = _host(codigo_respuesta="00")
    resultado = await _ejecutar_contra(host, base, datos_compra)

    assert host.solicitudes_recibidas == 1, "el host simulado debio recibir el 0100"
    assert resultado.estado is EstadoEjecucion.APROBADA
    assert resultado.aprobada
    assert resultado.respuesta is not None
    assert resultado.respuesta.mti == MTI_RESPUESTA_COMPRA
    assert resultado.respuesta.valor("39") == "00"
    assert resultado.motivos == ()

    guardadas = await RepositorioEjecucionesSQLite(base).listar()
    assert len(guardadas) == 1
    ejecucion = guardadas[0]
    assert ejecucion.estado is EstadoEjecucion.APROBADA
    assert ejecucion.codigo_respuesta == "00"
    assert ejecucion.mti_solicitud == "0100"
    assert ejecucion.mti_respuesta == MTI_RESPUESTA_COMPRA
    assert ejecucion.destino_host == host.host
    assert ejecucion.latencia_ms is not None


async def test_recorrido_completo_rechazado(base, datos_compra):
    resultado = await _ejecutar_contra(_host(codigo_respuesta="05"), base, datos_compra)
    assert resultado.estado is EstadoEjecucion.RECHAZADA
    assert resultado.ejecucion.codigo_respuesta == "05"
    assert any("05" in m for m in resultado.motivos)


async def test_recorrido_completo_timeout(base, datos_compra):
    """El host acepta la conexion y no responde. Limite corto, no diez segundos."""
    resultado = await _ejecutar_contra(
        _host(responder=False), base, datos_compra, tiempo_limite=0.3
    )
    assert resultado.estado is EstadoEjecucion.TIMEOUT
    assert resultado.respuesta is None

    guardadas = await RepositorioEjecucionesSQLite(base).listar()
    assert guardadas[0].estado is EstadoEjecucion.TIMEOUT
    assert guardadas[0].codigo_respuesta is None


async def test_falso_positivo_codigo_aprobado_con_correlacion_incorrecta(base, datos_compra):
    """PROYECTO.md seccion 7.6: el simulador no debe afirmar exito sin serlo.

    El host responde 00 pero con un STAN que no corresponde a la solicitud. Es
    una aprobacion que no es de esta transaccion, y debe registrarse INVALIDA.
    """
    host = _host(codigo_respuesta="00", campos_alterados={"11": "999999"})
    resultado = await _ejecutar_contra(host, base, datos_compra)

    assert resultado.estado is EstadoEjecucion.INVALIDA
    assert resultado.estado is not EstadoEjecucion.APROBADA
    assert not resultado.aprobada
    assert any("11" in m for m in resultado.motivos)

    guardadas = await RepositorioEjecucionesSQLite(base).listar()
    assert guardadas[0].estado is EstadoEjecucion.INVALIDA


async def test_un_fallo_de_conexion_es_un_error_y_no_un_timeout(base, datos_compra):
    """El transporte distingue no poder conectar de conectar y no recibir.

    Se fuerza el fallo con un host irresoluble porque es portable: no depende de
    como cada sistema operativo trate una conexion a un puerto cerrado. Ver la
    entrada correspondiente en BITACORA.md.
    """
    from sibutestlab8583.domain.errores import ErrorDeConexion

    transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=5.0)
    orquestador = construir_orquestador(
        base,
        transporte,
        destino=DestinoTcp(host="host-que-no-existe.sibutestlab.invalid", puerto=9),
    )
    with pytest.raises(ErrorDeConexion):
        await orquestador.ejecutar_compra(datos_compra)


async def test_lo_persistido_no_contiene_el_pan_completo(base, datos_compra):
    """La politica de PAN comprobada sobre el recorrido real, no en teoria."""
    await _ejecutar_contra(_host(codigo_respuesta="00"), base, datos_compra)

    with sqlite3.connect(base) as conexion:
        filas = conexion.execute("SELECT * FROM ejecuciones").fetchall()

    assert filas
    for fila in filas:
        for valor in fila:
            assert PAN_DEMO not in str(valor)

    guardada = (await RepositorioEjecucionesSQLite(base).listar())[0]
    assert "************" in guardada.solicitud_enmascarada
    assert PAN_DEMO not in guardada.solicitud_enmascarada

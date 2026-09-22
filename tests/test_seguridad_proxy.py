"""Seguridad del Proxy ISO 8583 transparente (Fase E1, 2026-09-21, punto 29
del encargo): el proxy recibe bytes REALES de un cliente -un PAN real
podria estar entre ellos, a diferencia del Host Simulado, que solo ve
mensajes que el genera- y sin embargo nunca persiste uno.

`MensajeProxyCapturado` es estructuralmente ciego (ver `test_proxy_
persistencia.py::test_mensaje_proxy_capturado_no_tiene_ningun_campo_para_
el_payload`); esta suite prueba el comportamiento de EXTREMO A EXTREMO -un
mensaje real con PAN cruza el proxy y ninguna fila de `proxy_sesiones`/
`proxy_mensajes` contiene una secuencia de 12-19 digitos-, con la MISMA
heuristica que ya protege el repositorio Git."""

from __future__ import annotations

import re
from decimal import Decimal

from conftest import construir_orquestador
from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO
from sibutestlab8583.adapters.persistence.sqlite_repos import (
    RepositorioMensajesProxySQLite,
    RepositorioSesionesProxySQLite,
)
from sibutestlab8583.adapters.proxy import ProxyIso8583
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.adapters.transporte.tcp import TransporteTcp
from sibutestlab8583.domain.modelos import DatosCompraFinanciera, DestinoTcp, EstadoEjecucion
from sibutestlab8583.profiles.generico import PERFIL_GENERICO

#: Misma heuristica que `test_datos_sinteticos.py`/`test_seguridad_reglas_
#: host_d2.py`: una secuencia de 12-19 digitos es indistinguible de un PAN
#: real -si aparece en una fila persistida, algo se filtro.
_PATRON_PAN = re.compile(r"\d{12,19}")


async def test_una_compra_financiera_real_cruza_el_proxy_sin_dejar_un_pan_persistido(base):
    """Prueba de extremo a extremo, no solo estructural: el DE2/DE4/DE14 de
    una 0200 real (con el PAN sintetico de la tarjeta demo) viaja por el
    proxy en RAW -el proxy los reenvia byte a byte-, y aun asi ninguna fila
    de `proxy_sesiones`/`proxy_mensajes` contiene la secuencia del PAN ni
    ninguna otra corrida de 12-19 digitos."""
    host = HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion())
    async with host:
        proxy = ProxyIso8583(
            FramingDemostracion(), DestinoTcp(host=host.host, puerto=host.puerto),
            codec=CodecIso8583(), perfil=PERFIL_GENERICO,
            repositorio_sesiones=RepositorioSesionesProxySQLite(base),
            repositorio_mensajes=RepositorioMensajesProxySQLite(base),
        )
        async with proxy:
            transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
            orquestador = construir_orquestador(
                base, transporte, destino=DestinoTcp(host=proxy.host, puerto=proxy.puerto),
                tiempo_limite=2.0,
            )
            resultado = await orquestador.ejecutar_compra_financiera(
                DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=Decimal("150.00"))
            )
    assert resultado.estado is EstadoEjecucion.APROBADA

    import sqlite3

    conexion = sqlite3.connect(str(base))
    try:
        filas_sesiones = conexion.execute(
            "SELECT session_id, cliente_host, upstream_host, estado, motivo_cierre"
            " FROM proxy_sesiones"
        ).fetchall()
        filas_mensajes = conexion.execute(
            "SELECT session_id, direccion, mti, interpretable, stan, rrn FROM proxy_mensajes"
        ).fetchall()
    finally:
        conexion.close()

    assert filas_mensajes, "la compra financiera debio capturar al menos un mensaje"
    for fila in (*filas_sesiones, *filas_mensajes):
        for valor in fila:
            if valor is not None:
                assert not _PATRON_PAN.search(str(valor)), f"posible PAN persistido: {valor!r}"


async def test_el_pump_nunca_decodifica_para_decidir_el_forwarding(base):
    """Punto 3 del encargo: prohibido decode->modificar->encode->enviar
    para reenviar. Prueba negativa: un `codec` que SIEMPRE falla al
    decodificar no debe impedir que el proxy reenvie el mismo mensaje ISO
    real igual de bien -el forwarding no puede depender de que el codec
    tenga exito."""
    from sibutestlab8583.domain.errores import ErrorDeDecodificacion

    class _CodecQueSiempreFalla:
        def decodificar(self, payload, perfil):
            raise ErrorDeDecodificacion("simulado: el forwarding no debe depender de esto")

    host = HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion())
    async with host:
        proxy = ProxyIso8583(
            FramingDemostracion(), DestinoTcp(host=host.host, puerto=host.puerto),
            codec=_CodecQueSiempreFalla(), perfil=PERFIL_GENERICO,
            repositorio_sesiones=RepositorioSesionesProxySQLite(base),
            repositorio_mensajes=RepositorioMensajesProxySQLite(base),
        )
        async with proxy:
            transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
            orquestador = construir_orquestador(
                base, transporte, destino=DestinoTcp(host=proxy.host, puerto=proxy.puerto),
                tiempo_limite=2.0,
            )
            from sibutestlab8583.domain.modelos import DatosEcho
            resultado = await orquestador.ejecutar_network_echo(DatosEcho())
    assert resultado.estado is EstadoEjecucion.APROBADA

    mensajes = await RepositorioMensajesProxySQLite(base).listar_por_sesion(
        (await RepositorioSesionesProxySQLite(base).listar())[0].session_id
    )
    assert mensajes and all(m.interpretable is False and m.mti is None for m in mensajes)


async def test_e2_1_stan_nunca_se_persiste_si_el_perfil_lo_marca_sensible(base):
    """Punto 3 del encargo E2.1: `perfil.es_sensible(DE)` es la UNICA
    autoridad -se vuelve a consultar en cada captura. Si un perfil (hoy
    hipotetico, mañana real) marcara DE11 como sensible, el proxy NUNCA
    debe persistirlo como correlador, aunque este en la whitelist de
    candidatos (`CAMPO_STAN`)."""
    import dataclasses

    from sibutestlab8583.adapters.proxy.servidor import CAMPO_STAN

    perfil_con_stan_sensible = dataclasses.replace(
        PERFIL_GENERICO, campos_sensibles=frozenset({CAMPO_STAN})
    )
    host = HostSimulado(CodecIso8583(), perfil_con_stan_sensible, FramingDemostracion())
    async with host:
        proxy = ProxyIso8583(
            FramingDemostracion(), DestinoTcp(host=host.host, puerto=host.puerto),
            codec=CodecIso8583(), perfil=perfil_con_stan_sensible,
            repositorio_sesiones=RepositorioSesionesProxySQLite(base),
            repositorio_mensajes=RepositorioMensajesProxySQLite(base),
        )
        async with proxy:
            transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
            orquestador = construir_orquestador(
                base, transporte, destino=DestinoTcp(host=proxy.host, puerto=proxy.puerto),
                tiempo_limite=2.0,
            )
            from sibutestlab8583.domain.modelos import DatosEcho
            # Marcar DE11 sensible tambien afecta la validacion RN-3 del
            # lado cliente (correlacion) -irrelevante para este test, que
            # solo verifica que el PROXY nunca persiste el correlador.
            await orquestador.ejecutar_network_echo(DatosEcho())

    mensajes = await RepositorioMensajesProxySQLite(base).listar_por_sesion(
        (await RepositorioSesionesProxySQLite(base).listar())[0].session_id
    )
    assert mensajes and all(m.stan is None for m in mensajes)

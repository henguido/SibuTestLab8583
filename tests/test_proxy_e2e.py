"""E2E reales del Proxy ISO 8583 transparente (Fase E1, 2026-09-21). Sin
dobles del nucleo: TCP real, `ProxyIso8583` real, `HostSimulado` real donde
aplica, SQLite real.

Los cinco escenarios del encargo (puntos 24-28):
  1. 0200 -> 0210 a traves del proxy, bytes preservados exactamente.
  2. 0800 -> 0810 a traves del proxy.
  3. Una regla D1/D2 del upstream (rechazo) atraviesa el proxy sin alterarse.
  4. El upstream desconecta -el proxy lo refleja limpio hacia el cliente.
  5. Un frame no interpretable como ISO 8583 cruza igual, sin bloquear el
     trafico -el proxy solo lo marca en la observabilidad.

`test_bytes_forwarding_es_exacto_en_ambos_sentidos` es la prueba
byte-for-byte obligatoria (punto 30): compara los bytes tal como los
recibio cada extremo, no los campos ISO ya interpretados.
"""

from __future__ import annotations

import asyncio
import socket
from decimal import Decimal

from conftest import construir_orquestador
from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO
from sibutestlab8583.adapters.persistence.sqlite_repos import (
    RepositorioMensajesProxySQLite,
    RepositorioReglasHostSQLite,
    RepositorioSesionesProxySQLite,
)
from sibutestlab8583.adapters.proxy import ProxyIso8583
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.adapters.transporte.tcp import TransporteTcp
from sibutestlab8583.application.reglas_host import DatosNuevaRegla, ServicioReglasHost
from sibutestlab8583.domain.modelos import DatosCompraFinanciera, DatosEcho, DestinoTcp, EstadoEjecucion
from sibutestlab8583.domain.proxy import DireccionMensajeProxy, MotivoCierreProxy
from sibutestlab8583.domain.reglas_host import CAMPO_MTI, CondicionRegla
from sibutestlab8583.profiles.generico import PERFIL_GENERICO


def _host(**kwargs) -> HostSimulado:
    return HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), **kwargs)


def _proxy(destino, base, **kwargs) -> ProxyIso8583:
    return ProxyIso8583(
        FramingDemostracion(), destino,
        codec=CodecIso8583(), perfil=PERFIL_GENERICO,
        repositorio_sesiones=RepositorioSesionesProxySQLite(base),
        repositorio_mensajes=RepositorioMensajesProxySQLite(base),
        **kwargs,
    )


async def _echo(base, host, puerto, tiempo_limite=2.0):
    transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=tiempo_limite)
    orquestador = construir_orquestador(
        base, transporte, destino=DestinoTcp(host=host, puerto=puerto), tiempo_limite=tiempo_limite,
    )
    return await orquestador.ejecutar_network_echo(DatosEcho())


async def _compra_financiera(base, host, puerto, monto="150.00", tiempo_limite=2.0):
    transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=tiempo_limite)
    orquestador = construir_orquestador(
        base, transporte, destino=DestinoTcp(host=host, puerto=puerto), tiempo_limite=tiempo_limite,
    )
    return await orquestador.ejecutar_compra_financiera(
        DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=Decimal(monto))
    )


async def test_0800_a_0810_a_traves_del_proxy(base):
    """Escenario 2 del encargo."""
    host = _host()
    async with host:
        proxy = _proxy(DestinoTcp(host=host.host, puerto=host.puerto), base)
        async with proxy:
            resultado = await _echo(base, proxy.host, proxy.puerto)
    assert resultado.estado is EstadoEjecucion.APROBADA


async def test_0200_a_0210_a_traves_del_proxy(base):
    """Escenario 1 del encargo (correccion funcional; la prueba byte-for-byte
    dedicada es `test_bytes_forwarding_es_exacto_en_ambos_sentidos`)."""
    host = _host()
    async with host:
        proxy = _proxy(DestinoTcp(host=host.host, puerto=host.puerto), base)
        async with proxy:
            resultado = await _compra_financiera(base, proxy.host, proxy.puerto)
    assert resultado.estado is EstadoEjecucion.APROBADA


async def test_regla_de_rechazo_del_upstream_atraviesa_el_proxy_sin_alterarse(base):
    """Escenario 3 del encargo: una regla D1/D2 real del upstream (rechazo
    DE39=51 para monto alto) debe verse IDENTICA del lado del cliente,
    cruzando el proxy -demuestra integracion Proxy + Host Rules."""
    servicio = ServicioReglasHost(RepositorioReglasHostSQLite(base), PERFIL_GENERICO)
    await servicio.crear(DatosNuevaRegla(
        nombre="Rechazo E1", prioridad=10,
        condiciones=[CondicionRegla(CAMPO_MTI, "igual", "0200")],
        de39="51",
    ))
    reglas = await servicio.listar()
    host = _host(reglas=reglas)
    async with host:
        proxy = _proxy(DestinoTcp(host=host.host, puerto=host.puerto), base)
        async with proxy:
            resultado = await _compra_financiera(base, proxy.host, proxy.puerto, monto="999999.00")
    assert resultado.estado is EstadoEjecucion.RECHAZADA
    assert resultado.respuesta.valor("39") == "51"


async def test_upstream_desconecta_se_refleja_limpio_hacia_el_cliente(base):
    """Escenario 4 del encargo: un upstream que acepta la conexion y la
    cierra sin responder nada -el proxy no debe colgarse ni sintetizar una
    respuesta; el cliente debe ver un fallo de transporte real."""
    async def _upstream_que_cierra(lector, escritor):
        escritor.close()

    servidor_falso = await asyncio.start_server(_upstream_que_cierra, "127.0.0.1", 0)
    host_falso, puerto_falso = servidor_falso.sockets[0].getsockname()
    async with servidor_falso:
        proxy = _proxy(DestinoTcp(host=host_falso, puerto=puerto_falso), base)
        async with proxy:
            resultado = await _echo(base, proxy.host, proxy.puerto, tiempo_limite=2.0)
    assert resultado.estado in (EstadoEjecucion.ERROR_TRANSMISION, EstadoEjecucion.ERROR_CONEXION)


async def test_upstream_caido_al_conectar_cierra_la_conexion_cliente_sin_colgarse(base):
    """Punto 11 del encargo: si el proxy no puede conectar al upstream,
    cierra la conexion-cliente (sin inventar una respuesta) y lo registra."""
    receptor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    receptor.bind(("127.0.0.1", 0))
    puerto_libre = receptor.getsockname()[1]
    receptor.close()  # nadie escucha ahi -conexion rechazada real, no un doble

    proxy = _proxy(
        DestinoTcp(host="127.0.0.1", puerto=puerto_libre), base, tiempo_limite_conexion=1.0,
    )
    async with proxy:
        resultado = await _echo(base, proxy.host, proxy.puerto, tiempo_limite=5.0)
    assert resultado.estado in (EstadoEjecucion.ERROR_TRANSMISION, EstadoEjecucion.ERROR_CONEXION)

    sesiones = await RepositorioSesionesProxySQLite(base).listar()
    assert any(s.motivo_cierre is MotivoCierreProxy.FALLO_CONEXION_UPSTREAM for s in sesiones)


async def test_mensaje_no_interpretable_atraviesa_sin_bloquear_el_trafico(base):
    """Escenario 5 del encargo: bytes que no decodifican como ISO 8583
    cruzan el proxy igual (comparados byte a byte), y quedan marcados
    `interpretable=False` en la observabilidad -nunca se descartan."""
    recibido_por_stub = []

    async def _stub_no_iso(lector, escritor):
        crudo = await FramingDemostracion().leer_mensaje_completo(lector)
        recibido_por_stub.append(crudo)
        escritor.write(FramingDemostracion().preparar(b"NO-ES-UN-MENSAJE-ISO8583"))
        await escritor.drain()
        escritor.close()

    servidor_stub = await asyncio.start_server(_stub_no_iso, "127.0.0.1", 0)
    host_stub, puerto_stub = servidor_stub.sockets[0].getsockname()
    async with servidor_stub:
        proxy = _proxy(DestinoTcp(host=host_stub, puerto=puerto_stub), base)
        async with proxy:
            lector, escritor = await asyncio.open_connection(proxy.host, proxy.puerto)
            payload_enviado = b"TAMPOCO-ES-ISO8583-VALIDO"
            escritor.write(FramingDemostracion().preparar(payload_enviado))
            await escritor.drain()
            recibido_por_cliente = await FramingDemostracion().leer_mensaje_completo(lector)
            escritor.close()
            await asyncio.sleep(0.1)  # deja que el registro de auditoria termine

    assert recibido_por_stub == [payload_enviado]
    assert recibido_por_cliente == b"NO-ES-UN-MENSAJE-ISO8583"

    mensajes_repo = RepositorioMensajesProxySQLite(base)
    sesiones = await RepositorioSesionesProxySQLite(base).listar()
    filas = await mensajes_repo.listar_por_sesion(sesiones[0].session_id)
    assert len(filas) == 2
    assert all(f.interpretable is False and f.mti is None for f in filas)


async def test_bytes_forwarding_es_exacto_en_ambos_sentidos(base):
    """Prueba OBLIGATORIA (punto 30): compara los bytes CRUDOS -no campos
    ISO ya interpretados- en cada extremo real. request_cliente ==
    request_upstream, response_upstream == response_cliente."""
    recibido_por_upstream = []

    async def _stub(lector, escritor):
        crudo = await FramingDemostracion().leer_mensaje_completo(lector)
        recibido_por_upstream.append(crudo)
        respuesta = bytes(reversed(crudo))  # payload arbitrario, distinguible
        escritor.write(FramingDemostracion().preparar(respuesta))
        await escritor.drain()
        escritor.close()

    servidor_stub = await asyncio.start_server(_stub, "127.0.0.1", 0)
    host_stub, puerto_stub = servidor_stub.sockets[0].getsockname()
    async with servidor_stub:
        proxy = _proxy(DestinoTcp(host=host_stub, puerto=puerto_stub), base)
        async with proxy:
            lector, escritor = await asyncio.open_connection(proxy.host, proxy.puerto)
            enviado_por_cliente = bytes(range(1, 101))  # 100 bytes arbitrarios
            escritor.write(FramingDemostracion().preparar(enviado_por_cliente))
            await escritor.drain()
            recibido_por_cliente = await FramingDemostracion().leer_mensaje_completo(lector)
            escritor.close()

    assert recibido_por_upstream == [enviado_por_cliente]
    assert recibido_por_cliente == bytes(reversed(enviado_por_cliente))


async def test_multiples_conexiones_concurrentes_no_se_cruzan(base):
    """Punto 15 del encargo: varias sesiones simultaneas, cada una aislada
    -sin STAN ni datos de transaccion compartidos entre ellas."""
    host = _host()
    async with host:
        proxy = _proxy(DestinoTcp(host=host.host, puerto=host.puerto), base)
        async with proxy:
            resultados = await asyncio.gather(*[
                _echo(base, proxy.host, proxy.puerto) for _ in range(8)
            ])
    assert all(r.estado is EstadoEjecucion.APROBADA for r in resultados)
    assert proxy.sesiones_atendidas == 8

    sesiones = await RepositorioSesionesProxySQLite(base).listar()
    assert len(sesiones) == 8
    assert len({s.session_id for s in sesiones}) == 8

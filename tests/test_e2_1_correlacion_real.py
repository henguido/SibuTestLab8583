"""E2.1 -- Correlacion robusta de intercambios Proxy, contra el PROXY REAL
(2026-09-21). `test_proxy_intercambios.py` ya prueba el algoritmo de forma
pura/unitaria; esta suite complementa con evidencia de que el mismo
comportamiento ocurre de verdad cuando dos solicitudes reales viajan
CONCURRENTEMENTE por la misma conexion (full-duplex real, no simulado) y
las respuestas llegan en orden invertido.

Sin dobles del nucleo: TCP real, `ProxyIso8583` real, SQLite real. El
"host" de este archivo es un stub minimo que decodifica/responde con el
codec real, pero deliberadamente invierte el orden de sus respuestas -es
la unica forma de forzar, de manera determinista y sin depender de
condiciones de carrera del sistema operativo, el escenario exacto que el
encargo pide comprobar (0210 B antes que 0210 A)."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal

from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO
from sibutestlab8583.adapters.persistence.sqlite_repos import RepositorioTarjetasSQLite
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.application.captura_a_escenario import InteraccionNoImportable
from sibutestlab8583.composicion import Composicion, Configuracion
from sibutestlab8583.domain.armado import armar_compra_financiera
from sibutestlab8583.domain.modelos import DatosCompraFinanciera, DestinoTcp, MensajeIso
from sibutestlab8583.domain.proxy import DireccionMensajeProxy, derivar_intercambios
from sibutestlab8583.domain.validacion import mti_de_respuesta
from sibutestlab8583.profiles.generico import PERFIL_GENERICO

import pytest


async def _armar_0200(base, *, stan: str, monto: str = "10.00") -> bytes:
    tarjeta = await RepositorioTarjetasSQLite(base).obtener(CARD_ID_DEMO)
    mensaje = armar_compra_financiera(
        DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=Decimal(monto)),
        tarjeta, stan=stan, momento=datetime.now(timezone.utc), perfil=PERFIL_GENERICO,
    )
    return CodecIso8583().codificar(mensaje, PERFIL_GENERICO)


def _responder_0210(payload_0200: bytes) -> bytes:
    """Construye una respuesta 0210 real -mismos campos de correlacion que
    el request, DE39=00- reutilizando el codec real, igual que haria un
    host de verdad."""
    solicitud = CodecIso8583().decodificar(payload_0200, PERFIL_GENERICO)
    campos = {n: c.valor for n, c in solicitud.campos.items()}
    campos["39"] = "00"
    respuesta = MensajeIso(mti=mti_de_respuesta(solicitud.mti), campos=campos)
    return CodecIso8583().codificar(respuesta, PERFIL_GENERICO)


async def test_dos_0200_concurrentes_con_stan_distinto_se_correlacionan_por_stan(base):
    """Prueba de fuego de E2.1: A (STAN 000101) y B (STAN 000102) viajan
    por la MISMA conexion antes de que llegue ninguna respuesta; el stub
    responde B primero, A despues -orden EXACTAMENTE invertido-. El proxy
    debe capturar ambos STAN, y `derivar_intercambios` debe emparejar
    101<->101 y 102<->102, nunca por FIFO."""
    framing = FramingDemostracion()
    payload_a = await _armar_0200(base, stan="000101")
    payload_b = await _armar_0200(base, stan="000102")

    async def _stub(lector, escritor):
        # Lee las DOS solicitudes ANTES de responder nada -full-duplex
        # real: ambas ya estan "en vuelo" cuando se decide el orden de
        # respuesta.
        recibido_1 = await framing.leer_mensaje_completo(lector)
        recibido_2 = await framing.leer_mensaje_completo(lector)
        # Responde en orden INVERTIDO al de llegada.
        for crudo in (recibido_2, recibido_1):
            escritor.write(framing.preparar(_responder_0210(crudo)))
            await escritor.drain()
        escritor.close()

    servidor_stub = await asyncio.start_server(_stub, "127.0.0.1", 0)
    host_stub, puerto_stub = servidor_stub.sockets[0].getsockname()
    composicion = Composicion(Configuracion(ruta_base_datos=base))
    async with servidor_stub:
        proxy = composicion.proxy(DestinoTcp(host=host_stub, puerto=puerto_stub))
        async with proxy:
            lector, escritor = await asyncio.open_connection(proxy.host, proxy.puerto)
            escritor.write(framing.preparar(payload_a))
            escritor.write(framing.preparar(payload_b))
            await escritor.drain()
            respuesta_1 = await framing.leer_mensaje_completo(lector)
            respuesta_2 = await framing.leer_mensaje_completo(lector)
            escritor.close()
            await asyncio.sleep(0.2)  # deja terminar el registro de auditoria

    # El proxy reenvio las respuestas en el mismo orden invertido que el
    # stub las envio -transparencia intacta, el proxy no reordena nada.
    assert CodecIso8583().decodificar(respuesta_1, PERFIL_GENERICO).campos["11"].valor == "000102"
    assert CodecIso8583().decodificar(respuesta_2, PERFIL_GENERICO).campos["11"].valor == "000101"

    sesiones = await composicion.sesiones_proxy.listar()
    mensajes = await composicion.mensajes_proxy.listar_por_sesion(sesiones[0].session_id)
    intercambios = {i.solicitud.stan: i for i in derivar_intercambios(mensajes)}

    assert intercambios["000101"].correlacionado
    assert intercambios["000101"].respuesta.stan == "000101"
    assert intercambios["000102"].correlacionado
    assert intercambios["000102"].respuesta.stan == "000102"


async def test_sin_correladores_suficientes_queda_ambiguo_y_sin_boton_crear_escenario(base):
    """Punto 7 del encargo: mismo escenario de dos solicitudes en vuelo,
    pero SIN STAN capturable (perfil que lo marca sensible -ver
    `test_seguridad_proxy.py::test_e2_1_stan_nunca_se_persiste_si_el_perfil_
    lo_marca_sensible` para la razon de seguridad-): debe quedar
    explicitamente ambiguo, y `ServicioCapturaAEscenario.proponer` debe
    rechazarlo -nunca ofrecer "Crear escenario" sobre una correlacion
    dudosa."""
    import dataclasses

    from sibutestlab8583.adapters.iso8583.codec import CodecIso8583 as _Codec
    from sibutestlab8583.adapters.proxy import ProxyIso8583
    from sibutestlab8583.adapters.persistence.sqlite_repos import (
        RepositorioMensajesProxySQLite, RepositorioSesionesProxySQLite,
    )

    perfil_sin_stan_seguro = dataclasses.replace(PERFIL_GENERICO, campos_sensibles=frozenset({"11"}))
    framing = FramingDemostracion()
    payload_a = await _armar_0200(base, stan="000201")
    payload_b = await _armar_0200(base, stan="000202")

    async def _stub(lector, escritor):
        r1 = await framing.leer_mensaje_completo(lector)
        r2 = await framing.leer_mensaje_completo(lector)
        for crudo in (r2, r1):
            escritor.write(framing.preparar(_responder_0210(crudo)))
            await escritor.drain()
        escritor.close()

    servidor_stub = await asyncio.start_server(_stub, "127.0.0.1", 0)
    host_stub, puerto_stub = servidor_stub.sockets[0].getsockname()
    async with servidor_stub:
        proxy = ProxyIso8583(
            framing, DestinoTcp(host=host_stub, puerto=puerto_stub),
            codec=_Codec(), perfil=perfil_sin_stan_seguro,
            repositorio_sesiones=RepositorioSesionesProxySQLite(base),
            repositorio_mensajes=RepositorioMensajesProxySQLite(base),
        )
        async with proxy:
            lector, escritor = await asyncio.open_connection(proxy.host, proxy.puerto)
            escritor.write(framing.preparar(payload_a))
            escritor.write(framing.preparar(payload_b))
            await escritor.drain()
            await framing.leer_mensaje_completo(lector)
            await framing.leer_mensaje_completo(lector)
            escritor.close()
            await asyncio.sleep(0.2)

    sesiones = await RepositorioSesionesProxySQLite(base).listar()
    mensajes = await RepositorioMensajesProxySQLite(base).listar_por_sesion(sesiones[0].session_id)
    assert all(m.stan is None for m in mensajes)  # confirmado: no se capturo el correlador

    intercambios = derivar_intercambios(mensajes)
    assert not any(i.correlacionado for i in intercambios)  # ambiguo, no adivinado

    composicion = Composicion(Configuracion(ruta_base_datos=base))
    for intercambio in intercambios:
        with pytest.raises(InteraccionNoImportable):
            await composicion.captura_a_escenario.proponer(
                sesiones[0].session_id, intercambio.solicitud.mensaje_id
            )

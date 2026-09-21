"""Captura -> Escenario desde la interfaz web (Fase E2, 2026-09-21).

Vertical real: HTTP -> ProxyIso8583/HostSimulado reales -> SQLite real.
Confirma el recorrido completo del formulario de revision, el caso "no
importable" (MTI sin operacion soportada / intercambio no correlacionado),
y la trazabilidad visible en la lista de escenarios.
"""

from __future__ import annotations

from decimal import Decimal

import httpx2

from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.adapters.transporte.tcp import TransporteTcp
from sibutestlab8583.composicion import Composicion, Configuracion
from sibutestlab8583.domain.modelos import DatosCompraFinanciera, DestinoTcp, EstadoEjecucion
from sibutestlab8583.domain.proxy import DireccionMensajeProxy, MensajeProxyCapturado, SesionProxy
from sibutestlab8583.profiles.generico import PERFIL_GENERICO
from sibutestlab8583.web.app import crear_app
from conftest import construir_orquestador


def _composicion(base):
    return Composicion(Configuracion(ruta_base_datos=base, host_destino="127.0.0.1", tiempo_limite=2.0))


async def _capturar_compra_financiera_real(base, composicion):
    host = HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion())
    async with host:
        proxy = composicion.proxy(DestinoTcp(host=host.host, puerto=host.puerto))
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
        sesiones = await composicion.sesiones_proxy.listar()
        session_id = sesiones[0].session_id
        mensajes = await composicion.mensajes_proxy.listar_por_sesion(session_id)
    solicitud = next(m for m in mensajes if m.direccion is DireccionMensajeProxy.CLIENTE_A_UPSTREAM)
    return session_id, solicitud.mensaje_id


async def test_detalle_de_sesion_muestra_crear_escenario_para_un_intercambio_correlacionado(base):
    composicion = _composicion(base)
    session_id, id_solicitud = await _capturar_compra_financiera_real(base, composicion)
    app = crear_app(composicion)

    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://p") as cliente:
        respuesta = await cliente.get(f"/proxy/sesiones/{session_id}")
    assert respuesta.status_code == 200
    assert "Crear escenario" in respuesta.text
    assert "0200 → 0210" in respuesta.text


async def test_flujo_completo_crear_escenario_desde_la_web(base):
    composicion = _composicion(base)
    session_id, id_solicitud = await _capturar_compra_financiera_real(base, composicion)

    host_replay = HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion())
    async with host_replay:
        app = crear_app(composicion)
        async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://p") as cliente:
            r_form = await cliente.get(
                f"/proxy/sesiones/{session_id}/mensajes/{id_solicitud}/crear-escenario"
            )
            assert r_form.status_code == 200
            assert "Guardar escenario" in r_form.text
            assert "Metadata únicamente" in r_form.text  # aviso de seguridad, siempre visible

            await composicion.administracion_conexiones.crear(
                __import__("sibutestlab8583.application.conexiones", fromlist=["DatosNuevaConexion"]).DatosNuevaConexion(
                    conexion_id="WEB-E2", nombre="aux", host=host_replay.host, puerto=str(host_replay.puerto),
                )
            )
            r_post = await cliente.post(
                f"/proxy/sesiones/{session_id}/mensajes/{id_solicitud}/crear-escenario",
                data={
                    "nombre": "Escenario web E2", "card_id": CARD_ID_DEMO, "monto": "150.00",
                    "conexion_id": "WEB-E2", "tipo_esperado_39": "igual", "valor_esperado_39": "00",
                    "estado_esperado": "aprobada",
                },
            )
            assert r_post.status_code == 303
            assert r_post.headers["location"] == "/escenarios"

            r_lista = await cliente.get("/escenarios")
    assert "Escenario web E2" in r_lista.text
    assert "Desde captura de Proxy" in r_lista.text
    assert f"/proxy/sesiones/{session_id}" in r_lista.text


async def test_mti_no_soportado_muestra_no_disponible_sin_boton(base):
    """Punto 14/21: 0400/0420 (o cualquier MTI sin operacion soportada)
    nunca ofrece "Crear escenario" -solo un motivo explicativo."""
    composicion = _composicion(base)
    await composicion.sesiones_proxy.crear(SesionProxy(
        session_id="S-0400W", cliente_host="127.0.0.1", cliente_puerto=1,
        upstream_host="127.0.0.1", upstream_puerto=2,
    ))
    await composicion.mensajes_proxy.registrar(MensajeProxyCapturado(
        session_id="S-0400W", direccion=DireccionMensajeProxy.CLIENTE_A_UPSTREAM,
        orden=1, longitud=10, mti="0400", interpretable=True,
    ))
    await composicion.mensajes_proxy.registrar(MensajeProxyCapturado(
        session_id="S-0400W", direccion=DireccionMensajeProxy.UPSTREAM_A_CLIENTE,
        orden=1, longitud=10, mti="0410", interpretable=True,
    ))
    app = crear_app(composicion)
    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://p") as cliente:
        respuesta = await cliente.get("/proxy/sesiones/S-0400W")
    assert respuesta.status_code == 200
    assert "Crear escenario" not in respuesta.text
    assert "no tiene un constructor de escenario soportado" in respuesta.text


async def test_intento_de_crear_escenario_sobre_mti_no_soportado_da_400(base):
    composicion = _composicion(base)
    await composicion.sesiones_proxy.crear(SesionProxy(
        session_id="S-0400X", cliente_host="127.0.0.1", cliente_puerto=1,
        upstream_host="127.0.0.1", upstream_puerto=2,
    ))
    await composicion.mensajes_proxy.registrar(MensajeProxyCapturado(
        session_id="S-0400X", direccion=DireccionMensajeProxy.CLIENTE_A_UPSTREAM,
        orden=1, longitud=10, mti="0400", interpretable=True,
    ))
    await composicion.mensajes_proxy.registrar(MensajeProxyCapturado(
        session_id="S-0400X", direccion=DireccionMensajeProxy.UPSTREAM_A_CLIENTE,
        orden=1, longitud=10, mti="0410", interpretable=True,
    ))
    mensajes = await composicion.mensajes_proxy.listar_por_sesion("S-0400X")
    solicitud = next(m for m in mensajes if m.direccion is DireccionMensajeProxy.CLIENTE_A_UPSTREAM)
    app = crear_app(composicion)
    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://p") as cliente:
        respuesta = await cliente.get(f"/proxy/sesiones/S-0400X/mensajes/{solicitud.mensaje_id}/crear-escenario")
    assert respuesta.status_code == 400

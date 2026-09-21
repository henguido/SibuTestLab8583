"""E2E reales de Captura -> Escenario (Fase E2, 2026-09-21). Sin dobles:
TCP real, `ProxyIso8583`/`HostSimulado` reales, SQLite real, reejecucion
real vía `EjecutorDeEscenarios` -el mismo camino que usa la pantalla de
escenarios y `CorredorDeSuites`, nunca uno especial para captura.

Los cinco escenarios del encargo (puntos 23-27):
  1. 0200 -> 0210/00 real, capturado, convertido en escenario, reejecutado
     -> PASS (Expected DE39=00, aprobada).
  2. 0200 -> 0210/51 (regla D1 real de rechazo), convertido con expectativa
     51/rechazada -> RECHAZADA pero QA PASS.
  3. 0800 -> 0810 (Echo), sin tarjeta.
  4. Campos opcionales permitidos por el perfil (DE18/DE25) SI se
     transfieren al escenario cuando se agregan en la revision.
  5. Un campo que el perfil NO permite como opcional para el escenario
     nunca se cuela silenciosamente.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import construir_orquestador
from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO
from sibutestlab8583.adapters.persistence.sqlite_repos import RepositorioReglasHostSQLite
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.adapters.transporte.tcp import TransporteTcp
from sibutestlab8583.application.captura_a_escenario import InteraccionNoImportable
from sibutestlab8583.application.conexiones import DatosNuevaConexion
from sibutestlab8583.application.escenarios import DatosNuevoEscenario
from sibutestlab8583.application.reglas_host import DatosNuevaRegla, ServicioReglasHost
from sibutestlab8583.composicion import Composicion, Configuracion
from sibutestlab8583.domain.modelos import (
    DatosCompraFinanciera,
    DatosEcho,
    DestinoTcp,
    EstadoEjecucion,
    Expectativas,
    ExpectativaCampo,
)
from sibutestlab8583.domain.proxy import DireccionMensajeProxy, MensajeProxyCapturado, SesionProxy
from sibutestlab8583.domain.reglas_host import CAMPO_MTI, CondicionRegla
from sibutestlab8583.profiles.generico import PERFIL_GENERICO


def _composicion(base) -> Composicion:
    return Composicion(Configuracion(ruta_base_datos=base))


async def _crear_conexion_a(composicion, host: HostSimulado, conexion_id: str) -> str:
    await composicion.administracion_conexiones.crear(DatosNuevaConexion(
        conexion_id=conexion_id, nombre="Host real de prueba", host=host.host, puerto=str(host.puerto),
    ))
    return conexion_id


async def _capturar_compra_financiera(base, *, reglas=None, monto="150.00"):
    """Levanta un HostSimulado real + un Proxy real, ejecuta una compra
    financiera real a traves del proxy, y devuelve (session_id,
    mensaje_id_solicitud, mensaje_id_respuesta, resultado)."""
    host = HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), reglas=reglas or ())
    composicion = _composicion(base)
    async with host:
        proxy = composicion.proxy(DestinoTcp(host=host.host, puerto=host.puerto))
        async with proxy:
            transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
            orquestador = construir_orquestador(
                base, transporte, destino=DestinoTcp(host=proxy.host, puerto=proxy.puerto),
                tiempo_limite=2.0,
            )
            resultado = await orquestador.ejecutar_compra_financiera(
                DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=Decimal(monto))
            )
        sesiones = await composicion.sesiones_proxy.listar()
        session_id = sesiones[0].session_id
        mensajes = await composicion.mensajes_proxy.listar_por_sesion(session_id)
    solicitud = next(m for m in mensajes if m.direccion is DireccionMensajeProxy.CLIENTE_A_UPSTREAM)
    respuesta = next(m for m in mensajes if m.direccion is DireccionMensajeProxy.UPSTREAM_A_CLIENTE)
    return session_id, solicitud.mensaje_id, respuesta.mensaje_id, resultado


async def _capturar_echo(base):
    host = HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion())
    composicion = _composicion(base)
    async with host:
        proxy = composicion.proxy(DestinoTcp(host=host.host, puerto=host.puerto))
        async with proxy:
            transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
            orquestador = construir_orquestador(
                base, transporte, destino=DestinoTcp(host=proxy.host, puerto=proxy.puerto),
                tiempo_limite=2.0,
            )
            resultado = await orquestador.ejecutar_network_echo(DatosEcho())
        sesiones = await composicion.sesiones_proxy.listar()
        session_id = sesiones[0].session_id
        mensajes = await composicion.mensajes_proxy.listar_por_sesion(session_id)
    solicitud = next(m for m in mensajes if m.direccion is DireccionMensajeProxy.CLIENTE_A_UPSTREAM)
    return session_id, solicitud.mensaje_id, resultado


async def test_primera_e2e_compra_financiera_aprobada_captura_a_escenario_a_pass(base):
    session_id, id_solicitud, id_respuesta, real = await _capturar_compra_financiera(base)
    assert real.estado is EstadoEjecucion.APROBADA

    composicion = _composicion(base)
    propuesta = await composicion.captura_a_escenario.proponer(session_id, id_solicitud)
    assert propuesta.mti_solicitud == "0200"
    assert propuesta.requiere_tarjeta
    assert propuesta.requiere_monto

    host_replay = HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion())
    async with host_replay:
        conexion_id = await _crear_conexion_a(composicion, host_replay, "E2E1")
        creado = await composicion.captura_a_escenario.crear_desde_captura(
            DatosNuevoEscenario(
                nombre="E2E1", mti=propuesta.mti_solicitud, conexion_id=conexion_id,
                card_id=CARD_ID_DEMO, monto=Decimal("150.00"),
                expectativas=Expectativas(
                    estado=EstadoEjecucion.APROBADA,
                    campos={"39": ExpectativaCampo(tipo="igual", valor="00")},
                ),
            ),
            session_id=session_id, mensaje_id_solicitud=id_solicitud, mensaje_id_respuesta=id_respuesta,
        )
        resultado_reejecutado = await composicion.ejecutor_escenarios.ejecutar(creado.escenario_id)

    assert resultado_reejecutado.estado is EstadoEjecucion.APROBADA
    assert resultado_reejecutado.ejecucion.evaluacion_estado == "pass"

    origen = await composicion.origen_captura_escenario.obtener_por_escenario(creado.escenario_id)
    assert origen.session_id == session_id
    assert origen.mensaje_id_solicitud == id_solicitud


async def test_segunda_e2e_rechazo_capturado_expectativa_51_qa_pass(base):
    """Punto 24: captura 0200->0210/51 (regla D1 real), escenario con
    expectativa 51/rechazada, reejecucion -> RECHAZADA pero QA PASS."""
    servicio_reglas = ServicioReglasHost(RepositorioReglasHostSQLite(base), PERFIL_GENERICO)
    await servicio_reglas.crear(DatosNuevaRegla(
        nombre="Rechazo E2", prioridad=10,
        condiciones=[CondicionRegla(CAMPO_MTI, "igual", "0200")], de39="51",
    ))
    reglas = await servicio_reglas.listar()

    session_id, id_solicitud, id_respuesta, real = await _capturar_compra_financiera(
        base, reglas=reglas, monto="999999.00"
    )
    assert real.estado is EstadoEjecucion.RECHAZADA
    assert real.respuesta.valor("39") == "51"

    composicion = _composicion(base)
    host_rechazo = HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), reglas=reglas)
    async with host_rechazo:
        conexion_id = await _crear_conexion_a(composicion, host_rechazo, "E2E2")
        creado = await composicion.captura_a_escenario.crear_desde_captura(
            DatosNuevoEscenario(
                nombre="E2E2", mti="0200", conexion_id=conexion_id,
                card_id=CARD_ID_DEMO, monto=Decimal("999999.00"),
                expectativas=Expectativas(
                    estado=EstadoEjecucion.RECHAZADA,
                    campos={"39": ExpectativaCampo(tipo="igual", valor="51")},
                ),
            ),
            session_id=session_id, mensaje_id_solicitud=id_solicitud, mensaje_id_respuesta=id_respuesta,
        )
        resultado = await composicion.ejecutor_escenarios.ejecutar(creado.escenario_id)

    assert resultado.estado is EstadoEjecucion.RECHAZADA
    assert resultado.ejecucion.evaluacion_estado == "pass"


async def test_tercera_e2e_echo_capturado_sin_tarjeta(base):
    session_id, id_solicitud, real = await _capturar_echo(base)
    assert real.estado is EstadoEjecucion.APROBADA

    composicion = _composicion(base)
    propuesta = await composicion.captura_a_escenario.proponer(session_id, id_solicitud)
    assert propuesta.mti_solicitud == "0800"
    assert not propuesta.requiere_tarjeta
    assert not propuesta.requiere_monto

    host_replay = HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion())
    async with host_replay:
        conexion_id = await _crear_conexion_a(composicion, host_replay, "E2E3")
        creado = await composicion.captura_a_escenario.crear_desde_captura(
            DatosNuevoEscenario(nombre="E2E3", mti="0800", conexion_id=conexion_id),
            session_id=session_id, mensaje_id_solicitud=id_solicitud, mensaje_id_respuesta=propuesta.mensaje_id_respuesta,
        )
        resultado = await composicion.ejecutor_escenarios.ejecutar(creado.escenario_id)
    assert resultado.estado is EstadoEjecucion.APROBADA


async def test_cuarta_e2e_campos_opcionales_permitidos_se_transfieren(base):
    """Punto 26: DE18/DE25 (opcionales del perfil para 0200) SI se
    conservan en el escenario si el creador los agrega explicitamente."""
    session_id, id_solicitud, id_respuesta, _ = await _capturar_compra_financiera(base)
    composicion = _composicion(base)
    propuesta = await composicion.captura_a_escenario.proponer(session_id, id_solicitud)
    assert "18" in propuesta.campos_opcionales_disponibles
    assert "25" in propuesta.campos_opcionales_disponibles

    host_replay = HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion())
    async with host_replay:
        conexion_id = await _crear_conexion_a(composicion, host_replay, "E2E4")
        creado = await composicion.captura_a_escenario.crear_desde_captura(
            DatosNuevoEscenario(
                nombre="E2E4", mti="0200", conexion_id=conexion_id,
                card_id=CARD_ID_DEMO, monto=Decimal("150.00"),
                campos_manuales={"18": "5411", "25": "00"},
            ),
            session_id=session_id, mensaje_id_solicitud=id_solicitud, mensaje_id_respuesta=id_respuesta,
        )
    guardado = await composicion.administracion_escenarios.obtener(creado.escenario_id)
    assert guardado.campos_manuales["18"] == "5411"
    assert guardado.campos_manuales["25"] == "00"


async def test_quinta_e2e_campo_no_permitido_nunca_se_cuela_silenciosamente(base):
    """Punto 27: un campo que la politica del perfil NO permite como
    opcional/editable para este MTI se rechaza -nunca se acepta en
    silencio como si fuera legitimo."""
    session_id, id_solicitud, id_respuesta, _ = await _capturar_compra_financiera(base)
    composicion = _composicion(base)

    campo_no_permitido = "11"  # STAN: automatico, nunca editable/opcional
    politica = PERFIL_GENERICO.politica("0200")
    assert campo_no_permitido not in politica.opcionales
    assert campo_no_permitido not in politica.editables

    host_replay = HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion())
    async with host_replay:
        conexion_id = await _crear_conexion_a(composicion, host_replay, "E2E5")
        with pytest.raises(ValueError):
            await composicion.captura_a_escenario.crear_desde_captura(
                DatosNuevoEscenario(
                    nombre="E2E5", mti="0200", conexion_id=conexion_id,
                    card_id=CARD_ID_DEMO, monto=Decimal("150.00"),
                    campos_manuales={campo_no_permitido: "999999"},
                ),
                session_id=session_id, mensaje_id_solicitud=id_solicitud, mensaje_id_respuesta=id_respuesta,
            )


async def test_intercambio_no_correlacionado_no_es_importable(base):
    session_id, id_solicitud, _, _ = await _capturar_compra_financiera(base)
    composicion = _composicion(base)
    await composicion.mensajes_proxy.registrar(MensajeProxyCapturado(
        session_id=session_id, direccion=DireccionMensajeProxy.CLIENTE_A_UPSTREAM,
        orden=99, longitud=10, mti="0200", interpretable=True,
    ))
    mensajes = await composicion.mensajes_proxy.listar_por_sesion(session_id)
    huerfana_id = max(m.mensaje_id for m in mensajes if m.orden == 99)

    with pytest.raises(InteraccionNoImportable):
        await composicion.captura_a_escenario.proponer(session_id, huerfana_id)


async def test_mti_no_soportado_no_es_importable(base):
    """Punto 14: 0400/0420 no tienen constructor de escenario -no se
    permite convertir una captura aislada en escenario."""
    composicion = _composicion(base)
    await composicion.sesiones_proxy.crear(SesionProxy(
        session_id="S-0400", cliente_host="127.0.0.1", cliente_puerto=1,
        upstream_host="127.0.0.1", upstream_puerto=2,
    ))
    await composicion.mensajes_proxy.registrar(MensajeProxyCapturado(
        session_id="S-0400", direccion=DireccionMensajeProxy.CLIENTE_A_UPSTREAM,
        orden=1, longitud=10, mti="0400", interpretable=True,
    ))
    await composicion.mensajes_proxy.registrar(MensajeProxyCapturado(
        session_id="S-0400", direccion=DireccionMensajeProxy.UPSTREAM_A_CLIENTE,
        orden=1, longitud=10, mti="0410", interpretable=True,
    ))
    mensajes = await composicion.mensajes_proxy.listar_por_sesion("S-0400")
    solicitud = next(m for m in mensajes if m.direccion is DireccionMensajeProxy.CLIENTE_A_UPSTREAM)

    with pytest.raises(InteraccionNoImportable):
        await composicion.captura_a_escenario.proponer("S-0400", solicitud.mensaje_id)

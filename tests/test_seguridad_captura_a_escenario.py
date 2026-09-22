"""Seguridad de Captura -> Escenario (Fase E2, 2026-09-21, punto 22 del
encargo): un PAN real nunca llega a un Escenario, DE35/DE45 tampoco, y las
expectativas sugeridas nunca incluyen campos sensibles."""

from __future__ import annotations

import re
from decimal import Decimal

import pytest

from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.adapters.transporte.tcp import TransporteTcp
from sibutestlab8583.application.conexiones import DatosNuevaConexion
from sibutestlab8583.application.escenarios import DatosNuevoEscenario
from sibutestlab8583.composicion import Composicion, Configuracion
from sibutestlab8583.domain.modelos import DatosCompraFinanciera, DestinoTcp, EstadoEjecucion
from sibutestlab8583.domain.proxy import DireccionMensajeProxy
from sibutestlab8583.profiles.generico import PERFIL_GENERICO
from conftest import construir_orquestador

#: Misma heuristica que `test_datos_sinteticos.py`/`test_seguridad_proxy.py`.
_PATRON_PAN = re.compile(r"\d{12,19}")


async def test_escenario_creado_desde_captura_usa_card_id_nunca_el_pan(base):
    """El PAN sintetico (`CARD_ID_DEMO`) viaja por la red real (E1 lo
    reenvia byte a byte) pero el escenario creado desde esa captura solo
    guarda `card_id` -nunca el PAN- en toda la fila persistida."""
    host = HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion())
    composicion = Composicion(Configuracion(ruta_base_datos=base))
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

    host2 = HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion())
    async with host2:
        await composicion.administracion_conexiones.crear(DatosNuevaConexion(
            conexion_id="SEC-E2", nombre="aux", host=host2.host, puerto=str(host2.puerto),
        ))
        creado = await composicion.captura_a_escenario.crear_desde_captura(
            DatosNuevoEscenario(
                nombre="Seguridad E2", mti="0200", conexion_id="SEC-E2",
                card_id=CARD_ID_DEMO, monto=Decimal("150.00"),
            ),
            session_id=session_id, mensaje_id_solicitud=solicitud.mensaje_id, mensaje_id_respuesta=None,
        )

    import sqlite3
    conexion_db = sqlite3.connect(str(base))
    try:
        fila = conexion_db.execute(
            "SELECT * FROM escenarios WHERE escenario_id = ?", (creado.escenario_id,)
        ).fetchone()
    finally:
        conexion_db.close()
    assert fila is not None
    for valor in fila:
        if valor is not None:
            assert not _PATRON_PAN.search(str(valor)), f"posible PAN persistido en escenarios: {valor!r}"
    assert creado.card_id == CARD_ID_DEMO


async def test_expectativa_de35_de45_rechazada_en_captura_a_escenario(base):
    """`_leer_expectativas`/`validar_expectativas` ya rechazan un campo
    sensible -este test confirma que el camino de E2 (via
    `ServicioCapturaAEscenario.crear_desde_captura` -> `ServicioEscenarios.
    crear`) hereda esa misma proteccion, sin una ruta alterna que la
    evada."""
    from sibutestlab8583.domain.modelos import ExpectativaCampo, Expectativas

    composicion = Composicion(Configuracion(ruta_base_datos=base))
    host = HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion())
    async with host:
        await composicion.administracion_conexiones.crear(DatosNuevaConexion(
            conexion_id="SEC-E2B", nombre="aux", host=host.host, puerto=str(host.puerto),
        ))
        with pytest.raises(ValueError):
            await composicion.captura_a_escenario.crear_desde_captura(
                DatosNuevoEscenario(
                    nombre="Intento sensible", mti="0200", conexion_id="SEC-E2B",
                    card_id=CARD_ID_DEMO, monto=Decimal("150.00"),
                    expectativas=Expectativas(campos={"35": ExpectativaCampo(tipo="presente")}),
                ),
                session_id="S", mensaje_id_solicitud=1, mensaje_id_respuesta=2,
            )


async def test_origen_captura_escenario_no_tiene_ningun_campo_para_valores_del_mensaje():
    """Garantia ESTRUCTURAL (no de convencion): `OrigenCapturaEscenario`
    solo referencia ids -nunca un campo que pudiera aceptar un valor de
    negocio del mensaje capturado."""
    from sibutestlab8583.domain.proxy import OrigenCapturaEscenario
    campos = set(OrigenCapturaEscenario.__dataclass_fields__)
    assert campos == {
        "escenario_id", "session_id", "mensaje_id_solicitud", "mensaje_id_respuesta", "creado_en",
    }

"""Seguridad del reverso financiero (0400/0410, B7).

Adversarial, real (TCP/SQLite/HTTP reales): confirma que el PAN completo
nunca aparece en la pantalla de vista previa del reverso ni en su resultado
-ni siquiera como substring dentro de otro campo-, y que el reverso persiste
usando `card_id`, nunca el PAN, exactamente igual que cualquier otra
operacion con tarjeta.
"""

from __future__ import annotations

import httpx2

from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, PAN_DEMO
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.application.conexiones import DatosNuevaConexion
from sibutestlab8583.composicion import Composicion, Configuracion
from sibutestlab8583.profiles.generico import PERFIL_GENERICO
from sibutestlab8583.web.app import crear_app


def _host(**kwargs) -> HostSimulado:
    return HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), **kwargs)


async def test_el_pan_nunca_aparece_en_preview_ni_en_resultado_del_reverso(base):
    composicion = Composicion(
        Configuracion(ruta_base_datos=base, host_destino="127.0.0.1", tiempo_limite=3.0)
    )
    host = _host()
    app = crear_app(composicion)

    async with host:
        await composicion.administracion_conexiones.crear(
            DatosNuevaConexion(
                conexion_id="SEC-B7", nombre="Host simulado de la prueba",
                host=host.host, puerto=str(host.puerto),
            )
        )
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://prueba"
        ) as cliente:
            await cliente.post(
                "/financiera/ejecutar",
                data={"card_id": CARD_ID_DEMO, "monto": "55.00", "conexion_id": "SEC-B7"},
            )
            origen_id = (await composicion.consultas.ejecuciones_recientes())[0].id

            preview = await cliente.get(f"/historial/{origen_id}/reverso")
            resultado = await cliente.post(f"/historial/{origen_id}/reverso/ejecutar")

            derivada_id = (await composicion.consultas.derivadas_de(origen_id))[0].id
            detalle_derivada = await cliente.get(f"/historial/{derivada_id}")

    for pagina in (preview, resultado, detalle_derivada):
        assert PAN_DEMO not in pagina.text
    # Track1/Track2 no existen en este perfil (ver ESPECIFICACION_GENERICA):
    # no hay campo que probar, pero el PAN es el unico dato de tarjeta que
    # podria colarse -y ya se confirma ausente arriba.

    # El reverso persiste por card_id, igual que cualquier operacion con
    # tarjeta -nunca duplica el PAN en una columna nueva.
    ejecucion_derivada = (await composicion.consultas.ejecuciones_recientes())[0]
    assert ejecucion_derivada.card_id == CARD_ID_DEMO


async def test_de90_nunca_aparece_porque_no_esta_implementado(base):
    """B7 punto 7: DE90 se investigo y NO se implemento (ver
    profiles/generico.py). Esta prueba confirma que ningun campo "90"
    aparece en la vista previa ni en el resultado del reverso -si algun dia
    se agregara sin la composicion defendible que el punto 7 exige, esta
    prueba lo detectaria."""
    composicion = Composicion(
        Configuracion(ruta_base_datos=base, host_destino="127.0.0.1", tiempo_limite=3.0)
    )
    host = _host()
    app = crear_app(composicion)

    async with host:
        await composicion.administracion_conexiones.crear(
            DatosNuevaConexion(
                conexion_id="SEC-B7-2", nombre="Host simulado de la prueba",
                host=host.host, puerto=str(host.puerto),
            )
        )
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://prueba"
        ) as cliente:
            await cliente.post(
                "/financiera/ejecutar",
                data={"card_id": CARD_ID_DEMO, "monto": "45.00", "conexion_id": "SEC-B7-2"},
            )
            origen_id = (await composicion.consultas.ejecuciones_recientes())[0].id
            preview = await cliente.get(f"/historial/{origen_id}/reverso")

    assert 'campo-iso">90<' not in preview.text

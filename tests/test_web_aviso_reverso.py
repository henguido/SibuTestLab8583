"""B8: aviso de reverso (0420/0430) desde la interfaz web.

Vertical real -HTTP -> nucleo real -> TCP real -> SQLite real-, espejo de
`tests/test_web_reverso_financiero.py`. Agrega la prueba propia de B8: el
historial debe listar 0400 y 0420 como derivadas DISTINTAS del mismo origen
(punto 15 del checkpoint), con navegacion bidireccional para ambas.
"""

from __future__ import annotations

from decimal import Decimal

import httpx2

from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.application.conexiones import DatosNuevaConexion
from sibutestlab8583.composicion import Composicion, Configuracion
from sibutestlab8583.profiles.generico import PERFIL_GENERICO
from sibutestlab8583.web.app import crear_app


def _host(**kwargs) -> HostSimulado:
    return HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), **kwargs)


async def _financiera_aprobada_real(cliente, *, monto="80.00", conexion="VERTICAL-B8"):
    resultado = await cliente.post(
        "/financiera/ejecutar",
        data={"card_id": CARD_ID_DEMO, "monto": monto, "conexion_id": conexion},
    )
    assert resultado.status_code == 200
    return resultado


async def test_el_boton_crear_aviso_de_reverso_aparece_solo_para_una_financiera_aprobada(base):
    composicion = Composicion(
        Configuracion(ruta_base_datos=base, host_destino="127.0.0.1", tiempo_limite=3.0)
    )
    host = _host()
    app = crear_app(composicion)

    async with host:
        await composicion.administracion_conexiones.crear(
            DatosNuevaConexion(
                conexion_id="VERTICAL-B8", nombre="Host simulado de la prueba",
                host=host.host, puerto=str(host.puerto),
            )
        )
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://prueba"
        ) as cliente:
            await _financiera_aprobada_real(cliente, monto="80.00")
            await _financiera_aprobada_real(cliente, monto="500000.00")
            await cliente.post(
                "/compra",
                data={"card_id": CARD_ID_DEMO, "monto": "20.00", "conexion_id": "VERTICAL-B8"},
            )
            await cliente.post("/echo/ejecutar", data={"conexion_id": "VERTICAL-B8"})

            guardadas = await composicion.consultas.ejecuciones_recientes(limite=10)

    por_estado = {(e.mti_solicitud, e.estado.value): e.id for e in guardadas}
    id_aprobada = por_estado[("0200", "aprobada")]
    id_rechazada = por_estado[("0200", "rechazada")]
    id_autorizacion = por_estado[("0100", "aprobada")]
    id_echo = por_estado[("0800", "aprobada")]

    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://prueba"
    ) as cliente:
        detalle_aprobada = await cliente.get(f"/historial/{id_aprobada}")
        detalle_rechazada = await cliente.get(f"/historial/{id_rechazada}")
        detalle_autorizacion = await cliente.get(f"/historial/{id_autorizacion}")
        detalle_echo = await cliente.get(f"/historial/{id_echo}")

    assert "Crear aviso de reverso" in detalle_aprobada.text
    assert "Crear aviso de reverso" not in detalle_rechazada.text
    assert "Crear aviso de reverso" not in detalle_autorizacion.text
    assert "Crear aviso de reverso" not in detalle_echo.text


async def test_recorrido_completo_preview_ejecutar_y_navegacion_bidireccional(base):
    composicion = Composicion(
        Configuracion(ruta_base_datos=base, host_destino="127.0.0.1", tiempo_limite=3.0)
    )
    host = _host()
    app = crear_app(composicion)

    async with host:
        await composicion.administracion_conexiones.crear(
            DatosNuevaConexion(
                conexion_id="VERTICAL-B8-2", nombre="Host simulado de la prueba",
                host=host.host, puerto=str(host.puerto),
            )
        )
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://prueba"
        ) as cliente:
            await _financiera_aprobada_real(cliente, monto="65.00", conexion="VERTICAL-B8-2")
            origen_id = (await composicion.consultas.ejecuciones_recientes())[0].id

            preview = await cliente.get(f"/historial/{origen_id}/aviso-reverso")
            assert preview.status_code == 200
            assert "0420" in preview.text
            assert f"Ejecución #{origen_id}" in preview.text

            ejecutar = await cliente.post(f"/historial/{origen_id}/aviso-reverso/ejecutar")
            assert ejecutar.status_code == 200
            assert "0420" in ejecutar.text
            assert "0430" in ejecutar.text

            derivada_id = (await composicion.consultas.derivadas_de(origen_id))[0].id

            detalle_origen = await cliente.get(f"/historial/{origen_id}")
            detalle_derivada = await cliente.get(f"/historial/{derivada_id}")

    assert f'href="/historial/{derivada_id}"' in detalle_origen.text
    assert "Ninguna todavía." not in detalle_origen.text
    assert "Originada desde la ejecución" in detalle_derivada.text
    assert f'href="/historial/{origen_id}"' in detalle_derivada.text


async def test_no_se_puede_crear_un_aviso_de_reverso_de_un_origen_inexistente(base):
    composicion = Composicion(
        Configuracion(ruta_base_datos=base, host_destino="127.0.0.1", tiempo_limite=3.0)
    )
    app = crear_app(composicion)

    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://prueba"
    ) as cliente:
        preview = await cliente.get("/historial/999999/aviso-reverso")
        ejecutar = await cliente.post("/historial/999999/aviso-reverso/ejecutar")

    assert preview.status_code == 404
    assert ejecutar.status_code == 404


async def test_no_se_puede_forzar_por_post_un_origen_no_elegible(base):
    """Adversarial (mismo criterio que el reverso financiero, B7 puntos
    15/16): un POST directo contra un origen NO elegible (una 0100) debe
    rechazarse igual que si se hubiera intentado desde el preview."""
    composicion = Composicion(
        Configuracion(ruta_base_datos=base, host_destino="127.0.0.1", tiempo_limite=3.0)
    )
    host = _host()
    app = crear_app(composicion)

    async with host:
        await composicion.administracion_conexiones.crear(
            DatosNuevaConexion(
                conexion_id="VERTICAL-B8-3", nombre="Host simulado de la prueba",
                host=host.host, puerto=str(host.puerto),
            )
        )
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://prueba"
        ) as cliente:
            await cliente.post(
                "/compra",
                data={"card_id": CARD_ID_DEMO, "monto": "20.00", "conexion_id": "VERTICAL-B8-3"},
            )
            autorizacion_id = (await composicion.consultas.ejecuciones_recientes())[0].id

            preview = await cliente.get(f"/historial/{autorizacion_id}/aviso-reverso")
            ejecutar = await cliente.post(f"/historial/{autorizacion_id}/aviso-reverso/ejecutar")

    assert preview.status_code == 404
    assert ejecutar.status_code == 404
    assert len(await composicion.consultas.derivadas_de(autorizacion_id)) == 0


async def test_el_historial_lista_un_reverso_y_un_aviso_de_reverso_como_derivadas_distintas(base):
    """B8, punto 15: el historial debe distinguir "Reverso financiero · 0400"
    de "Aviso de reverso · 0420" para el mismo origen -no solo mostrar dos
    filas identicas-, con navegacion bidireccional para ambas."""
    composicion = Composicion(
        Configuracion(ruta_base_datos=base, host_destino="127.0.0.1", tiempo_limite=3.0)
    )
    host = _host()
    app = crear_app(composicion)

    async with host:
        await composicion.administracion_conexiones.crear(
            DatosNuevaConexion(
                conexion_id="VERTICAL-B8-4", nombre="Host simulado de la prueba",
                host=host.host, puerto=str(host.puerto),
            )
        )
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://prueba"
        ) as cliente:
            await _financiera_aprobada_real(cliente, monto="45.00", conexion="VERTICAL-B8-4")
            origen_id = (await composicion.consultas.ejecuciones_recientes())[0].id

            await cliente.post(f"/historial/{origen_id}/reverso/ejecutar")
            await cliente.post(f"/historial/{origen_id}/aviso-reverso/ejecutar")

            detalle_origen = await cliente.get(f"/historial/{origen_id}")

    derivadas = await composicion.consultas.derivadas_de(origen_id)
    assert {d.mti_solicitud for d in derivadas} == {"0400", "0420"}

    texto = detalle_origen.text
    assert "Reverso financiero" in texto
    assert "Aviso de reverso" in texto
    for derivada in derivadas:
        assert f'href="/historial/{derivada.id}"' in texto

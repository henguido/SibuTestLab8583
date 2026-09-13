"""B6: el detalle historico muestra el modelo de operacion derivada -sin
0400/0410 implementado todavia-.

Vertical, HTTP -> nucleo real -> TCP real -> SQLite real (mismo estilo que
`test_detalle_historial.py::test_vertical_transaccion_real_y_detalle_coherente`):
ejecuta una compra financiera real y aprobada, confirma que su detalle
muestra el indicador pasivo "Elegible para reverso", y -como B6 todavia no
puede CREAR una derivada real (no hay 0400)- inserta una segunda ejecucion
con `ejecucion_origen_id` apuntando a la primera directamente en SQLite
(exactamente como hace `test_detalle_historial.py` para simular una fila
historica), para confirmar la navegacion origen<->derivadas en ambos
sentidos.
"""

from __future__ import annotations

import sqlite3
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


async def test_una_financiera_aprobada_muestra_elegible_para_reverso(base):
    composicion = Composicion(
        Configuracion(ruta_base_datos=base, host_destino="127.0.0.1", tiempo_limite=3.0)
    )
    host = HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion())
    app = crear_app(composicion)

    async with host:
        await composicion.administracion_conexiones.crear(
            DatosNuevaConexion(
                conexion_id="VERTICAL-B6", nombre="Host simulado de la prueba",
                host=host.host, puerto=str(host.puerto),
            )
        )
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://prueba"
        ) as cliente:
            resultado_web = await cliente.post(
                "/financiera/ejecutar",
                data={"card_id": CARD_ID_DEMO, "monto": "40.00", "conexion_id": "VERTICAL-B6"},
            )
            assert resultado_web.status_code == 200

            guardadas = await composicion.consultas.ejecuciones_recientes()
            assert len(guardadas) == 1
            ejecucion_id = guardadas[0].id

            detalle = await cliente.get(f"/historial/{ejecucion_id}")

    assert detalle.status_code == 200
    assert "Elegible para reverso" in detalle.text
    assert "Ninguna todavía." in detalle.text  # sin derivadas todavia


async def test_navegacion_origen_y_derivada_en_ambos_sentidos(base):
    """B6 todavia no puede CREAR una derivada real (no hay 0400/0410): se
    inserta directamente en SQLite -mismo criterio que usa
    `test_detalle_historial.py` para simular filas historicas-, para probar
    la navegacion que el modelo ya soporta.
    """
    composicion = Composicion(
        Configuracion(ruta_base_datos=base, host_destino="127.0.0.1", tiempo_limite=3.0)
    )
    host = HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion())
    app = crear_app(composicion)

    async with host:
        await composicion.administracion_conexiones.crear(
            DatosNuevaConexion(
                conexion_id="VERTICAL-B6-2", nombre="Host simulado de la prueba",
                host=host.host, puerto=str(host.puerto),
            )
        )
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://prueba"
        ) as cliente:
            resultado_web = await cliente.post(
                "/financiera/ejecutar",
                data={"card_id": CARD_ID_DEMO, "monto": "60.00", "conexion_id": "VERTICAL-B6-2"},
            )
            assert resultado_web.status_code == 200
            origen_id = (await composicion.consultas.ejecuciones_recientes())[0].id

            # Simula una derivada (futuro reverso) insertando directamente en
            # SQLite -no hay ruta web que la cree todavia en B6-.
            with sqlite3.connect(base) as conexion:
                conexion.execute(
                    "INSERT INTO ejecuciones"
                    " (creada_en, mti_solicitud, stan, estado, ejecucion_origen_id)"
                    " VALUES ('2026-09-13T00:00:00+00:00', '0100', '000999', 'aprobada', ?)",
                    (origen_id,),
                )
                conexion.commit()
                derivada_id = conexion.execute(
                    "SELECT id FROM ejecuciones WHERE stan = '000999'"
                ).fetchone()[0]

            detalle_origen = await cliente.get(f"/historial/{origen_id}")
            detalle_derivada = await cliente.get(f"/historial/{derivada_id}")

    assert f'href="/historial/{derivada_id}"' in detalle_origen.text
    assert "Ninguna todavía." not in detalle_origen.text

    assert f"Originada desde la ejecución" in detalle_derivada.text
    assert f'href="/historial/{origen_id}"' in detalle_derivada.text

"""C1: Secuencias transaccionales desde la interfaz web.

Vertical real -HTTP -> nucleo real -> TCP real -> SQLite real-: crea un
escenario de compra financiera, crea una secuencia (compra + reverso) y la
ejecuta desde la ruta web, confirmando la navegacion Secuencias -> corrida
-> detalle de cada paso -> Isoscopio real.
"""

from __future__ import annotations

from decimal import Decimal

import httpx2

from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.application.conexiones import DatosNuevaConexion
from sibutestlab8583.application.escenarios import DatosNuevoEscenario
from sibutestlab8583.composicion import Composicion, Configuracion
from sibutestlab8583.domain.modelos import MTI_COMPRA_FINANCIERA
from sibutestlab8583.profiles.generico import PERFIL_GENERICO
from sibutestlab8583.web.app import crear_app


def _host(**kwargs) -> HostSimulado:
    return HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), **kwargs)


async def test_crear_y_ejecutar_una_secuencia_real_desde_la_web(base):
    composicion = Composicion(
        Configuracion(ruta_base_datos=base, host_destino="127.0.0.1", tiempo_limite=3.0)
    )
    host = _host()
    app = crear_app(composicion)

    async with host:
        await composicion.administracion_conexiones.crear(
            DatosNuevaConexion(
                conexion_id="WEB-C1", nombre="Host simulado de la prueba",
                host=host.host, puerto=str(host.puerto),
            )
        )
        escenario = await composicion.administracion_escenarios.crear(
            DatosNuevoEscenario(
                nombre="Compra financiera web C1", conexion_id="WEB-C1",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("55.00"),
            )
        )

        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://prueba"
        ) as cliente:
            # El formulario ofrece el escenario recien creado.
            formulario = await cliente.get("/secuencias/nueva")
            assert formulario.status_code == 200
            assert "Compra financiera web C1" in formulario.text

            crear = await cliente.post(
                "/secuencias",
                data={"nombre": "Compra + reverso (web)", "escenario_id": escenario.escenario_id},
            )
            assert crear.status_code in (200, 303)

            lista = await cliente.get("/secuencias")
            assert "Compra + reverso (web)" in lista.text

            secuencia_id = (await composicion.administracion_secuencias.listar())[0].secuencia_id
            ejecutar = await cliente.post(f"/secuencias/{secuencia_id}/ejecutar", follow_redirects=True)
            assert ejecutar.status_code == 200
            assert "Compra + reverso (web)" in ejecutar.text
            assert "PASS" not in ejecutar.text or "Sin expectativas" in ejecutar.text

            corridas = await composicion.corridas_secuencia.listar()
            corrida_id = corridas[0].corrida_id
            pasos = await composicion.corridas_secuencia.obtener_pasos(corrida_id)
            paso1, paso2 = sorted(pasos, key=lambda p: p.orden)

            detalle_corrida = await cliente.get(f"/secuencias/corridas/{corrida_id}")
            assert detalle_corrida.status_code == 200
            assert f'href="/historial/{paso1.ejecucion_id}"' in detalle_corrida.text
            assert f'href="/historial/{paso2.ejecucion_id}"' in detalle_corrida.text

            detalle_ejecucion_2 = await cliente.get(f"/historial/{paso2.ejecucion_id}")
            assert detalle_ejecucion_2.status_code == 200
            assert "Originada desde la ejecución" in detalle_ejecucion_2.text
            assert f'href="/historial/{paso1.ejecucion_id}"' in detalle_ejecucion_2.text


async def test_una_secuencia_inexistente_no_se_puede_ejecutar(base):
    composicion = Composicion(
        Configuracion(ruta_base_datos=base, host_destino="127.0.0.1", tiempo_limite=3.0)
    )
    app = crear_app(composicion)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://prueba"
    ) as cliente:
        respuesta = await cliente.post("/secuencias/NO-EXISTE/ejecutar")
    assert respuesta.status_code == 404

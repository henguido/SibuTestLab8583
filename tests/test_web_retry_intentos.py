"""UI de corrida: intentos de retry visibles (C3, 2026-09-14, punto 26 del
checkpoint). Vertical real -HTTP -> nucleo real -> TCP real-, mismo estilo
que `tests/test_web_secuencias.py`.
"""

from __future__ import annotations

import asyncio

import httpx2

from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.application.conexiones import DatosNuevaConexion
from sibutestlab8583.application.escenarios import DatosNuevoEscenario
from sibutestlab8583.application.secuencias import DatosNuevaSecuencia, DatosPaso
from sibutestlab8583.composicion import Composicion, Configuracion
from sibutestlab8583.domain.modelos import ORIGEN_PASO_INDEPENDIENTE, MTI_ECHO
from sibutestlab8583.profiles.generico import PERFIL_GENERICO
from sibutestlab8583.web.app import crear_app


def _host(**kwargs) -> HostSimulado:
    return HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), **kwargs)


async def test_la_corrida_muestra_los_intentos_de_un_paso_con_retry(base):
    composicion = Composicion(
        Configuracion(ruta_base_datos=base, host_destino="127.0.0.1", tiempo_limite=0.3)
    )
    host = _host(responder=False)
    app = crear_app(composicion)

    async with host:
        await composicion.administracion_conexiones.crear(
            DatosNuevaConexion(
                conexion_id="WEB-RETRY", nombre="Host simulado de la prueba",
                host=host.host, puerto=str(host.puerto),
            )
        )
        escenario = await composicion.administracion_escenarios.crear(
            DatosNuevoEscenario(nombre="Echo con retry web", conexion_id="WEB-RETRY", mti=MTI_ECHO)
        )
        secuencia = await composicion.administracion_secuencias.crear(
            DatosNuevaSecuencia(
                nombre="Retry visible en la web",
                pasos=[
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=escenario.escenario_id,
                        max_retries=1,
                    ),
                ],
            )
        )

        async def _permitir_responder_tras_el_primer_intento():
            while host.solicitudes_recibidas < 1:
                await asyncio.sleep(0.01)
            host._responder = True

        tarea = asyncio.create_task(_permitir_responder_tras_el_primer_intento())
        corrida = await composicion.ejecutor_secuencia.ejecutar(secuencia.secuencia_id)
        await tarea

    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://prueba"
    ) as cliente:
        detalle = await cliente.get(f"/secuencias/corridas/{corrida.corrida_id}")

    assert detalle.status_code == 200
    texto = detalle.text
    assert "Reintentos (C3): 2 intentos" in texto
    assert "1" in texto  # numero_intento 1
    assert "2" in texto  # numero_intento 2

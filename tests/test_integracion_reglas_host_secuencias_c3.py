"""Integracion D1 (reglas del Host) + C3 (retry de Echo), punto 28 del
checkpoint: "quiero poder crear una regla 0800 -> timeout y luego ejecutar
una secuencia C3 que tenga retry de Echo. Eso debe activar el retry sin
test doubles."

D1 no tiene reglas con estado (contador/`visto_antes`) todavia -deliberado,
punto 30/40: "no deformar D1" con stateful rules-. Por eso el SEGUNDO
intento se habilita alternando `activa` de la MISMA regla ya cargada en el
host real (`dataclasses.replace`, exactamente el mismo criterio ya usado en
`tests/test_retry_echo.py` para alternar `host._responder`): sigue siendo
el host real, la misma conexion TCP, el mismo motor de reglas -nunca un
adapter/doble que reemplace la evaluacion real-.
"""

from __future__ import annotations

import asyncio
import dataclasses

from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.sqlite_repos import (
    RepositorioCorridasSecuenciaSQLite,
    RepositorioDestinosSQLite,
    RepositorioEjecucionesSQLite,
    RepositorioEscenariosSQLite,
    RepositorioSecuenciasSQLite,
    RepositorioTarjetasSQLite,
)
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.adapters.transporte.tcp import TransporteTcp
from sibutestlab8583.application.conexiones import DatosNuevaConexion, ServicioConexiones
from sibutestlab8583.application.ejecutor_escenarios import EjecutorDeEscenarios
from sibutestlab8583.application.ejecutor_secuencia import EjecutorDeSecuencia
from sibutestlab8583.application.escenarios import DatosNuevoEscenario, ServicioEscenarios
from sibutestlab8583.application.secuencias import DatosNuevaSecuencia, DatosPaso, ServicioSecuencias
from sibutestlab8583.domain.modelos import ORIGEN_PASO_INDEPENDIENTE, MTI_ECHO, EstadoPasoSecuencia
from sibutestlab8583.domain.reglas_host import (
    CAMPO_MTI,
    CondicionRegla,
    ComportamientoRegla,
    ReglaHost,
    RespuestaRegla,
    TipoComportamiento,
)
from sibutestlab8583.profiles.generico import PERFIL_GENERICO


def _host(**kwargs) -> HostSimulado:
    return HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), **kwargs)


async def test_una_regla_de_timeout_activa_el_retry_de_echo_de_c3(base):
    regla_timeout = ReglaHost(
        nombre="Echo timeout (D1+C3)", prioridad=1, activa=True,
        condiciones=(CondicionRegla(CAMPO_MTI, "igual", MTI_ECHO),),
        respuesta=RespuestaRegla(de39="00"),
        comportamiento=ComportamientoRegla(tipo=TipoComportamiento.TIMEOUT.value),
    )
    host = _host(reglas=[regla_timeout])

    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=0.3)
        conexiones = ServicioConexiones(RepositorioDestinosSQLite(base))
        await conexiones.crear(
            DatosNuevaConexion(
                conexion_id="D1-C3-RETRY", nombre="Host simulado de la prueba",
                host=host.host, puerto=str(host.puerto),
            )
        )
        escenarios = ServicioEscenarios(
            RepositorioEscenariosSQLite(base), RepositorioTarjetasSQLite(base),
            RepositorioDestinosSQLite(base), PERFIL_GENERICO,
        )

        async def fabrica(destino, tiempo_limite):
            from conftest import construir_orquestador
            return construir_orquestador(base, transporte, destino=destino, tiempo_limite=tiempo_limite)

        ejecutor_escenarios = EjecutorDeEscenarios(escenarios, conexiones, fabrica)
        secuencias = ServicioSecuencias(RepositorioSecuenciasSQLite(base), RepositorioEscenariosSQLite(base))
        corridas = RepositorioCorridasSecuenciaSQLite(base)
        ejecutor = EjecutorDeSecuencia(
            secuencias, escenarios, ejecutor_escenarios, RepositorioEjecucionesSQLite(base),
            corridas, fabrica, PERFIL_GENERICO,
        )

        escenario = await escenarios.crear(
            DatosNuevoEscenario(nombre="Echo con retry (D1+C3)", conexion_id="D1-C3-RETRY", mti=MTI_ECHO)
        )
        secuencia = await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="Retry de Echo activado por una regla D1",
                pasos=[
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=escenario.escenario_id,
                        max_retries=1,
                    ),
                ],
            )
        )

        async def _desactivar_la_regla_tras_el_primer_intento():
            # Mismo criterio que alternar `host._responder` en C3: se
            # alterna la MISMA regla ya cargada en el host REAL en
            # ejecucion -nunca un doble, nunca un adapter de reemplazo. D1
            # no necesita "stateful rules" para esto: basta con que la
            # prueba, desde afuera, desactive la regla entre intentos.
            while host.solicitudes_recibidas < 1:
                await asyncio.sleep(0.01)
            host._reglas = (dataclasses.replace(regla_timeout, activa=False),)

        tarea = asyncio.create_task(_desactivar_la_regla_tras_el_primer_intento())
        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)
        await tarea

    pasos = await corridas.obtener_pasos(corrida.corrida_id)
    paso = pasos[0]
    # Primer intento: la regla D1 (TIMEOUT) goberno -> ERROR tecnico real.
    # Segundo intento: la regla ya esta inactiva -> cae al comportamiento
    # default del host (echo siempre aprueba) -> SIN_EXPECTATIVAS.
    assert paso.resultado is EstadoPasoSecuencia.SIN_EXPECTATIVAS
    assert paso.ejecucion_id is not None

    intentos = await corridas.obtener_intentos(corrida.corrida_id, paso.orden)
    assert len(intentos) == 2
    assert intentos[0].resultado is EstadoPasoSecuencia.ERROR
    assert intentos[1].resultado is EstadoPasoSecuencia.SIN_EXPECTATIVAS

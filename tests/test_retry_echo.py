"""Retry minimo y seguro (C3, 2026-09-14, puntos 7-11/23-24 del checkpoint).

Alcance deliberadamente angosto: `max_retries > 0` SOLO se admite hoy para
un paso independiente cuyo escenario es Echo (0800) -la unica operacion sin
efecto de negocio en este laboratorio (investigado explicitamente antes de
implementar, ver `domain.modelos.MAX_RETRIES_MINIMO`)-. Nunca 0200/0400/
0420: un timeout o una transmision indeterminada despues de enviarlos no
permite demostrar si el host ya proceso el mensaje, y reintentarlos
automaticamente arriesgaria duplicar un efecto financiero.

E2E real: TCP real, mismo `HostSimulado` que el resto de la suite -sin
tocar su codigo de produccion-: el flag `responder` (ya existente, atributo
de instancia simple) se alterna DESDE LA PRUEBA entre intentos para inducir
un timeout real en el primer intento y una respuesta real en el segundo,
sin expandir el simulador ni construir infraestructura nueva de Fase D.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal

import pytest

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
from sibutestlab8583.application.secuencias import (
    DatosNuevaSecuencia,
    DatosPaso,
    ServicioSecuencias,
)
from sibutestlab8583.domain.modelos import (
    ORIGEN_PASO_DERIVADO,
    ORIGEN_PASO_INDEPENDIENTE,
    EstadoEjecucion,
    EstadoPasoSecuencia,
    MTI_COMPRA_FINANCIERA,
    MTI_ECHO,
)
from sibutestlab8583.profiles.generico import PERFIL_GENERICO

from conftest import construir_orquestador


def _host(**kwargs) -> HostSimulado:
    return HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), **kwargs)


def _servicios(base, transporte):
    escenarios = ServicioEscenarios(
        RepositorioEscenariosSQLite(base), RepositorioTarjetasSQLite(base),
        RepositorioDestinosSQLite(base), PERFIL_GENERICO,
    )
    conexiones = ServicioConexiones(RepositorioDestinosSQLite(base))

    async def fabrica(destino, tiempo_limite):
        return construir_orquestador(base, transporte, destino=destino, tiempo_limite=tiempo_limite)

    ejecutor_escenarios = EjecutorDeEscenarios(escenarios, conexiones, fabrica)
    secuencias = ServicioSecuencias(RepositorioSecuenciasSQLite(base), RepositorioEscenariosSQLite(base))
    corridas = RepositorioCorridasSecuenciaSQLite(base)
    ejecuciones = RepositorioEjecucionesSQLite(base)
    ejecutor = EjecutorDeSecuencia(
        secuencias, escenarios, ejecutor_escenarios, ejecuciones, corridas, fabrica, PERFIL_GENERICO
    )
    return conexiones, escenarios, secuencias, ejecutor, corridas, ejecuciones


async def _crear_conexion(conexiones, host, conexion_id):
    await conexiones.crear(
        DatosNuevaConexion(
            conexion_id=conexion_id, nombre="Host simulado de la prueba",
            host=host.host, puerto=str(host.puerto),
        )
    )


async def test_max_retries_solo_se_admite_para_un_escenario_echo(base):
    """Punto 8: rechazado al GUARDAR la secuencia, no en ejecucion."""
    escenarios = ServicioEscenarios(
        RepositorioEscenariosSQLite(base), RepositorioTarjetasSQLite(base),
        RepositorioDestinosSQLite(base), PERFIL_GENERICO,
    )
    secuencias = ServicioSecuencias(RepositorioSecuenciasSQLite(base), RepositorioEscenariosSQLite(base))

    from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, DESTINO_ID_DEMO

    escenario_compra = await escenarios.crear(
        DatosNuevoEscenario(
            nombre="Compra (no Echo)", conexion_id=DESTINO_ID_DEMO,
            mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("10.00"),
        )
    )
    with pytest.raises(ValueError, match="Echo"):
        await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="Retry sobre compra financiera (rechazado)",
                pasos=[
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE,
                        escenario_id=escenario_compra.escenario_id, max_retries=2,
                    ),
                ],
            )
        )


async def test_un_paso_derivado_nunca_admite_retries_ni_siquiera_al_guardar(base):
    """Punto 8, reforzado: la restriccion de dominio (`PasoSecuencia.
    __post_init__`) ya rechaza esto antes de que `_validar_pasos` necesite
    consultar ningun escenario."""
    escenarios = ServicioEscenarios(
        RepositorioEscenariosSQLite(base), RepositorioTarjetasSQLite(base),
        RepositorioDestinosSQLite(base), PERFIL_GENERICO,
    )
    secuencias = ServicioSecuencias(RepositorioSecuenciasSQLite(base), RepositorioEscenariosSQLite(base))

    from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, DESTINO_ID_DEMO

    escenario = await escenarios.crear(
        DatosNuevoEscenario(
            nombre="Compra", conexion_id=DESTINO_ID_DEMO,
            mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("10.00"),
        )
    )
    with pytest.raises(ValueError, match="derivado"):
        await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="Retry sobre un reverso",
                pasos=[
                    DatosPaso(origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=escenario.escenario_id),
                    DatosPaso(origen_tipo=ORIGEN_PASO_DERIVADO, origen_paso_orden=1, max_retries=1),
                ],
            )
        )


async def test_retry_real_de_echo_timeout_en_el_primer_intento_exito_en_el_segundo(base):
    """Punto 24: primer intento induce un timeout real (host no responde);
    segundo intento SI responde -real, sin mocks-. El resultado final del
    paso es el del intento que SI tuvo respuesta, pero AMBOS intentos quedan
    auditables por separado (puntos 9-11)."""
    host = _host(responder=False)
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=0.3)
        conexiones, escenarios, secuencias, ejecutor, corridas, ejecuciones = _servicios(
            base, transporte
        )
        await _crear_conexion(conexiones, host, "C3-RETRY-1")

        escenario = await escenarios.crear(
            DatosNuevoEscenario(nombre="Echo con retry", conexion_id="C3-RETRY-1", mti=MTI_ECHO)
        )
        secuencia = await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="Retry real de Echo",
                pasos=[
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=escenario.escenario_id,
                        max_retries=1,
                    ),
                ],
            )
        )

        # El primer intento (dentro de ejecutor.ejecutar) vera responder=False
        # -timeout real-. Antes de que el motor llegue al SEGUNDO intento,
        # el host ya deberia estar respondiendo: como ambos intentos ocurren
        # en la misma llamada sincronica, alternamos el flag de la MISMA
        # instancia ya corriendo a partir de la primera solicitud recibida
        # -sigue siendo el host real, la misma conexion TCP, nunca un doble.
        async def _permitir_responder_tras_el_primer_intento():
            while host.solicitudes_recibidas < 1:
                await asyncio.sleep(0.01)
            host._responder = True

        tarea = asyncio.create_task(_permitir_responder_tras_el_primer_intento())
        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)
        await tarea

    pasos = await corridas.obtener_pasos(corrida.corrida_id)
    paso = pasos[0]
    assert paso.resultado is EstadoPasoSecuencia.SIN_EXPECTATIVAS
    assert paso.ejecucion_id is not None

    ejecucion_final = await ejecuciones.obtener(paso.ejecucion_id)
    assert ejecucion_final.estado is EstadoEjecucion.APROBADA

    intentos = await corridas.obtener_intentos(corrida.corrida_id, paso.orden)
    assert len(intentos) == 2
    assert intentos[0].numero_intento == 1
    assert intentos[0].resultado is EstadoPasoSecuencia.ERROR
    assert intentos[1].numero_intento == 2
    assert intentos[1].resultado is EstadoPasoSecuencia.SIN_EXPECTATIVAS
    assert intentos[1].ejecucion_id == paso.ejecucion_id


async def test_sin_retry_configurado_un_timeout_no_reintenta(base):
    """Comportamiento por defecto (`max_retries=0`, el de C1): un timeout
    real en un Echo SIN retry configurado queda ERROR de una vez, sin
    ningun intento adicional ni fila en la tabla de intentos."""
    host = _host(responder=False)
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=0.2)
        conexiones, escenarios, secuencias, ejecutor, corridas, _ = _servicios(base, transporte)
        await _crear_conexion(conexiones, host, "C3-RETRY-2")

        escenario = await escenarios.crear(
            DatosNuevoEscenario(nombre="Echo sin retry", conexion_id="C3-RETRY-2", mti=MTI_ECHO)
        )
        secuencia = await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="Sin retry",
                pasos=[
                    DatosPaso(origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=escenario.escenario_id),
                ],
            )
        )
        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)

    pasos = await corridas.obtener_pasos(corrida.corrida_id)
    assert pasos[0].resultado is EstadoPasoSecuencia.ERROR

    intentos = await corridas.obtener_intentos(corrida.corrida_id, pasos[0].orden)
    assert len(intentos) == 0

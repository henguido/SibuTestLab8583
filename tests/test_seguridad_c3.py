"""Seguridad de las superficies nuevas de C3 (2026-09-14, punto 23 del
checkpoint): razones de politica, intentos de retry, y expectativas
dinamicas nunca revelan datos sensibles -ni PAN, ni texto de excepcion
crudo, ni traceback-.
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest

from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO
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
    ExpectativaCampo,
    Expectativas,
    EstadoEjecucion,
    PoliticaContinuacion,
    MTI_COMPRA_FINANCIERA,
)
from sibutestlab8583.profiles.generico import PERFIL_GENERICO

from conftest import construir_orquestador

#: Misma heuristica que `test_datos_sinteticos.py::
#: test_ningun_archivo_versionable_contiene_un_pan_completo`: una secuencia
#: de 12-19 digitos consecutivos es indistinguible de un PAN real.
_PATRON_PAN = re.compile(r"\d{12,19}")


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


async def test_el_motivo_de_detenido_por_politica_nunca_incluye_texto_crudo(base):
    """El `detalle` de un paso BLOQUEADO por politica DETENER solo describe
    ORDEN y CAUSA en texto fijo y seguro -nunca la excepcion real, nunca un
    traceback."""
    host = _host(responder=False)
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=0.2)
        conexiones, escenarios, secuencias, ejecutor, corridas, _ = _servicios(base, transporte)
        await _crear_conexion(conexiones, host, "C3-SEC-1")

        paso1 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Paso 1 (timeout)", conexion_id="C3-SEC-1",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("40.00"),
            )
        )
        paso2 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Paso 2", conexion_id="C3-SEC-1",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("41.00"),
            )
        )
        secuencia = await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="Seguridad DETENER",
                pasos=[
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso1.escenario_id,
                        on_error=PoliticaContinuacion.DETENER.value,
                    ),
                    DatosPaso(origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso2.escenario_id),
                ],
            )
        )
        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)

    pasos = sorted(await corridas.obtener_pasos(corrida.corrida_id), key=lambda p: p.orden)
    detalle = pasos[1].detalle
    assert detalle == (
        "No se ejecutó: el paso 1 terminó en ERROR y su política de continuación es DETENER."
    )
    # Ni traceback, ni nombres de excepcion, ni referencias a modulos internos.
    for palabra_prohibida in ("Traceback", "Exception", "raise", ".py", "socket"):
        assert palabra_prohibida not in detalle


async def test_los_intentos_de_retry_nunca_contienen_datos_de_tarjeta(base):
    """Retry solo aplica a Echo (sin card_id, ver C3.5): confirma
    estructuralmente que ningun intento persistido puede cargar un PAN,
    ademas de que su detalle sigue siendo texto generico y seguro."""
    from sibutestlab8583.domain.modelos import MTI_ECHO

    host = _host(responder=False)
    async with host:
        import asyncio

        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=0.3)
        conexiones, escenarios, secuencias, ejecutor, corridas, _ = _servicios(base, transporte)
        await _crear_conexion(conexiones, host, "C3-SEC-2")

        escenario = await escenarios.crear(
            DatosNuevoEscenario(nombre="Echo con retry", conexion_id="C3-SEC-2", mti=MTI_ECHO)
        )
        assert escenario.card_id is None  # Echo nunca tiene tarjeta -nada que filtrar.

        secuencia = await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="Seguridad retry",
                pasos=[
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=escenario.escenario_id,
                        max_retries=1,
                    ),
                ],
            )
        )

        async def _permitir_responder():
            while host.solicitudes_recibidas < 1:
                await asyncio.sleep(0.01)
            host._responder = True

        tarea = asyncio.create_task(_permitir_responder())
        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)
        await tarea

    pasos = await corridas.obtener_pasos(corrida.corrida_id)
    intentos = await corridas.obtener_intentos(corrida.corrida_id, pasos[0].orden)
    assert len(intentos) == 2
    for intento in intentos:
        if intento.detalle:
            assert not _PATRON_PAN.search(intento.detalle)


async def test_expectativa_dinamica_resuelta_nunca_expone_un_campo_sensible(base):
    """Confirma, ademas de la excepcion ya probada en
    test_expectativas_dinamicas.py, que si por algun motivo la resolucion
    avanzara, el `detalle` de auditoria de un paso PASS/FAIL nunca contiene
    una secuencia con forma de PAN -campo no sensible resuelto, DE39-."""
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        conexiones, escenarios, secuencias, ejecutor, corridas, _ = _servicios(base, transporte)
        await _crear_conexion(conexiones, host, "C3-SEC-3")

        paso1 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Paso 1 (compra)", conexion_id="C3-SEC-3",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("45.00"),
            )
        )
        secuencia = await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="Seguridad expectativa dinamica",
                pasos=[
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso1.escenario_id,
                        paso_id="purchase",
                    ),
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_DERIVADO, origen_paso_orden=1, paso_id="reversal",
                        expectativas=Expectativas(
                            campos={"39": ExpectativaCampo(
                                tipo="igual", valor="{{step.purchase.response.de39}}"
                            )}
                        ),
                    ),
                ],
            )
        )
        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)

    pasos = sorted(await corridas.obtener_pasos(corrida.corrida_id), key=lambda p: p.orden)
    detalle = pasos[1].detalle
    assert detalle is not None
    assert not _PATRON_PAN.search(detalle)

"""`EjecutorDeSecuencia` con politica de continuacion (STOP/CONTINUE, C3).

E2E real: TCP real, codec real, SQLite real, host simulado real -mismo
estilo que `test_ejecutor_secuencia.py`-. Cubre los casos exigidos por el
checkpoint (puntos 17-22): CONTINUAR deja correr pasos independientes
posteriores sin importar el resultado del anterior; DETENER bloquea TODOS
los pasos siguientes; ninguna politica de flujo puede saltarse una
precondicion de dominio (un paso derivado sigue BLOQUEADO por elegibilidad
aunque la politica diga CONTINUAR); SIN_EXPECTATIVAS nunca activa
`on_qa_fail`; el resultado global nunca es "el ultimo paso gana".
"""

from __future__ import annotations

from decimal import Decimal

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
    MTI_COMPRA_FINANCIERA,
    EstadoEjecucion,
    EstadoPasoSecuencia,
    Expectativas,
    PoliticaContinuacion,
    ResultadoGlobalSuite,
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


async def test_continuar_deja_correr_un_paso_independiente_pese_a_un_fail_qa_previo(base):
    """Punto 17: Paso 1 FAIL QA con on_qa_fail=CONTINUAR -> Paso 2
    independiente SI se ejecuta."""
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        conexiones, escenarios, secuencias, ejecutor, corridas, _ = _servicios(base, transporte)
        await _crear_conexion(conexiones, host, "C3-CONT-1")

        # Rechazo por monto, con expectativa de APROBADA -> FAIL QA real.
        paso1 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Paso 1 (fail qa)", conexion_id="C3-CONT-1",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("500000.00"),
                expectativas=Expectativas(estado=EstadoEjecucion.APROBADA),
            )
        )
        paso2 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Paso 2 (independiente)", conexion_id="C3-CONT-1",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("30.00"),
            )
        )
        secuencia = await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="CONTINUAR tras FAIL QA",
                pasos=[
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso1.escenario_id,
                        on_qa_fail=PoliticaContinuacion.CONTINUAR.value,
                    ),
                    DatosPaso(origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso2.escenario_id),
                ],
            )
        )
        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)

    pasos = sorted(await corridas.obtener_pasos(corrida.corrida_id), key=lambda p: p.orden)
    assert pasos[0].resultado is EstadoPasoSecuencia.FAIL
    assert pasos[1].resultado is EstadoPasoSecuencia.SIN_EXPECTATIVAS
    assert pasos[1].ejecucion_id is not None


async def test_continuar_no_rompe_la_precondicion_de_un_reverso_derivado(base):
    """Punto 18: Paso 1 (0200 rechazada, expectativa APROBADA -> FAIL QA),
    on_qa_fail=CONTINUAR. Paso 2 (reverso derivado del paso 1) debe seguir
    BLOQUEADO por elegibilidad -CONTINUAR nunca inventa un origen elegible."""
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        conexiones, escenarios, secuencias, ejecutor, corridas, _ = _servicios(base, transporte)
        await _crear_conexion(conexiones, host, "C3-CONT-2")

        paso1 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Paso 1 (rechazada, fail qa)", conexion_id="C3-CONT-2",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("500000.00"),
                expectativas=Expectativas(estado=EstadoEjecucion.APROBADA),
            )
        )
        secuencia = await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="CONTINUAR no rompe elegibilidad",
                pasos=[
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso1.escenario_id,
                        on_qa_fail=PoliticaContinuacion.CONTINUAR.value,
                    ),
                    DatosPaso(origen_tipo=ORIGEN_PASO_DERIVADO, origen_paso_orden=1),
                ],
            )
        )
        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)

    pasos = sorted(await corridas.obtener_pasos(corrida.corrida_id), key=lambda p: p.orden)
    assert pasos[0].resultado is EstadoPasoSecuencia.FAIL
    assert pasos[1].resultado is EstadoPasoSecuencia.BLOQUEADO
    assert pasos[1].ejecucion_id is None


async def test_resultado_global_no_es_el_ultimo_paso_gana(base):
    """Punto 19: Paso 1 FAIL QA (on_qa_fail=CONTINUAR), Paso 2 independiente
    en PASS -> resultado global FAIL, aunque el ultimo paso haya pasado."""
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        conexiones, escenarios, secuencias, ejecutor, corridas, _ = _servicios(base, transporte)
        await _crear_conexion(conexiones, host, "C3-CONT-3")

        paso1 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Paso 1 (fail qa)", conexion_id="C3-CONT-3",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("500000.00"),
                expectativas=Expectativas(estado=EstadoEjecucion.APROBADA),
            )
        )
        paso2 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Paso 2 (pass)", conexion_id="C3-CONT-3",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("30.00"),
                expectativas=Expectativas(estado=EstadoEjecucion.APROBADA),
            )
        )
        secuencia = await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="Resultado global no es el ultimo paso",
                pasos=[
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso1.escenario_id,
                        on_qa_fail=PoliticaContinuacion.CONTINUAR.value,
                    ),
                    DatosPaso(origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso2.escenario_id),
                ],
            )
        )
        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)

    pasos = sorted(await corridas.obtener_pasos(corrida.corrida_id), key=lambda p: p.orden)
    assert pasos[0].resultado is EstadoPasoSecuencia.FAIL
    assert pasos[1].resultado is EstadoPasoSecuencia.PASS
    assert corrida.resultado_global == ResultadoGlobalSuite.FAIL


async def test_sin_expectativas_nunca_activa_on_qa_fail(base):
    """Punto 20: un paso SIN_EXPECTATIVAS (aprobada o rechazada sin nada que
    comparar) nunca dispara `on_qa_fail`, aunque este en DETENER: el paso
    siguiente debe ejecutarse con normalidad."""
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        conexiones, escenarios, secuencias, ejecutor, corridas, _ = _servicios(base, transporte)
        await _crear_conexion(conexiones, host, "C3-CONT-4")

        paso1 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Paso 1 (sin expectativas)", conexion_id="C3-CONT-4",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("40.00"),
            )
        )
        paso2 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Paso 2 (independiente)", conexion_id="C3-CONT-4",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("41.00"),
            )
        )
        secuencia = await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="SIN_EXPECTATIVAS nunca detiene",
                pasos=[
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso1.escenario_id,
                        on_qa_fail=PoliticaContinuacion.DETENER.value,
                        on_error=PoliticaContinuacion.DETENER.value,
                    ),
                    DatosPaso(origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso2.escenario_id),
                ],
            )
        )
        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)

    pasos = sorted(await corridas.obtener_pasos(corrida.corrida_id), key=lambda p: p.orden)
    assert pasos[0].resultado is EstadoPasoSecuencia.SIN_EXPECTATIVAS
    assert pasos[1].resultado is EstadoPasoSecuencia.SIN_EXPECTATIVAS
    assert pasos[1].ejecucion_id is not None


async def test_detener_bloquea_todos_los_pasos_siguientes_tras_un_error(base):
    """Punto 21 (primer caso): Paso 1 ERROR (timeout, on_error=DETENER) ->
    TODOS los pasos siguientes quedan BLOQUEADO, con el motivo explicando
    que fue la politica de continuacion -no una precondicion de dominio-."""
    host = _host(responder=False)
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=0.2)
        conexiones, escenarios, secuencias, ejecutor, corridas, ejecuciones = _servicios(
            base, transporte
        )
        await _crear_conexion(conexiones, host, "C3-DET-1")

        paso1 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Paso 1 (timeout)", conexion_id="C3-DET-1",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("40.00"),
            )
        )
        paso2 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Paso 2 (independiente, nunca deberia correr)", conexion_id="C3-DET-1",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("41.00"),
            )
        )
        secuencia = await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="DETENER tras ERROR",
                pasos=[
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso1.escenario_id,
                        on_error=PoliticaContinuacion.DETENER.value,
                    ),
                    DatosPaso(origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso2.escenario_id),
                    DatosPaso(origen_tipo=ORIGEN_PASO_DERIVADO, origen_paso_orden=1),
                ],
            )
        )
        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)

    pasos = sorted(await corridas.obtener_pasos(corrida.corrida_id), key=lambda p: p.orden)
    assert pasos[0].resultado is EstadoPasoSecuencia.ERROR
    assert "timeout" in pasos[0].detalle.lower()
    assert pasos[1].resultado is EstadoPasoSecuencia.BLOQUEADO
    assert pasos[1].ejecucion_id is None
    assert "política de continuación" in pasos[1].detalle.lower()
    assert pasos[2].resultado is EstadoPasoSecuencia.BLOQUEADO
    assert pasos[2].ejecucion_id is None
    assert corrida.resultado_global == ResultadoGlobalSuite.ERROR

    # El paso 1 SI se persistio como ejecucion TIMEOUT real -el error tecnico
    # ocurrio de verdad, no se simulo-.
    ejecucion_1 = await ejecuciones.obtener(pasos[0].ejecucion_id)
    assert ejecucion_1.estado is EstadoEjecucion.TIMEOUT


async def test_continuar_tras_error_deja_correr_independientes_pero_no_rompe_dependientes(base):
    """Punto 21 (segundo caso): on_error=CONTINUAR -> el paso independiente
    siguiente SI corre; el paso derivado que depende del que fallo sigue
    BLOQUEADO (por elegibilidad, no por la politica)."""
    host = _host(responder=False)
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=0.2)
        conexiones, escenarios, secuencias, ejecutor, corridas, _ = _servicios(base, transporte)
        await _crear_conexion(conexiones, host, "C3-DET-2")

        paso1 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Paso 1 (timeout)", conexion_id="C3-DET-2",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("40.00"),
            )
        )
        paso2 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Paso 2 (independiente)", conexion_id="C3-DET-2",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("41.00"),
            )
        )
        secuencia = await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="CONTINUAR tras ERROR",
                pasos=[
                    DatosPaso(origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso1.escenario_id),
                    DatosPaso(origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso2.escenario_id),
                    DatosPaso(origen_tipo=ORIGEN_PASO_DERIVADO, origen_paso_orden=1),
                ],
            )
        )
        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)

    pasos = sorted(await corridas.obtener_pasos(corrida.corrida_id), key=lambda p: p.orden)
    assert pasos[0].resultado is EstadoPasoSecuencia.ERROR
    # CONTINUAR (default): el paso 2 independiente SI se intento y corrio.
    assert pasos[1].resultado is not EstadoPasoSecuencia.BLOQUEADO
    assert pasos[1].ejecucion_id is not None
    # El paso 3 (derivado del 1, que fallo tecnicamente) sigue BLOQUEADO
    # -por elegibilidad, nunca por la politica-.
    assert pasos[2].resultado is EstadoPasoSecuencia.BLOQUEADO
    assert pasos[2].ejecucion_id is None

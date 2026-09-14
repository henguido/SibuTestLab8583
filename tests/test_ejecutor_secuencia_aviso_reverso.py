"""`EjecutorDeSecuencia` con un paso derivado de tipo aviso de reverso (B8).

E2E real (TCP/codec/SQLite/host simulado reales, sin dobles), espejo de
`test_ejecutor_secuencia.py` -que solo cubria el reverso financiero (C1)-.
Cubre el recorrido exigido por el checkpoint (punto 16):

    Paso "purchase": compra financiera (0200) -> 0210/00 -> ejecucion A
    Paso "reversal_advice": aviso de reverso derivado de "purchase"
        -> 0420 -> 0430/00 -> ejecucion B
    ejecucion_origen_id (B) == A, resuelto via ContextoSecuencia (por
    orden), SIN ejecucion_id fijo -mismo mecanismo estructural que C1 usa
    para el reverso financiero, nunca las variables de paso de C2 (punto 17
    del checkpoint B8: una operacion derivada completa sigue usando
    `ReferenciaEjecucion`/`ContextoSecuencia`, no `{{step...}}`).

Y las mismas negativas obligatorias que ya protege el reverso financiero
(puntos 19/20/21): 0200 rechazada bloquea el aviso, timeout en el primer
paso bloquea el aviso, y por separado, misma expectativa por paso que ya
evalua el motor sin ningun caso especial para 0420.
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
    OPERACION_AVISO_REVERSO,
    MTI_COMPRA_FINANCIERA,
    EstadoEjecucion,
    EstadoPasoSecuencia,
    Expectativas,
    ExpectativaCampo,
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
    ejecutor_secuencia = EjecutorDeSecuencia(
        secuencias, escenarios, ejecutor_escenarios, ejecuciones, corridas, fabrica, PERFIL_GENERICO
    )
    return conexiones, escenarios, secuencias, ejecutor_secuencia, corridas


async def _crear_conexion(conexiones: ServicioConexiones, host: HostSimulado, conexion_id: str):
    await conexiones.crear(
        DatosNuevaConexion(
            conexion_id=conexion_id, nombre="Host simulado de la prueba",
            host=host.host, puerto=str(host.puerto),
        )
    )


async def _crear_secuencia_compra_y_aviso(
    escenarios: ServicioEscenarios, secuencias: ServicioSecuencias, conexion_id: str,
    *, monto=Decimal("70.00"), nombre="Compra + aviso de reverso",
    expectativas_compra=None, expectativas_aviso=None,
):
    escenario = await escenarios.crear(
        DatosNuevoEscenario(
            nombre="Compra financiera de la secuencia", conexion_id=conexion_id,
            mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=monto,
            expectativas=expectativas_compra,
        )
    )
    return await secuencias.crear(
        DatosNuevaSecuencia(
            nombre=nombre,
            pasos=[
                DatosPaso(
                    origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=escenario.escenario_id,
                    paso_id="purchase",
                ),
                DatosPaso(
                    origen_tipo=ORIGEN_PASO_DERIVADO, origen_paso_orden=1,
                    paso_id="reversal_advice", operacion_derivada=OPERACION_AVISO_REVERSO,
                    expectativas=expectativas_aviso,
                ),
            ],
        )
    )


async def test_secuencia_real_compra_financiera_y_aviso_de_reverso(base):
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        conexiones, escenarios, secuencias, ejecutor, corridas = _servicios(base, transporte)
        await _crear_conexion(conexiones, host, "SEQ-B8")
        secuencia = await _crear_secuencia_compra_y_aviso(escenarios, secuencias, "SEQ-B8")

        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)

    assert corrida.total == 2
    assert corrida.resultado_global == ResultadoGlobalSuite.SIN_EXPECTATIVAS
    assert corrida.cantidad_sin_expectativas == 2
    assert corrida.cantidad_bloqueado == 0

    pasos = await corridas.obtener_pasos(corrida.corrida_id)
    paso1, paso2 = sorted(pasos, key=lambda p: p.orden)
    assert paso1.resultado is EstadoPasoSecuencia.SIN_EXPECTATIVAS
    assert paso2.resultado is EstadoPasoSecuencia.SIN_EXPECTATIVAS
    assert paso1.ejecucion_id is not None
    assert paso2.ejecucion_id is not None
    assert paso1.paso_id == "purchase"
    assert paso2.paso_id == "reversal_advice"

    repo_ejecuciones = RepositorioEjecucionesSQLite(base)
    ejecucion_2 = await repo_ejecuciones.obtener(paso2.ejecucion_id)
    ejecucion_1 = await repo_ejecuciones.obtener(paso1.ejecucion_id)
    assert ejecucion_2.mti_solicitud == "0420"
    assert ejecucion_2.mti_respuesta == "0430"
    # Nucleo del punto 16/17: la identidad del origen se resuelve via
    # ContextoSecuencia (estructural, por orden) -nunca un ejecucion_id fijo
    # escrito a mano en la definicion, y nunca reemplazado por una variable
    # de paso de C2.
    assert ejecucion_2.ejecucion_origen_id == paso1.ejecucion_id
    assert ejecucion_2.stan != ejecucion_1.stan


async def test_una_financiera_rechazada_bloquea_el_aviso_de_reverso(base):
    """Punto 20 del checkpoint: 0200 -> 0210/51 debe producir el aviso
    BLOQUEADO, nunca ejecutar un 0420 sobre un origen no elegible."""
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        conexiones, escenarios, secuencias, ejecutor, corridas = _servicios(base, transporte)
        await _crear_conexion(conexiones, host, "SEQ-B8-RECHAZO")
        secuencia = await _crear_secuencia_compra_y_aviso(
            escenarios, secuencias, "SEQ-B8-RECHAZO", monto=Decimal("500000.00"),
        )

        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)

    assert corrida.cantidad_bloqueado == 1
    assert corrida.resultado_global == ResultadoGlobalSuite.INCOMPLETA

    pasos = await corridas.obtener_pasos(corrida.corrida_id)
    paso1, paso2 = sorted(pasos, key=lambda p: p.orden)
    assert paso1.resultado is EstadoPasoSecuencia.SIN_EXPECTATIVAS
    assert paso1.ejecucion_id is not None
    assert paso2.resultado is EstadoPasoSecuencia.BLOQUEADO
    assert paso2.ejecucion_id is None  # nunca se genero ningun 0420


async def test_timeout_en_el_primer_paso_bloquea_el_aviso_de_reverso(base):
    """Punto 21: ERROR/TIMEOUT en el paso origen -> paso 2 NO se ejecuta, sin
    generar ninguna ejecucion 0420."""
    host = _host(responder=False)
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=0.2)
        conexiones, escenarios, secuencias, ejecutor, corridas = _servicios(base, transporte)
        await _crear_conexion(conexiones, host, "SEQ-B8-TIMEOUT")
        secuencia = await _crear_secuencia_compra_y_aviso(escenarios, secuencias, "SEQ-B8-TIMEOUT")

        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)

    assert corrida.cantidad_bloqueado == 1
    pasos = await corridas.obtener_pasos(corrida.corrida_id)
    paso1, paso2 = sorted(pasos, key=lambda p: p.orden)
    assert paso1.ejecucion_id is not None
    assert paso2.resultado is EstadoPasoSecuencia.BLOQUEADO
    assert paso2.ejecucion_id is None


async def test_expectativas_por_paso_se_evaluan_sin_caso_especial_para_0420(base):
    """Punto 19: paso 1 puede esperar DE39=00, paso 2 (aviso) tambien -el
    motor ya existente evalua ambos sin ningun if especial para 0420."""
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        conexiones, escenarios, secuencias, ejecutor, corridas = _servicios(base, transporte)
        await _crear_conexion(conexiones, host, "SEQ-B8-EXPECT")
        secuencia = await _crear_secuencia_compra_y_aviso(
            escenarios, secuencias, "SEQ-B8-EXPECT",
            expectativas_compra=Expectativas(estado=EstadoEjecucion.APROBADA),
            expectativas_aviso=Expectativas(
                estado=EstadoEjecucion.APROBADA,
                campos={"39": ExpectativaCampo(tipo="igual", valor="00")},
            ),
        )

        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)

    assert corrida.resultado_global == ResultadoGlobalSuite.PASS
    pasos = await corridas.obtener_pasos(corrida.corrida_id)
    paso1, paso2 = sorted(pasos, key=lambda p: p.orden)
    assert paso1.resultado is EstadoPasoSecuencia.PASS
    assert paso2.resultado is EstadoPasoSecuencia.PASS


async def test_una_secuencia_puede_tener_pasos_de_reverso_y_de_aviso_distintos(base):
    """No hay UI para esto (mismo criterio que C2), pero el motor de
    secuencias soporta representar ambas operaciones derivadas dentro de la
    misma corrida via `operacion_derivada` por paso -aqui, dos pasos
    derivados independientes del mismo origen."""
    from sibutestlab8583.domain.modelos import OPERACION_REVERSO_FINANCIERO

    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        conexiones, escenarios, secuencias, ejecutor, corridas = _servicios(base, transporte)
        await _crear_conexion(conexiones, host, "SEQ-B8-AMBAS")

        escenario = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Compra financiera", conexion_id="SEQ-B8-AMBAS",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("50.00"),
            )
        )
        secuencia = await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="Compra + reverso + aviso de reverso",
                pasos=[
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=escenario.escenario_id,
                        paso_id="purchase",
                    ),
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_DERIVADO, origen_paso_orden=1,
                        paso_id="reversal", operacion_derivada=OPERACION_REVERSO_FINANCIERO,
                    ),
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_DERIVADO, origen_paso_orden=1,
                        paso_id="reversal_advice", operacion_derivada=OPERACION_AVISO_REVERSO,
                    ),
                ],
            )
        )

        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)

    assert corrida.cantidad_bloqueado == 0
    pasos = await corridas.obtener_pasos(corrida.corrida_id)
    por_paso_id = {p.paso_id: p for p in pasos}

    repo_ejecuciones = RepositorioEjecucionesSQLite(base)
    ejecucion_reverso = await repo_ejecuciones.obtener(por_paso_id["reversal"].ejecucion_id)
    ejecucion_aviso = await repo_ejecuciones.obtener(por_paso_id["reversal_advice"].ejecucion_id)

    assert ejecucion_reverso.mti_solicitud == "0400"
    assert ejecucion_aviso.mti_solicitud == "0420"
    assert ejecucion_reverso.ejecucion_origen_id == por_paso_id["purchase"].ejecucion_id
    assert ejecucion_aviso.ejecucion_origen_id == por_paso_id["purchase"].ejecucion_id

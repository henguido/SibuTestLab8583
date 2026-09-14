"""`EjecutorDeSecuencia`: ejecucion completa de una secuencia (Fase C1).

E2E real (TCP/codec/SQLite/host simulado reales, sin dobles) -mismo estilo
que `test_orquestador_reverso_financiero.py`-: cubre el recorrido completo
exigido por el checkpoint (puntos 27/28/29):

    Paso 1: compra financiera (0200) -> 0210/00 -> ejecucion A
    Paso 2: reverso derivado del paso 1 -> 0400 -> 0410/00 -> ejecucion B
    ejecucion_origen_id (B) == A

y las dos negativas obligatorias: 0200 rechazada (paso 2 BLOQUEADO, nunca
0400) y error/timeout en el paso 1 (paso 2 BLOQUEADO, ninguna ejecucion 0400
generada).
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
from sibutestlab8583.application.conexiones import (
    DatosNuevaConexion,
    ServicioConexiones,
)
from sibutestlab8583.application.ejecutor_escenarios import EjecutorDeEscenarios
from sibutestlab8583.application.ejecutor_secuencia import (
    EjecutorDeSecuencia,
    SecuenciaNoEjecutable,
)
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
    ExpectativaCampo,
    Expectativas,
    ResultadoGlobalSuite,
)
from sibutestlab8583.profiles.generico import PERFIL_GENERICO

import pytest

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


async def _crear_secuencia_compra_y_reverso(
    escenarios: ServicioEscenarios, secuencias: ServicioSecuencias, conexion_id: str,
    *, monto=Decimal("70.00"), nombre="Compra + reverso",
):
    escenario = await escenarios.crear(
        DatosNuevoEscenario(
            nombre="Compra financiera de la secuencia", conexion_id=conexion_id,
            mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=monto,
        )
    )
    return await secuencias.crear(
        DatosNuevaSecuencia(
            nombre=nombre,
            pasos=[
                DatosPaso(origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=escenario.escenario_id),
                DatosPaso(origen_tipo=ORIGEN_PASO_DERIVADO, origen_paso_orden=1),
            ],
        )
    )


async def test_secuencia_real_compra_financiera_y_reverso(base):
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        conexiones, escenarios, secuencias, ejecutor, corridas = _servicios(base, transporte)
        await _crear_conexion(conexiones, host, "SEQ-C1")
        secuencia = await _crear_secuencia_compra_y_reverso(escenarios, secuencias, "SEQ-C1")

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

    # Semantica critica (protegida explicitamente, punto priorizado por el
    # propietario tras revisar la Corrida #1 real): dos transacciones
    # APROBADAS sin ninguna expectativa QA definida es SIN_EXPECTATIVAS,
    # NUNCA un PASS implicito -mismo principio que domain.expectativas.
    # evaluar_expectativas ya aplica a una sola ejecucion, elevado aqui al
    # agregado de la secuencia.
    assert paso1.resultado is not EstadoPasoSecuencia.PASS
    assert paso2.resultado is not EstadoPasoSecuencia.PASS
    assert corrida.resultado_global is not ResultadoGlobalSuite.PASS
    assert corrida.cantidad_pass == 0

    repo_ejecuciones = RepositorioEjecucionesSQLite(base)
    ejecucion_2 = await repo_ejecuciones.obtener(paso2.ejecucion_id)
    ejecucion_1 = await repo_ejecuciones.obtener(paso1.ejecucion_id)
    assert ejecucion_2.mti_solicitud == "0400"
    assert ejecucion_2.mti_respuesta == "0410"
    assert ejecucion_2.ejecucion_origen_id == paso1.ejecucion_id
    assert ejecucion_2.stan != ejecucion_1.stan


async def test_una_financiera_rechazada_bloquea_el_reverso(base):
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        conexiones, escenarios, secuencias, ejecutor, corridas = _servicios(base, transporte)
        await _crear_conexion(conexiones, host, "SEQ-C1-RECHAZO")
        # Por encima del umbral sintetico de rechazo del host simulado.
        secuencia = await _crear_secuencia_compra_y_reverso(
            escenarios, secuencias, "SEQ-C1-RECHAZO", monto=Decimal("500000.00"),
        )

        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)

    assert corrida.cantidad_bloqueado == 1
    assert corrida.resultado_global == ResultadoGlobalSuite.INCOMPLETA

    pasos = await corridas.obtener_pasos(corrida.corrida_id)
    paso1, paso2 = sorted(pasos, key=lambda p: p.orden)
    assert paso1.resultado is EstadoPasoSecuencia.SIN_EXPECTATIVAS  # la 0200 SI se ejecuto
    assert paso1.ejecucion_id is not None
    assert paso2.resultado is EstadoPasoSecuencia.BLOQUEADO
    assert paso2.ejecucion_id is None  # nunca se genero ningun 0400


async def test_una_financiera_rechazada_con_expectativa_correcta_es_pass_qa(base):
    """Semantica contraria a la de arriba, protegida a proposito (punto
    priorizado por el propietario): una transaccion RECHAZADA (DE39=51) NO
    es un fallo de QA si el escenario esperaba exactamente ese desenlace
    -EstadoEjecucion (transaccional) y EstadoEvaluacion (QA) son ejes
    independientes, ver domain/expectativas.py-. El paso 1 debe marcar PASS
    aunque la 0200 haya sido rechazada de verdad.
    """
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        conexiones, escenarios, secuencias, ejecutor, corridas = _servicios(base, transporte)
        await _crear_conexion(conexiones, host, "SEQ-C1-PASS-RECHAZO")

        escenario = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Financiera con expectativa de rechazo", conexion_id="SEQ-C1-PASS-RECHAZO",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("500000.00"),
                expectativas=Expectativas(estado=EstadoEjecucion.RECHAZADA),
            )
        )
        secuencia = await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="Rechazo esperado + reverso (no elegible)",
                pasos=[
                    DatosPaso(origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=escenario.escenario_id),
                    DatosPaso(origen_tipo=ORIGEN_PASO_DERIVADO, origen_paso_orden=1),
                ],
            )
        )

        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)

    pasos = await corridas.obtener_pasos(corrida.corrida_id)
    paso1, paso2 = sorted(pasos, key=lambda p: p.orden)

    # El paso 1 es PASS de QA -la 0200 se rechazo exactamente como se esperaba-,
    # sin que eso implique que la transaccion "tuvo exito" ni que el reverso
    # se vuelva elegible: son preguntas independientes.
    assert paso1.resultado is EstadoPasoSecuencia.PASS
    repo_ejecuciones = RepositorioEjecucionesSQLite(base)
    ejecucion_1 = await repo_ejecuciones.obtener(paso1.ejecucion_id)
    assert ejecucion_1.estado is EstadoEjecucion.RECHAZADA

    # El paso 2 sigue BLOQUEADO: un PASS de QA no vuelve elegible un origen
    # que domain.elegibilidad_reverso ya rechazo (solo 0200 APROBADA sirve).
    assert paso2.resultado is EstadoPasoSecuencia.BLOQUEADO
    assert paso2.ejecucion_id is None


async def test_timeout_en_el_primer_paso_bloquea_el_reverso(base):
    host = _host(responder=False)
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=0.2)
        conexiones, escenarios, secuencias, ejecutor, corridas = _servicios(base, transporte)
        await _crear_conexion(conexiones, host, "SEQ-C1-TIMEOUT")
        secuencia = await _crear_secuencia_compra_y_reverso(escenarios, secuencias, "SEQ-C1-TIMEOUT")

        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)

    assert corrida.cantidad_bloqueado == 1
    pasos = await corridas.obtener_pasos(corrida.corrida_id)
    paso1, paso2 = sorted(pasos, key=lambda p: p.orden)
    assert paso1.ejecucion_id is not None  # el timeout SI se persiste como ejecucion
    assert paso2.resultado is EstadoPasoSecuencia.BLOQUEADO
    assert paso2.ejecucion_id is None


async def test_una_secuencia_inexistente_se_rechaza(base):
    transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
    _, _, _, ejecutor, _ = _servicios(base, transporte)
    with pytest.raises(SecuenciaNoEjecutable):
        await ejecutor.ejecutar("NO-EXISTE")


async def test_dos_reversos_desde_el_mismo_origen_quedan_como_pasos_distintos(base):
    """1 origen -> N derivadas (B6) tambien aplica dentro de una secuencia:
    dos pasos derivados del mismo paso 1 producen dos ejecuciones distintas."""
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        conexiones, escenarios, secuencias, ejecutor, corridas = _servicios(base, transporte)
        await _crear_conexion(conexiones, host, "SEQ-C1-MULTI")
        escenario = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Compra financiera multi-reverso", conexion_id="SEQ-C1-MULTI",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("40.00"),
            )
        )
        secuencia = await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="Compra + dos reversos",
                pasos=[
                    DatosPaso(origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=escenario.escenario_id),
                    DatosPaso(origen_tipo=ORIGEN_PASO_DERIVADO, origen_paso_orden=1),
                    DatosPaso(origen_tipo=ORIGEN_PASO_DERIVADO, origen_paso_orden=1),
                ],
            )
        )

        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)

    assert corrida.cantidad_bloqueado == 0
    pasos = await corridas.obtener_pasos(corrida.corrida_id)
    paso1, paso2, paso3 = sorted(pasos, key=lambda p: p.orden)
    assert paso2.ejecucion_id != paso3.ejecucion_id

    repo_ejecuciones = RepositorioEjecucionesSQLite(base)
    derivadas = await repo_ejecuciones.listar_derivadas(paso1.ejecucion_id)
    assert {d.id for d in derivadas} == {paso2.ejecucion_id, paso3.ejecucion_id}

"""Expectativas dinamicas en un paso derivado (C3, 2026-09-14, puntos 12-16
del checkpoint): un valor esperado puede depender de la RESPUESTA de un
paso anterior -`{{step.purchase.response.de38}}`-, reutilizando el MISMO
motor de referencias de paso de C2 (`application.variables_secuencia`),
nunca un lenguaje nuevo.

E2E real: TCP real, codec real, SQLite real, host simulado real -mismo
estilo que `test_ejecutor_secuencia_aviso_reverso.py`-.
"""

from __future__ import annotations

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
from sibutestlab8583.application.contexto_secuencia import ContextoSecuencia
from sibutestlab8583.application.ejecutor_escenarios import EjecutorDeEscenarios
from sibutestlab8583.application.ejecutor_secuencia import EjecutorDeSecuencia
from sibutestlab8583.application.escenarios import DatosNuevoEscenario, ServicioEscenarios
from sibutestlab8583.application.secuencias import (
    DatosNuevaSecuencia,
    DatosPaso,
    ServicioSecuencias,
)
from sibutestlab8583.application.variables_secuencia import resolver_expectativas_de_paso
from sibutestlab8583.domain.errores import CampoDeEjecucionSensible
from sibutestlab8583.domain.modelos import (
    ORIGEN_PASO_DERIVADO,
    ORIGEN_PASO_INDEPENDIENTE,
    ExpectativaCampo,
    Expectativas,
    EstadoPasoSecuencia,
    MTI_COMPRA_FINANCIERA,
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


async def test_expectativa_dinamica_real_sobre_un_reverso_derivado(base):
    """Punto 12: paso 1 compra, paso 2 (reverso derivado) espera DE37 igual
    al DE38 real del paso 1. El reverso siempre copia DE37 desde la
    referencia del origen (no desde texto libre): si la 0200 original no
    trae RRN, DE37 no viaja en el 0400 -por eso la expectativa dinamica se
    arma sobre DE39 (codigo de respuesta), que si es comparable, para
    demostrar resolucion real sin depender de datos que el reverso no
    controla."""
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        conexiones, escenarios, secuencias, ejecutor, corridas, ejecuciones = _servicios(
            base, transporte
        )
        await _crear_conexion(conexiones, host, "C3-EXP-1")

        paso1 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Paso 1 (compra)", conexion_id="C3-EXP-1",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("70.00"),
            )
        )
        secuencia = await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="Expectativa dinamica real",
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
    assert pasos[0].resultado is EstadoPasoSecuencia.SIN_EXPECTATIVAS
    assert pasos[1].resultado is EstadoPasoSecuencia.PASS
    # Auditoria (punto 14): expresion Y valor resuelto, ambos en el detalle.
    assert "{{step.purchase.response.de39}}" in pasos[1].detalle
    assert "→ 00" in pasos[1].detalle

    ejecucion_1 = await ejecuciones.obtener(pasos[0].ejecucion_id)
    ejecucion_2 = await ejecuciones.obtener(pasos[1].ejecucion_id)
    assert ejecucion_1.codigo_respuesta == "00"
    assert ejecucion_2.codigo_respuesta == "00"

    # La definicion de la secuencia sigue guardando la EXPRESION, nunca el
    # valor resuelto -misma filosofia que C2 con campos_manuales.
    secuencia_recargada = await secuencias.obtener(secuencia.secuencia_id)
    paso2_def = next(p for p in secuencia_recargada.pasos if p.paso_id == "reversal")
    assert paso2_def.expectativas.campos["39"].valor == "{{step.purchase.response.de39}}"


async def test_expectativa_dinamica_que_falla_produce_fail_qa_real(base):
    """Si el valor resuelto NO coincide con lo recibido, el paso debe ser
    FAIL -no se finge exito porque la expresion se resolvio sin error-."""
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        conexiones, escenarios, secuencias, ejecutor, corridas, _ = _servicios(base, transporte)
        await _crear_conexion(conexiones, host, "C3-EXP-2")

        paso1 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Paso 1 (compra)", conexion_id="C3-EXP-2",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("55.00"),
            )
        )
        secuencia = await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="Expectativa dinamica que falla",
                pasos=[
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso1.escenario_id,
                        paso_id="purchase",
                    ),
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_DERIVADO, origen_paso_orden=1, paso_id="reversal",
                        expectativas=Expectativas(
                            campos={"39": ExpectativaCampo(tipo="igual", valor="51")}
                        ),
                    ),
                ],
            )
        )
        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)

    pasos = sorted(await corridas.obtener_pasos(corrida.corrida_id), key=lambda p: p.orden)
    assert pasos[1].resultado is EstadoPasoSecuencia.FAIL


async def test_no_hay_expectativa_dinamica_por_defecto_c2_sigue_funcionando(base):
    """Confirma que 0420->0430 tambien admite expectativas dinamicas (no
    solo 0400), demostrando que el mecanismo es generico por operacion
    derivada, no acoplado a reverso financiero."""
    from sibutestlab8583.domain.modelos import OPERACION_AVISO_REVERSO

    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        conexiones, escenarios, secuencias, ejecutor, corridas, _ = _servicios(base, transporte)
        await _crear_conexion(conexiones, host, "C3-EXP-3")

        paso1 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Paso 1 (compra)", conexion_id="C3-EXP-3",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("60.00"),
            )
        )
        secuencia = await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="Expectativa dinamica sobre aviso de reverso",
                pasos=[
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso1.escenario_id,
                        paso_id="purchase",
                    ),
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_DERIVADO, origen_paso_orden=1,
                        paso_id="reversal_advice", operacion_derivada=OPERACION_AVISO_REVERSO,
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
    assert pasos[1].resultado is EstadoPasoSecuencia.PASS


async def test_expectativa_dinamica_sobre_campo_sensible_se_rechaza(base):
    """Punto 15: mismas reglas de C2 -DE2/DE35/DE45 nunca referenciables,
    ni siquiera para comparar dentro de una expectativa-."""
    escenarios = ServicioEscenarios(
        RepositorioEscenariosSQLite(base), RepositorioTarjetasSQLite(base),
        RepositorioDestinosSQLite(base), PERFIL_GENERICO,
    )
    paso1 = await escenarios.crear(
        DatosNuevoEscenario(
            nombre="Paso 1", conexion_id="LOCAL-DEMO",
            mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("10.00"),
        )
    )
    contexto = ContextoSecuencia()
    contexto.registrar(1, ejecucion_id=999, paso_id="purchase")
    ejecuciones = RepositorioEjecucionesSQLite(base)

    for campo_sensible in ("2", "35", "45"):
        expectativas = Expectativas(
            campos={
                campo_sensible: ExpectativaCampo(
                    tipo="igual", valor=f"{{{{step.purchase.request.de{campo_sensible}}}}}"
                )
            }
        )
        with pytest.raises(CampoDeEjecucionSensible):
            await resolver_expectativas_de_paso(expectativas, contexto, ejecuciones, PERFIL_GENERICO)


async def test_expectativa_dinamica_no_puede_referenciar_un_paso_posterior(base):
    """Punto 16: se valida al GUARDAR la secuencia, igual que ya se valida
    para campos_manuales -nunca en ejecucion. El paso 2 (derivado del 1)
    intenta que su expectativa referencie al paso 3 (posterior): rechazado
    antes de guardar, sin importar que el paso 3 exista en la MISMA
    secuencia."""
    escenarios = ServicioEscenarios(
        RepositorioEscenariosSQLite(base), RepositorioTarjetasSQLite(base),
        RepositorioDestinosSQLite(base), PERFIL_GENERICO,
    )
    paso1 = await escenarios.crear(
        DatosNuevoEscenario(
            nombre="Paso 1", conexion_id="LOCAL-DEMO",
            mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("10.00"),
        )
    )
    paso3 = await escenarios.crear(
        DatosNuevoEscenario(
            nombre="Paso 3", conexion_id="LOCAL-DEMO",
            mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("11.00"),
        )
    )
    secuencias = ServicioSecuencias(RepositorioSecuenciasSQLite(base), RepositorioEscenariosSQLite(base))

    with pytest.raises(ValueError, match="ANTERIOR"):
        await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="Expectativa hacia adelante",
                pasos=[
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso1.escenario_id,
                        paso_id="purchase",
                    ),
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_DERIVADO, origen_paso_orden=1, paso_id="reversal",
                        expectativas=Expectativas(
                            campos={"39": ExpectativaCampo(
                                tipo="igual", valor="{{step.later.response.de39}}"
                            )}
                        ),
                    ),
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso3.escenario_id,
                        paso_id="later",
                    ),
                ],
            )
        )

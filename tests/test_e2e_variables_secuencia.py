"""E2E real de referencias entre pasos (Fase C2, punto 24/25 del checkpoint).

TCP/codec/SQLite/host simulado reales, sin dobles: dos pasos INDEPENDIENTES
(dos compras financieras), donde el segundo escenario tiene guardada una
referencia `{{step.purchase.response.de38}}` en un campo editable (DE37).
Confirma que el motor resuelve el valor real y que el mensaje 0200 del
paso 2 lo transmite de verdad -no solo que el motor "sabe resolver algo".

Segunda E2E (punto 25): referencia a metadata (`execution_id`), validada
en el motor/contexto sin necesitar enviarla como campo ISO.
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
from sibutestlab8583.application.serializacion import interpretar
from sibutestlab8583.domain.modelos import (
    ORIGEN_PASO_INDEPENDIENTE,
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
    ejecutor_secuencia = EjecutorDeSecuencia(
        secuencias, escenarios, ejecutor_escenarios, ejecuciones, corridas, fabrica, PERFIL_GENERICO,
    )
    return conexiones, escenarios, secuencias, ejecutor_secuencia, corridas, ejecuciones


async def test_paso_2_transmite_de_verdad_un_valor_producido_por_el_paso_1(base):
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        conexiones, escenarios, secuencias, ejecutor, corridas, ejecuciones = _servicios(
            base, transporte
        )
        await conexiones.crear(
            DatosNuevaConexion(
                conexion_id="C2-E2E", nombre="Host simulado de la prueba",
                host=host.host, puerto=str(host.puerto),
            )
        )

        paso1 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Paso 1 - compra financiera", conexion_id="C2-E2E",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("33.00"),
            )
        )
        # DE32 (institucion adquirente) es opcional y LLVAR(11) en 0200:
        # acepta un valor corto como el STAN de otro paso sin violar ninguna
        # longitud fija -a diferencia de DE37, fijo en 12 caracteres, que un
        # STAN de 6 digitos nunca podria llenar validamente (C3 lo detecto:
        # antes de la correccion de `_clasificar`, un DE37 mal formado
        # producia NO_ENVIADA -RN-4, el codec rechaza la longitud- pero esa
        # falla tecnica quedaba oculta bajo SIN_EXPECTATIVAS).
        paso2 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Paso 2 - referencia al paso 1", conexion_id="C2-E2E",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("12.00"),
                campos_manuales={"32": "{{step.purchase.response.de38}}"},
            )
        )

        secuencia = await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="Referencia real entre pasos",
                pasos=[
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso1.escenario_id,
                        paso_id="purchase",
                    ),
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso2.escenario_id,
                        paso_id="segunda_compra",
                    ),
                ],
            )
        )

        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)

    assert corrida.cantidad_error == 0
    pasos_corrida = await corridas.obtener_pasos(corrida.corrida_id)
    paso1_corrida, paso2_corrida = sorted(pasos_corrida, key=lambda p: p.orden)
    assert paso1_corrida.resultado is EstadoPasoSecuencia.SIN_EXPECTATIVAS
    assert paso2_corrida.resultado is EstadoPasoSecuencia.SIN_EXPECTATIVAS

    ejecucion_1 = await ejecuciones.obtener(paso1_corrida.ejecucion_id)
    ejecucion_2 = await ejecuciones.obtener(paso2_corrida.ejecucion_id)

    # DE38 del paso 1 (el host lo copia del STAN al aprobar) debe aparecer
    # de verdad como DE32 en el mensaje REAL transmitido por el paso 2.
    solicitud_2 = interpretar(ejecucion_2.solicitud_json, ejecucion_2.solicitud_enmascarada)
    assert solicitud_2.valor("32") == ejecucion_1.stan

    # El escenario del paso 2 sigue guardando la EXPRESION, nunca el valor
    # resuelto -misma filosofia que Fase A (congelar, no resolver)-.
    escenario_2_recargado = await escenarios.obtener(paso2.escenario_id)
    assert escenario_2_recargado.campos_manuales["32"] == "{{step.purchase.response.de38}}"


async def test_referencia_a_execution_id_no_necesita_enviarse_como_campo_iso(base):
    """Punto 25: `execution_id` es metadata interna -se valida en el
    motor/contexto, sin exigir que se envie como campo ISO-. Esta prueba
    confirma que el motor resuelve la metadata correctamente cuando SI se
    usa (en un campo cualquiera que la acepte como texto), demostrando el
    namespace separado sin forzar un caso de negocio artificial."""
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        conexiones, escenarios, secuencias, ejecutor, corridas, ejecuciones = _servicios(
            base, transporte
        )
        await conexiones.crear(
            DatosNuevaConexion(
                conexion_id="C2-E2E-META", nombre="Host simulado de la prueba",
                host=host.host, puerto=str(host.puerto),
            )
        )
        paso1 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Paso 1 metadata", conexion_id="C2-E2E-META",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("20.00"),
            )
        )
        # DE32 (opcional, LLVAR hasta 11) sirve para transportar el
        # execution_id como texto sin inventar significado de negocio nuevo
        # -a diferencia de DE41 (terminal, FIJO en 8 caracteres), que un id
        # autoincremental corto no llenaria validamente (mismo hallazgo de
        # C3 documentado en el otro test de este archivo: un campo FIJO mal
        # dimensionado produce NO_ENVIADA, no un fallo de este mecanismo).
        paso2 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Paso 2 metadata", conexion_id="C2-E2E-META",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("21.00"),
                campos_manuales={"32": "{{step.purchase.execution_id}}"},
            )
        )
        secuencia = await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="Referencia a execution_id",
                pasos=[
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso1.escenario_id,
                        paso_id="purchase",
                    ),
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso2.escenario_id,
                        paso_id="segunda",
                    ),
                ],
            )
        )

        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)

    assert corrida.cantidad_error == 0
    pasos_corrida = await corridas.obtener_pasos(corrida.corrida_id)
    paso1_corrida, paso2_corrida = sorted(pasos_corrida, key=lambda p: p.orden)

    ejecucion_2 = await ejecuciones.obtener(paso2_corrida.ejecucion_id)
    solicitud_2 = interpretar(ejecucion_2.solicitud_json, ejecucion_2.solicitud_enmascarada)
    assert solicitud_2.valor("32") == str(paso1_corrida.ejecucion_id)


async def test_un_paso_origen_que_no_produce_ejecucion_bloquea_el_dependiente(base):
    """Punto 9 del checkpoint: si el paso origen termino sin producir
    NINGUNA ejecucion (aqui: su escenario se desactivo despues de crear la
    secuencia -`EjecutorDeEscenarios.ejecutar` revienta ANTES de tocar el
    orquestador-), el paso que lo referencia debe quedar BLOQUEADO -nunca
    con un valor `None` resuelto en silencio."""
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        conexiones, escenarios, secuencias, ejecutor, corridas, ejecuciones = _servicios(
            base, transporte
        )
        await conexiones.crear(
            DatosNuevaConexion(
                conexion_id="C2-E2E-BLOQ", nombre="Host simulado de la prueba",
                host=host.host, puerto=str(host.puerto),
            )
        )
        paso1 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Paso 1 que se desactiva", conexion_id="C2-E2E-BLOQ",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("15.00"),
            )
        )
        paso2 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Paso 2 dependiente", conexion_id="C2-E2E-BLOQ",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("16.00"),
                campos_manuales={"37": "{{step.purchase.response.de38}}"},
            )
        )
        secuencia = await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="Origen desactivado",
                pasos=[
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso1.escenario_id,
                        paso_id="purchase",
                    ),
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso2.escenario_id,
                        paso_id="segunda",
                    ),
                ],
            )
        )
        await escenarios.cambiar_estado(paso1.escenario_id, activo=False)

        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)

    assert corrida.cantidad_bloqueado == 1
    pasos_corrida = await corridas.obtener_pasos(corrida.corrida_id)
    paso1_corrida, paso2_corrida = sorted(pasos_corrida, key=lambda p: p.orden)
    assert paso1_corrida.resultado is EstadoPasoSecuencia.ERROR
    assert paso1_corrida.ejecucion_id is None
    assert paso2_corrida.resultado is EstadoPasoSecuencia.BLOQUEADO
    assert paso2_corrida.ejecucion_id is None


async def test_una_referencia_sensible_colada_despues_de_crear_revienta_en_ejecucion(base):
    """Adversarial: aunque `ServicioSecuencias.crear` valida referencias al
    guardar, un escenario editado DESPUES (fuera de este flujo) podria
    llegar a tener una referencia a un campo sensible. El motor debe
    seguir rechazandola en tiempo de ejecucion -nunca resolverla-."""
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        conexiones, escenarios, secuencias, ejecutor, corridas, ejecuciones = _servicios(
            base, transporte
        )
        await conexiones.crear(
            DatosNuevaConexion(
                conexion_id="C2-E2E-SENSIBLE", nombre="Host simulado de la prueba",
                host=host.host, puerto=str(host.puerto),
            )
        )
        paso1 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Paso 1 sensible", conexion_id="C2-E2E-SENSIBLE",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("17.00"),
            )
        )
        paso2 = await escenarios.crear(
            DatosNuevoEscenario(
                nombre="Paso 2 sensible", conexion_id="C2-E2E-SENSIBLE",
                mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("18.00"),
            )
        )
        secuencia = await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="Referencia sensible colada",
                pasos=[
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso1.escenario_id,
                        paso_id="purchase",
                    ),
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso2.escenario_id,
                        paso_id="segunda",
                    ),
                ],
            )
        )
        # Se edita el escenario del paso 2 DESPUES de guardar la secuencia,
        # sin volver a pasar por `ServicioSecuencias.crear`/su validacion.
        from sibutestlab8583.application.escenarios import DatosEdicionEscenario

        await escenarios.actualizar(
            paso2.escenario_id,
            DatosEdicionEscenario(
                nombre=paso2.nombre, conexion_id="C2-E2E-SENSIBLE",
                card_id=CARD_ID_DEMO, monto=Decimal("18.00"),
                campos_manuales={"37": "{{step.purchase.request.de2}}"},
            ),
        )

        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)

    pasos_corrida = await corridas.obtener_pasos(corrida.corrida_id)
    paso1_corrida, paso2_corrida = sorted(pasos_corrida, key=lambda p: p.orden)
    assert paso1_corrida.resultado is EstadoPasoSecuencia.SIN_EXPECTATIVAS
    assert paso2_corrida.resultado is EstadoPasoSecuencia.ERROR
    assert paso2_corrida.ejecucion_id is None

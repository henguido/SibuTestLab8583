"""E2E principal de D2 (punto 22 del checkpoint): una secuencia C3 con
retry de Echo, ejecutada contra reglas del Host D2 con `max_aplicaciones`,
TOTALMENTE AUTOMATICA -sin alternar nada desde la prueba (a diferencia de
`test_integracion_reglas_host_secuencias_c3.py`, escrito en D1/C3 antes de
que D2 existiera, que necesitaba alternar `regla.activa` manualmente entre
intentos). Aqui el propio motor de reglas decide, con `max_aplicaciones=1`
sobre la regla de TIMEOUT, que el primer intento falla y el segundo cae al
fallback -exactamente la razon central de Fase D (integrar con el retry de
C3 sin test doubles).

Real: TCP real, HostSimulado real, motor de reglas real, SQLite real,
retry de C3 real.
"""

from __future__ import annotations

from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.sqlite_repos import (
    RepositorioCorridasSecuenciaSQLite,
    RepositorioDestinosSQLite,
    RepositorioEjecucionesSQLite,
    RepositorioEscenariosSQLite,
    RepositorioEstadoReglasHostSQLite,
    RepositorioEventosReglasHostSQLite,
    RepositorioReglasHostSQLite,
    RepositorioSecuenciasSQLite,
    RepositorioTarjetasSQLite,
)
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.adapters.transporte.tcp import TransporteTcp
from sibutestlab8583.application.conexiones import DatosNuevaConexion, ServicioConexiones
from sibutestlab8583.application.ejecutor_escenarios import EjecutorDeEscenarios
from sibutestlab8583.application.ejecutor_secuencia import EjecutorDeSecuencia
from sibutestlab8583.application.escenarios import DatosNuevoEscenario, ServicioEscenarios
from sibutestlab8583.application.reglas_host import DatosNuevaRegla, ServicioReglasHost
from sibutestlab8583.application.secuencias import DatosNuevaSecuencia, DatosPaso, ServicioSecuencias
from sibutestlab8583.domain.modelos import ORIGEN_PASO_INDEPENDIENTE, MTI_ECHO, EstadoPasoSecuencia
from sibutestlab8583.domain.reglas_host import (
    CAMPO_MTI,
    ComportamientoRegla,
    CondicionRegla,
    TipoComportamiento,
)
from sibutestlab8583.profiles.generico import PERFIL_GENERICO

from conftest import construir_orquestador


def _host(**kwargs) -> HostSimulado:
    return HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), **kwargs)


async def test_secuencia_c3_con_retry_de_echo_contra_reglas_d2_totalmente_automatico(base):
    servicio_reglas = ServicioReglasHost(RepositorioReglasHostSQLite(base), PERFIL_GENERICO)
    regla_timeout = await servicio_reglas.crear(DatosNuevaRegla(
        nombre="Timeout primer intento (D2)", prioridad=10,
        condiciones=[CondicionRegla(CAMPO_MTI, "igual", MTI_ECHO)],
        de39="00",
        comportamiento=ComportamientoRegla(tipo=TipoComportamiento.TIMEOUT.value),
        max_aplicaciones=1,
    ))
    regla_fallback = await servicio_reglas.crear(DatosNuevaRegla(
        nombre="Normal despues (D2)", prioridad=20,
        condiciones=[CondicionRegla(CAMPO_MTI, "igual", MTI_ECHO)],
        de39="00",
    ))

    estado_repo = RepositorioEstadoReglasHostSQLite(base)
    eventos_repo = RepositorioEventosReglasHostSQLite(base)
    host = _host(
        reglas=[regla_timeout, regla_fallback],
        repositorio_estado=estado_repo,
        repositorio_eventos=eventos_repo,
    )

    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=0.3)
        conexiones = ServicioConexiones(RepositorioDestinosSQLite(base))
        await conexiones.crear(DatosNuevaConexion(
            conexion_id="D2-C3-RETRY", nombre="Host simulado de la prueba",
            host=host.host, puerto=str(host.puerto),
        ))
        escenarios = ServicioEscenarios(
            RepositorioEscenariosSQLite(base), RepositorioTarjetasSQLite(base),
            RepositorioDestinosSQLite(base), PERFIL_GENERICO,
        )

        async def fabrica(destino, tiempo_limite):
            return construir_orquestador(base, transporte, destino=destino, tiempo_limite=tiempo_limite)

        ejecutor_escenarios = EjecutorDeEscenarios(escenarios, conexiones, fabrica)
        secuencias = ServicioSecuencias(RepositorioSecuenciasSQLite(base), RepositorioEscenariosSQLite(base))
        corridas = RepositorioCorridasSecuenciaSQLite(base)
        ejecutor = EjecutorDeSecuencia(
            secuencias, escenarios, ejecutor_escenarios, RepositorioEjecucionesSQLite(base),
            corridas, fabrica, PERFIL_GENERICO,
        )

        escenario = await escenarios.crear(
            DatosNuevoEscenario(nombre="Echo con retry (D2+C3)", conexion_id="D2-C3-RETRY", mti=MTI_ECHO)
        )
        secuencia = await secuencias.crear(DatosNuevaSecuencia(
            nombre="Retry automatico gobernado por reglas D2",
            pasos=[
                DatosPaso(
                    origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=escenario.escenario_id,
                    max_retries=1,
                ),
            ],
        ))

        # SIN alternar nada: el motor de reglas D2 decide por si solo que el
        # primer intento agota la regla de timeout y el segundo cae al
        # fallback -exactamente el punto 22 del checkpoint.
        corrida = await ejecutor.ejecutar(secuencia.secuencia_id)

    pasos = await corridas.obtener_pasos(corrida.corrida_id)
    paso = pasos[0]
    assert paso.resultado is EstadoPasoSecuencia.SIN_EXPECTATIVAS
    assert paso.ejecucion_id is not None

    intentos = await corridas.obtener_intentos(corrida.corrida_id, paso.orden)
    assert len(intentos) == 2
    assert intentos[0].resultado is EstadoPasoSecuencia.ERROR
    assert intentos[1].resultado is EstadoPasoSecuencia.SIN_EXPECTATIVAS

    # Auditoria del lado del HOST (D2): confirma que regla goberno cada
    # intento y con que numero de aplicacion -evidencia independiente de la
    # auditoria de C3 (tabla de intentos), del lado del simulador.
    eventos = sorted(await eventos_repo.listar(), key=lambda e: e.evento_id)
    assert eventos[0].regla_nombre == "Timeout primer intento (D2)"
    assert eventos[0].match_number == 1
    assert eventos[1].regla_nombre == "Normal despues (D2)"

    estado_timeout = await estado_repo.obtener(regla_timeout.regla_id)
    assert estado_timeout.aplicaciones_consumidas == 1

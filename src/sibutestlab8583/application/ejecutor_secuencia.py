"""Ejecucion de una secuencia completa: Fase C1.

CORRIDA DE SECUENCIA = ejecucion historica concreta de una `Secuencia`
(dominio: `CorridaSecuencia` + `PasoCorridaSecuencia`). Este servicio SOLO
orquesta el recorrido paso a paso y clasifica resultados; no reimplementa
RN-1..RN-4 ni Expected vs Actual, ni duplica "como ejecutar un escenario
guardado" (eso sigue siendo exclusivo de `EjecutorDeEscenarios`, reutilizado
tal cual para un paso INDEPENDIENTE) ni "como construir/validar un reverso
desde otra ejecucion" (eso sigue siendo exclusivo de `Orquestador.
ejecutar_reverso_financiero` -> `referencia_origen_elegible`, B6/B7,
reutilizado tal cual para un paso DERIVADO).

SECUENCIAL, Y SE DETIENE POR DEPENDENCIA -A DIFERENCIA DE `CorredorDeSuites`
=============================================================================
`CorredorDeSuites` aisla la falla de UN item y sigue con el siguiente,
porque los escenarios de una suite son independientes entre si. Una
secuencia NO puede seguir asi: si el paso 1 no produce una ejecucion
elegible, el paso 2 (derivado) no tiene de donde sacar su
`ejecucion_origen_id` -no es un fallo aislado de un item mas, es que la
PRECONDICION del paso siguiente nunca se cumplio-. Ese paso queda
`BLOQUEADO`, nunca `FAIL` (no se ejecuto nada que evaluar) ni `ERROR` (no
fallo tecnicamente: simplemente no pudo empezar).

La deteccion de "el origen no es elegible" NUNCA se duplica aqui: se deja
que `Orquestador.ejecutar_reverso_financiero` la haga (recibe el
`ejecucion_origen_id` crudo y revienta con `EjecucionOrigenNoEncontrada`/
`EjecucionOrigenNoElegible` si no corresponde) y este ejecutor solo
clasifica esa excepcion como `BLOQUEADO`. Es la misma regla de elegibilidad
de B6 (`domain.elegibilidad_reverso`), nunca una segunda copia.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Awaitable, Callable, Sequence

from ..domain.errores import (
    EjecucionOrigenNoElegible,
    EjecucionOrigenNoEncontrada,
    ErrorDelSimulador,
)
from ..domain.modelos import (
    ORIGEN_PASO_DERIVADO,
    ORIGEN_PASO_INDEPENDIENTE,
    CorridaSecuencia,
    DatosReversoFinanciero,
    DestinoTcp,
    EstadoCorridaSuite,
    EstadoPasoSecuencia,
    PasoCorridaSecuencia,
    PasoSecuencia,
    Secuencia,
)
from ..domain.puertos import RepositorioCorridasSecuencia, RepositorioEjecuciones
from ..domain.secuencias import calcular_resultado_global_secuencia
from .contexto_secuencia import ContextoSecuencia
from .ejecutor_escenarios import EjecutorDeEscenarios, EscenarioNoEjecutable
from .escenarios import EscenarioNoEncontrado, ServicioEscenarios
from .orquestador import Orquestador, TarjetaDesconocida
from .secuencias import ServicioSecuencias

#: Mensajes seguros y controlados, mismo criterio que `corredor_suites.py`:
#: nunca `str(excepcion)` ni traceback.
_MOTIVO_ESCENARIO_NO_ENCONTRADO = "El escenario ya no existe en el catálogo."
_MOTIVO_ESCENARIO_NO_EJECUTABLE = (
    "El escenario no está disponible para ejecutarse (inactivo, tarjeta o "
    "conexión no disponible, o incompatible con el perfil actual)."
)
_MOTIVO_TARJETA_DESCONOCIDA = "La tarjeta del escenario no existe o está inactiva."
_MOTIVO_ERROR_DEL_SIMULADOR = (
    "No se pudo construir o interpretar el mensaje ISO 8583 para este paso."
)
_MOTIVO_FALLO_INESPERADO = (
    "Fallo técnico inesperado durante la ejecución. Revise el registro del servidor."
)
_MOTIVO_ORIGEN_SIN_EJECUCION = (
    "El paso del que este depende no produjo ninguna ejecución: no hay origen que reversar."
)
_MOTIVO_ORIGEN_NO_ELEGIBLE = (
    "La ejecución producida por el paso origen no es elegible para un reverso "
    "(no es una compra financiera aprobada)."
)
_MOTIVO_ORIGEN_SIN_DESTINO = (
    "La ejecución origen no registra un destino de transmisión: no se puede reversar."
)


class SecuenciaNoEjecutable(Exception):
    """La secuencia no existe, esta inactiva, o no tiene pasos."""


class EjecutorDeSecuencia:
    def __init__(
        self,
        administracion_secuencias: ServicioSecuencias,
        administracion_escenarios: ServicioEscenarios,
        ejecutor_escenarios: EjecutorDeEscenarios,
        repositorio_ejecuciones: RepositorioEjecuciones,
        repositorio_corridas: RepositorioCorridasSecuencia,
        fabrica_orquestador: Callable[[DestinoTcp, float | None], Awaitable[Orquestador]],
        reloj: Callable[[], datetime] | None = None,
    ) -> None:
        self._secuencias = administracion_secuencias
        self._escenarios = administracion_escenarios
        self._ejecutor_escenarios = ejecutor_escenarios
        self._ejecuciones = repositorio_ejecuciones
        self._corridas = repositorio_corridas
        self._fabrica_orquestador = fabrica_orquestador
        self._reloj = reloj or (lambda: datetime.now(timezone.utc))

    async def ejecutar(self, secuencia_id: str) -> CorridaSecuencia:
        secuencia = await self._secuencias.obtener_activa(secuencia_id)
        if secuencia is None:
            raise SecuenciaNoEjecutable(f"la secuencia {secuencia_id!r} no existe o está inactiva")
        if not secuencia.pasos:
            raise SecuenciaNoEjecutable(f"la secuencia {secuencia_id!r} no tiene pasos")
        return await self._correr(secuencia)

    async def _correr(self, secuencia: Secuencia) -> CorridaSecuencia:
        pasos_ordenados = sorted(secuencia.pasos, key=lambda p: p.orden)
        nombres_escenario = await self._resolver_nombres_escenario(pasos_ordenados)

        pasos_iniciales = [
            PasoCorridaSecuencia(
                corrida_id=0,  # placeholder: crear_con_pasos usa el id recien asignado
                orden=paso.orden,
                origen_tipo=paso.origen_tipo,
                resultado=EstadoPasoSecuencia.NO_EJECUTADO,
                escenario_id=paso.escenario_id,
                escenario_nombre=nombres_escenario.get(paso.orden),
                origen_paso_orden=paso.origen_paso_orden,
            )
            for paso in pasos_ordenados
        ]

        corrida = CorridaSecuencia(
            secuencia_id=secuencia.secuencia_id,
            secuencia_nombre=secuencia.nombre,
            total=len(pasos_ordenados),
            iniciada_en=self._reloj(),
        )
        corrida_id = await self._corridas.crear_con_pasos(corrida, pasos_iniciales)

        contexto = ContextoSecuencia()
        conteos: dict[EstadoPasoSecuencia, int] = {estado: 0 for estado in EstadoPasoSecuencia}
        for paso in pasos_ordenados:
            resultado, ejecucion_id, detalle, evaluacion_json = await self._ejecutar_paso(
                paso, contexto
            )
            if ejecucion_id is not None:
                contexto.registrar(paso.orden, ejecucion_id)
            conteos[resultado] += 1
            await self._corridas.actualizar_paso(
                PasoCorridaSecuencia(
                    corrida_id=corrida_id,
                    orden=paso.orden,
                    origen_tipo=paso.origen_tipo,
                    resultado=resultado,
                    escenario_id=paso.escenario_id,
                    escenario_nombre=nombres_escenario.get(paso.orden),
                    origen_paso_orden=paso.origen_paso_orden,
                    ejecucion_id=ejecucion_id,
                    detalle=detalle,
                    evaluacion_json=evaluacion_json,
                )
            )

        corrida.cantidad_pass = conteos[EstadoPasoSecuencia.PASS]
        corrida.cantidad_fail = conteos[EstadoPasoSecuencia.FAIL]
        corrida.cantidad_error = conteos[EstadoPasoSecuencia.ERROR]
        corrida.cantidad_sin_expectativas = conteos[EstadoPasoSecuencia.SIN_EXPECTATIVAS]
        corrida.cantidad_bloqueado = conteos[EstadoPasoSecuencia.BLOQUEADO]
        corrida.cantidad_no_ejecutado = conteos[EstadoPasoSecuencia.NO_EJECUTADO]
        corrida.estado = EstadoCorridaSuite.FINALIZADA
        corrida.resultado_global = calcular_resultado_global_secuencia(conteos)
        corrida.finalizada_en = self._reloj()
        await self._corridas.cerrar(corrida)
        return corrida

    async def _resolver_nombres_escenario(
        self, pasos: Sequence[PasoSecuencia]
    ) -> dict[int, str | None]:
        """Nombre para MOSTRAR de cada paso -resuelto ANTES de correr, igual
        criterio que `CorredorDeSuites._resolver_nombres`-: un paso
        independiente muestra el nombre del escenario; uno derivado muestra
        una etiqueta fija ("Reverso del paso N"), porque no tiene escenario
        propio.
        """
        nombres: dict[int, str | None] = {}
        for paso in pasos:
            if paso.origen_tipo == ORIGEN_PASO_INDEPENDIENTE:
                escenario = await self._escenarios.obtener(paso.escenario_id)
                nombres[paso.orden] = escenario.nombre if escenario is not None else paso.escenario_id
            else:
                nombres[paso.orden] = f"Reverso del paso {paso.origen_paso_orden}"
        return nombres

    async def _ejecutar_paso(
        self, paso: PasoSecuencia, contexto: ContextoSecuencia
    ) -> tuple[EstadoPasoSecuencia, int | None, str | None, str | None]:
        if paso.origen_tipo == ORIGEN_PASO_INDEPENDIENTE:
            return await self._ejecutar_paso_independiente(paso)
        return await self._ejecutar_paso_derivado(paso, contexto)

    async def _ejecutar_paso_independiente(
        self, paso: PasoSecuencia
    ) -> tuple[EstadoPasoSecuencia, int | None, str | None, str | None]:
        """Delega enteramente en `EjecutorDeEscenarios`: mismo mecanismo que
        ya usa `CorredorDeSuites._ejecutar_item` para un escenario suelto.
        """
        try:
            resultado = await self._ejecutor_escenarios.ejecutar(paso.escenario_id)
        except EscenarioNoEncontrado:
            return EstadoPasoSecuencia.ERROR, None, _MOTIVO_ESCENARIO_NO_ENCONTRADO, None
        except EscenarioNoEjecutable:
            return EstadoPasoSecuencia.ERROR, None, _MOTIVO_ESCENARIO_NO_EJECUTABLE, None
        except TarjetaDesconocida:
            return EstadoPasoSecuencia.ERROR, None, _MOTIVO_TARJETA_DESCONOCIDA, None
        except ErrorDelSimulador:
            return EstadoPasoSecuencia.ERROR, None, _MOTIVO_ERROR_DEL_SIMULADOR, None
        except Exception:
            # Excepcion no contemplada: nunca su texto, nunca traceback.
            return EstadoPasoSecuencia.ERROR, None, _MOTIVO_FALLO_INESPERADO, None

        return _clasificar(resultado.ejecucion)

    async def _ejecutar_paso_derivado(
        self, paso: PasoSecuencia, contexto: ContextoSecuencia
    ) -> tuple[EstadoPasoSecuencia, int | None, str | None, str | None]:
        """Construye un reverso financiero derivado del paso
        `paso.origen_paso_orden` -la UNICA operacion derivada que C1
        soporta (punto 20 del checkpoint)-. Nunca reconstruye la referencia
        a mano: `Orquestador.ejecutar_reverso_financiero` ya hace toda la
        resolucion/validacion segura (B6/B7).
        """
        ejecucion_origen_id = contexto.ejecucion_id_de(paso.origen_paso_orden)
        if ejecucion_origen_id is None:
            return EstadoPasoSecuencia.BLOQUEADO, None, _MOTIVO_ORIGEN_SIN_EJECUCION, None

        origen = await self._ejecuciones.obtener(ejecucion_origen_id)
        if origen is None or not origen.destino_host:
            return EstadoPasoSecuencia.BLOQUEADO, None, _MOTIVO_ORIGEN_SIN_DESTINO, None

        destino = DestinoTcp(host=origen.destino_host, puerto=origen.destino_puerto)
        try:
            orquestador = await self._fabrica_orquestador(destino, None)
            resultado = await orquestador.ejecutar_reverso_financiero(
                DatosReversoFinanciero(ejecucion_origen_id=ejecucion_origen_id),
                expectativas=paso.expectativas,
            )
        except (EjecucionOrigenNoEncontrada, EjecucionOrigenNoElegible):
            return EstadoPasoSecuencia.BLOQUEADO, None, _MOTIVO_ORIGEN_NO_ELEGIBLE, None
        except ErrorDelSimulador:
            return EstadoPasoSecuencia.ERROR, None, _MOTIVO_ERROR_DEL_SIMULADOR, None
        except Exception:
            return EstadoPasoSecuencia.ERROR, None, _MOTIVO_FALLO_INESPERADO, None

        return _clasificar(resultado.ejecucion)


def _clasificar(
    ejecucion,
) -> tuple[EstadoPasoSecuencia, int | None, str | None, str | None]:
    """Clasifica una `Ejecucion` ya persistida en su `EstadoPasoSecuencia` -
    mismo criterio que `CorredorDeSuites._ejecutar_item`: nunca recalcula
    Expected vs Actual, solo lee `evaluacion_estado`/`evaluacion_json`.
    """
    if ejecucion.evaluacion_estado == "pass":
        return EstadoPasoSecuencia.PASS, ejecucion.id, None, ejecucion.evaluacion_json
    if ejecucion.evaluacion_estado == "fail":
        return EstadoPasoSecuencia.FAIL, ejecucion.id, None, ejecucion.evaluacion_json
    return EstadoPasoSecuencia.SIN_EXPECTATIVAS, ejecucion.id, None, None

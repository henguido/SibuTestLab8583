"""Ejecucion secuencial de una suite completa: Bloque 4.

CORRIDA DE SUITE = ejecucion historica concreta de una `Suite` (dominio:
`CorridaSuite` + `ItemCorridaSuite`). Este servicio SOLO orquesta el recorrido
y clasifica resultados; no reimplementa RN-1..RN-4 ni Expected vs Actual, ni
duplica la resolucion de "como ejecutar un escenario guardado" -eso vive
exclusivamente en `EjecutorDeEscenarios`, reutilizado aqui tal cual-.

Secuencial a proposito: sin `asyncio.gather`, sin concurrencia, sin scheduler.
Un escenario no ejecutable, o una excepcion inesperada de cualquiera, se
aisla como un item en ERROR y la corrida continua con el siguiente -nunca se
aborta la suite completa por un item-.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable

from ..domain.errores import ErrorDelSimulador
from ..domain.modelos import (
    CorridaSuite,
    EstadoCorridaSuite,
    EstadoItemCorrida,
    ItemCorridaSuite,
)
from ..domain.puertos import RepositorioCorridasSuite
from ..domain.suites import calcular_resultado_global
from .ejecutor_escenarios import EjecutorDeEscenarios, EscenarioNoEjecutable
from .escenarios import EscenarioNoEncontrado, ServicioEscenarios
from .orquestador import TarjetaDesconocida
from .suites import ServicioSuites

#: Mensajes seguros y controlados para las causas de ERROR conocidas -nunca
#: `str(excepcion)` ni traceback: ver la correccion "6. ERRORES" del diseno.
_MOTIVO_ESCENARIO_NO_ENCONTRADO = "El escenario ya no existe en el catálogo."
_MOTIVO_ESCENARIO_NO_EJECUTABLE = (
    "El escenario no está disponible para ejecutarse (inactivo, tarjeta o "
    "conexión no disponible, o incompatible con el perfil actual)."
)
_MOTIVO_TARJETA_DESCONOCIDA = "La tarjeta del escenario no existe o está inactiva."
_MOTIVO_ERROR_DEL_SIMULADOR = (
    "No se pudo construir o interpretar el mensaje ISO 8583 para este escenario."
)
_MOTIVO_FALLO_INESPERADO = "Fallo técnico inesperado durante la ejecución."


class SuiteNoEjecutable(Exception):
    """La suite no existe, esta inactiva, o no tiene escenarios."""


class CorredorDeSuites:
    def __init__(
        self,
        administracion_suites: ServicioSuites,
        administracion_escenarios: ServicioEscenarios,
        repositorio_corridas: RepositorioCorridasSuite,
        ejecutor: EjecutorDeEscenarios,
        reloj: Callable[[], datetime] | None = None,
    ) -> None:
        self._suites = administracion_suites
        self._escenarios = administracion_escenarios
        self._corridas = repositorio_corridas
        self._ejecutor = ejecutor
        self._reloj = reloj or (lambda: datetime.now(timezone.utc))

    async def ejecutar(self, suite_id: str) -> CorridaSuite:
        suite = await self._suites.obtener_activa(suite_id)
        if suite is None:
            raise SuiteNoEjecutable(f"la suite {suite_id!r} no existe o está inactiva")
        if not suite.escenarios:
            raise SuiteNoEjecutable(f"la suite {suite_id!r} no tiene escenarios")

        # Nombres resueltos ANTES de abrir la corrida: se presembran los items
        # ya con el nombre de ese momento, igual criterio que ya usa
        # `Ejecucion.escenario_nombre` -si el escenario se renombra despues,
        # el item historico no cambia.
        nombres = []
        for escenario_id in suite.escenarios:
            escenario = await self._escenarios.obtener(escenario_id)
            nombres.append(escenario.nombre if escenario is not None else escenario_id)

        items_iniciales = [
            ItemCorridaSuite(
                corrida_id=0,  # placeholder: crear_con_items usa el id recien asignado
                escenario_id=escenario_id,
                escenario_nombre=nombre,
                orden=orden,
                resultado=EstadoItemCorrida.NO_EJECUTADO,
            )
            for orden, (escenario_id, nombre) in enumerate(
                zip(suite.escenarios, nombres), start=1
            )
        ]

        corrida = CorridaSuite(
            suite_id=suite.suite_id,
            suite_nombre=suite.nombre,
            total=len(suite.escenarios),
            iniciada_en=self._reloj(),
        )
        corrida_id = await self._corridas.crear_con_items(corrida, items_iniciales)

        conteos: dict[EstadoItemCorrida, int] = {estado: 0 for estado in EstadoItemCorrida}
        for orden, (escenario_id, nombre) in enumerate(zip(suite.escenarios, nombres), start=1):
            resultado_item, ejecucion_id, detalle, evaluacion_json = await self._ejecutar_item(
                escenario_id
            )
            conteos[resultado_item] += 1
            await self._corridas.actualizar_item(
                ItemCorridaSuite(
                    corrida_id=corrida_id,
                    escenario_id=escenario_id,
                    escenario_nombre=nombre,
                    orden=orden,
                    resultado=resultado_item,
                    ejecucion_id=ejecucion_id,
                    detalle=detalle,
                    evaluacion_json=evaluacion_json,
                )
            )

        corrida.cantidad_pass = conteos[EstadoItemCorrida.PASS]
        corrida.cantidad_fail = conteos[EstadoItemCorrida.FAIL]
        corrida.cantidad_error = conteos[EstadoItemCorrida.ERROR]
        corrida.cantidad_sin_expectativas = conteos[EstadoItemCorrida.SIN_EXPECTATIVAS]
        corrida.cantidad_no_ejecutado = conteos[EstadoItemCorrida.NO_EJECUTADO]
        corrida.estado = EstadoCorridaSuite.FINALIZADA
        corrida.resultado_global = calcular_resultado_global(conteos)
        corrida.finalizada_en = self._reloj()
        await self._corridas.cerrar(corrida)
        return corrida

    async def _ejecutar_item(
        self, escenario_id: str
    ) -> tuple[EstadoItemCorrida, int | None, str | None, str | None]:
        """Delega enteramente en `EjecutorDeEscenarios`: aisla cualquier falla
        de ESTE escenario como ERROR, sin abortar la corrida, y clasifica un
        exito segun `evaluacion_estado` -nunca recalcula Expected vs Actual-.
        """
        try:
            resultado = await self._ejecutor.ejecutar(escenario_id)
        except EscenarioNoEncontrado:
            return EstadoItemCorrida.ERROR, None, _MOTIVO_ESCENARIO_NO_ENCONTRADO, None
        except EscenarioNoEjecutable:
            return EstadoItemCorrida.ERROR, None, _MOTIVO_ESCENARIO_NO_EJECUTABLE, None
        except TarjetaDesconocida:
            return EstadoItemCorrida.ERROR, None, _MOTIVO_TARJETA_DESCONOCIDA, None
        except ErrorDelSimulador:
            return EstadoItemCorrida.ERROR, None, _MOTIVO_ERROR_DEL_SIMULADOR, None
        except Exception:
            # Excepcion no contemplada: nunca su texto, nunca traceback.
            return EstadoItemCorrida.ERROR, None, _MOTIVO_FALLO_INESPERADO, None

        ejecucion = resultado.ejecucion
        if ejecucion.evaluacion_estado == "pass":
            return EstadoItemCorrida.PASS, ejecucion.id, None, ejecucion.evaluacion_json
        if ejecucion.evaluacion_estado == "fail":
            return EstadoItemCorrida.FAIL, ejecucion.id, None, ejecucion.evaluacion_json
        return EstadoItemCorrida.SIN_EXPECTATIVAS, ejecucion.id, None, None

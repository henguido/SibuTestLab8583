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
from typing import Callable, Sequence

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
_MOTIVO_FALLO_INESPERADO = (
    "Fallo técnico inesperado durante la ejecución. Revise el registro del servidor."
)


class SuiteNoEjecutable(Exception):
    """La suite no existe, esta inactiva, o no tiene escenarios."""


class CorridaOrigenNoEncontrada(Exception):
    """No existe una corrida con el `corrida_id` que se quiere reintentar."""


class SinItemsReintentables(Exception):
    """La corrida origen no tiene ningun item en FAIL o ERROR."""


#: Resultados de un item que "reintentar fallidos" vuelve a intentar. Decision
#: explicita, no tacita: FAIL y ERROR son los dos casos donde el escenario no
#: quedo en un desenlace conforme -uno porque no cumplio la expectativa, el
#: otro porque ni siquiera se pudo evaluar-. SIN_EXPECTATIVAS queda afuera
#: porque no fallo nada: se ejecuto bien y el escenario simplemente no definia
#: que esperaba, reintentarlo no cambiaria nada relevante. NO_EJECUTADO queda
#: afuera tambien: solo sobrevive en una corrida que quedo interrumpida (un
#: crash de proceso a mitad de camino), un caso excepcional que esta funcion
#: no intenta resolver -si en el futuro se decide incluirlo, es un cambio de
#: una linea aqui, no una migracion.
_RESULTADOS_REINTENTABLES = frozenset({EstadoItemCorrida.FAIL, EstadoItemCorrida.ERROR})


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
        nombres = await self._resolver_nombres(suite.escenarios)
        return await self._correr(suite.suite_id, suite.nombre, list(zip(suite.escenarios, nombres)))

    async def reintentar_fallidos(self, corrida_id: int) -> CorridaSuite:
        """Crea una corrida NUEVA con solo los escenarios que en `corrida_id`
        quedaron en FAIL o ERROR -nunca modifica ni reutiliza la corrida
        original, que permanece intacta para poder seguir comparandola-.

        La seleccion de QUE escenarios reintentar viene de los ITEMS
        HISTORICOS de la corrida origen, nunca de la membresia actual de la
        suite: si la suite gano escenarios nuevos despues de esa corrida, no
        entran aqui aunque hoy formen parte de ella. Cada escenario
        seleccionado se ejecuta con su configuracion ACTUAL (tarjeta, monto,
        conexion, expectativa vigentes) -exactamente lo mismo que ya hace
        `ejecutar()` y "Ejecutar" en la pantalla de un escenario suelto-, asi
        que un escenario eliminado o desactivado desde la corrida original
        cae en ERROR con el mismo motivo ya controlado que usa
        `_ejecutar_item`, sin abortar el reintento de los demas.
        """
        origen = await self._corridas.obtener(corrida_id)
        if origen is None:
            raise CorridaOrigenNoEncontrada(corrida_id)

        items_origen = await self._corridas.obtener_items(corrida_id)
        seleccionados = [
            (item.escenario_id, item.escenario_nombre)
            for item in sorted(items_origen, key=lambda i: i.orden)
            if item.resultado in _RESULTADOS_REINTENTABLES
        ]
        if not seleccionados:
            raise SinItemsReintentables(
                f"la corrida {corrida_id} no tiene ningún ítem en FAIL o ERROR"
            )

        # El nombre para MOSTRAR se resuelve de nuevo contra el catalogo
        # vivo -igual criterio que `ejecutar()`-: si el escenario todavia
        # existe, el item de la corrida nueva muestra su nombre actual; si
        # ya no existe, cae al nombre historico como ultimo recurso, nunca
        # a una cadena vacia.
        escenario_ids = [escenario_id for escenario_id, _ in seleccionados]
        nombres_actuales = await self._resolver_nombres(
            escenario_ids, nombres_historicos=dict(seleccionados)
        )
        return await self._correr(
            origen.suite_id, origen.suite_nombre, list(zip(escenario_ids, nombres_actuales))
        )

    async def _resolver_nombres(
        self, escenario_ids: Sequence[str], *, nombres_historicos: dict[str, str] | None = None
    ) -> list[str]:
        nombres_historicos = nombres_historicos or {}
        nombres = []
        for escenario_id in escenario_ids:
            escenario = await self._escenarios.obtener(escenario_id)
            if escenario is not None:
                nombres.append(escenario.nombre)
            else:
                nombres.append(nombres_historicos.get(escenario_id, escenario_id))
        return nombres

    async def _correr(
        self, suite_id: str, suite_nombre: str, pares_escenario_nombre: Sequence[tuple[str, str]]
    ) -> CorridaSuite:
        """Nucleo compartido de ejecucion secuencial: abre la corrida con
        todos los items presembrados en NO_EJECUTADO, corre cada uno con
        `EjecutorDeEscenarios` (aislando su falla como ERROR, sin abortar la
        corrida), y cierra con los contadores y el resultado global. Tanto
        `ejecutar()` como `reintentar_fallidos()` terminan aqui -ningun
        segundo runner paralelo, ninguna logica de ejecucion duplicada.
        """
        items_iniciales = [
            ItemCorridaSuite(
                corrida_id=0,  # placeholder: crear_con_items usa el id recien asignado
                escenario_id=escenario_id,
                escenario_nombre=nombre,
                orden=orden,
                resultado=EstadoItemCorrida.NO_EJECUTADO,
            )
            for orden, (escenario_id, nombre) in enumerate(pares_escenario_nombre, start=1)
        ]

        corrida = CorridaSuite(
            suite_id=suite_id,
            suite_nombre=suite_nombre,
            total=len(pares_escenario_nombre),
            iniciada_en=self._reloj(),
        )
        corrida_id = await self._corridas.crear_con_items(corrida, items_iniciales)

        conteos: dict[EstadoItemCorrida, int] = {estado: 0 for estado in EstadoItemCorrida}
        for orden, (escenario_id, nombre) in enumerate(pares_escenario_nombre, start=1):
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

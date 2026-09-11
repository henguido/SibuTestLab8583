"""Comparacion historica de dos corridas de la MISMA suite.

Servicio neutral de aplicacion, mismo espiritu que `exportacion_corridas.py`:
recibe (via el repositorio) dos `CorridaSuite` ya persistidas y sus
`Sequence[ItemCorridaSuite]`, y solo lee lo que esos snapshots ya
persisten -nunca vuelve a evaluar Expected vs Actual, nunca consulta el
escenario vivo, la suite viva ni la expectativa actual-. Por eso la
comparacion sigue siendo valida aunque el escenario se haya renombrado,
desactivado, eliminado, o la suite se haya editado despues de AMBAS
corridas: nada de eso se lee aqui.

El emparejamiento entre corridas es por `escenario_id` -la unica clave
estable que persiste `ItemCorridaSuite`, independiente de `orden` (que un
reintento puede renumerar) y de `escenario_nombre` (mutable, aunque ya
venga congelado por corrida)-. Un escenario presente en una suite nunca se
repite dentro de sus propios items (ver `web.app._leer_escenarios_de_suite`,
que arma la seleccion recorriendo el catalogo real: un mismo escenario_id no
puede marcarse dos veces), asi que emparejar por esta clave no es ambiguo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Sequence

from ..domain.comparacion_corridas import CambioItem, ComparacionItem, clasificar_cambio
from ..domain.modelos import EstadoItemCorrida, ItemCorridaSuite
from ..domain.puertos import RepositorioCorridasSuite


class CorridaNoEncontrada(Exception):
    """No existe una corrida con ese `corrida_id`."""


class CorridasDeSuitesDistintas(Exception):
    """Las dos corridas a comparar no pertenecen a la misma suite."""


class ItemsHistoricosDuplicados(Exception):
    """Una corrida historica tiene mas de un item con el mismo `escenario_id`.

    Nunca deberia ocurrir por los caminos actuales de la aplicacion
    (`ServicioSuites._validar_escenarios` rechaza un escenario repetido al
    crear o editar una suite, y tanto `ejecutar()` como
    `reintentar_fallidos()` presiembran los items de una corrida a partir de
    esa membresia ya validada), pero `corrida_suite_items` no tiene una
    restriccion UNIQUE sobre `escenario_id` -su PRIMARY KEY es
    `(corrida_id, orden)`, ver `adapters/persistence/esquema.py`-, asi que un
    dato corrupto (insertado por fuera de la aplicacion, o por un bug
    futuro) es posible a nivel de esquema. El comparador se niega a elegir
    uno en silencio -el `{escenario_id: item ...}` de antes se quedaba con
    "el ultimo que gana" sin avisar-: prefiere fallar de forma explicada
    antes que mostrar una comparacion que podria estar ocultando un item.

    Lleva `corrida_id` y `escenario_id` -ambos identificadores tecnicos,
    nunca datos de tarjeta- para que el mensaje sea accionable sin exponer
    nada sensible.
    """

    def __init__(self, corrida_id: int, escenario_id: str) -> None:
        super().__init__(
            f"la corrida {corrida_id} tiene más de un ítem histórico con el "
            f"escenario {escenario_id!r}: no se puede comparar de forma confiable"
        )
        self.corrida_id = corrida_id
        self.escenario_id = escenario_id


@dataclass(frozen=True)
class ResumenComparacion:
    """Conteo por tipo de cambio, para la seccion RESUMEN de la vista."""

    sin_cambio: int = 0
    mejoro: int = 0
    empeoro: int = 0
    cambio: int = 0
    solo_en_a: int = 0
    solo_en_b: int = 0


@dataclass(frozen=True)
class ComparacionCorridas:
    """El resultado completo de comparar la corrida A contra la corrida B."""

    corrida_a: object
    corrida_b: object
    items: Sequence[ComparacionItem]
    resumen: ResumenComparacion


def _contenido_comparable(item: ItemCorridaSuite | None) -> object:
    """Lo que decide si "cambio el contenido" para un mismo `resultado`.

    FAIL: la lista de discrepancias tal como quedo persistida (comparacion
    estructural, no de texto formateado). ERROR: el texto de `detalle` -es
    lo unico que ERROR persiste-. Cualquier otro resultado (PASS,
    SIN_EXPECTATIVAS, NO_EJECUTADO): `None`, porque `clasificar_cambio` no
    llega a comparar contenido para ellos (PASS siempre vacio por
    construccion; los otros dos quedan fuera de `_RANGO_EVALUABLE`).
    """
    if item is None:
        return None
    if item.resultado == EstadoItemCorrida.FAIL and item.evaluacion_json:
        datos = json.loads(item.evaluacion_json)
        return datos.get("discrepancias", [])
    if item.resultado == EstadoItemCorrida.ERROR:
        return item.detalle
    return None


class ServicioComparacionCorridas:
    def __init__(self, repositorio_corridas: RepositorioCorridasSuite) -> None:
        self._corridas = repositorio_corridas

    async def comparar(self, corrida_a_id: int, corrida_b_id: int) -> ComparacionCorridas:
        corrida_a = await self._corridas.obtener(corrida_a_id)
        if corrida_a is None:
            raise CorridaNoEncontrada(corrida_a_id)
        corrida_b = await self._corridas.obtener(corrida_b_id)
        if corrida_b is None:
            raise CorridaNoEncontrada(corrida_b_id)
        if corrida_a.suite_id != corrida_b.suite_id:
            raise CorridasDeSuitesDistintas(
                f"la corrida {corrida_a_id} es de la suite {corrida_a.suite_id!r} y la "
                f"corrida {corrida_b_id} es de la suite {corrida_b.suite_id!r}"
            )

        items_a = await self._corridas.obtener_items(corrida_a_id)
        items_b = await self._corridas.obtener_items(corrida_b_id)
        return _comparar_items(corrida_a, corrida_b, items_a, items_b)


def _indice_por_escenario(
    corrida_id: int, items: Sequence[ItemCorridaSuite]
) -> dict[str, ItemCorridaSuite]:
    """El mismo `{escenario_id: item}` de antes, pero detectando un duplicado
    en vez de quedarse con "el ultimo que gana" en silencio -ver
    `ItemsHistoricosDuplicados`-.
    """
    indice: dict[str, ItemCorridaSuite] = {}
    for item in items:
        if item.escenario_id in indice:
            raise ItemsHistoricosDuplicados(corrida_id, item.escenario_id)
        indice[item.escenario_id] = item
    return indice


def _comparar_items(
    corrida_a, corrida_b,
    items_a: Sequence[ItemCorridaSuite], items_b: Sequence[ItemCorridaSuite],
) -> ComparacionCorridas:
    """Separado de `comparar()` -sin `await`, sin repositorio- para poder
    probarlo con `ItemCorridaSuite` construidos a mano, sin base de datos.
    """
    por_escenario_a = _indice_por_escenario(corrida_a.corrida_id, items_a)
    por_escenario_b = _indice_por_escenario(corrida_b.corrida_id, items_b)

    # Preserva el orden de aparicion: primero los escenarios de A (en su
    # propio orden), luego los que solo estan en B y no en A -nunca se
    # pierde un escenario por estar "fuera de rango" del mas corto de los
    # dos-.
    vistos: set[str] = set()
    orden_escenarios: list[str] = []
    for item in items_a:
        if item.escenario_id not in vistos:
            vistos.add(item.escenario_id)
            orden_escenarios.append(item.escenario_id)
    for item in items_b:
        if item.escenario_id not in vistos:
            vistos.add(item.escenario_id)
            orden_escenarios.append(item.escenario_id)

    conteos = {cambio: 0 for cambio in CambioItem}
    resultado: list[ComparacionItem] = []
    for escenario_id in orden_escenarios:
        item_a = por_escenario_a.get(escenario_id)
        item_b = por_escenario_b.get(escenario_id)
        if item_a is None:
            cambio = CambioItem.SOLO_EN_B
        elif item_b is None:
            cambio = CambioItem.SOLO_EN_A
        else:
            cambio = clasificar_cambio(
                item_a.resultado, item_b.resultado,
                _contenido_comparable(item_a), _contenido_comparable(item_b),
            )
        conteos[cambio] += 1
        resultado.append(
            ComparacionItem(escenario_id=escenario_id, cambio=cambio, item_a=item_a, item_b=item_b)
        )

    resumen = ResumenComparacion(
        sin_cambio=conteos[CambioItem.SIN_CAMBIO],
        mejoro=conteos[CambioItem.MEJORO],
        empeoro=conteos[CambioItem.EMPEORO],
        cambio=conteos[CambioItem.CAMBIO],
        solo_en_a=conteos[CambioItem.SOLO_EN_A],
        solo_en_b=conteos[CambioItem.SOLO_EN_B],
    )
    return ComparacionCorridas(corrida_a=corrida_a, corrida_b=corrida_b, items=resultado, resumen=resumen)

"""Clasificacion de un cambio entre dos snapshots historicos de un mismo
escenario, en dos corridas de la misma suite.

Funcion pura: solo compara `EstadoItemCorrida` y el contenido ya persistido
de discrepancias/detalle, sin red, sin base de datos, sin conocer que es un
`Orquestador` ni un escenario vivo. Mismo espiritu que
`domain/suites.py::calcular_resultado_global`: el algoritmo vive aqui,
aislado, para que `application.comparacion_corridas` no tenga que
reimplementarlo ni el bloque de pruebas tenga que inferirlo de un efecto
secundario.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .modelos import EstadoItemCorrida, ItemCorridaSuite


class CambioItem(str, Enum):
    """Como cambio UN escenario entre la corrida A y la corrida B.

    Los primeros cuatro valores son mutuamente excluyentes y cubren todo par
    de items presente en ambas corridas; los ultimos dos son de presencia,
    no de resultado, y solo se usan cuando el escenario falta de un lado.
    """

    SIN_CAMBIO = "sin_cambio"
    MEJORO = "mejoro"
    EMPEORO = "empeoro"
    CAMBIO = "cambio"
    SOLO_EN_A = "solo_en_a"
    SOLO_EN_B = "solo_en_b"


#: Orden de severidad SOLO dentro de este subconjunto: son los tres unicos
#: `EstadoItemCorrida` que representan un resultado evaluable en una escala
#: de "que tan bien le fue a este escenario" -PASS es mejor que FAIL, que a
#: su vez es mejor que ERROR-. SIN_EXPECTATIVAS y NO_EJECUTADO quedan FUERA
#: a proposito: no hay expectativa que se haya cumplido o no, asi que no
#: existe un "mejor"/"peor" legitimo para ellos, solo "distinto".
_RANGO_EVALUABLE: dict[EstadoItemCorrida, int] = {
    EstadoItemCorrida.ERROR: 0,
    EstadoItemCorrida.FAIL: 1,
    EstadoItemCorrida.PASS: 2,
}


def clasificar_cambio(
    resultado_a: EstadoItemCorrida,
    resultado_b: EstadoItemCorrida,
    discrepancias_a: object,
    discrepancias_b: object,
) -> CambioItem:
    """Clasifica el cambio de UN escenario entre dos corridas ya presentes en
    ambas (el caso SOLO_EN_A/SOLO_EN_B se decide antes de llegar aqui, en
    `application.comparacion_corridas`, porque ahi es donde se sabe que un
    lado no tiene item).

    Regla completa, sin excepciones tacitas:

    1. Mismo `resultado` en A y B:
       - Si ese resultado es evaluable (PASS/FAIL/ERROR): compara el
         contenido (`discrepancias_a` vs `discrepancias_b` -para FAIL, la
         lista de discrepancias; para ERROR, el texto de `detalle`; para
         PASS, siempre vacio en los dos lados por construccion). Distinto
         contenido con el mismo resultado es CAMBIO (ej. FAIL -> FAIL pero
         cambio que campo no cumplio); igual contenido es SIN_CAMBIO.
       - Si ese resultado NO es evaluable (SIN_EXPECTATIVAS o NO_EJECUTADO
         en ambos lados): SIN_CAMBIO, no hay nada que comparar.
    2. Resultado distinto en A y B, y AMBOS evaluables (PASS/FAIL/ERROR):
       compara el rango de severidad. B mejor que A -> MEJORO
       (FAIL->PASS, ERROR->PASS, ERROR->FAIL). B peor que A -> EMPEORO
       (PASS->FAIL, PASS->ERROR, FAIL->ERROR).

       Decision explicita para FAIL<->ERROR, el unico par que el pedido no
       fijaba de antemano: ERROR se ubica POR DEBAJO de FAIL en la escala,
       porque FAIL todavia informa algo evaluable (que criterio no se
       cumplio, con su discrepancia); ERROR no informa nada de eso -el
       escenario ni siquiera se pudo ejecutar o evaluar-. Por eso
       FAIL -> ERROR es EMPEORO (se perdio la capacidad de diagnostico) y
       ERROR -> FAIL es MEJORO (se recupero, aunque la expectativa siga sin
       cumplirse).
    3. Resultado distinto en A y B, y AL MENOS UNO no evaluable
       (SIN_EXPECTATIVAS o NO_EJECUTADO de un lado, cualquier otra cosa del
       otro): CAMBIO. No se puede graduar como mejor/peor -no habia
       expectativa que perder ni ganar-, pero es un cambio real y debe
       quedar visible, no silenciado como SIN_CAMBIO.
    """
    if resultado_a == resultado_b:
        if resultado_a not in _RANGO_EVALUABLE:
            return CambioItem.SIN_CAMBIO
        return CambioItem.SIN_CAMBIO if discrepancias_a == discrepancias_b else CambioItem.CAMBIO

    rango_a = _RANGO_EVALUABLE.get(resultado_a)
    rango_b = _RANGO_EVALUABLE.get(resultado_b)
    if rango_a is None or rango_b is None:
        return CambioItem.CAMBIO
    return CambioItem.MEJORO if rango_b > rango_a else CambioItem.EMPEORO


@dataclass(frozen=True)
class ComparacionItem:
    """El resultado de comparar UN `escenario_id` entre dos corridas.

    `item_a`/`item_b` son `None` exactamente cuando `cambio` es
    `SOLO_EN_B`/`SOLO_EN_A` respectivamente -nunca los dos a la vez, nunca
    ambos `None`-. Guarda los `ItemCorridaSuite` completos (no solo el
    resultado) para que la presentacion pueda mostrar detalle/discrepancias
    de cada lado sin tener que volver a consultar nada.
    """

    escenario_id: str
    cambio: CambioItem
    item_a: ItemCorridaSuite | None
    item_b: ItemCorridaSuite | None

"""Calculo del resultado agregado de una corrida de suite.

Funcion pura: solo cuenta `EstadoItemCorrida`, sin red, sin base de datos, sin
conocer que es un `Orquestador`. Mismo espiritu que `domain/expectativas.py`:
el algoritmo vive aqui, aislado, para que `application.corredor_suites` no
tenga que reimplementarlo ni el bloque de pruebas tenga que inferirlo de un
efecto secundario.
"""

from __future__ import annotations

from typing import Mapping

from .modelos import EstadoItemCorrida, ResultadoGlobalSuite


def calcular_resultado_global(conteos: Mapping[EstadoItemCorrida, int]) -> ResultadoGlobalSuite:
    """El resultado agregado de una corrida ya finalizada, a partir de cuantos
    items cayeron en cada `EstadoItemCorrida`.

    Prioridad estricta, de mayor a menor severidad -igual principio que
    "nunca un PASS por omision" de `domain.expectativas.evaluar_expectativas`,
    elevado a nivel de agregado:

    1. Si hay algun ERROR, o algun NO_EJECUTADO -una corrida FINALIZADA nunca
       deberia conservar uno, asi que su presencia aqui es una inconsistencia
       que se trata como ERROR, nunca como si no hubiera pasado nada-.
    2. Si no hay lo anterior pero hay algun FAIL.
    3. Si no hay ERROR/FAIL y hay mezcla de PASS + SIN_EXPECTATIVAS:
       INCOMPLETA -no todos los escenarios fueron realmente evaluados, asi
       que afirmar PASS seria enganoso para una suite de regresion-.
    4. Si TODOS son SIN_EXPECTATIVAS: SIN_EXPECTATIVAS.
    5. Si TODOS son PASS: PASS -"todos los escenarios tenian expectativas y
       todos cumplieron", el unico significado legitimo de un PASS de suite-.
    """
    tiene_error = conteos.get(EstadoItemCorrida.ERROR, 0) > 0
    tiene_no_ejecutado = conteos.get(EstadoItemCorrida.NO_EJECUTADO, 0) > 0
    tiene_fail = conteos.get(EstadoItemCorrida.FAIL, 0) > 0
    tiene_pass = conteos.get(EstadoItemCorrida.PASS, 0) > 0
    tiene_sin_expectativas = conteos.get(EstadoItemCorrida.SIN_EXPECTATIVAS, 0) > 0

    if tiene_error or tiene_no_ejecutado:
        return ResultadoGlobalSuite.ERROR
    if tiene_fail:
        return ResultadoGlobalSuite.FAIL
    if tiene_pass and tiene_sin_expectativas:
        return ResultadoGlobalSuite.INCOMPLETA
    if tiene_sin_expectativas:
        return ResultadoGlobalSuite.SIN_EXPECTATIVAS
    return ResultadoGlobalSuite.PASS

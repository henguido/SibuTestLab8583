"""Calculo del resultado agregado de una corrida de secuencia (Fase C1).

Funcion pura: solo cuenta `EstadoPasoSecuencia`, sin red, sin base de datos.
Mismo espiritu que `domain.suites.calcular_resultado_global`, del que esta
funcion es la contraparte para secuencias -no una copia: la prioridad
incorpora `BLOQUEADO`, el unico estado que Suites no tiene.
"""

from __future__ import annotations

from typing import Mapping

from .modelos import EstadoPasoSecuencia, ResultadoGlobalSuite


def calcular_resultado_global_secuencia(
    conteos: Mapping[EstadoPasoSecuencia, int],
) -> ResultadoGlobalSuite:
    """El resultado agregado de una corrida de secuencia ya finalizada.

    Prioridad estricta, de mayor a menor severidad -mismo principio que
    `domain.suites.calcular_resultado_global`-:

    1. Si hay algun ERROR, o algun NO_EJECUTADO -una corrida FINALIZADA
       nunca deberia conservar uno-.
    2. Si no hay lo anterior pero hay algun FAIL.
    3. Si no hay ERROR/FAIL pero hay algun BLOQUEADO: INCOMPLETA -la cadena
       se rompio en algun paso, nunca se llego a probar todo lo que la
       secuencia declaraba; afirmar PASS seria enganoso, igual razon que ya
       usa Suites para la mezcla PASS+SIN_EXPECTATIVAS-.
    4. Si no hay nada de lo anterior y hay mezcla de PASS + SIN_EXPECTATIVAS:
       INCOMPLETA, mismo criterio que Suites.
    5. Si TODOS son SIN_EXPECTATIVAS: SIN_EXPECTATIVAS.
    6. Si TODOS son PASS: PASS.
    """
    tiene_error = conteos.get(EstadoPasoSecuencia.ERROR, 0) > 0
    tiene_no_ejecutado = conteos.get(EstadoPasoSecuencia.NO_EJECUTADO, 0) > 0
    tiene_fail = conteos.get(EstadoPasoSecuencia.FAIL, 0) > 0
    tiene_bloqueado = conteos.get(EstadoPasoSecuencia.BLOQUEADO, 0) > 0
    tiene_pass = conteos.get(EstadoPasoSecuencia.PASS, 0) > 0
    tiene_sin_expectativas = conteos.get(EstadoPasoSecuencia.SIN_EXPECTATIVAS, 0) > 0

    if tiene_error or tiene_no_ejecutado:
        return ResultadoGlobalSuite.ERROR
    if tiene_fail:
        return ResultadoGlobalSuite.FAIL
    if tiene_bloqueado:
        return ResultadoGlobalSuite.INCOMPLETA
    if tiene_pass and tiene_sin_expectativas:
        return ResultadoGlobalSuite.INCOMPLETA
    if tiene_sin_expectativas:
        return ResultadoGlobalSuite.SIN_EXPECTATIVAS
    return ResultadoGlobalSuite.PASS

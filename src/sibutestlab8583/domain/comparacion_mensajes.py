"""Comparacion DESCRIPTIVA Request vs Response de un mismo intercambio ISO 8583
(Bloque 8/9 del Isoscopio 2.0).

**Esto NO es Expected vs Actual.** Expected vs Actual (`domain/expectativas.py` +
`application/orquestador.py::evaluar_expectativas`) es una ASERCION DE PRUEBA:
compara la respuesta contra lo que un escenario declaro esperar, y produce
PASS/FAIL. Esta comparacion es puramente DESCRIPTIVA: que campos aparecen en
la solicitud y en la respuesta, y si coinciden -sin ningun juicio de
correctitud-. Un campo distinto (DE41 si el host reescribe el terminal) o un
campo que solo aparece de un lado (DE39, que por construccion del protocolo
solo viaja en la respuesta) no son errores: son observaciones.

Pura: sin red, sin base de datos, sin conocer el `EstadoEjecucion` de la
transaccion ni el escenario. Recibe dos `Mapping[str, str]` -numero de campo
a valor, ya enmascarado por quien llama- y no necesita saber de donde vinieron.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Sequence


class EstadoComparacionCampo(str, Enum):
    COINCIDE = "coincide"
    DIFERENTE = "diferente"
    SOLO_REQUEST = "solo_request"
    SOLO_RESPONSE = "solo_response"


@dataclass(frozen=True)
class CampoComparado:
    """Un campo ISO comparado entre solicitud y respuesta.

    `request`/`response` son `None` cuando el campo no aparecio de ese lado
    -nunca una cadena vacia, que seria indistinguible de un valor vacio real-.
    """

    numero: str
    request: str | None
    response: str | None
    estado: EstadoComparacionCampo


def comparar_campos(
    campos_request: Mapping[str, str], campos_response: Mapping[str, str]
) -> Sequence[CampoComparado]:
    """Compara dos mensajes campo por campo, por union de sus numeros.

    Preserva todo campo de cualquiera de los dos lados -nunca se pierde uno
    por estar ausente del otro-, ordenados numericamente para que la tabla
    resultante sea facil de leer.
    """
    numeros = sorted({*campos_request.keys(), *campos_response.keys()}, key=int)
    resultado: list[CampoComparado] = []
    for numero in numeros:
        en_request = numero in campos_request
        en_response = numero in campos_response
        valor_request = campos_request.get(numero)
        valor_response = campos_response.get(numero)
        if en_request and en_response:
            estado = (
                EstadoComparacionCampo.COINCIDE
                if valor_request == valor_response
                else EstadoComparacionCampo.DIFERENTE
            )
        elif en_request:
            estado = EstadoComparacionCampo.SOLO_REQUEST
        else:
            estado = EstadoComparacionCampo.SOLO_RESPONSE
        resultado.append(
            CampoComparado(
                numero=numero, request=valor_request, response=valor_response, estado=estado
            )
        )
    return resultado

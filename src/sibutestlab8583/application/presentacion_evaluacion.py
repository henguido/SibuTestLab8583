"""Traduccion de una discrepancia estructurada a un mensaje humano.

Neutral a proposito: la web (`web/presentacion.py`) y la CLI (`cli.py`) son dos
interfaces hermanas que necesitan exactamente el mismo texto para la misma
discrepancia -no una CLI que dependa de la web, ni una web que dependa de la
CLI-. Esta funcion vive en `application` porque ninguna de las dos interfaces
debe depender de la otra, y ambas ya dependen de la capa de aplicacion.

No es Expected vs Actual: no evalua nada ni recalcula nada. Solo redacta en
prosa lo que `domain.expectativas.discrepancia_a_dict` ya estructuro, tal como
quedo congelado en un `evaluacion_json` (de `Ejecucion` o de
`ItemCorridaSuite`, da igual: ambos usan el mismo formato).
"""

from __future__ import annotations

from typing import Mapping


def mensaje_de_discrepancia(discrepancia: Mapping, descripciones: Mapping[str, str]) -> str:
    if discrepancia["criterio"] == "estado":
        return (
            f"Se esperaba el estado «{discrepancia['esperado']}» y se obtuvo "
            f"«{discrepancia['recibido']}»."
        )
    campo = discrepancia["campo"]
    nombre = descripciones.get(campo, f"Campo {campo}")
    tipo = discrepancia["tipo"]
    if tipo == "igual":
        recibido = discrepancia["recibido"] or "(ausente)"
        return f"Campo {campo} ({nombre}): se esperaba «{discrepancia['esperado']}» y llegó «{recibido}»."
    if tipo == "presente":
        return f"Campo {campo} ({nombre}): se esperaba que estuviera presente y no llegó."
    return f"Campo {campo} ({nombre}): se esperaba que estuviera ausente y llegó «{discrepancia['recibido']}»."

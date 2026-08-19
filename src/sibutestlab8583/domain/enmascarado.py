"""Enmascaramiento de datos de tarjeta.

Politica en CLAUDE.md: fuera de la pantalla de mantenimiento de tarjetas, un PAN
solo puede mostrarse enmascarado. Este modulo es el unico lugar que decide como
se enmascara, para que la regla no se reimplemente en cada borde.
"""

from __future__ import annotations

MASCARA = "*"
DIGITOS_VISIBLES = 4


def enmascarar_pan(pan: str) -> str:
    """Devuelve el PAN con todo oculto salvo los ultimos cuatro digitos.

    Un PAN de 16 digitos produce la representacion documentada ``************1234``.
    """
    limpio = "".join(c for c in pan if c.isdigit())
    if len(limpio) <= DIGITOS_VISIBLES:
        return MASCARA * len(limpio)
    return MASCARA * (len(limpio) - DIGITOS_VISIBLES) + limpio[-DIGITOS_VISIBLES:]


def enmascarar_campos(
    campos: dict[str, str], campos_sensibles: frozenset[str]
) -> dict[str, str]:
    """Copia los campos de un mensaje ISO enmascarando los que llevan datos de tarjeta.

    Se usa antes de persistir o de mostrar un mensaje: ni el historial ni el
    isoscopio deben exponer el PAN completo.
    """
    return {
        numero: enmascarar_pan(valor) if numero in campos_sensibles else valor
        for numero, valor in campos.items()
    }

"""Composicion comun a las operaciones derivadas financieras de este
laboratorio (B8, 2026-09-14): reverso financiero (0400, B7) y aviso de
reverso (0420, B8).

EXTRAIDA POR DUPLICACION MEDIDA, NO ANTICIPADA
===============================================
Hasta B8 solo existia una operacion derivada (`armar_reverso_financiero`,
`application/armado_reverso.py`). Al disenar la segunda (`armar_aviso_reverso`,
`application/armado_aviso_reverso.py`) se comparo campo por campo contra la
primera (B8, punto 8 del checkpoint) y resulto identica: mismos campos
"nuevo intercambio" (DE3/DE7/DE11) y "referenciado del original" (DE4/DE41/
DE49/DE37 opcional), misma validacion de snapshot incompleto. La UNICA
diferencia real entre las dos es el MTI y el codigo de proceso -que cada
perfil declara por separado (`profiles/generico.py`, B8 punto 7)-. Esta
funcion es esa composicion comun; `armar_reverso_financiero`/
`armar_aviso_reverso` son wrappers especificos y siguen siendo la API
publica que el resto del proyecto usa -nadie fuera de este modulo llama
`_componer_operacion_derivada_financiera` directamente.
"""

from __future__ import annotations

from datetime import datetime

from ..domain.armado import formatear_monto
from ..domain.errores import ReferenciaOrigenIncompleta
from ..domain.modelos import MensajeIso
from .referencia_ejecucion import ReferenciaEjecucion


def componer_operacion_derivada_financiera(
    mti: str,
    referencia_original: ReferenciaEjecucion,
    *,
    stan_nuevo: str,
    momento_nuevo: datetime,
    codigo_proceso: str,
) -> MensajeIso:
    """Arma un mensaje derivado (0400 o 0420) a partir del snapshot seguro de
    la ejecucion origen -nunca del escenario vivo, nunca de texto que alguien
    escriba a mano-. Ver docstring del modulo para por que existe esta
    funcion en vez de que cada wrapper repita la composicion.

    `stan_nuevo`/`momento_nuevo` son SIEMPRE nuevos: ninguna operacion
    derivada reutiliza el STAN de la 0200 que referencia.

    Revienta con `ReferenciaOrigenIncompleta` si el snapshot no trae monto,
    moneda o terminal -los tres son obligatorios en toda 0200 aprobada-. DE37
    (RRN) es la unica excepcion: se incluye solo si el original lo tenia.
    """
    if referencia_original.monto is None:
        raise ReferenciaOrigenIncompleta("la ejecución origen no tiene monto registrado")
    if not referencia_original.moneda:
        raise ReferenciaOrigenIncompleta("la ejecución origen no tiene moneda registrada")
    if not referencia_original.terminal:
        raise ReferenciaOrigenIncompleta("la ejecución origen no tiene terminal registrado")

    campos = {
        "3": codigo_proceso,
        "7": momento_nuevo.strftime("%m%d%H%M%S"),
        "11": stan_nuevo,
        "4": formatear_monto(referencia_original.monto),
        "41": referencia_original.terminal,
        "49": referencia_original.moneda,
    }
    if referencia_original.rrn:
        campos["37"] = referencia_original.rrn
    return MensajeIso(mti=mti, campos=campos)

"""Construccion del mensaje de aviso de reverso (0420, B8).

CONSTRUCTOR CERRADO, NO LIBRE -mismo criterio que 0400 (B7)
============================================================
Igual que `armar_reverso_financiero`, `armar_aviso_reverso` no recibe ningun
campo de texto libre: cada campo del 0420 es "nuevo intercambio" (DE3/DE7/
DE11) o "referenciado del original" (DE4/DE41/DE49/DE37, copiados de
`ReferenciaEjecucion`). La composicion es identica a la del 0400 -medida,
no asumida, ver `application/armado_operacion_derivada.py`-; lo que cambia
es el MTI y el codigo de proceso, que vienen de la politica propia de 0420
en `profiles/generico.py` (B8, punto 7: nunca referenciando la politica de
0400 aunque terminen compartiendo forma).

DIFERENCIA FUNCIONAL FRENTE A 0400 (investigada con Agente A, B8)
==================================================================
Un reverso (0400) es una SOLICITUD que el receptor puede negar. Un aviso de
reverso (0420) es la NOTIFICACION de un reverso que YA OCURRIO -el emisor no
esta pidiendo permiso, esta informando un hecho consumado, y el receptor
(0430) esta obligado a aceptarlo, no a evaluarlo de nuevo-. Esa diferencia
de contrato es de negocio/protocolo, no de campos: por eso son dos
operaciones derivadas separadas en este laboratorio (dos MTI, dos builders,
dos metodos de `Orquestador`) aun compartiendo la misma composicion de campos
y el mismo origen (`ReferenciaEjecucion`).

DE90 -mismo analisis y misma decision que 0400/0410 (B7, no repetido aqui:
ver `application/armado_reverso.py` y `profiles/generico.py`): NO
implementado, sin fuente para DE33.
"""

from __future__ import annotations

from datetime import datetime

from ..domain.modelos import MTI_AVISO_REVERSO, MensajeIso
from ..profiles.generico import CODIGO_PROCESO_AVISO_REVERSO
from .armado_operacion_derivada import componer_operacion_derivada_financiera
from .referencia_ejecucion import ReferenciaEjecucion


def armar_aviso_reverso(
    referencia_original: ReferenciaEjecucion,
    *,
    stan_nuevo: str,
    momento_nuevo: datetime,
) -> MensajeIso:
    """Arma el 0420 (aviso de reverso, B8) a partir del snapshot seguro de la
    ejecucion origen -nunca del escenario vivo, nunca de texto que alguien
    escriba a mano-.

    `stan_nuevo`/`momento_nuevo` son SIEMPRE nuevos: un aviso de reverso
    nunca reutiliza el STAN de la 0200 que referencia, ni el de un 0400 que
    pudiera existir para el mismo origen.

    Revienta con `ReferenciaOrigenIncompleta` si el snapshot no trae monto,
    moneda o terminal. DE37 (RRN) es la unica excepcion: se incluye solo si
    el original lo tenia.
    """
    return componer_operacion_derivada_financiera(
        MTI_AVISO_REVERSO,
        referencia_original,
        stan_nuevo=stan_nuevo,
        momento_nuevo=momento_nuevo,
        codigo_proceso=CODIGO_PROCESO_AVISO_REVERSO,
    )

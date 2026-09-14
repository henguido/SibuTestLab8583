"""Construccion del mensaje de reverso financiero (0400, B7).

CONSTRUCTOR CERRADO, NO LIBRE
=============================
A diferencia de `domain.armado.armar_compra`/`armar_compra_financiera`
-que reciben `campos_manuales` porque el usuario SI puede fijar algunos
valores-, `armar_reverso_financiero` no recibe absolutamente ningun campo de
texto libre (B7, punto 5): cada campo del 0400 es "nuevo intercambio"
(DE3/DE7/DE11, generados aqui mismo) o "referenciado del original"
(DE4/DE41/DE49/DE37, copiados de `ReferenciaEjecucion`, nunca reescritos por
quien pida el reverso).

Vive en `application/`, no en `domain/armado.py`: su unico dato de entrada,
`ReferenciaEjecucion`, es un tipo de la capa de aplicacion (B6) -el dominio
no puede depender de ella sin invertir la direccion de dependencia del
proyecto (`web -> application -> dominio/puertos -> adaptadores`)-.

DE90 (Original Data Elements) -investigado y NO implementado (B7, punto 7)
===========================================================================
Ver `profiles/generico.py`, seccion "Reverso financiero", para la
justificacion completa: los ultimos 11 caracteres de un DE90 defendible
(ID de institucion receptora/forwarding, DE33) no tienen ninguna fuente en
este perfil, y rellenarlos fabricaria un dato que este laboratorio no
tiene. La correlacion origen<->reverso se apoya en DE37 (RRN, cuando el
original lo tuvo) a nivel de protocolo, y en `Ejecucion.ejecucion_origen_id`
(B6) a nivel de aplicacion -nunca en STAN/RRN como identidad exclusiva,
ver `domain/modelos.py`.

COMPOSICION COMPARTIDA CON EL AVISO DE REVERSO (B8, 2026-09-14)
================================================================
`armar_reverso_financiero` delega en
`application.armado_operacion_derivada.componer_operacion_derivada_financiera`
-la composicion resulto identica a la del aviso de reverso (0420, B8) al
compararlas campo por campo, asi que se extrajo una unica funcion comun en
vez de mantener dos copias-. Esta funcion sigue siendo la API publica: nadie
fuera de este modulo debe llamar a la funcion compartida directamente.
"""

from __future__ import annotations

from datetime import datetime

from ..domain.modelos import MTI_REVERSO_FINANCIERO, MensajeIso
from ..profiles.generico import CODIGO_PROCESO_REVERSO_FINANCIERO
from .armado_operacion_derivada import componer_operacion_derivada_financiera
from .referencia_ejecucion import ReferenciaEjecucion


def armar_reverso_financiero(
    referencia_original: ReferenciaEjecucion,
    *,
    stan_nuevo: str,
    momento_nuevo: datetime,
) -> MensajeIso:
    """Arma el 0400 (reverso financiero, B7) a partir del snapshot seguro de
    la ejecucion origen -nunca del escenario vivo, nunca de texto que
    alguien escriba a mano-.

    `stan_nuevo`/`momento_nuevo` son SIEMPRE nuevos: un reverso nunca
    reutiliza el STAN de la 0200 que reversa (B7, punto 6; verificado en
    `tests/test_armado_reverso.py`).

    Revienta con `ReferenciaOrigenIncompleta` si el snapshot no trae monto,
    moneda o terminal -los tres son obligatorios en toda 0200 aprobada (ver
    `profiles.generico.OBLIGATORIOS_0200`), asi que su ausencia aqui
    señalaria un snapshot corrupto, no un caso de negocio valido-. DE37
    (RRN) es la unica excepcion: se incluye solo si el original lo tenia.
    """
    return componer_operacion_derivada_financiera(
        MTI_REVERSO_FINANCIERO,
        referencia_original,
        stan_nuevo=stan_nuevo,
        momento_nuevo=momento_nuevo,
        codigo_proceso=CODIGO_PROCESO_REVERSO_FINANCIERO,
    )

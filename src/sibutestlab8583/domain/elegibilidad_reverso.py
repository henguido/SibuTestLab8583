"""Regla de dominio: que ejecucion puede originar una operacion derivada
(un futuro reverso, B6, 2026-09-13).

Pura -sin red, sin base de datos-, igual que `domain/validacion.py`. Vive
aparte de RN-1..RN-4 porque no es una regla de PROTOCOLO (no decide si una
respuesta corresponde a una solicitud): es una regla de NEGOCIO de este
laboratorio sobre cuando tiene sentido conceptual derivar una operacion
nueva de una ejecucion pasada. Nunca en Jinja, nunca repetida en la capa web.

DECISION DE ALCANCE (B6, investigada con Agente A -dominio de pagos/reversos,
fuentes publicas genericas, ninguna especifica de marca-): un reverso existe
para deshacer un EFECTO ya producido -tipicamente, fondos movidos-. Reversar
una transaccion que nunca aprobo no tiene ese efecto que deshacer: la
literatura generica describe eso como un caso degenerado (a lo sumo, un
"nada que reversar" de vuelta), no el caso primario. Por eso, para este
laboratorio:

- Compra financiera (0200) APROBADA es la UNICA operacion elegible hoy: es
  la unica que mueve fondos en este perfil generico.
- Autorizacion (0100) queda deliberadamente FUERA en esta primera version:
  una autorizacion tampoco mueve fondos por si sola (es una reserva/verificacion),
  asi que igual no seria el primer candidato -aunque en la practica real las
  autorizaciones tambien se reversan, este laboratorio prefiere no afirmar
  esa regla sin evidencia mas especifica; documentado como decision abierta,
  no como limitacion tecnica-.
- Echo (0800) queda fuera: no mueve fondos, no tiene concepto de reverso.
- Compra financiera RECHAZADA (por ejemplo, DE39="51") queda EXPLICITAMENTE
  fuera (punto 8 de B6): un rechazo nunca tuvo efecto que deshacer.
- ERROR_CONEXION/ERROR_TRANSMISION/TIMEOUT/NO_ENVIADA/INVALIDA quedan fuera:
  no hay una respuesta aprobada y correlacionada que confirme un efecto
  producido -sin eso, no hay nada que este laboratorio pueda demostrar que
  se debe deshacer-.

Esta lista es deliberadamente conservadora y ampliable: agregar una
operacion elegible es agregar su MTI a `_MTIS_ELEGIBLES`, nunca reescribir
esta funcion.
"""

from __future__ import annotations

from .modelos import Ejecucion, EstadoEjecucion, MTI_COMPRA_FINANCIERA

#: MTI de solicitud cuyas ejecuciones APROBADAS pueden originar una
#: operacion derivada. Ver docstring del modulo para la justificacion de
#: por que hoy es solo compra financiera.
_MTIS_ELEGIBLES: frozenset[str] = frozenset({MTI_COMPRA_FINANCIERA})


def puede_generar_operacion_derivada(ejecucion: Ejecucion) -> bool:
    """`True` solo si esta ejecucion es un candidato razonable para un
    futuro reverso: su MTI esta en `_MTIS_ELEGIBLES` Y su estado es
    `APROBADA` -ambas condiciones, no una u otra-.

    No verifica que la ejecucion no tenga YA derivadas: nada en este
    laboratorio impone cardinalidad 1:1 (una misma ejecucion origen puede
    tener varias derivadas), asi que "ya tiene una derivada" no descalifica
    -eso es una decision de UI/negocio distinta, no de elegibilidad tecnica.
    """
    return ejecucion.mti_solicitud in _MTIS_ELEGIBLES and ejecucion.estado is EstadoEjecucion.APROBADA

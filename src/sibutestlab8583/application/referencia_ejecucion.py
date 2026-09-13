"""Snapshot seguro de una ejecucion pasada, para una futura operacion
derivada (reverso, B6, 2026-09-13).

`ReferenciaEjecucion` es DELIBERADAMENTE angosta: expone solo lo que
`domain/elegibilidad_reverso.py` y un futuro `armar_reverso` necesitarian
-nunca el mensaje completo, nunca `card_id` para re-derivar el PAN fuera del
camino normal de construccion-. Investigado con Agente D (seguridad, B6):
ningun campo de `Ejecucion` guarda el PAN/Track en claro -el enmascarado se
garantiza en dos capas independientes, `MensajeIso.enmascarado()` en el
productor y `_verificar_enmascarado` como barrera de persistencia (ver
`application/serializacion.py`)-, asi que leer estos campos de vuelta nunca
expone datos de tarjeta. `card_id` en si NO es el PAN -es el identificador
de catalogo, el mismo que ya usa cualquier operacion para derivar la tarjeta
real en el momento de armar un mensaje real (`armar_compra_financiera`)-:
se incluye aqui precisamente para que una futura construccion de reverso
repita ese mismo camino seguro, no para saltarselo.

Nunca se construye desde el escenario ACTUAL ni desde el perfil vigente
(punto 5 de B6): siempre desde el snapshot ya persistido de la ejecucion
origen (`DetalleEjecucion`), para que editar el escenario o el perfil
despues no altere lo que un reverso futuro reconstruiria.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from ..domain.elegibilidad_reverso import puede_generar_operacion_derivada
from ..domain.errores import EjecucionOrigenNoElegible, EjecucionOrigenNoEncontrada
from ..domain.puertos import RepositorioEjecuciones
from .consultas import DetalleEjecucion
from .serializacion import interpretar

#: Numeros de campo de la RESPUESTA que un futuro reverso podria necesitar
#: para correlacionar/justificar la operacion derivada (DE37 RRN, DE38
#: codigo de autorizacion -ver investigacion de dominio, Agente A-). Ninguno
#: de los dos es sensible (`domain.modelos.CAMPOS_SENSIBLES` es solo
#: {"2","35","45"}), y de todas formas llegan ya enmascarados si alguna vez
#: lo fueran: `respuesta.campos` proviene de `MensajeSerializado`, que
#: `application/serializacion.py` garantiza construido a partir del mensaje
#: ya enmascarado. Deliberadamente angosto -no "todos los campos de la
#: respuesta"-: agregar uno mas es agregar su numero aqui, nunca reescribir
#: la funcion.
CAMPOS_REFERENCIA_RESPUESTA: frozenset[str] = frozenset({"37", "38"})


@dataclass(frozen=True)
class ReferenciaEjecucion:
    """Lo minimo y seguro que una operacion derivada necesita saber de su
    ejecucion origen. Nunca el mensaje completo, nunca RAW, nunca PAN/Track.
    """

    ejecucion_id: int
    mti_solicitud: str
    mti_respuesta: str | None
    stan: str
    monto: Decimal | None
    moneda: str | None
    card_id: str | None
    codigo_respuesta: str | None
    destino_host: str | None
    destino_puerto: int | None
    creada_en: datetime
    #: DE41 (terminal) y DE37 (RRN) de la SOLICITUD original (B7): ninguno de
    #: los dos es sensible, y un futuro reverso los necesita como datos
    #: "referenciados del original" (ver `application/armado_reverso.py`).
    #: `rrn` puede ser `None` -DE37 no es obligatorio en una 0200 (ver
    #: `profiles.generico.OBLIGATORIOS_0200`), asi que el original pudo no
    #: haberlo tenido nunca-.
    terminal: str | None
    rrn: str | None
    #: Subconjunto whitelisted de campos de la RESPUESTA (ver
    #: `CAMPOS_REFERENCIA_RESPUESTA`), numero -> valor ya enmascarado/seguro.
    #: Ausente (no en el dict) si ese campo no vino en la respuesta original.
    campos_respuesta: dict[str, str]


def referencia_desde_detalle(detalle: DetalleEjecucion) -> ReferenciaEjecucion:
    """Construye la referencia a partir del snapshot YA PERSISTIDO de una
    ejecucion pasada (`DetalleEjecucion`, `application/consultas.py`) -nunca
    del escenario vivo ni del perfil vigente. Es la unica funcion que arma
    `ReferenciaEjecucion`: ningun llamador debe construirla a mano.
    """
    ejecucion = detalle.ejecucion
    campos_respuesta = {
        campo.numero: campo.valor
        for campo in detalle.respuesta.campos
        if campo.numero in CAMPOS_REFERENCIA_RESPUESTA
    }
    return ReferenciaEjecucion(
        ejecucion_id=ejecucion.id,
        mti_solicitud=ejecucion.mti_solicitud,
        mti_respuesta=ejecucion.mti_respuesta,
        stan=ejecucion.stan,
        monto=ejecucion.monto,
        moneda=ejecucion.moneda,
        card_id=ejecucion.card_id,
        codigo_respuesta=ejecucion.codigo_respuesta,
        destino_host=ejecucion.destino_host,
        destino_puerto=ejecucion.destino_puerto,
        creada_en=ejecucion.creada_en,
        terminal=detalle.solicitud.valor("41"),
        rrn=detalle.solicitud.valor("37"),
        campos_respuesta=campos_respuesta,
    )


async def referencia_origen_elegible(
    ejecucion_origen_id: int, repositorio_ejecuciones: RepositorioEjecuciones,
) -> ReferenciaEjecucion:
    """Resuelve, valida y construye la referencia de una futura operacion
    derivada, en un unico lugar reusado por el orquestador (B7,
    `ejecutar_reverso_financiero`) y por la vista previa del reverso -nunca
    duplicado-.

    Revienta con `EjecucionOrigenNoEncontrada`/`EjecucionOrigenNoElegible`
    si `ejecucion_origen_id` no existe o no cumple
    `domain.elegibilidad_reverso.puede_generar_operacion_derivada` (B6): la
    autoridad de elegibilidad es SIEMPRE del servidor, nunca de lo que un
    POST declare (B7, puntos 15/16) -asi una ejecucion origen no elegible,
    o un id inexistente, nunca llega a generar un STAN ni a tocar la red.
    """
    origen = await repositorio_ejecuciones.obtener(ejecucion_origen_id)
    if origen is None:
        raise EjecucionOrigenNoEncontrada(f"no existe la ejecución #{ejecucion_origen_id}")
    if not puede_generar_operacion_derivada(origen):
        raise EjecucionOrigenNoElegible(
            f"la ejecución #{ejecucion_origen_id} no es elegible para generar una operación derivada"
        )
    detalle = DetalleEjecucion(
        ejecucion=origen,
        solicitud=interpretar(origen.solicitud_json, origen.solicitud_enmascarada),
        respuesta=interpretar(origen.respuesta_json, origen.respuesta_enmascarada),
    )
    return referencia_desde_detalle(detalle)

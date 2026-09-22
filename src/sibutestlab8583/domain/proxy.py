"""Modelo de dominio del Proxy ISO 8583 transparente (Fase E1, 2026-09-21).

Un proxy se sienta entre un cliente y un host/switch upstream, reenviando
frames TAL CUAL -nunca decodifica-modifica-reencodea para reenviar (ver
`adapters.proxy.servidor`, que es quien de verdad mueve bytes). Este modulo
solo define los tipos DE DATOS de una sesion y de un mensaje capturado, en
el mismo espiritu que `domain.reglas_host` separa el modelo de la
evaluacion: puros, sin I/O, sin asyncio.

SEGURIDAD (punto 9/29 del encargo): `MensajeProxyCapturado` es
deliberadamente ciego a los campos de un mensaje -igual que
`domain.reglas_host.EventoReglaHost` (D1/D2), el tipo de captura no tiene
ningun campo tipo `Mapping[str, str]`/`raw`/`payload` que pueda aceptar un
valor arbitrario del mensaje. Solo metadata: direccion, orden, longitud,
MTI (si el frame pudo decodificarse). Nunca el PAN, nunca Track1/Track2,
nunca el frame completo -eso vive solo en memoria, durante el forwarding,
y nunca cruza hacia persistencia u observabilidad.

CORRELADORES SEGUROS (E2.1, 2026-09-21): dos campos NOMBRADOS
explicitamente -`stan` (DE11) y `rrn` (DE37)- se agregan como excepcion
DELIBERADA y ACOTADA a la regla anterior, nunca como un
`Mapping[str, str]` generico que pudiera aceptar cualquier numero de
campo: son los unicos dos correladores que este modulo conoce, elegidos
porque ninguno de los dos es sensible (`perfil.es_sensible` los excluiria
si algun perfil futuro los marcara asi -ver `adapters.proxy.servidor.
_registrar_mensaje`, que vuelve a consultar esa autoridad en cada captura,
nunca confia ciegamente en que "11"/"37" sean siempre seguros). Sin
`stan`/`rrn` (captura historica, anterior a E2.1, o el campo no aparecio
en el mensaje), la correlacion sigue funcionando por MTI + orden
temporal -ver `derivar_intercambios`."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Sequence

from .validacion import mti_de_respuesta


class EstadoSesionProxy(str, Enum):
    """Ciclo de vida de una sesion: nace conectando, pasa a activa en cuanto
    el upstream responde la conexion TCP, y termina cerrada -nunca un
    booleano suelto "activo/inactivo" (mismo criterio que D2 con
    `EstadoReglaHost`/`es_agotada`: un enum explicito, no una bandera)."""

    CONECTANDO = "conectando"
    ACTIVA = "activa"
    CERRADA = "cerrada"


class MotivoCierreProxy(str, Enum):
    """Por que termino una sesion -siempre explicito, nunca "se cerro" a
    secas. Distingue el lado que origino el cierre (cliente/upstream) y si
    fue un cierre limpio (EOF) o un error de transporte."""

    EOF_CLIENTE = "eof_cliente"
    EOF_UPSTREAM = "eof_upstream"
    ERROR_CLIENTE = "error_cliente"
    ERROR_UPSTREAM = "error_upstream"
    TIMEOUT_INACTIVIDAD = "timeout_inactividad"
    FALLO_CONEXION_UPSTREAM = "fallo_conexion_upstream"
    APAGADO_PROXY = "apagado_proxy"


class DireccionMensajeProxy(str, Enum):
    """De que lado hacia cual cruzo un frame -nunca implicito por orden de
    aparicion en una lista."""

    CLIENTE_A_UPSTREAM = "cliente_a_upstream"
    UPSTREAM_A_CLIENTE = "upstream_a_cliente"


@dataclass
class SesionProxy:
    """Una conexion-cliente y su conexion-upstream emparejada 1:1. Mutable
    -a diferencia de `ReglaHost`/`EventoReglaHost` (que son inmutables
    porque representan configuracion/auditoria ya decidida), una sesion
    describe una conexion VIVA cuyo estado cambia mientras el proxy la
    atiende; el repositorio persiste snapshots de estos cambios, nunca
    referencias compartidas."""

    session_id: str
    cliente_host: str
    cliente_puerto: int
    upstream_host: str
    upstream_puerto: int
    estado: EstadoSesionProxy = EstadoSesionProxy.CONECTANDO
    motivo_cierre: MotivoCierreProxy | None = None
    inicio: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    fin: datetime | None = None


@dataclass(frozen=True)
class IntercambioProxy:
    """Un par logico solicitud/respuesta DERIVADO en tiempo de lectura por
    `derivar_intercambios` -nunca persistido (Fase E2, punto 2 del encargo:
    "no persistirlo automaticamente si puede derivarse"). `respuesta` es
    `None` cuando no se encontro una correlacion confiable -nunca se
    inventa una pareja por posicion (punto 3)."""

    solicitud: "MensajeProxyCapturado"
    respuesta: "MensajeProxyCapturado | None"
    correlacionado: bool


#: Orden de preferencia de los correladores seguros -STAN primero (E2.1,
#: punto 4 del encargo): si el STAN de la solicitud coincide con EXACTAMENTE
#: una candidata, esa coincidencia PESA MAS que la posicion temporal (nunca
#: se exige DE37 si la solicitud no lo trae).
_ATRIBUTOS_CORRELADORES = ("stan", "rrn")


def derivar_intercambios(mensajes: Sequence["MensajeProxyCapturado"]) -> tuple[IntercambioProxy, ...]:
    """Empareja cada solicitud (`CLIENTE_A_UPSTREAM`) interpretable con una
    respuesta (`UPSTREAM_A_CLIENTE`) interpretable, no usada todavia, cuyo
    MTI sea exactamente `mti_de_respuesta(mti_solicitud)` y que haya
    ocurrido despues en el tiempo.

    Algoritmo (E2.1, punto 4 del encargo -cierra la ambiguedad real de un
    proxy full-duplex con dos solicitudes del mismo MTI en vuelo a la
    vez-): entre las candidatas por MTI/tiempo, si la solicitud trae un
    correlador seguro (`stan`, y si no `rrn`) que coincide con EXACTAMENTE
    una candidata, esa es la pareja -sin importar si hay otras candidatas
    mas cercanas en el tiempo. Solo si NINGUN correlador esta disponible
    (captura anterior a E2.1, o el campo no viajo en el mensaje) se cae a
    "unica candidata por tiempo" -y solo si es realmente unica-. Con mas
    de una candidata y sin un correlador que la distinga: `correlacionado
    =False`, nunca una pareja inventada por cercania posicional (punto 5).

    Deliberadamente NO correlaciona por posicion/orden -el `orden` de
    `MensajeProxyCapturado` es un contador POR DIRECCION (ver
    `adapters.proxy.servidor`), nunca un indice global de la sesion."""
    ordenados = sorted(mensajes, key=lambda m: (m.creado_en, m.orden))
    respuestas_disponibles = [
        m for m in ordenados
        if m.direccion is DireccionMensajeProxy.UPSTREAM_A_CLIENTE and m.interpretable
    ]
    consumidas: set[object] = set()
    intercambios: list[IntercambioProxy] = []
    for solicitud in ordenados:
        if solicitud.direccion is not DireccionMensajeProxy.CLIENTE_A_UPSTREAM:
            continue
        respuesta_encontrada = _correlacionar_respuesta(
            solicitud, respuestas_disponibles, consumidas
        )
        if respuesta_encontrada is not None:
            clave = respuesta_encontrada.mensaje_id
            consumidas.add(clave if clave is not None else id(respuesta_encontrada))
        intercambios.append(IntercambioProxy(
            solicitud=solicitud, respuesta=respuesta_encontrada,
            correlacionado=respuesta_encontrada is not None,
        ))
    return tuple(intercambios)


def _correlacionar_respuesta(
    solicitud: "MensajeProxyCapturado",
    respuestas_disponibles: Sequence["MensajeProxyCapturado"],
    consumidas: set[object],
) -> "MensajeProxyCapturado | None":
    if not solicitud.interpretable:
        return None
    try:
        esperado = mti_de_respuesta(solicitud.mti)
    except (KeyError, IndexError):
        return None

    candidatas = [
        r for r in respuestas_disponibles
        if (r.mensaje_id if r.mensaje_id is not None else id(r)) not in consumidas
        and r.mti == esperado
        and r.creado_en >= solicitud.creado_en
    ]
    if not candidatas:
        return None

    for atributo in _ATRIBUTOS_CORRELADORES:
        valor_solicitud = getattr(solicitud, atributo)
        if valor_solicitud is None:
            continue
        exactas = [c for c in candidatas if getattr(c, atributo) == valor_solicitud]
        if len(exactas) == 1:
            return exactas[0]
        # Mas de una candidata comparte el mismo correlador (no deberia
        # pasar en trafico real -un STAN se reutiliza dentro de una
        # ventana- pero nunca se adivina cual es la correcta): ninguna
        # coincidencia, no cero candidatas -> ambiguo, no temporal.
        if len(exactas) > 1:
            return None

    if len(candidatas) == 1:
        return candidatas[0]
    return None


@dataclass(frozen=True)
class MensajeProxyCapturado:
    """Metadata segura de UN frame que cruzo el proxy en una direccion.
    Nunca contiene el payload ni ningun campo del mensaje -ver el aviso de
    seguridad al inicio de este modulo."""

    session_id: str
    direccion: DireccionMensajeProxy
    orden: int
    longitud: int
    mti: str | None = None
    interpretable: bool = True
    mensaje_id: int | None = None
    creado_en: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    stan: str | None = None
    rrn: str | None = None


@dataclass(frozen=True)
class OrigenCapturaEscenario:
    """Trazabilidad de procedencia (Fase E2): un Escenario nacio de esta
    sesion/mensaje del Proxy. Tabla separada de `Escenario` -mismo principio
    de D1/D2/E1: la procedencia es un hecho historico, nunca deberia mutar
    ni arrastrarse en silencio al duplicar el escenario."""

    escenario_id: str
    session_id: str
    mensaje_id_solicitud: int
    mensaje_id_respuesta: int | None = None
    creado_en: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

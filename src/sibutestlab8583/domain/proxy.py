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
y nunca cruza hacia persistencia u observabilidad."""

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


def derivar_intercambios(mensajes: Sequence["MensajeProxyCapturado"]) -> tuple[IntercambioProxy, ...]:
    """Empareja cada solicitud (`CLIENTE_A_UPSTREAM`) interpretable con la
    primera respuesta (`UPSTREAM_A_CLIENTE`) interpretable, no usada
    todavia, cuyo MTI sea exactamente `mti_de_respuesta(mti_solicitud)` y
    que haya ocurrido despues en el tiempo -mismo criterio de "el orden
    importa" que ya usa RN-3 para correlacionar solicitud/respuesta del
    lado cliente-host (`domain.validacion`).

    Deliberadamente NO correlaciona por posicion/orden -el `orden` de
    `MensajeProxyCapturado` es un contador POR DIRECCION (ver
    `adapters.proxy.servidor`), nunca un indice global de la sesion- ni por
    STAN -el proxy nunca lo captura, ver el aviso de seguridad de este
    modulo-. Una solicitud sin respuesta correlacionada (agotamiento,
    desconexion, MTI no reconocido, o una respuesta ya consumida por una
    solicitud anterior) queda con `respuesta=None`/`correlacionado=False`
    -nunca se inventa una pareja por cercania posicional (E2, punto 3)."""
    ordenados = sorted(mensajes, key=lambda m: (m.creado_en, m.orden))
    respuestas_disponibles = [
        m for m in ordenados
        if m.direccion is DireccionMensajeProxy.UPSTREAM_A_CLIENTE and m.interpretable
    ]
    consumidas: set[int | None] = set()
    intercambios: list[IntercambioProxy] = []
    for solicitud in ordenados:
        if solicitud.direccion is not DireccionMensajeProxy.CLIENTE_A_UPSTREAM:
            continue
        respuesta_encontrada: MensajeProxyCapturado | None = None
        if solicitud.interpretable:
            try:
                esperado = mti_de_respuesta(solicitud.mti)
            except (KeyError, IndexError):
                esperado = None
            if esperado is not None:
                for candidata in respuestas_disponibles:
                    clave = candidata.mensaje_id if candidata.mensaje_id is not None else id(candidata)
                    if (
                        clave not in consumidas
                        and candidata.mti == esperado
                        and candidata.creado_en >= solicitud.creado_en
                    ):
                        respuesta_encontrada = candidata
                        consumidas.add(clave)
                        break
        intercambios.append(IntercambioProxy(
            solicitud=solicitud, respuesta=respuesta_encontrada,
            correlacionado=respuesta_encontrada is not None,
        ))
    return tuple(intercambios)


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

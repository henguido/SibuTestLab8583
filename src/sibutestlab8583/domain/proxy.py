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

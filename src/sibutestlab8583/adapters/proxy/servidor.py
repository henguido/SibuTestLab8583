"""Proxy TCP ISO 8583 TRANSPARENTE (Fase E1, 2026-09-21).

Cliente -> ProxyIso8583 -> Upstream (host/switch real o `HostSimulado`).

TRANSPARENCIA COMO REQUISITO (punto 2/3/30 del encargo): el forwarding
preserva el frame ORIGINAL byte por byte -nunca hace
`decode -> modificar -> encode -> enviar`. Cada `_pump` lee un frame
opaco con `framing.leer_mensaje_completo()` y lo reescribe con
`framing.preparar()` sobre el MISMO payload, sin tocarlo. El codec ISO 8583
solo se invoca DESPUES de reenviar, sobre una copia, exclusivamente para
observabilidad (MTI capturado en `proxy_mensajes`) -si falla, nunca aborta
ni retrasa el forwarding (punto 10: "no bloquea el trafico").

Reutiliza el mismo `FramingStrategy` que el cliente y el Host Simulado
(nunca un protocolo nuevo, punto 6). A diferencia de `HostSimulado`/
`TransporteTcp` (una conexion = un solo mensaje = cierre), una sesion de
proxy es una conexion PERSISTENTE con dos "pumps" concurrentes -uno por
sentido- corriendo mientras la conexion viva (full duplex, punto 5).

CIERRE COORDINADO (punto 5 del encargo): en cuanto un lado se cae (EOF o
error), el proxy cierra el OTRO lado y cancela su pump -nunca deja una
tarea huerfana corriendo despues de que la sesion termino.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from datetime import datetime, timezone
from typing import NamedTuple

from ...domain.errores import ErrorDeCodec, ErrorDeFraming
from ...domain.modelos import DestinoTcp
from ...domain.proxy import (
    DireccionMensajeProxy,
    EstadoSesionProxy,
    MensajeProxyCapturado,
    MotivoCierreProxy,
    SesionProxy,
)

logger = logging.getLogger(__name__)

#: Tiempos por defecto. Distintos, a proposito, del `tiempo_limite` de
#: `TransporteTcp`: ahi se acota UNA transaccion ISO; aqui se acota (a)
#: cuanto se espera para que el upstream acepte la conexion TCP inicial y
#: (b) cuanto puede pasar SIN que un lado mande nada antes de considerar la
#: sesion inactiva (punto 14 del encargo: "no confundir timeout del proxy
#: con timeout ISO de una transaccion").
TIEMPO_LIMITE_CONEXION_POR_DEFECTO = 5.0
TIEMPO_LIMITE_INACTIVIDAD_POR_DEFECTO = 120.0

#: Correladores seguros (E2.1): los UNICOS dos campos que este adaptador
#: intenta extraer para observabilidad, ademas del MTI -nunca una lista
#: abierta. `perfil.es_sensible` sigue siendo la autoridad que decide si
#: de verdad se persisten (ver `_registrar_mensaje`).
CAMPO_STAN = "11"
CAMPO_RRN = "37"

_MOTIVO_EOF_POR_DIRECCION = {
    DireccionMensajeProxy.CLIENTE_A_UPSTREAM: MotivoCierreProxy.EOF_CLIENTE,
    DireccionMensajeProxy.UPSTREAM_A_CLIENTE: MotivoCierreProxy.EOF_UPSTREAM,
}
_MOTIVO_ERROR_ORIGEN_POR_DIRECCION = {
    DireccionMensajeProxy.CLIENTE_A_UPSTREAM: MotivoCierreProxy.ERROR_CLIENTE,
    DireccionMensajeProxy.UPSTREAM_A_CLIENTE: MotivoCierreProxy.ERROR_UPSTREAM,
}
_MOTIVO_ERROR_DESTINO_POR_DIRECCION = {
    DireccionMensajeProxy.CLIENTE_A_UPSTREAM: MotivoCierreProxy.ERROR_UPSTREAM,
    DireccionMensajeProxy.UPSTREAM_A_CLIENTE: MotivoCierreProxy.ERROR_CLIENTE,
}


class _SesionActiva(NamedTuple):
    sesion: SesionProxy
    cliente_escritor: asyncio.StreamWriter
    upstream_escritor: asyncio.StreamWriter
    tarea_c2u: asyncio.Task
    tarea_u2c: asyncio.Task
    tareas_auditoria: list


class ProxyIso8583:
    """Servidor TCP asincrono que reenvia frames tal cual entre un cliente
    y un upstream configurado. `codec`/`perfil` son OPCIONALES: sin ellos,
    el proxy sigue reenviando exactamente igual, solo que ningun mensaje se
    marca como interpretable (nunca decodifica -> el forwarding no depende
    del codec, punto 3 del encargo)."""

    def __init__(
        self,
        framing,
        destino_upstream: DestinoTcp,
        *,
        codec=None,
        perfil=None,
        tiempo_limite_conexion: float = TIEMPO_LIMITE_CONEXION_POR_DEFECTO,
        tiempo_limite_inactividad: float = TIEMPO_LIMITE_INACTIVIDAD_POR_DEFECTO,
        repositorio_sesiones=None,
        repositorio_mensajes=None,
    ) -> None:
        self._framing = framing
        self._destino = destino_upstream
        self._codec = codec
        self._perfil = perfil
        self._tiempo_limite_conexion = tiempo_limite_conexion
        self._tiempo_limite_inactividad = tiempo_limite_inactividad
        self._repositorio_sesiones = repositorio_sesiones
        self._repositorio_mensajes = repositorio_mensajes
        self._servidor: asyncio.AbstractServer | None = None
        self._sesiones: dict[str, _SesionActiva] = {}
        self.host: str | None = None
        self.puerto: int | None = None
        self.sesiones_atendidas = 0

    async def iniciar(self, host: str = "127.0.0.1", puerto: int = 0) -> tuple[str, int]:
        """Levanta el servidor. Con puerto 0 el sistema asigna uno efimero."""
        self._servidor = await asyncio.start_server(self._atender, host, puerto)
        direccion = self._servidor.sockets[0].getsockname()
        self.host, self.puerto = direccion[0], direccion[1]
        return self.host, self.puerto

    async def detener(self) -> None:
        """Apagado ordenado (punto 6/11 del encargo): deja de aceptar
        conexiones nuevas, cierra ambos lados de cada sesion activa -lo que
        hace que sus pumps reciban EOF/error y se cierren por el mecanismo
        normal de `_atender`, sin un segundo camino de limpieza paralelo- y
        espera a que todas terminen antes de devolver el control."""
        if self._servidor is not None:
            self._servidor.close()
        tareas = []
        for activa in list(self._sesiones.values()):
            activa.cliente_escritor.close()
            activa.upstream_escritor.close()
            tareas.extend((activa.tarea_c2u, activa.tarea_u2c, *activa.tareas_auditoria))
        if tareas:
            await asyncio.gather(*tareas, return_exceptions=True)
        if self._servidor is not None:
            await self._servidor.wait_closed()
            self._servidor = None

    async def __aenter__(self) -> "ProxyIso8583":
        await self.iniciar()
        return self

    async def __aexit__(self, *_) -> None:
        await self.detener()

    async def _atender(
        self, cliente_lector: asyncio.StreamReader, cliente_escritor: asyncio.StreamWriter
    ) -> None:
        session_id = uuid.uuid4().hex
        peer = cliente_escritor.get_extra_info("peername") or ("desconocido", 0)
        sesion = SesionProxy(
            session_id=session_id,
            cliente_host=str(peer[0]),
            cliente_puerto=int(peer[1]),
            upstream_host=self._destino.host,
            upstream_puerto=self._destino.puerto,
        )
        if self._repositorio_sesiones is not None:
            await self._repositorio_sesiones.crear(sesion)

        try:
            upstream_lector, upstream_escritor = await asyncio.wait_for(
                asyncio.open_connection(self._destino.host, self._destino.puerto),
                timeout=self._tiempo_limite_conexion,
            )
        except (OSError, asyncio.TimeoutError):
            await self._finalizar(sesion, MotivoCierreProxy.FALLO_CONEXION_UPSTREAM)
            cliente_escritor.close()
            with contextlib.suppress(Exception):
                await cliente_escritor.wait_closed()
            return

        self.sesiones_atendidas += 1
        sesion.estado = EstadoSesionProxy.ACTIVA
        if self._repositorio_sesiones is not None:
            await self._repositorio_sesiones.actualizar(sesion)

        # Tareas de registro de auditoria (`_registrar_mensaje`), lanzadas
        # SIN esperar en linea desde el pump -ver `_pump`- para que
        # cancelar un pump (cuando el otro lado ya cerro) nunca aborte una
        # escritura de auditoria que YA estaba en curso. Rastreadas aqui
        # para poder esperarlas explicitamente antes de dar la sesion por
        # terminada: un `asyncio.shield` sin esto protege la escritura de
        # la cancelacion, pero nadie esperaria a que de verdad termine.
        tareas_auditoria: list[asyncio.Task] = []
        contador_c2u = [0]
        contador_u2c = [0]
        tarea_c2u = asyncio.create_task(self._pump(
            cliente_lector, upstream_escritor, DireccionMensajeProxy.CLIENTE_A_UPSTREAM,
            sesion, contador_c2u, tareas_auditoria,
        ))
        tarea_u2c = asyncio.create_task(self._pump(
            upstream_lector, cliente_escritor, DireccionMensajeProxy.UPSTREAM_A_CLIENTE,
            sesion, contador_u2c, tareas_auditoria,
        ))
        self._sesiones[session_id] = _SesionActiva(
            sesion, cliente_escritor, upstream_escritor, tarea_c2u, tarea_u2c, tareas_auditoria
        )

        try:
            listas, pendientes = await asyncio.wait(
                {tarea_c2u, tarea_u2c}, return_when=asyncio.FIRST_COMPLETED
            )
            motivo = next(iter(listas)).result()
            for pendiente in pendientes:
                pendiente.cancel()
            if pendientes:
                await asyncio.gather(*pendientes, return_exceptions=True)
            if tareas_auditoria:
                await asyncio.gather(*tareas_auditoria, return_exceptions=True)
        finally:
            self._sesiones.pop(session_id, None)
            cliente_escritor.close()
            upstream_escritor.close()
            with contextlib.suppress(Exception):
                await cliente_escritor.wait_closed()
            with contextlib.suppress(Exception):
                await upstream_escritor.wait_closed()

        await self._finalizar(sesion, motivo)

    async def _pump(
        self,
        lector: asyncio.StreamReader,
        escritor: asyncio.StreamWriter,
        direccion: DireccionMensajeProxy,
        sesion: SesionProxy,
        contador: list,
        tareas_auditoria: list,
    ) -> MotivoCierreProxy:
        """Lee frames del origen y los reenvia AL ESCRITOR SIN TOCARLOS
        (punto 3: prohibido decode->modificar->encode->enviar para
        reenviar). Corre hasta que el origen se cierra, el destino falla al
        escribir, o pasa `tiempo_limite_inactividad` sin un frame nuevo."""
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(
                        self._framing.leer_mensaje_completo(lector),
                        timeout=self._tiempo_limite_inactividad,
                    )
                except asyncio.TimeoutError:
                    return MotivoCierreProxy.TIMEOUT_INACTIVIDAD
                except ErrorDeFraming as error:
                    parcial = getattr(error.__cause__, "partial", None)
                    if parcial is not None and len(parcial) == 0:
                        return _MOTIVO_EOF_POR_DIRECCION[direccion]
                    return _MOTIVO_ERROR_ORIGEN_POR_DIRECCION[direccion]

                try:
                    escritor.write(self._framing.preparar(payload))
                    await escritor.drain()
                except (OSError, ErrorDeFraming):
                    return _MOTIVO_ERROR_DESTINO_POR_DIRECCION[direccion]

                contador[0] += 1
                # Lanzada como tarea INDEPENDIENTE, nunca esperada en linea
                # aqui: si ESTE pump se cancela (porque el otro lado ya
                # cerro, ver `_atender`) mientras el registro de auditoria
                # sigue en vuelo, la cancelacion del pump nunca debe abortar
                # una escritura que YA esta en curso -un `await` directo (o
                # incluso `asyncio.shield`, que protege la escritura pero
                # a nadie deja esperandola) dejaria a `_atender` creyendo
                # terminada la sesion antes de que el INSERT realmente
                # comprometiera. `_atender` reune estas tareas explicitamente
                # (`tareas_auditoria`) antes de finalizar la sesion.
                tareas_auditoria.append(asyncio.ensure_future(
                    self._registrar_mensaje(sesion, direccion, contador[0], payload)
                ))
        except asyncio.CancelledError:
            raise
        except OSError:
            return _MOTIVO_ERROR_ORIGEN_POR_DIRECCION[direccion]

    async def _registrar_mensaje(
        self, sesion: SesionProxy, direccion: DireccionMensajeProxy, orden: int, payload: bytes,
    ) -> None:
        """Observabilidad de mejor esfuerzo, DESPUES de reenviar (nunca
        antes, nunca bloqueando el forwarding): intenta decodificar una
        COPIA del payload solo para capturar el MTI y, si estan presentes y
        no son sensibles, los correladores seguros DE11 (STAN)/DE37 (RRN)
        -E2.1, ver el aviso de seguridad en `domain.proxy`-. Si falla, el
        mensaje queda igual registrado con `interpretable=False` -nunca se
        descarta, nunca detiene el trafico (punto 10)."""
        mti: str | None = None
        interpretable = False
        stan: str | None = None
        rrn: str | None = None
        if self._codec is not None and self._perfil is not None:
            try:
                decodificado = self._codec.decodificar(bytes(payload), self._perfil)
                mti = decodificado.mti
                interpretable = True
                # Autoridad UNICA de sensibilidad -nunca una lista propia
                # para el proxy (punto 3 del encargo E2.1): se vuelve a
                # consultar en cada captura, nunca se confia en que "11"/
                # "37" sean siempre seguros de antemano.
                if CAMPO_STAN in decodificado.campos and not self._perfil.es_sensible(CAMPO_STAN):
                    stan = decodificado.campos[CAMPO_STAN].valor
                if CAMPO_RRN in decodificado.campos and not self._perfil.es_sensible(CAMPO_RRN):
                    rrn = decodificado.campos[CAMPO_RRN].valor
            except ErrorDeCodec:
                interpretable = False
            except Exception:  # nunca deja que un fallo de observabilidad tumbe el proxy
                logger.exception("fallo inesperado decodificando para observabilidad")
                interpretable = False

        if self._repositorio_mensajes is None:
            return
        mensaje = MensajeProxyCapturado(
            session_id=sesion.session_id,
            direccion=direccion,
            orden=orden,
            longitud=len(payload),
            mti=mti,
            interpretable=interpretable,
            stan=stan,
            rrn=rrn,
        )
        await self._repositorio_mensajes.registrar(mensaje)

    async def _finalizar(self, sesion: SesionProxy, motivo: MotivoCierreProxy) -> None:
        sesion.estado = EstadoSesionProxy.CERRADA
        sesion.motivo_cierre = motivo
        sesion.fin = datetime.now(timezone.utc)
        if self._repositorio_sesiones is not None:
            await self._repositorio_sesiones.actualizar(sesion)

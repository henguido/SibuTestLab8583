"""Orquestador del recorrido de compra 0100/0110.

Es la unica pieza que conoce a todas las demas, y las conoce **solo por sus
contratos**: no importa `aiosqlite`, ni `pyiso8583`, ni `asyncio.open_connection`.
Eso es lo que permitira que el motor de pruebas de carga reutilice transporte,
validacion y persistencia sin modificarlos.

Orden del recorrido, que no se altera:

    DatosCompra -> armar 0100 -> RN-4 -> codificar -> transporte
                -> FalloDeConexion?    -> ERROR_CONEXION
                -> FalloDeTransmision? -> ERROR_TRANSMISION
                -> TiempoAgotado?      -> TIMEOUT (RN-2)
                -> bytes?              -> decodificar -> RN-3 y RN-1

Todo intento queda persistido, incluidos los que no llegan a la red: un intento
que desaparece del historial deja al usuario sin rastro de haberlo hecho.

Los estados se eligen por lo que cada situacion permite **demostrar**:

- NO_ENVIADA solo cuando es demostrable que no se llego a intentar transmision
  por la red: falta un campo obligatorio (RN-4), el codec no pudo codificar, o
  el framing de salida rechazo el payload antes de abrir la conexion. El framing
  pertenece al transporte, asi que no se dice 'no llego al transporte'.
- ERROR_CONEXION solo cuando no hubo sesion TCP.
- ERROR_TRANSMISION cuando hubo sesion y el intercambio quedo indeterminado.
  Aqui **no** se afirma que nada se envio, porque no se puede saber.
- TIMEOUT solo con las cuatro premisas de RN-2 cumplidas. Que el drenaje local
  termine no demuestra que el destino recibiera: eso no se afirma en ningun lado.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Callable

from ..domain.armado import armar_compra
from ..domain.catalogo import CatalogoDeRespuestas
from ..domain.errores import ErrorDeCodec, ErrorDeFraming
from ..domain.modelos import (
    CAMPOS_SENSIBLES,
    DatosCompra,
    DestinoTcp,
    Ejecucion,
    EstadoEjecucion,
    FalloDeConexion,
    FalloDeTransmision,
    MensajeInterpretado,
    MensajeIso,
    ResultadoCompra,
    TiempoAgotado,
)
from ..domain.puertos import (
    GeneradorStan,
    RepositorioEjecuciones,
    RepositorioTarjetas,
    Transporte,
)
from ..domain.validacion import CAMPO_CODIGO_RESPUESTA, evaluar_respuesta, validar_envio


class TarjetaDesconocida(Exception):
    """El `card_id` no existe en el catalogo de tarjetas de prueba."""


class Orquestador:
    def __init__(
        self,
        *,
        codec,
        perfil,
        catalogo: CatalogoDeRespuestas,
        transporte: Transporte,
        repositorio_ejecuciones: RepositorioEjecuciones,
        repositorio_tarjetas: RepositorioTarjetas,
        generador_stan: GeneradorStan,
        destino: DestinoTcp,
        codigo_proceso: str,
        tiempo_limite: float | None = None,
        reloj: Callable[[], datetime] | None = None,
    ) -> None:
        self._codec = codec
        self._perfil = perfil
        self._catalogo = catalogo
        self._transporte = transporte
        self._ejecuciones = repositorio_ejecuciones
        self._tarjetas = repositorio_tarjetas
        self._destino = destino
        self._codigo_proceso = codigo_proceso
        self._tiempo_limite = tiempo_limite
        self._stan = generador_stan
        self._reloj = reloj or (lambda: datetime.now(timezone.utc))

    async def ejecutar_compra(self, datos: DatosCompra) -> ResultadoCompra:
        tarjeta = await self._tarjetas.obtener(datos.card_id)
        if tarjeta is None:
            raise TarjetaDesconocida(f"no existe la tarjeta {datos.card_id!r}")

        momento = self._reloj()
        # El STAN lo entrega un puerto persistente, no un contador de esta
        # instancia: el orquestador se construye por peticion y un contador
        # local reiniciaria en 1 cada vez.
        stan = await self._stan.siguiente()
        solicitud = armar_compra(
            datos,
            tarjeta,
            stan=stan,
            momento=momento,
            codigo_proceso=self._codigo_proceso,
        )

        # --- RN-4: si falta un obligatorio, no se codifica ni se envia ---
        validacion = validar_envio(solicitud, self._perfil)
        if not validacion:
            return await self._registrar(
                solicitud,
                stan,
                datos,
                EstadoEjecucion.NO_ENVIADA,
                motivos=validacion.motivos,
            )

        # Codificar puede fallar. Si falla, no se llega a intentar transmision
        # por la red, y eso si es demostrable: es el mismo caso que RN-4.
        try:
            payload = self._codec.codificar(solicitud, self._perfil)
        except ErrorDeCodec as error:
            return await self._registrar(
                solicitud, stan, datos, EstadoEjecucion.NO_ENVIADA, motivos=(str(error),)
            )

        inicio = time.monotonic()
        try:
            respuesta_cruda = await self._transporte.enviar(
                payload, self._destino, self._tiempo_limite
            )
        except ErrorDeFraming as error:
            # preparar() corre antes de abrir la conexion, asi que aqui tambien es
            # demostrable que nada se intento transmitir. Un fallo de DESenmarcado
            # despues de conectar no llega por aqui: el transporte lo convierte en
            # FalloDeTransmision, porque entonces ya no se puede afirmar lo mismo.
            return await self._registrar(
                solicitud, stan, datos, EstadoEjecucion.NO_ENVIADA, motivos=(str(error),)
            )
        latencia_ms = int((time.monotonic() - inicio) * 1000)

        # --- No hubo sesion TCP. Demostrable que nada se transmitio ---
        if isinstance(respuesta_cruda, FalloDeConexion):
            return await self._registrar(
                solicitud,
                stan,
                datos,
                EstadoEjecucion.ERROR_CONEXION,
                motivos=(respuesta_cruda.detalle,),
                latencia_ms=latencia_ms,
            )

        # --- Hubo sesion y el intercambio quedo indeterminado ---
        if isinstance(respuesta_cruda, FalloDeTransmision):
            return await self._registrar(
                solicitud,
                stan,
                datos,
                EstadoEjecucion.ERROR_TRANSMISION,
                motivos=(respuesta_cruda.detalle,),
                latencia_ms=latencia_ms,
            )

        # --- RN-2: se espero una respuesta y no llego dentro del limite.
        # Sin respuesta no hay nada que evaluar ---
        if isinstance(respuesta_cruda, TiempoAgotado):
            return await self._registrar(
                solicitud,
                stan,
                datos,
                EstadoEjecucion.TIMEOUT,
                motivos=(
                    f"sin respuesta en {respuesta_cruda.limite_segundos:g} s",
                ),
                latencia_ms=latencia_ms,
            )

        try:
            interpretada = self._codec.decodificar(respuesta_cruda, self._perfil)
        except ErrorDeCodec as error:
            return await self._registrar(
                solicitud,
                stan,
                datos,
                EstadoEjecucion.INVALIDA,
                motivos=(str(error),),
                latencia_ms=latencia_ms,
            )

        # --- RN-3 primero, luego RN-1 ---
        estado, motivos = evaluar_respuesta(
            solicitud, interpretada.como_mensaje(), self._catalogo, self._perfil
        )
        return await self._registrar(
            solicitud,
            stan,
            datos,
            estado,
            motivos=motivos,
            respuesta=interpretada,
            latencia_ms=latencia_ms,
        )

    async def _registrar(
        self,
        solicitud: MensajeIso,
        stan: str,
        datos: DatosCompra,
        estado: EstadoEjecucion,
        *,
        motivos: tuple[str, ...] = (),
        respuesta: MensajeInterpretado | None = None,
        latencia_ms: int | None = None,
    ) -> ResultadoCompra:
        """Construye la Ejecucion, la persiste enmascarada y devuelve el resultado."""
        # Se registra el destino en todo intento que llego a tocar la red, y por
        # eso tambien en ERROR_CONEXION: saber contra que se intento es la mitad
        # del diagnostico. Solo NO_ENVIADA se queda sin destino, porque no hubo.
        hubo_intento_de_red = estado is not EstadoEjecucion.NO_ENVIADA
        ejecucion = Ejecucion(
            card_id=datos.card_id,
            monto=datos.monto,
            moneda=datos.moneda,
            stan=stan,
            estado=estado,
            mti_solicitud=solicitud.mti,
            mti_respuesta=respuesta.mti if respuesta else None,
            codigo_respuesta=respuesta.valor(CAMPO_CODIGO_RESPUESTA) if respuesta else None,
            destino_host=self._destino.host if hubo_intento_de_red else None,
            destino_puerto=self._destino.puerto if hubo_intento_de_red else None,
            solicitud_enmascarada=_serializar(solicitud.enmascarado()),
            respuesta_enmascarada=(
                _serializar(respuesta.enmascarado().como_mensaje()) if respuesta else None
            ),
            latencia_ms=latencia_ms,
            creada_en=self._reloj(),
        )
        await self._ejecuciones.guardar(ejecucion)
        return ResultadoCompra(
            ejecucion=ejecucion,
            solicitud=solicitud.enmascarado(),
            respuesta=respuesta.enmascarado() if respuesta else None,
            motivos=tuple(motivos),
        )


def _serializar(mensaje: MensajeIso) -> str:
    """Texto legible de un mensaje YA enmascarado, para persistir y mostrar.

    Recibe siempre la version enmascarada; la comprobacion de abajo existe para
    que un cambio futuro no cuele un PAN completo a la base de datos.
    """
    partes = [f"MTI={mensaje.mti}"]
    for numero in sorted(mensaje.campos, key=int):
        valor = mensaje.campos[numero]
        if numero in CAMPOS_SENSIBLES and valor.isdigit():
            raise AssertionError(f"el campo {numero} llego sin enmascarar a la persistencia")
        partes.append(f"{numero}={valor}")
    return " | ".join(partes)


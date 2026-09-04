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
from .serializacion import a_json_respuesta, a_json_solicitud, a_texto


class TarjetaDesconocida(Exception):
    """El `card_id` no existe en el catalogo de tarjetas de prueba, o esta inactiva.

    Una tarjeta inactiva se trata igual que una inexistente para una ejecucion
    nueva: no se le revela al llamador la diferencia entre "no existe" y "existe
    pero esta desactivada", porque para el flujo de compra el efecto es el
    mismo, y no vale la pena una segunda excepcion para una distincion que nadie
    consume todavia.
    """


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
        self._tiempo_limite = tiempo_limite
        self._stan = generador_stan
        self._reloj = reloj or (lambda: datetime.now(timezone.utc))

    async def ejecutar_compra(
        self,
        datos: DatosCompra,
        *,
        escenario_id: str | None = None,
        escenario_nombre: str | None = None,
    ) -> ResultadoCompra:
        """Arma, valida y ejecuta una compra. `escenario_id`/`escenario_nombre`
        son puramente informativos: este metodo no sabe que es un escenario ni
        depende de `application.escenarios` -el llamador ya resolvio esos
        valores, y aqui solo se copian a la `Ejecucion` para trazabilidad en el
        historial-. Construccion y ejecucion no se separan: reejecutar un
        escenario es simplemente volver a llamar esto con el `DatosCompra`
        equivalente, sin duplicar ninguna logica.
        """
        tarjeta = await self._tarjetas.obtener(datos.card_id)
        # Una tarjeta inactiva no debe poder iniciar una ejecucion nueva, sin
        # importar si la peticion vino del selector de la pantalla de compra o
        # de un request armado a mano: el servidor no confia en que el cliente
        # solo haya ofrecido tarjetas activas.
        if tarjeta is None or not tarjeta.activa:
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
            perfil=self._perfil,
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
                escenario_id=escenario_id,
                escenario_nombre=escenario_nombre,
            )

        # Codificar puede fallar. Si falla, no se llega a intentar transmision
        # por la red, y eso si es demostrable: es el mismo caso que RN-4.
        try:
            payload = self._codec.codificar(solicitud, self._perfil)
        except ErrorDeCodec as error:
            return await self._registrar(
                solicitud, stan, datos, EstadoEjecucion.NO_ENVIADA, motivos=(str(error),),
                escenario_id=escenario_id, escenario_nombre=escenario_nombre,
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
                solicitud, stan, datos, EstadoEjecucion.NO_ENVIADA, motivos=(str(error),),
                escenario_id=escenario_id, escenario_nombre=escenario_nombre,
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
                escenario_id=escenario_id,
                escenario_nombre=escenario_nombre,
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
                escenario_id=escenario_id,
                escenario_nombre=escenario_nombre,
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
                escenario_id=escenario_id,
                escenario_nombre=escenario_nombre,
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
                escenario_id=escenario_id,
                escenario_nombre=escenario_nombre,
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
            escenario_id=escenario_id,
            escenario_nombre=escenario_nombre,
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
        escenario_id: str | None = None,
        escenario_nombre: str | None = None,
    ) -> ResultadoCompra:
        """Construye la Ejecucion, la persiste enmascarada y devuelve el resultado."""
        # Se registra el destino en todo intento que llego a tocar la red, y por
        # eso tambien en ERROR_CONEXION: saber contra que se intento es la mitad
        # del diagnostico. Solo NO_ENVIADA se queda sin destino, porque no hubo.
        hubo_intento_de_red = estado is not EstadoEjecucion.NO_ENVIADA
        # Se persisten DOS representaciones del mismo mensaje ya enmascarado: el
        # texto de siempre, legible de un vistazo, y la estructurada, que es la
        # unica que permite recuperar un valor sin depender de un separador.
        # La respuesta se serializa desde el `MensajeInterpretado` y no desde
        # `como_mensaje()`, porque esa proyeccion descarta el `crudo` por campo.
        solicitud_enmascarada = solicitud.enmascarado()
        respuesta_enmascarada = respuesta.enmascarado() if respuesta else None
        perfil = self._perfil.nombre
        ejecucion = Ejecucion(
            card_id=datos.card_id,
            monto=datos.monto,
            # La moneda ya no es una propiedad de DatosCompra: es el campo 49
            # efectivamente armado (default del perfil o valor manual), la
            # misma fuente de verdad que ve el isoscopio.
            moneda=solicitud.campos.get("49", ""),
            stan=stan,
            estado=estado,
            mti_solicitud=solicitud.mti,
            mti_respuesta=respuesta.mti if respuesta else None,
            codigo_respuesta=respuesta.valor(CAMPO_CODIGO_RESPUESTA) if respuesta else None,
            destino_host=self._destino.host if hubo_intento_de_red else None,
            destino_puerto=self._destino.puerto if hubo_intento_de_red else None,
            solicitud_enmascarada=a_texto(solicitud_enmascarada),
            respuesta_enmascarada=(
                a_texto(respuesta_enmascarada.como_mensaje()) if respuesta_enmascarada else None
            ),
            solicitud_json=a_json_solicitud(solicitud_enmascarada, perfil),
            respuesta_json=(
                a_json_respuesta(respuesta_enmascarada, perfil)
                if respuesta_enmascarada
                else None
            ),
            latencia_ms=latencia_ms,
            escenario_id=escenario_id,
            escenario_nombre=escenario_nombre,
            creada_en=self._reloj(),
        )
        await self._ejecuciones.guardar(ejecucion)
        return ResultadoCompra(
            ejecucion=ejecucion,
            solicitud=solicitud_enmascarada,
            respuesta=respuesta_enmascarada,
            motivos=tuple(motivos),
        )


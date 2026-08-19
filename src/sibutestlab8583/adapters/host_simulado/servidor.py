"""Host simulado: recibe un 0100 y responde un 0110 correlacionado.

Reutiliza el mismo codec, el mismo perfil generico y el mismo framing de
demostracion que el cliente. No valida reglas de negocio: es el sistema
receptor, no el simulador. Decide un codigo de respuesta configurable y lo
devuelve.

Deliberadamente simple. No es un motor de escenarios: solo lo necesario para
provocar en pruebas una aprobacion, un rechazo explicito, una falta de respuesta
y una respuesta mal correlacionada.
"""

from __future__ import annotations

import asyncio
from typing import Mapping

from ...domain.errores import ErrorDeFraming
from ...domain.modelos import MTI_RESPUESTA_COMPRA
from ...domain.validacion import CAMPO_CODIGO_RESPUESTA, campos_de_correlacion

#: Campo que el autorizador agrega cuando aprueba.
CAMPO_AUTORIZACION = "38"


class HostSimulado:
    """Servidor TCP asincrono para la demostracion y las pruebas."""

    def __init__(
        self,
        codec,
        perfil,
        framing,
        *,
        codigo_respuesta: str = "00",
        responder: bool = True,
        campos_alterados: Mapping[str, str] | None = None,
    ) -> None:
        self._codec = codec
        self._perfil = perfil
        self._framing = framing
        self._codigo = codigo_respuesta
        self._responder = responder
        self._alterados = dict(campos_alterados or {})
        self._servidor: asyncio.AbstractServer | None = None
        self._apagado: asyncio.Event | None = None
        self.host: str | None = None
        self.puerto: int | None = None
        self.solicitudes_recibidas = 0

    async def iniciar(self, host: str = "127.0.0.1", puerto: int = 0) -> tuple[str, int]:
        """Levanta el servidor. Con puerto 0 el sistema asigna uno efimero."""
        self._apagado = asyncio.Event()
        self._servidor = await asyncio.start_server(self._atender, host, puerto)
        direccion = self._servidor.sockets[0].getsockname()
        self.host, self.puerto = direccion[0], direccion[1]
        return self.host, self.puerto

    async def detener(self) -> None:
        """Apaga el servidor y libera a los manejadores que estan esperando.

        El evento se avisa ANTES de cerrar: `Server.wait_closed()` espera a que
        terminen los manejadores activos, y el modo "no responder" mantiene uno
        deliberadamente vivo. Sin este aviso, detener el host se colgaria.
        """
        if self._apagado is not None:
            self._apagado.set()
        if self._servidor is not None:
            self._servidor.close()
            await self._servidor.wait_closed()
            self._servidor = None

    async def __aenter__(self) -> "HostSimulado":
        await self.iniciar()
        return self

    async def __aexit__(self, *_) -> None:
        await self.detener()

    async def _atender(
        self, lector: asyncio.StreamReader, escritor: asyncio.StreamWriter
    ) -> None:
        try:
            payload = await self._framing.leer_mensaje_completo(lector)
        except ErrorDeFraming:
            escritor.close()
            return

        self.solicitudes_recibidas += 1

        if not self._responder:
            # Provoca el caso de RN-2: la conexion queda abierta y no llega nada.
            # Se espera al apagado, no a un plazo fijo, para que detener el host
            # sea inmediato y la prueba no dependa de un temporizador.
            try:
                if self._apagado is not None:
                    await self._apagado.wait()
            except asyncio.CancelledError:
                pass
            finally:
                escritor.close()
            return

        solicitud = self._codec.decodificar(payload, self._perfil).como_mensaje()
        respuesta = self._construir_respuesta(solicitud)
        escritor.write(self._framing.preparar(self._codec.codificar(respuesta, self._perfil)))
        await escritor.drain()
        escritor.close()

    def _construir_respuesta(self, solicitud):
        """Devuelve el 0110 con los campos de correlacion copiados de la solicitud."""
        from ...domain.modelos import MensajeIso

        campos = {
            numero: solicitud.campos[numero]
            for numero in campos_de_correlacion(self._perfil, MTI_RESPUESTA_COMPRA)
            if numero in solicitud.campos
        }
        campos[CAMPO_CODIGO_RESPUESTA] = self._codigo
        if self._codigo == "00":
            campos[CAMPO_AUTORIZACION] = solicitud.campos.get("11", "000000")
        campos.update(self._alterados)
        return MensajeIso(mti=MTI_RESPUESTA_COMPRA, campos=campos)

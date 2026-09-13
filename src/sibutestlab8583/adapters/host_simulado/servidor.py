"""Host simulado: recibe un 0100, un 0800 (B2) o un 0200 (B4) y responde
correlacionado.

Reutiliza el mismo codec, el mismo perfil generico y el mismo framing de
demostracion que el cliente. No valida reglas de negocio: es el sistema
receptor, no el simulador. Decide un codigo de respuesta configurable y lo
devuelve.

Deliberadamente simple. No es un motor de escenarios (eso es Fase D, Host
Simulator 2.0, con reglas declarativas): solo lo necesario para provocar en
pruebas una aprobacion, un rechazo explicito, una falta de respuesta y una
respuesta mal correlacionada.

B2 (2026-09-12): `_construir_respuesta` deriva el MTI de respuesta con
`mti_de_respuesta(solicitud.mti)` -la misma regla generica que ya usa RN-3-,
en vez de asumir siempre `MTI_RESPUESTA_COMPRA`. El echo (0800) siempre
responde con exito (DE39="00"): en esta primera entrega no hay concepto de
"echo rechazado", y `--codigo` sigue siendo exclusivo de compra. `_alterados`
(inyeccion de campos para pruebas adversariales) sigue aplicando a cualquier
MTI, sin cambios.

B4 (2026-09-13): la compra financiera (0200) agrega el primer RECHAZO
DETERMINISTA de este laboratorio que no depende de `--codigo`: si el monto
de la solicitud supera `UMBRAL_SINTETICO_RECHAZO_FINANCIERO`, la respuesta
trae DE39="51" (fondos insuficientes) en vez de "00", SIN que quien construyo
el host tuviera que pasar ningun parametro para activarlo. Es una regla de
LABORATORIO, deliberadamente sintetica -umbral arbitrario, no un limite de
ninguna marca ni de ningun emisor real-, pensada solo para poder demostrar
PASS/FAIL/rechazo con una operacion financiera real (ver
`test_seguridad_...`/`test_host_simulado_compra_financiera.py`). Un llamador
que fije `--codigo`/`codigo_respuesta` explicitamente a un valor distinto de
"00" sigue ganando siempre -mismo mecanismo ya usado por compra para forzar
un codigo en pruebas-, asi que esta regla nunca le quita a nadie la
capacidad de forzar un codigo especifico a mano.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from typing import Mapping

from ...domain.armado import formatear_monto
from ...domain.errores import ErrorDeFraming
from ...domain.modelos import MTI_COMPRA, MTI_COMPRA_FINANCIERA, MTI_ECHO, MensajeIso
from ...domain.validacion import CAMPO_CODIGO_RESPUESTA, campos_de_correlacion, mti_de_respuesta

#: Campo que el autorizador agrega cuando aprueba una compra (o una compra
#: financiera, B4). No aplica a echo: un echo no tiene concepto de "codigo de
#: autorizacion".
CAMPO_AUTORIZACION = "38"

#: El echo de este laboratorio siempre "responde bien" en esta primera
#: entrega: no hay todavia un concepto de "echo rechazado" (ver
#: docs/roadmap/SIBU_3.md, Fase D para reglas declarativas de rechazo).
CODIGO_ECHO_EXITOSO = "00"

#: Umbral SINTETICO de laboratorio para el rechazo automatico de una compra
#: financiera (B4): un monto que lo supera responde DE39="51". No es un
#: limite de ninguna marca, banco ni procesador real -un numero elegido para
#: que la demostracion pueda producir un rechazo sin depender de `--codigo`-.
UMBRAL_SINTETICO_RECHAZO_FINANCIERO = Decimal("100000.00")
_MONTO_UMBRAL_RECHAZO_FINANCIERO = formatear_monto(UMBRAL_SINTETICO_RECHAZO_FINANCIERO)

#: Codigo de "fondos insuficientes" para el rechazo sintetico por monto. Un
#: numero de catalogo generico de laboratorio (ver `domain/catalogo.py`), no
#: una especificacion de marca.
CODIGO_RECHAZO_MONTO_SINTETICO = "51"


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
        """Devuelve la respuesta con los campos de correlacion copiados de la
        solicitud. El MTI de respuesta se DERIVA de `solicitud.mti` -nunca un
        literal fijo-, para que este host sirva para cualquier MTI que el
        perfil declare, no solo compra.
        """
        mti_respuesta = mti_de_respuesta(solicitud.mti)
        campos = {
            numero: solicitud.campos[numero]
            for numero in campos_de_correlacion(self._perfil, mti_respuesta)
            if numero in solicitud.campos
        }
        if solicitud.mti == MTI_ECHO:
            # Un echo siempre "responde bien" en esta primera entrega: no hay
            # concepto de rechazo ni de codigo de autorizacion para el.
            campos[CAMPO_CODIGO_RESPUESTA] = CODIGO_ECHO_EXITOSO
        elif solicitud.mti == MTI_COMPRA_FINANCIERA and self._codigo == "00":
            # Rechazo sintetico por monto (B4, ver docstring del modulo): solo
            # se activa cuando nadie pidio un codigo explicito (`self._codigo`
            # sigue en su default "00") -si alguien fijo `--codigo` a mano,
            # esa eleccion explicita sigue ganando, igual que ya vale para
            # compra, sin ningun camino especial aqui.
            codigo = (
                CODIGO_RECHAZO_MONTO_SINTETICO
                if solicitud.campos.get("4", "0") > _MONTO_UMBRAL_RECHAZO_FINANCIERO
                else "00"
            )
            campos[CAMPO_CODIGO_RESPUESTA] = codigo
            if codigo == "00":
                campos[CAMPO_AUTORIZACION] = solicitud.campos.get("11", "000000")
        else:
            # Cubre MTI_COMPRA (codigo explicito o default) y MTI_COMPRA_FINANCIERA
            # cuando alguien SI fijo `--codigo` a mano (self._codigo != "00"):
            # el rechazo sintetico por monto ya se resolvio en el elif de arriba.
            campos[CAMPO_CODIGO_RESPUESTA] = self._codigo
            if solicitud.mti == MTI_COMPRA and self._codigo == "00":
                campos[CAMPO_AUTORIZACION] = solicitud.campos.get("11", "000000")
        campos.update(self._alterados)
        return MensajeIso(mti=mti_respuesta, campos=campos)

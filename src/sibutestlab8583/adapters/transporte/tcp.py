"""Transporte TCP asincrono.

Limites que este modulo respeta:

- **No conoce ISO 8583.** Recibe y devuelve bytes opacos; el enmarcado y el
  desenmarcado se delegan a la `FramingStrategy`.
- **No persiste nada.**
- **Ninguna excepcion de `asyncio` ni ningun `OSError` sale de aqui.** Las
  condiciones de red se devuelven como resultado. Que un destino no este
  disponible es una observacion normal para una herramienta de pruebas.
- El limite de tiempo se inyecta, para que las pruebas no tengan que esperar los
  diez segundos de la demostracion.

TRES FASES, Y EL RESULTADO DEPENDE DE LO QUE CADA UNA PERMITE DEMOSTRAR
=======================================================================

| Fase                  | Falla                        | Resultado           |
|-----------------------|------------------------------|---------------------|
| 0. Enmarcar el payload| `preparar()` lo rechaza      | lanza ErrorDeFraming|
| 1. Conectar           | rechazo, ruta, DNS, tiempo   | FalloDeConexion     |
| 2. Enviar             | `drain()` falla o se agota   | FalloDeTransmision  |
| 3. Esperar respuesta  | se agota el tiempo           | TiempoAgotado (RN-2)|
| 3. Esperar respuesta  | canal roto o desenmarcado    | FalloDeTransmision  |

**Por que la fase 2 no es un error de conexion.** Cuando `open_connection` ya
retorno, la sesion TCP existio. `write()` solo encola en el buffer local y
`drain()` habla de ese buffer, no de la aplicacion remota: si falla, pudieron
haber salido cero bytes, algunos o todos, y TCP no le dice al programa cual de los
tres. El resultado del intercambio queda **indeterminado**, y llamarlo "error de
conexion" afirmaria que no hubo canal, lo cual es falso.

**Por que la fase 3 con tiempo agotado si es RN-2.** Ahi las cuatro premisas de
RN-2 se cumplen y son observables: se conecto, el drenaje termino, se empezo a
esperar, y no llego una respuesta completa dentro del limite.

**La fase 0 es la unica donde se lanza.** `preparar()` corre antes de tocar la
red, asi que un payload que no se puede enmarcar si permite afirmar que nada se
intento transmitir. No es una condicion de red y por eso no es un resultado: el
orquestador lo registra como un mensaje que no se envio.
"""

from __future__ import annotations

import asyncio

from ...domain.errores import ErrorDeFraming
from ...domain.modelos import (
    DestinoTcp,
    FalloDeConexion,
    FalloDeTransmision,
    TiempoAgotado,
)
from ...domain.puertos import FramingStrategy

#: Limite de la demostracion y de produccion, segun PROYECTO.md seccion 4 (RN-2).
TIEMPO_LIMITE_POR_DEFECTO = 10.0


class TransporteTcp:
    """Abre una conexion, envia un mensaje enmarcado y espera uno de vuelta."""

    def __init__(
        self,
        framing: FramingStrategy,
        *,
        tiempo_limite: float = TIEMPO_LIMITE_POR_DEFECTO,
    ) -> None:
        self._framing = framing
        self._tiempo_limite = tiempo_limite

    @property
    def tiempo_limite(self) -> float:
        return self._tiempo_limite

    async def enviar(
        self,
        payload: bytes,
        destino: DestinoTcp,
        tiempo_limite: float | None = None,
    ) -> bytes | TiempoAgotado | FalloDeConexion | FalloDeTransmision:
        limite = self._tiempo_limite if tiempo_limite is None else tiempo_limite

        # --- fase 0: enmarcar, antes de tocar la red ---
        # Si esto falla, y solo si esto falla, es demostrable que nada se intento
        # transmitir. Se deja propagar; ver el docstring del modulo.
        enmarcado = self._framing.preparar(payload)

        # --- fase 1: conectar ---
        try:
            lector, escritor = await asyncio.wait_for(
                asyncio.open_connection(destino.host, destino.puerto), timeout=limite
            )
        except asyncio.TimeoutError:
            return FalloDeConexion(
                f"no se pudo establecer la conexion con {destino}:"
                f" se agoto el tiempo tras {limite:g} s"
            )
        except OSError as error:
            return FalloDeConexion(f"no se pudo establecer la conexion con {destino}: {error}")

        # Desde aqui la sesion TCP existio: ningun fallo posterior puede
        # describirse como "no se envio".
        try:
            # --- fase 2: enviar ---
            try:
                escritor.write(enmarcado)
                await asyncio.wait_for(escritor.drain(), timeout=limite)
            except asyncio.TimeoutError:
                return FalloDeTransmision(
                    f"la conexion con {destino} se establecio, pero el envio no pudo"
                    f" completarse en {limite:g} s: no puede determinarse cuanto"
                    " recibio el destino"
                )
            except OSError as error:
                return FalloDeTransmision(
                    f"la conexion con {destino} se establecio y el envio se"
                    f" interrumpio ({error}): no puede determinarse cuanto recibio"
                    " el destino"
                )

            # --- fase 3: esperar la respuesta ---
            try:
                return await asyncio.wait_for(
                    self._framing.leer_mensaje_completo(lector), timeout=limite
                )
            except asyncio.TimeoutError:
                # Las cuatro premisas de RN-2 se cumplen. Solo aqui.
                return TiempoAgotado(limite_segundos=limite)
            except (OSError, ErrorDeFraming) as error:
                # El desenmarcado no pudo completar un mensaje, o el canal se
                # rompio. Hubo sesion TCP y la escritura local termino, pero el
                # intercambio quedo sin cerrar: no es RN-2 y no es un error de
                # conexion. Tampoco se puede afirmar que el destino recibiera.
                return FalloDeTransmision(
                    f"el intercambio con {destino} se interrumpio antes de recibir"
                    f" una respuesta completa ({error}): no puede determinarse"
                    " cuanto recibio o proceso el destino"
                )
        finally:
            await _cerrar(escritor)


async def _cerrar(escritor) -> None:
    """Cierra la conexion pase lo que pase, sin enmascarar el resultado."""
    try:
        escritor.close()
        await escritor.wait_closed()
    except (OSError, asyncio.TimeoutError):
        pass  # la conexion ya estaba rota; no hay nada que rescatar

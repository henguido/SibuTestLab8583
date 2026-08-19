"""Transporte TCP asincrono.

Limites que este modulo respeta:

- **No conoce ISO 8583.** Recibe y devuelve bytes opacos; el enmarcado y el
  desenmarcado se delegan a la `FramingStrategy`.
- **No persiste nada.**
- Un tiempo de espera agotado se **devuelve** como `TiempoAgotado`, no se lanza:
  RN-2 lo cuenta aparte de un rechazo. Un fallo de conexion si es un error.
- El limite de tiempo se inyecta, para que las pruebas no tengan que esperar los
  diez segundos de la demostracion.

Es asincrono desde el inicio para que el motor de pruebas de carga pueda
reutilizar este mismo contrato con muchas tareas concurrentes, sin reescribirlo.
"""

from __future__ import annotations

import asyncio

from ...domain.errores import ErrorDeConexion, ErrorDeTransporte
from ...domain.modelos import DestinoTcp, TiempoAgotado
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
    ) -> bytes | TiempoAgotado:
        limite = self._tiempo_limite if tiempo_limite is None else tiempo_limite
        enmarcado = self._framing.preparar(payload)

        try:
            lector, escritor = await asyncio.wait_for(
                asyncio.open_connection(destino.host, destino.puerto), timeout=limite
            )
        except asyncio.TimeoutError:
            return TiempoAgotado(limite_segundos=limite)
        except OSError as error:
            raise ErrorDeConexion(f"no se pudo conectar con {destino}: {error}") from error

        try:
            escritor.write(enmarcado)
            await asyncio.wait_for(escritor.drain(), timeout=limite)
            return await asyncio.wait_for(
                self._framing.leer_mensaje_completo(lector), timeout=limite
            )
        except asyncio.TimeoutError:
            return TiempoAgotado(limite_segundos=limite)
        except OSError as error:
            raise ErrorDeTransporte(f"fallo la comunicacion con {destino}: {error}") from error
        finally:
            await _cerrar(escritor)


async def _cerrar(escritor: asyncio.StreamWriter) -> None:
    """Cierra la conexion pase lo que pase, sin enmascarar el resultado."""
    try:
        escritor.close()
        await escritor.wait_closed()
    except (OSError, asyncio.TimeoutError):
        pass  # la conexion ya estaba rota; no hay nada que rescatar

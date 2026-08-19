"""Framing de demostracion de SibuTestLab8583.

QUE ES Y QUE NO ES
==================
Es el enmarcado que usan **nuestro cliente y nuestro host simulado** para
delimitar mensajes dentro de un stream TCP durante la demostracion academica.

**No es el framing de Visa, de Mastercard ni de ningun switch real.** No se
atribuye a ninguna marca y no debe presentarse como tal. El framing que exija un
switch de QA real dependera de la especificacion de ese ambiente, y cuando exista
se implementara como otra `FramingStrategy` sin tocar el transporte.

FORMATO
=======
Prefijo binario de 2 bytes, big-endian, con la longitud del payload:

    [ largo (2 bytes, big-endian) ][ payload de exactamente `largo` bytes ]

POR QUE ESTE Y NO OTRO
======================
- Es simple, suficiente para los mensajes de esta demostracion, y corresponde a
  un patron utilizado por implementaciones de ISO 8583 sobre TCP. **No
  representa una especificacion de Visa ni de Mastercard, y no pretende ser un
  framing universal de ISO 8583.**
- Big-endian es el orden de red, y `int.from_bytes` lo resuelve sin ambiguedad
  de plataforma.
- 2 bytes permiten hasta 65535 bytes, muy por encima de un 0100 o un 0110 de
  este perfil. Un prefijo de 4 bytes solo agregaria capacidad que no se usa.
- La alternativa de longitud en ASCII (por ejemplo cuatro digitos) es legible en
  un `tcpdump`, pero obliga a decidir relleno y codificacion, y confunde el
  limite: el largo dejaria de ser opaco y se parecerian demasiado el enmarcado y
  el contenido. Un delimitador tipo centinela quedaria descartado porque el
  payload es binario y podria contener el centinela.

Este modulo **nunca interpreta ISO 8583**: no sabe que es un MTI ni un bitmap.
Solo sabe donde termina un mensaje.
"""

from __future__ import annotations

from ...domain.errores import ErrorDeFraming
from ...domain.puertos import LectorDeStream

LARGO_PREFIJO = 2
ORDEN_BYTES = "big"
#: Con 2 bytes de prefijo no puede anunciarse un mensaje mayor.
MAXIMO_PAYLOAD = 2 ** (8 * LARGO_PREFIJO) - 1


class FramingDemostracion:
    """Prefijo binario de 2 bytes big-endian con la longitud del payload."""

    nombre = "demostracion-longitud-2-bytes"

    def preparar(self, payload: bytes) -> bytes:
        """Antepone la longitud al payload opaco."""
        if not payload:
            raise ErrorDeFraming("no se enmarca un payload vacio")
        if len(payload) > MAXIMO_PAYLOAD:
            raise ErrorDeFraming(
                f"payload de {len(payload)} bytes: excede el maximo de {MAXIMO_PAYLOAD}"
            )
        return len(payload).to_bytes(LARGO_PREFIJO, ORDEN_BYTES) + payload

    async def leer_mensaje_completo(self, lector: LectorDeStream) -> bytes:
        """Lee el prefijo y luego exactamente esa cantidad de bytes."""
        prefijo = await self._leer_exacto(lector, LARGO_PREFIJO, "el prefijo de longitud")
        largo = int.from_bytes(prefijo, ORDEN_BYTES)
        if largo == 0:
            raise ErrorDeFraming("el prefijo anuncia un mensaje de longitud cero")
        return await self._leer_exacto(lector, largo, f"el payload de {largo} bytes")

    @staticmethod
    async def _leer_exacto(lector: LectorDeStream, cantidad: int, que: str) -> bytes:
        """Lee `cantidad` bytes o falla con un error propio y explicito."""
        try:
            datos = await lector.readexactly(cantidad)
        except Exception as error:  # IncompleteReadError, conexion cerrada, etc.
            leidos = len(getattr(error, "partial", b"") or b"")
            raise ErrorDeFraming(
                f"el stream se corto antes de completar {que}: "
                f"se leyeron {leidos} de {cantidad} bytes"
            ) from error
        if len(datos) != cantidad:
            raise ErrorDeFraming(
                f"lectura incompleta de {que}: {len(datos)} de {cantidad} bytes"
            )
        return bytes(datos)

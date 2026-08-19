"""Adaptador del contrato Codec sobre pyiso8583.

Limites que este modulo respeta:

- **No conoce sockets** ni base de datos.
- **No decide reglas de aprobacion**: no mira el campo 39 ni consulta catalogos.
- **Recibe el perfil como parametro** en cada llamada, por lo que nunca sabe si
  corresponde a una marca o a otra. Hoy solo existe el perfil generico.
- Traduce `EncodeError` y `DecodeError` de la libreria a errores propios, para
  que el orquestador no importe pyiso8583.
"""

from __future__ import annotations

import iso8583

from ...domain.errores import ErrorDeCodificacion, ErrorDeDecodificacion
from ...domain.modelos import CampoInterpretado, MensajeInterpretado, MensajeIso

#: Claves que pyiso8583 usa para el MTI y los bitmaps, no para campos de datos.
CLAVES_ESTRUCTURALES = frozenset({"h", "t", "p", "1"})


class CodecIso8583:
    """Convierte entre `MensajeIso` del dominio y los bytes de la red."""

    def codificar(self, mensaje: MensajeIso, perfil) -> bytes:
        documento = {"t": mensaje.mti, **dict(mensaje.campos)}
        try:
            crudo, _ = iso8583.encode(documento, perfil.especificacion)
        except iso8583.EncodeError as error:
            raise ErrorDeCodificacion(
                f"no se pudo codificar el MTI {mensaje.mti} con el perfil "
                f"{perfil.nombre!r}: {error}"
            ) from error
        return bytes(crudo)

    def decodificar(self, payload: bytes, perfil) -> MensajeInterpretado:
        try:
            decodificado, codificado = iso8583.decode(bytes(payload), perfil.especificacion)
        except iso8583.DecodeError as error:
            raise ErrorDeDecodificacion(
                f"no se pudo interpretar la respuesta con el perfil "
                f"{perfil.nombre!r}: {error}"
            ) from error

        campos = {
            numero: CampoInterpretado(
                numero=numero,
                valor=valor,
                crudo=_texto_crudo(codificado.get(numero)),
                descripcion=_descripcion(perfil, numero),
            )
            for numero, valor in decodificado.items()
            if numero not in CLAVES_ESTRUCTURALES
        }
        return MensajeInterpretado(mti=decodificado.get("t", ""), campos=campos)


def _texto_crudo(codificado) -> str:
    """Bytes tal como viajaron, en texto, para el isoscopio."""
    if not codificado:
        return ""
    datos = codificado.get("data", b"")
    return datos.decode("ascii", errors="replace") if isinstance(datos, (bytes, bytearray)) else str(datos)


def _descripcion(perfil, numero: str) -> str:
    definicion = perfil.especificacion.get(numero, {})
    return definicion.get("desc", f"Campo {numero}")

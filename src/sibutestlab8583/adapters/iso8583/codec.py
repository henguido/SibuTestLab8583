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
from ...domain.modelos import CAMPOS_SENSIBLES, CampoInterpretado, MensajeInterpretado, MensajeIso

#: Claves que pyiso8583 usa para el MTI y los bitmaps, no para campos de datos.
CLAVES_ESTRUCTURALES = frozenset({"h", "t", "p", "1"})


class MensajeSinEnmascararError(AssertionError):
    """Un campo sensible llego sin enmascarar a `bitmap_hex`/`raw_hex_seguro`.

    Es `AssertionError` a proposito, mismo criterio que
    `application/serializacion.py::ErrorDeEnmascarado`: no es una condicion
    que el usuario pueda provocar, es un defecto de programacion -un llamador
    que olvido `.enmascarado()`- que debe romper fuerte en vez de dejar
    calcular un RAW/HEX o un bitmap sobre el PAN/Track completo.
    """


def _verificar_enmascarado_para_inspeccion(mensaje: MensajeIso) -> None:
    """Ultima barrera antes de re-codificar para bitmap/RAW: por diseno,
    `bitmap_hex`/`raw_hex_seguro` SOLO deben recibir un mensaje ya
    `enmascarado()` -ver sus docstrings-. Esta funcion no confia en que quien
    llama lo haya hecho: si un campo sensible todavia parece un numero
    (nunca empieza con el caracter de mascara), revienta aqui, antes de
    codificar nada, en vez de producir un RAW/HEX o un bitmap sobre datos
    reales de tarjeta.
    """
    for numero in CAMPOS_SENSIBLES:
        valor = mensaje.campos.get(numero)
        if valor and valor.isdigit():
            raise MensajeSinEnmascararError(
                f"el campo {numero} llego sin enmascarar a bitmap_hex/raw_hex_seguro"
            )


class CodecIso8583:
    """Convierte entre `MensajeIso` del dominio y los bytes de la red."""

    def codificar(self, mensaje: MensajeIso, perfil) -> bytes:
        documento = {"t": mensaje.mti, **dict(mensaje.campos)}
        try:
            crudo, _ = iso8583.encode(documento, perfil.especificacion)
        except iso8583.EncodeError as error:
            # Nunca `str(error)`/`error.msg`: ese texto lo redacta pyiso8583 y no
            # es un contrato que este proyecto controle ni pueda auditar hacia
            # adelante -una version futura de la libreria podria describir el
            # fallo citando el propio valor del campo, y este codigo no tiene
            # forma de saberlo de antemano-. Solo se usa `error.field`, el
            # numero de campo ISO donde fallo: un dato estructural, nunca el
            # contenido. El mensaje final es texto propio, no el de la libreria.
            raise ErrorDeCodificacion(
                f"no se pudo codificar el campo {error.field} para el MTI "
                f"{mensaje.mti} con el perfil {perfil.nombre!r}"
            ) from error
        return bytes(crudo)

    def _codificar_para_inspeccion(self, mensaje: MensajeIso, perfil):
        """Encode compartido por `bitmap_hex` y `raw_hex_seguro`: ambos son
        llamadas de solo lectura (no hay E/S, `iso8583.encode` es una funcion
        pura y barata), asi que no hace falta cambiar el contrato de
        `codificar()` -que ya usa el orquestador para transmitir- para
        obtenerlas.

        **ADVERTENCIA DE USO -no relajar sin releer esto-**: quien llama es
        responsable de pasar un `mensaje` ya `enmascarado()`, NUNCA el
        mensaje real con PAN/Track completo. Esta funcion no enmascara nada
        por su cuenta: solo re-codifica lo que se le da. Ver
        `application/vista_previa.py` y `web/app.py` (siempre pasan la
        version enmascarada). Segura POR CONSTRUCCION, no solo por disciplina
        del llamador: `_verificar_enmascarado_para_inspeccion` revienta antes
        de codificar si un campo sensible todavia parece un numero real.
        """
        _verificar_enmascarado_para_inspeccion(mensaje)
        documento = {"t": mensaje.mti, **dict(mensaje.campos)}
        try:
            crudo, codificado = iso8583.encode(documento, perfil.especificacion)
        except iso8583.EncodeError as error:
            raise ErrorDeCodificacion(
                f"no se pudo codificar el campo {error.field} para el MTI "
                f"{mensaje.mti} con el perfil {perfil.nombre!r}"
            ) from error
        except KeyError as error:
            # A diferencia de `codificar()` -que solo arma mensajes con campos
            # que el perfil VIGENTE ya declara-, esto tambien se llama con
            # mensajes reconstruidos de un historico (`web.app._bitmap_de_persistido`
            # /`_raw_de_persistido`): un numero que el perfil de hoy ya no
            # conoce (drift) no es un `EncodeError` de pyiso8583 -es un
            # `KeyError` propio al indexar la especificacion-, pero el
            # criterio es el mismo: no inventar un resultado, avisar que no
            # se pudo.
            raise ErrorDeCodificacion(
                f"el campo {error.args[0]} no esta definido en el perfil "
                f"{perfil.nombre!r}: no se puede inspeccionar el mensaje"
            ) from error
        return bytes(crudo), codificado

    def bitmap_hex(self, mensaje: MensajeIso, perfil) -> str:
        """El bitmap primario en hexadecimal, tal como se codificaria este
        mensaje -sin transmitirlo-. El bitmap solo depende de QUE campos
        estan presentes, nunca de sus valores: por eso es igual de valido
        calcularlo sobre un mensaje ya enmascarado que sobre el original.
        """
        _, codificado = self._codificar_para_inspeccion(mensaje, perfil)
        return _texto_crudo(codificado.get("p")).upper()

    def raw_hex_seguro(self, mensaje: MensajeIso, perfil) -> tuple[str, int]:
        """El mensaje COMPLETO codificado, en hexadecimal, y su longitud en
        bytes. Devuelve `(hex_en_mayusculas, longitud_en_bytes)`.

        **NUNCA se llama con el mensaje real**: el llamador SIEMPRE pasa la
        version ya `enmascarado()` -ver el mismo criterio en `bitmap_hex`-.
        Esto es intencional y es la unica estrategia de sanitizacion de este
        proyecto para RAW/HEX: en vez de capturar los bytes reales (que
        contendrian el PAN/Track completo en claro dentro del dump) y despues
        intentar redactar un rango de bytes -una tecnica fragil, propensa a
        un error de calculo de offset/longitud que dejara un fragmento
        filtrado-, se recodifica DESDE CERO el mensaje que ya tiene DE2/DE35
        reemplazados por asteriscos. El resultado nunca puede contener un PAN
        ni un Track completo, porque nunca se codifican: no se enmascara un
        dump, se construye uno que nunca tuvo el dato sensible.

        La longitud resultante SI es fiel a la transmitida de verdad -el
        enmascarado preserva el largo del campo-, aunque el contenido
        hexadecimal en si sea una reconstruccion seguro y no los bytes
        exactamente transmitidos. Ver `web.presentacion` para como se rotula
        esa distincion en pantalla.
        """
        crudo, _ = self._codificar_para_inspeccion(mensaje, perfil)
        return crudo.hex().upper(), len(crudo)

    def decodificar(self, payload: bytes, perfil) -> MensajeInterpretado:
        try:
            decodificado, codificado = iso8583.decode(bytes(payload), perfil.especificacion)
        except iso8583.DecodeError as error:
            # Mismo criterio que en `codificar`: solo `error.field`, nunca el
            # texto libre de la excepcion de la libreria.
            raise ErrorDeDecodificacion(
                f"no se pudo interpretar el campo {error.field} de la respuesta "
                f"con el perfil {perfil.nombre!r}"
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

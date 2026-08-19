"""Traduccion del dominio a lo que ve la pantalla.

Aqui no hay reglas de negocio: solo se decide como se rotula y con que tono se
muestra cada desenlace. El enmascaramiento **no se reimplementa**: llega ya
hecho desde el dominio.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence

from ..domain.errores import (
    ErrorDeCodec,
    ErrorDeConexion,
    ErrorDeFraming,
    ErrorDeTransporte,
)
from ..domain.modelos import (
    CAMPOS_SENSIBLES,
    EstadoEjecucion,
    MensajeInterpretado,
    MensajeIso,
    ResultadoCompra,
)

MONTO_MAXIMO = Decimal("9999999999.99")


@dataclass(frozen=True)
class Aviso:
    """Como se comunica un desenlace: titulo, explicacion y tono visual."""

    tono: str
    titulo: str
    detalle: str


@dataclass(frozen=True)
class FilaIsoscopio:
    numero: str
    descripcion: str
    valor: str
    crudo: str
    sensible: bool


#: Un tono por estado. Los cinco desenlaces se distinguen a simple vista, y el
#: fallo de infraestructura no se confunde con un rechazo del autorizador.
AVISOS: Mapping[EstadoEjecucion, Aviso] = {
    EstadoEjecucion.APROBADA: Aviso(
        "aprobada",
        "Transaccion aprobada",
        "El autorizador respondio con un codigo que el catalogo configurado marca como aprobado.",
    ),
    EstadoEjecucion.RECHAZADA: Aviso(
        "rechazada",
        "Transaccion rechazada",
        "El autorizador respondio, y su codigo no corresponde a una aprobacion.",
    ),
    EstadoEjecucion.INVALIDA: Aviso(
        "invalida",
        "Respuesta invalida",
        "Llego una respuesta, pero no corresponde a la solicitud enviada. "
        "No se cuenta como aprobada aunque su codigo lo diga.",
    ),
    EstadoEjecucion.TIMEOUT: Aviso(
        "timeout",
        "Sin respuesta",
        "El destino no respondio dentro del limite de tiempo. Se registra aparte de un rechazo.",
    ),
    EstadoEjecucion.NO_ENVIADA: Aviso(
        "no-enviada",
        "Mensaje incompleto: no se envio",
        "Faltaban campos obligatorios para el tipo de mensaje, asi que no se envio nada.",
    ),
}


def aviso_de(resultado: ResultadoCompra) -> Aviso:
    return AVISOS[resultado.estado]


def aviso_de_error(error: Exception) -> Aviso:
    """Convierte una excepcion tecnica en algo que el usuario pueda entender.

    Nunca se muestra la traza ni el texto crudo de una excepcion inesperada.
    """
    if isinstance(error, ErrorDeConexion):
        return Aviso(
            "error",
            "No se pudo conectar con el destino",
            "Revise que el host simulado o el switch esten disponibles en el host y puerto "
            "indicados. La transaccion no llego a enviarse.",
        )
    if isinstance(error, (ErrorDeFraming, ErrorDeTransporte)):
        return Aviso(
            "error",
            "Fallo la comunicacion con el destino",
            "La conexion se establecio pero el intercambio no pudo completarse.",
        )
    if isinstance(error, ErrorDeCodec):
        return Aviso(
            "error",
            "No se pudo interpretar el mensaje",
            "El contenido recibido no corresponde al perfil configurado.",
        )
    return Aviso(
        "error",
        "Ocurrio un error inesperado",
        "La operacion no pudo completarse. Revise el registro del servidor.",
    )


def validar_monto(texto: str) -> Decimal:
    """Convierte el monto del formulario. Lanza `ValueError` con texto util."""
    limpio = (texto or "").strip().replace(",", ".")
    if not limpio:
        raise ValueError("Indique un monto.")
    try:
        monto = Decimal(limpio)
    except InvalidOperation as error:
        raise ValueError("El monto debe ser un numero, por ejemplo 150.00") from error
    if monto <= 0:
        raise ValueError("El monto debe ser mayor que cero.")
    if monto > MONTO_MAXIMO:
        raise ValueError(f"El monto no puede superar {MONTO_MAXIMO}.")
    return monto


def validar_puerto(texto: str) -> int:
    try:
        puerto = int((texto or "").strip())
    except ValueError as error:
        raise ValueError("El puerto debe ser un numero entero.") from error
    if not 1 <= puerto <= 65535:
        raise ValueError("El puerto debe estar entre 1 y 65535.")
    return puerto


def validar_host(texto: str) -> str:
    host = (texto or "").strip()
    if not host:
        raise ValueError("Indique el host de destino.")
    return host


def filas_de_solicitud(
    mensaje: MensajeIso, descripciones: Mapping[str, str]
) -> Sequence[FilaIsoscopio]:
    """Isoscopio de la solicitud.

    No lleva representacion cruda: el mensaje enviado se conserva como valores
    del dominio, y mostrar bytes reconstruidos seria inventar un dato.
    """
    return [
        FilaIsoscopio(
            numero=numero,
            descripcion=descripciones.get(numero, f"Campo {numero}"),
            valor=mensaje.campos[numero],
            crudo="",
            sensible=numero in CAMPOS_SENSIBLES,
        )
        for numero in sorted(mensaje.campos, key=int)
    ]


def contexto_de_resultado(
    resultado: ResultadoCompra, destino, descripciones: Mapping[str, str]
) -> dict:
    """Arma lo que la plantilla de resultado necesita.

    Vive aqui y no en el endpoint para que este ultimo se limite a orquestar la
    peticion: validar la entrada, delegar el recorrido y elegir la plantilla.
    """
    return {
        "resultado": resultado,
        "aviso": aviso_de(resultado),
        "destino": destino,
        "filas_solicitud": filas_de_solicitud(resultado.solicitud, descripciones),
        "filas_respuesta": (
            filas_de_respuesta(resultado.respuesta) if resultado.respuesta else []
        ),
    }


def filas_de_respuesta(mensaje: MensajeInterpretado) -> Sequence[FilaIsoscopio]:
    """Isoscopio de la respuesta, con los bytes tal como llegaron."""
    return [
        FilaIsoscopio(
            numero=campo.numero,
            descripcion=campo.descripcion,
            valor=campo.valor,
            crudo=campo.crudo,
            sensible=campo.numero in CAMPOS_SENSIBLES,
        )
        for _, campo in sorted(mensaje.campos.items(), key=lambda par: int(par[0]))
    ]

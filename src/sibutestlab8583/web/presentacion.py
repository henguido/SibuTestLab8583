"""Traduccion del dominio a lo que ve la pantalla.

Aqui no hay reglas de negocio: solo se decide como se rotula y con que tono se
muestra cada desenlace. El enmascaramiento **no se reimplementa**: llega ya
hecho desde el dominio.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence

from ..application.serializacion import (
    AVISO_HEREDADO,
    ORIGEN_TEXTO,
    MensajeSerializado,
)
from ..domain.errores import ErrorDeCodec, ErrorDeFraming
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
    """Como se comunica un desenlace.

    Lleva cuatro pistas y el color es solo una de ellas: `senal` elige un dibujo,
    `etiqueta` da el rotulo corto para las tablas, `titulo` y `detalle` lo
    explican. Asi un desenlace sigue siendo reconocible sin distinguir colores.

    `senal` no se deriva de `tono` porque no son biyectivos: el tono `error` lo
    comparten el fallo de conexion y los errores tecnicos, y cada uno merece su
    propio dibujo.
    """

    tono: str
    titulo: str
    detalle: str
    etiqueta: str = ""
    senal: str = "neutro"


@dataclass(frozen=True)
class Seccion:
    """Una entrada de la navegacion principal."""

    clave: str
    ruta: str
    texto: str


#: Navegacion de la aplicacion, en un solo lugar. La plantilla base la recorre;
#: no hay ninguna lista de enlaces duplicada en el HTML.
#:
#: Solo se listan secciones con ruta servida: un enlace que no funciona es peor
#: que un enlace ausente.
SECCIONES: tuple[Seccion, ...] = (
    Seccion("compra", "/", "Nueva transacción"),
    Seccion("historial", "/historial", "Historial"),
    Seccion("configuracion", "/configuracion", "Configuración"),
)


@dataclass(frozen=True)
class FilaIsoscopio:
    numero: str
    descripcion: str
    valor: str
    crudo: str
    sensible: bool


@dataclass(frozen=True)
class FilaConstructor:
    """Una fila de la tabla del constructor: qué es este campo y quién lo fija.

    `origen` es uno de "derivado", "automatico" o "editable" — nunca
    "no_permitido", porque esta fila solo existe para campos que la política
    del perfil sí reconoce para el MTI. `valor` es el default declarado por el
    perfil cuando es editable; para derivados y automáticos queda vacío, la
    plantilla muestra en su lugar una nota de dónde sale el valor real.
    """

    numero: str
    descripcion: str
    valor: str
    origen: str
    obligatorio: bool


def filas_constructor(perfil, mti: str, descripciones: Mapping[str, str]) -> Sequence[FilaConstructor]:
    """Las filas del constructor para un MTI, gobernadas enteramente por el perfil.

    No hardcodea ningún número de campo: recorre lo que `perfil.politica(mti)`
    declara. Agregar un campo editable nuevo al perfil lo agrega aquí sin
    tocar esta función.
    """
    politica = perfil.politica(mti)
    obligatorios = perfil.obligatorios(mti)
    numeros = politica.derivados | politica.automaticos | politica.editables
    return [
        FilaConstructor(
            numero=numero,
            descripcion=descripciones.get(numero, f"Campo {numero}"),
            valor=politica.valores_por_defecto.get(numero, ""),
            origen=politica.origen(numero),
            obligatorio=numero in obligatorios,
        )
        for numero in sorted(numeros, key=int)
    ]


#: Un aviso por estado, uno por cada miembro de EstadoEjecucion. Los siete
#: desenlaces se distinguen a simple vista, y en particular un fallo de
#: infraestructura no se confunde con un rechazo del autorizador ni con una
#: falta de respuesta. Una prueba comprueba que no falte ninguno.
AVISOS: Mapping[EstadoEjecucion, Aviso] = {
    EstadoEjecucion.APROBADA: Aviso(
        "aprobada",
        "Transacción aprobada",
        "El autorizador respondió con un código que el catálogo configurado marca como aprobado.",
        etiqueta="Aprobada",
        senal="aprobada",
    ),
    EstadoEjecucion.RECHAZADA: Aviso(
        "rechazada",
        "Transacción rechazada",
        "El autorizador respondió, y su código no corresponde a una aprobación.",
        etiqueta="Rechazada",
        senal="rechazada",
    ),
    EstadoEjecucion.INVALIDA: Aviso(
        "invalida",
        "Respuesta inválida",
        "Llegó una respuesta, pero no corresponde a la solicitud enviada. "
        "No se cuenta como aprobada aunque su código lo diga.",
        etiqueta="Inválida",
        senal="invalida",
    ),
    EstadoEjecucion.TIMEOUT: Aviso(
        "timeout",
        "Sin respuesta del destino",
        "Se estableció la conexión, la escritura local terminó sin error y se esperó una "
        "respuesta completa hasta agotar el límite. No puede afirmarse desde aquí si el "
        "destino recibió o procesó el mensaje. Se registra aparte de un rechazo, de un "
        "fallo de conexión y de un intercambio interrumpido.",
        etiqueta="Sin respuesta",
        senal="timeout",
    ),
    EstadoEjecucion.ERROR_CONEXION: Aviso(
        "error",
        "No fue posible establecer conexión con el destino",
        "No llegó a haber sesión TCP, así que la solicitud no se transmitió. Revise que "
        "el host simulado o el switch estén disponibles en el host y puerto indicados. "
        "Esto no es un rechazo del autorizador ni una falta de respuesta.",
        etiqueta="Error de conexión",
        senal="conexion",
    ),
    EstadoEjecucion.ERROR_TRANSMISION: Aviso(
        "indeterminado",
        "El intercambio se interrumpió",
        "La conexión se estableció, pero el intercambio se interrumpió. No puede "
        "determinarse cuánto recibió el destino, así que no debe asumirse que la "
        "transacción no se procesó. Revise el destino antes de reintentar.",
        # El rotulo corto dice lo que se sabe, no lo que se supone: en una tabla
        # sin explicacion al lado, "interrumpida" se leeria como "no paso nada".
        etiqueta="Indeterminada",
        senal="transmision",
    ),
    EstadoEjecucion.NO_ENVIADA: Aviso(
        "no-enviada",
        "El mensaje no se envió",
        "No se llegó a intentar transmisión por la red. Puede ser porque faltaban campos "
        "obligatorios para su tipo, porque no se pudo codificar, o porque no se pudo "
        "preparar para transmitirlo. El motivo concreto aparece más abajo.",
        etiqueta="No enviada",
        senal="no-enviada",
    ),
}


def aviso_de(resultado: ResultadoCompra) -> Aviso:
    return AVISOS[resultado.estado]


def aviso_de_error(error: Exception) -> Aviso:
    """Convierte una excepcion tecnica en algo que el usuario pueda entender.

    Nunca se muestra la traza ni el texto crudo de una excepcion inesperada.

    Las condiciones de red **no** llegan por aqui: el transporte las devuelve como
    resultado y terminan en `AVISOS`, con su propio estado persistido. Esta
    funcion queda para lo que si es excepcional.
    """
    if isinstance(error, ErrorDeFraming):
        return Aviso(
            "error",
            "No se pudo preparar el mensaje para transmitirlo",
            "El contenido no cumple el formato de enmarcado configurado.",
            etiqueta="Error",
            senal="no-enviada",
        )
    if isinstance(error, ErrorDeCodec):
        return Aviso(
            "error",
            "No se pudo interpretar el mensaje",
            "El contenido recibido no corresponde al perfil configurado.",
            etiqueta="Error",
            senal="invalida",
        )
    return Aviso(
        "error",
        "Ocurrió un error inesperado",
        "La operación no pudo completarse. Revise el registro del servidor.",
        etiqueta="Error",
        senal="invalida",
    )


def validar_monto(texto: str) -> Decimal:
    """Convierte el monto del formulario. Lanza `ValueError` con texto util."""
    limpio = (texto or "").strip().replace(",", ".")
    if not limpio:
        raise ValueError("Indique un monto.")
    try:
        monto = Decimal(limpio)
    except InvalidOperation as error:
        raise ValueError("El monto debe ser un número, por ejemplo 150.00") from error
    if monto <= 0:
        raise ValueError("El monto debe ser mayor que cero.")
    if monto > MONTO_MAXIMO:
        raise ValueError(f"El monto no puede superar {MONTO_MAXIMO}.")
    return monto


def validar_activa(texto: str) -> bool:
    """Interpreta el valor exacto que envia el formulario de activar/desactivar.

    Solo admite ``"0"`` o ``"1"``: cualquier otro valor se rechaza en vez de
    convertirse silenciosamente en `False`. Un formulario manipulado que
    mande ``"si"``, ``"2"`` o nada no debe poder cambiar el estado de una
    tarjeta sin que el error quede explicito.
    """
    valor = (texto or "").strip()
    if valor not in ("0", "1"):
        raise ValueError("El valor de estado recibido no es válido.")
    return valor == "1"


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
        # El resultado es el desenlace de la pantalla de transaccion: la
        # navegacion sigue marcando esa seccion, no ninguna otra.
        "seccion": "compra",
        "resultado": resultado,
        "aviso": aviso_de(resultado),
        "destino": destino,
        "filas_solicitud": filas_de_solicitud(resultado.solicitud, descripciones),
        "filas_respuesta": (
            filas_de_respuesta(resultado.respuesta) if resultado.respuesta else []
        ),
    }


def filas_de_persistido(
    mensaje: MensajeSerializado, descripciones: Mapping[str, str]
) -> Sequence[FilaIsoscopio]:
    """Isoscopio de un mensaje leido de la base, para el detalle historico.

    El nombre de cada campo se re-deriva del perfil activo, porque la
    representacion persistida guarda numero y valor pero no la descripcion. Un
    numero que el perfil de hoy no conozca sale como `Campo 63`: no se inventa
    una descripcion ni se rompe la pagina.
    """
    return [
        FilaIsoscopio(
            numero=campo.numero,
            descripcion=descripciones.get(campo.numero, f"Campo {campo.numero}"),
            valor=campo.valor,
            crudo=campo.crudo or "",
            sensible=campo.numero in CAMPOS_SENSIBLES,
        )
        for campo in mensaje.campos
    ]


def contexto_de_detalle(detalle, descripciones: Mapping[str, str]) -> dict:
    """Arma lo que la plantilla del detalle historico necesita.

    La respuesta se considera existente por el MTI persistido y no por si la
    representacion trae campos: una fila sin `mti_respuesta` es una ejecucion que
    no obtuvo respuesta, y ahi la pantalla debe explicar el estado en lugar de
    mostrar una tabla vacia. Distinguirlo por el numero de campos confundiria
    "no hubo respuesta" con "la representacion no se pudo leer".
    """
    ejecucion = detalle.ejecucion
    filas_respuesta = filas_de_persistido(detalle.respuesta, descripciones)
    return {
        "seccion": "historial",
        "ejecucion": ejecucion,
        "aviso": AVISOS[ejecucion.estado],
        "solicitud": detalle.solicitud,
        "respuesta": detalle.respuesta,
        "filas_solicitud": filas_de_persistido(detalle.solicitud, descripciones),
        "filas_respuesta": filas_respuesta,
        "hubo_respuesta": ejecucion.mti_respuesta is not None,
        # La solicitud nunca trae representacion transmitida; la respuesta solo
        # si se leyo del JSON. Se decide por el contenido, no por suposicion.
        "respuesta_con_crudo": any(fila.crudo for fila in filas_respuesta),
        # Un unico aviso por ejecucion, no uno por tabla: el formato con el que
        # se registro es una propiedad de la fila, no de cada mensaje.
        "desde_formato_anterior": ORIGEN_TEXTO
        in (detalle.solicitud.origen, detalle.respuesta.origen),
        "avisos_tecnicos": _avisos_tecnicos(detalle.solicitud, detalle.respuesta),
    }


def _avisos_tecnicos(*mensajes: MensajeSerializado) -> tuple[str, ...]:
    """Avisos que no son el del formato anterior, sin repetir.

    El del formato anterior se comunica una sola vez y con su propia redaccion;
    aqui quedan los demas —un JSON ilegible, una version que este programa no
    interpreta—, que si son especificos y no deben perderse.
    """
    vistos: list[str] = []
    for mensaje in mensajes:
        for aviso in mensaje.avisos:
            if aviso != AVISO_HEREDADO and aviso not in vistos:
                vistos.append(aviso)
    return tuple(vistos)


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

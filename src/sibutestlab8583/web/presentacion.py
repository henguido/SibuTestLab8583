"""Traduccion del dominio a lo que ve la pantalla.

Aqui no hay reglas de negocio: solo se decide como se rotula y con que tono se
muestra cada desenlace. El enmascaramiento **no se reimplementa**: llega ya
hecho desde el dominio.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Mapping, Sequence

from ..application.serializacion import (
    AVISO_HEREDADO,
    ORIGEN_TEXTO,
    MensajeSerializado,
)
from ..domain.errores import ErrorDeCodec, ErrorDeFraming
from ..domain.expectativas import campos_permitidos_expectativa
from ..domain.modelos import (
    CAMPOS_SENSIBLES,
    EstadoEjecucion,
    FiltroHistorial,
    MensajeInterpretado,
    MensajeIso,
    ResultadoCompra,
)

#: Valores admitidos para el filtro de evaluacion del historial. "" significa
#: "sin restriccion" -nunca un cuarto valor de `EstadoEvaluacion`, que solo
#: conoce pass/fail-.
VALORES_FILTRO_EVALUACION = frozenset({"", "pass", "fail", "sin_expectativas"})

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
    Seccion("escenarios", "/escenarios", "Escenarios"),
    Seccion("suites", "/suites", "Suites"),
    Seccion("historial", "/historial", "Historial"),
    Seccion("configuracion", "/configuracion", "Configuración"),
)


@dataclass(frozen=True)
class GrupoNav:
    """Un grupo de la barra lateral: un rotulo y sus enlaces.

    Puramente de presentacion: cada `ruta` ya es una ruta SERVIDA hoy por
    `web/app.py` (nada nuevo se agrega aqui) -esto solo reagrupa enlaces que ya
    existian sueltos dentro de las paginas (p. ej. "Ver corridas" en
    `suites.html`, o los botones de `configuracion.html`) en una barra lateral
    persistente. `SECCIONES` (arriba) sigue existiendo tal cual para quien lo
    use; esto es una vista mas rica de la misma navegacion, no un reemplazo.
    """

    titulo: str
    entradas: tuple[Seccion, ...]


#: Barra lateral de la interfaz. El resaltado de "activo" no depende de una
#: clave por pantalla -habria que distinguir Conexiones de Tarjetas dentro de
#: la misma `seccion="configuracion"`, y Corridas dentro de `seccion="suites"`,
#: cosa que el contexto actual no distingue-: la plantilla decide el activo
#: comparando `request.url.path` contra `ruta`, con el prefijo mas largo que
#: coincida (ver `base.html`), asi que agregar un grupo aqui no exige tocar
#: ningun endpoint.
def ruta_activa(path: str, grupos: Sequence[GrupoNav]) -> str | None:
    """La ruta de `GRUPOS_NAV` que corresponde a la pantalla actual, o `None`.

    Con "/suites" y "/suites/corridas" ambos en la barra, un prefijo simple
    marcaria los dos como activos al visitar "/suites/corridas/7". Esta
    funcion resuelve eso por texto mas largo: entre todas las entradas cuya
    ruta coincide con `path`, gana la mas especifica. "/" solo coincide con
    "/" exacto -de lo contrario toda la aplicacion quedaria bajo "Nueva
    transacción"-, con una unica excepcion documentada: "/compra" (el POST
    que ejecuta la transaccion y renderiza `resultado.html`) es, para esto,
    la misma pantalla que "/" -exactamente el mismo par que ya distingue
    `contexto_de_resultado` con `"seccion": "compra"`-.
    """
    mejor: str | None = None
    for grupo in grupos:
        for entrada in grupo.entradas:
            ruta = entrada.ruta
            if ruta == "/":
                coincide = path in ("/", "/compra")
            else:
                coincide = path == ruta or path.startswith(ruta + "/")
            if coincide and (mejor is None or len(ruta) > len(mejor)):
                mejor = ruta
    return mejor


GRUPOS_NAV: tuple[GrupoNav, ...] = (
    GrupoNav("Ejecución", (
        Seccion("compra", "/", "Nueva transacción"),
        Seccion("historial", "/historial", "Historial"),
    )),
    GrupoNav("Automatización", (
        Seccion("escenarios", "/escenarios", "Escenarios"),
        Seccion("suites", "/suites", "Suites"),
        Seccion("corridas", "/suites/corridas", "Corridas"),
    )),
    GrupoNav("Configuración", (
        Seccion("conexiones", "/configuracion/conexiones", "Conexiones"),
        Seccion("tarjetas", "/configuracion/tarjetas", "Tarjetas"),
    )),
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


@dataclass(frozen=True)
class FilaExpectativa:
    """Una fila de la tabla de expectativas: un campo de la respuesta que se
    puede verificar, y con que tipo/valor quedo configurado (si alguno).
    """

    numero: str
    descripcion: str
    tipo: str  # "" si no hay expectativa fijada para este campo
    valor: str


def filas_expectativas(
    perfil, mti_respuesta: str, descripciones: Mapping[str, str], campos_fijados: Mapping[str, object]
) -> Sequence[FilaExpectativa]:
    """Las filas de la tabla de expectativas, gobernadas por
    `campos_permitidos_expectativa` -nunca una lista fija-. `campos_fijados`
    es `Expectativas.campos` (o un dict equivalente ya enviado en un POST):
    si un numero no esta ahi, la fila se muestra sin tipo/valor.
    """
    permitidos = campos_permitidos_expectativa(perfil, mti_respuesta)
    filas = []
    for numero in sorted(permitidos, key=int):
        fijado = campos_fijados.get(numero)
        if fijado is None:
            tipo, valor = "", ""
        elif isinstance(fijado, Mapping):
            tipo, valor = fijado.get("tipo", ""), fijado.get("valor") or ""
        else:  # ExpectativaCampo
            tipo, valor = fijado.tipo, fijado.valor or ""
        filas.append(
            FilaExpectativa(
                numero=numero,
                descripcion=descripciones.get(numero, f"Campo {numero}"),
                tipo=tipo,
                valor=valor,
            )
        )
    return filas


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


#: Estados que llevan una causa que explicar. APROBADA queda fuera a
#: proposito -no hay nada que diagnosticar-, y eso no debe confundirse con una
#: fila antigua sin `motivo_detalle`: la plantilla distingue ambos casos con
#: `motivo_esperado`.
ESTADOS_CON_MOTIVO = frozenset({
    EstadoEjecucion.RECHAZADA,
    EstadoEjecucion.INVALIDA,
    EstadoEjecucion.TIMEOUT,
    EstadoEjecucion.ERROR_CONEXION,
    EstadoEjecucion.ERROR_TRANSMISION,
    EstadoEjecucion.NO_ENVIADA,
})


def motivo_de(ejecucion) -> str | None:
    """El motivo persistido de una ejecucion historica, ya seguro para
    mostrar -es el mismo texto que ya redacta el dominio (nombres de campo,
    codigos de catalogo, texto de socket), nunca una excepcion cruda ni un
    mensaje ISO completo-. `None` cuando el estado no tiene motivo que
    explicar (APROBADA); una fila anterior a que este campo existiera
    tambien da `None` aqui, y la plantilla lo distingue con `motivo_esperado`.
    """
    if ejecucion.estado not in ESTADOS_CON_MOTIVO:
        return None
    return ejecucion.motivo_detalle


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


def _validar_fecha(texto: str, etiqueta: str) -> str:
    """Valida una fecha `AAAA-MM-DD` del formulario de filtros. Cadena vacia es
    valida -significa "sin restriccion en ese extremo"-; cualquier otra cosa
    que no sea una fecha real se rechaza en vez de pasarla tal cual a SQL.
    """
    texto = (texto or "").strip()
    if not texto:
        return ""
    try:
        date.fromisoformat(texto)
    except ValueError as error:
        raise ValueError(f"La fecha «{etiqueta}» no es una fecha válida (AAAA-MM-DD).") from error
    return texto


def leer_filtro_historial(
    *,
    desde: str,
    hasta: str,
    estado: str,
    evaluacion: str,
    card_id: str,
    destino: str,
    stan: str,
) -> FiltroHistorial:
    """Construye un `FiltroHistorial` a partir de los parámetros crudos de la
    URL. Lanza `ValueError` con un mensaje explicado ante cualquier valor que
    no sea uno de los que la propia pantalla de filtros puede producir -mismo
    principio que `validar_activa`: nunca se reinterpreta en silencio un
    parámetro manipulado.
    """
    desde = _validar_fecha(desde, "desde")
    hasta = _validar_fecha(hasta, "hasta")
    if desde and hasta and desde > hasta:
        raise ValueError("La fecha «desde» no puede ser posterior a «hasta».")

    estado_bruto = (estado or "").strip()
    estado_valido: EstadoEjecucion | None = None
    if estado_bruto:
        try:
            estado_valido = EstadoEjecucion(estado_bruto)
        except ValueError as error:
            raise ValueError("El estado del filtro no es válido.") from error

    evaluacion_bruta = (evaluacion or "").strip()
    if evaluacion_bruta not in VALORES_FILTRO_EVALUACION:
        raise ValueError("El filtro de expectativa no es válido.")

    return FiltroHistorial(
        desde=desde,
        hasta=hasta,
        estado=estado_valido,
        evaluacion=evaluacion_bruta,
        card_id=(card_id or "").strip(),
        destino=(destino or "").strip(),
        stan=(stan or "").strip(),
    )


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


@dataclass(frozen=True)
class FilaDiscrepancia:
    """Una discrepancia de Expected vs Actual, estructurada para una tabla
    CRITERIO/ESPERADO/RECIBIDO en vez de una sola oracion -mismo contenido
    que ya redacta `mensaje_de_discrepancia`, solo que sin unirlo en texto.

    Vive aqui (presentacion web) y no en `application/presentacion_evaluacion.py`
    a proposito: ese modulo es el que comparten CLI y exportacion CSV/JSON, y
    su contrato (una linea de texto) no cambia. Esta forma estructurada es
    exclusiva de la interfaz web.
    """

    criterio: str
    esperado: str
    recibido: str


@dataclass(frozen=True)
class EvaluacionMostrada:
    """PASS/FAIL de un escenario, ya traducido para mostrarse.

    Se arma a partir del snapshot (`Ejecucion.evaluacion_json`), nunca del
    escenario en vivo: si el escenario se edito despues, esto sigue mostrando
    exactamente lo que se evaluo en su momento.
    """

    estado: str  # "pass" | "fail"
    filas: Sequence[FilaDiscrepancia]


def _fila_de_discrepancia(discrepancia: Mapping, descripciones: Mapping[str, str]) -> FilaDiscrepancia:
    """Misma logica que `mensaje_de_discrepancia`, pero devuelve los tres
    valores por separado en vez de unirlos en una oracion.
    """
    if discrepancia["criterio"] == "estado":
        return FilaDiscrepancia(
            criterio="Estado de la transacción",
            esperado=discrepancia["esperado"] or "",
            recibido=discrepancia["recibido"] or "",
        )
    campo = discrepancia["campo"]
    nombre = descripciones.get(campo, f"Campo {campo}")
    tipo = discrepancia["tipo"]
    criterio = f"Campo {campo} · {nombre}"
    if tipo == "igual":
        return FilaDiscrepancia(
            criterio=criterio,
            esperado=discrepancia["esperado"] or "",
            recibido=discrepancia["recibido"] or "(ausente)",
        )
    if tipo == "presente":
        return FilaDiscrepancia(criterio=criterio, esperado="presente", recibido="(ausente)")
    return FilaDiscrepancia(
        criterio=criterio, esperado="ausente", recibido=discrepancia["recibido"] or ""
    )


def evaluacion_de_ejecucion(ejecucion, descripciones: Mapping[str, str]) -> EvaluacionMostrada | None:
    """`None` cuando el escenario no tenia expectativas -nunca "PASS" por
    omision-. Lee el snapshot congelado, no vuelve a evaluar nada.
    """
    if ejecucion.evaluacion_estado is None or not ejecucion.evaluacion_json:
        return None
    datos = json.loads(ejecucion.evaluacion_json)
    filas = [_fila_de_discrepancia(d, descripciones) for d in datos.get("discrepancias", [])]
    return EvaluacionMostrada(estado=ejecucion.evaluacion_estado, filas=tuple(filas))


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
        "evaluacion": evaluacion_de_ejecucion(resultado.ejecucion, descripciones),
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
        "evaluacion": evaluacion_de_ejecucion(ejecucion, descripciones),
        "motivo_esperado": ejecucion.estado in ESTADOS_CON_MOTIVO,
        "motivo_detalle": motivo_de(ejecucion),
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


# --------------------------------------------------------- Bloque 4: suites --


@dataclass(frozen=True)
class FilaSeleccionEscenario:
    """Una fila del constructor de suites: un escenario del catalogo, con si
    esta incluido en ESTA suite y en que orden -vacio si no esta incluido-.
    """

    escenario_id: str
    nombre: str
    activo: bool
    incluido: bool
    orden: str


def filas_seleccion_escenarios(
    catalogo: Sequence, escenarios_incluidos: Sequence[str]
) -> Sequence[FilaSeleccionEscenario]:
    """Todos los escenarios del catalogo, marcando cuales ya estan en la suite
    y en que orden -para que el constructor pueda mostrar la tabla completa,
    no solo los ya elegidos, igual criterio que `filas_expectativas`.

    Un escenario ya incluido conserva EXACTAMENTE su orden real dentro de la
    suite -nunca se toca-. Uno todavia NO incluido se prellena con el menor
    entero positivo que no colisione con ningun orden real ya ocupado -nunca
    con su posicion cruda en el catalogo, que si podria coincidir con el
    orden real de otro escenario cuando `escenarios_incluidos` no sigue el
    mismo orden que el catalogo (`ORDER BY nombre`)-. Es solo una sugerencia
    editable -nunca fuerza un orden, ni cambia como el servidor valida
    duplicados/huecos, ver `_leer_escenarios_de_suite`-, para que marcar
    varios checkboxes seguidos no obligue a escribir cada numero a mano.
    """
    posicion = {escenario_id: i + 1 for i, escenario_id in enumerate(escenarios_incluidos)}
    ocupados = set(posicion.values())
    siguiente_libre = 1
    filas = []
    for escenario in catalogo:
        if escenario.escenario_id in posicion:
            orden = posicion[escenario.escenario_id]
        else:
            while siguiente_libre in ocupados:
                siguiente_libre += 1
            orden = siguiente_libre
            ocupados.add(orden)
        filas.append(
            FilaSeleccionEscenario(
                escenario_id=escenario.escenario_id,
                nombre=escenario.nombre,
                activo=escenario.activo,
                incluido=escenario.escenario_id in posicion,
                orden=str(orden),
            )
        )
    return filas


def filas_seleccion_escenarios_desde_formulario(
    catalogo: Sequence, formulario_bruto
) -> Sequence[FilaSeleccionEscenario]:
    """Igual que `filas_seleccion_escenarios`, pero reconstruida desde un
    formulario que **todavia no se valido** -o que fallo la validacion-, no
    desde una `Suite` ya guardada.

    Existe para que un error al guardar una suite (por ejemplo, un orden
    invalido o repetido) conserve exactamente los escenarios que la persona
    habia marcado y el texto que habia escrito en "orden", en vez de volver a
    la seleccion vacia o a la de la suite tal como estaba antes de editar.
    Por eso `orden` aqui es el texto CRUDO del formulario -incluso si no es un
    entero valido-: esta funcion es solo de presentacion, la validacion real
    sigue siendo unicamente `_leer_escenarios_de_suite`.
    """
    return [
        FilaSeleccionEscenario(
            escenario_id=escenario.escenario_id,
            nombre=escenario.nombre,
            activo=escenario.activo,
            incluido=bool(formulario_bruto.get(f"incluir_{escenario.escenario_id}") or ""),
            orden=(formulario_bruto.get(f"orden_{escenario.escenario_id}", "") or ""),
        )
        for escenario in catalogo
    ]


#: Un aviso por resultado global de suite. INCOMPLETA y SIN_EXPECTATIVAS
#: reutilizan tonos ya existentes (`indeterminado`/`no-enviada`) en vez de
#: inventar clases CSS nuevas: no son un octavo y noveno desenlace de
#: ejecucion, son un resultado agregado con su propio significado.
AVISOS_RESULTADO_GLOBAL_SUITE: Mapping[str, Aviso] = {
    "pass": Aviso(
        "aprobada", "Suite en PASS",
        "Todos los escenarios de la corrida tenían expectativas y todos las cumplieron.",
        etiqueta="PASS", senal="aprobada",
    ),
    "fail": Aviso(
        "rechazada", "Suite en FAIL",
        "Al menos un escenario no cumplió su expectativa.",
        etiqueta="FAIL", senal="rechazada",
    ),
    "error": Aviso(
        "error", "Suite con errores",
        "Al menos un escenario no se pudo ejecutar, o la corrida quedó inconsistente.",
        etiqueta="ERROR", senal="",
    ),
    "incompleta": Aviso(
        "indeterminado", "Corrida incompleta",
        "Hubo escenarios que pasaron y escenarios sin expectativas: no todos los "
        "casos de esta corrida fueron realmente evaluados.",
        etiqueta="INCOMPLETA", senal="",
    ),
    "sin_expectativas": Aviso(
        "no-enviada", "Sin expectativas",
        "Ningún escenario de esta corrida definía qué resultado esperaba.",
        etiqueta="SIN EXPECTATIVAS", senal="",
    ),
}


@dataclass(frozen=True)
class FilaCorrida:
    """Una fila del listado de corridas."""

    corrida_id: int
    suite_nombre: str
    estado: str
    resultado_global: str | None
    total: int
    cantidad_pass: int
    cantidad_fail: int
    cantidad_error: int
    cantidad_sin_expectativas: int
    iniciada_en: str
    duracion: str


def _duracion(corrida) -> str:
    if corrida.finalizada_en is None:
        return "en curso"
    segundos = (corrida.finalizada_en - corrida.iniciada_en).total_seconds()
    return f"{segundos:.1f} s"


def fila_de_corrida(corrida) -> FilaCorrida:
    return FilaCorrida(
        corrida_id=corrida.corrida_id,
        suite_nombre=corrida.suite_nombre,
        estado=corrida.estado.value,
        resultado_global=corrida.resultado_global.value if corrida.resultado_global else None,
        total=corrida.total,
        cantidad_pass=corrida.cantidad_pass,
        cantidad_fail=corrida.cantidad_fail,
        cantidad_error=corrida.cantidad_error,
        cantidad_sin_expectativas=corrida.cantidad_sin_expectativas,
        iniciada_en=corrida.iniciada_en.strftime("%Y-%m-%d %H:%M:%S"),
        duracion=_duracion(corrida),
    )


@dataclass(frozen=True)
class FilaItemCorrida:
    """Una fila del detalle de una corrida: un escenario y su resultado.

    `evaluacion` se arma del `evaluacion_json` propio del item -nunca del
    escenario en vivo ni de una nueva evaluacion-: la corrida se explica con
    su propio snapshot, autosuficiente.
    """

    orden: int
    escenario_id: str
    escenario_nombre: str
    resultado: str
    detalle: str | None
    ejecucion_id: int | None
    evaluacion: EvaluacionMostrada | None


def filas_de_corrida(items: Sequence, descripciones: Mapping[str, str]) -> Sequence[FilaItemCorrida]:
    return [
        FilaItemCorrida(
            orden=item.orden,
            escenario_id=item.escenario_id,
            escenario_nombre=item.escenario_nombre,
            resultado=item.resultado.value,
            detalle=item.detalle,
            ejecucion_id=item.ejecucion_id,
            evaluacion=evaluacion_de_item(item, descripciones),
        )
        for item in items
    ]


def evaluacion_de_item(item, descripciones: Mapping[str, str]) -> EvaluacionMostrada | None:
    """Igual que `evaluacion_de_ejecucion`, pero leyendo el snapshot propio
    del item de corrida -nunca el de una `Ejecucion` releida, aunque
    `item.ejecucion_id` exista solo como enlace de navegacion-.
    """
    if not item.evaluacion_json:
        return None
    datos = json.loads(item.evaluacion_json)
    filas = [_fila_de_discrepancia(d, descripciones) for d in datos.get("discrepancias", [])]
    return EvaluacionMostrada(estado=datos["resultado"], filas=tuple(filas))

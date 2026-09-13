"""Modelos del dominio para los recorridos Multi-MTI de este laboratorio:
compra/autorizacion (0100/0110), echo de red (0800/0810) y compra financiera
(0200/0210, B4).

Existen para que no circulen diccionarios anonimos por la aplicacion. Son
deliberadamente planos: no hay jerarquia de clases ni modelos para MTIs fuera del
alcance aprobado en PROYECTO.md.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import Mapping

from .enmascarado import enmascarar_campos, enmascarar_pan

MTI_COMPRA = "0100"
MTI_RESPUESTA_COMPRA = "0110"

#: Network Management / Echo Test (B2, 2026-09-12): primera operacion distinta
#: de compra. Sin tarjeta, sin monto -ver `DatosEcho`, `Ejecucion.card_id`
#: nullable en `adapters/persistence/esquema.py`-. La respuesta se deriva con
#: `domain.validacion.mti_de_respuesta("0800")`, nunca una segunda constante
#: independiente calculada a mano.
MTI_ECHO = "0800"
MTI_RESPUESTA_ECHO = "0810"

#: Transaccion financiera (B4, 2026-09-13): primera operacion Multi-MTI que
#: confirma que `operacion` y `mti` son conceptos separados de verdad, no
#: solo en el papel (B3 los dejo listos para esto). Dentro de este
#: laboratorio, 0100 modela una AUTORIZACION (reserva/verificacion, sin mover
#: fondos por si sola) y 0200 modela una TRANSACCION FINANCIERA (mueve fondos
#: en el mismo mensaje) -es la distincion de dominio que ISO 8583 documenta en
#: general para estas dos familias, no una regla de una marca especifica-.
#: `OPERACION_COMPRA_FINANCIERA` es una intencion DISTINTA de
#: `OPERACION_COMPRA`, aunque hoy ambas se deriven 1:1 de su MTI: el dia que
#: 0200 deba representar mas de una intencion segun el codigo de proceso,
#: quien arme el escenario elegira la operacion explicitamente en vez de
#: derivarla de `OPERACION_POR_MTI`.
MTI_COMPRA_FINANCIERA = "0200"
MTI_RESPUESTA_COMPRA_FINANCIERA = "0210"

#: Reverso financiero (B7, 2026-09-13): la primera OPERACION DERIVADA real
#: de este laboratorio -deshace una 0200 ya aprobada, construida SIEMPRE
#: desde el snapshot seguro de esa ejecucion origen (B6,
#: `application.referencia_ejecucion.ReferenciaEjecucion`), nunca desde un
#: constructor libre. `armar_reverso_financiero` vive en
#: `application/armado_reverso.py`, no en `domain/armado.py`: su unico dato
#: de entrada es un tipo de la capa de aplicacion, y el dominio no puede
#: depender de ella (ver docstring de ese modulo).
MTI_REVERSO_FINANCIERO = "0400"
MTI_RESPUESTA_REVERSO_FINANCIERO = "0410"

#: Identificador de la INTENCION funcional de un escenario (B3, 2026-09-13),
#: separado del MTI: hoy cada MTI implica exactamente una operacion, asi que
#: `OPERACION_POR_MTI` alcanza para derivarlo sin ambiguedad. El campo existe
#: por adelantado porque un MTI futuro (ej. 0200) SI podria representar mas
#: de una operacion segun el codigo de proceso -en ese momento, quien arme el
#: escenario decidira la operacion explicitamente en vez de derivarla de este
#: mapa; el campo ya esta listo para cargarla-. No es un catalogo de negocio:
#: son dos strings, y agregar uno tercero no es una migracion, es una linea.
OPERACION_COMPRA = "purchase"
OPERACION_ECHO = "network_echo"
OPERACION_COMPRA_FINANCIERA = "financial_purchase"
#: Reverso financiero (B7): identidad funcional separada de "0400", mismo
#: criterio que las tres anteriores -esta vez la separacion no es teorica:
#: `MTI_REVERSO_FINANCIERO` identifica el MENSAJE, `OPERACION_REVERSO_FINANCIERO`
#: identifica que ESTE mensaje concreto es una operacion derivada de otra
#: ejecucion (ver `Ejecucion.ejecucion_origen_id`, B6).
OPERACION_REVERSO_FINANCIERO = "financial_reversal"
OPERACION_POR_MTI: Mapping[str, str] = {
    MTI_COMPRA: OPERACION_COMPRA,
    MTI_ECHO: OPERACION_ECHO,
    MTI_COMPRA_FINANCIERA: OPERACION_COMPRA_FINANCIERA,
    MTI_REVERSO_FINANCIERO: OPERACION_REVERSO_FINANCIERO,
}

#: Campos ISO que transportan datos de tarjeta y nunca se persisten en claro.
#: Piso UNIVERSAL de dominio -protege estos tres numeros para CUALQUIER
#: perfil, incluso los que `MensajeIso.enmascarado()`/`MensajeInterpretado.
#: enmascarado()` (sin acceso a un perfil: son metodos de dataclass sin ese
#: parametro) no pueden consultar-. DE2 (PAN), DE35 (Track 2) y DE45
#: (Track 1) son sensibles POR DEFINICION del estandar ISO 8583, no por
#: decision de un perfil -asi que protegerlos aqui, a nivel de dominio, es
#: correcto incluso antes de que exista ningun perfil que los declare-.
#:
#: B3 (2026-09-13, ARCH-001/SEC-001): un perfil puede declarar sensibilidad
#: ADICIONAL, especifica de si mismo, via `PerfilDeMarca.campos_sensibles`/
#: `es_sensible()` (`profiles/generico.py`), consultado por los guardias que
#: SI reciben un perfil real (`domain.expectativas.
#: campos_permitidos_expectativa`, `domain.validacion.campos_de_correlacion`,
#: `adapters.iso8583.codec._verificar_enmascarado_para_inspeccion`). Los que
#: no lo reciben (este archivo, `application/serializacion.py`,
#: `web/presentacion.py` -presentacion pura, la proteccion real ya ocurrio
#: antes de llegar ahi-) siguen con este piso universal, que ya cubre los
#: tres campos que hoy existen.
CAMPOS_SENSIBLES = frozenset({"2", "35", "45"})

#: El numero de trazabilidad (campo 11) tiene exactamente seis digitos.
LARGO_STAN = 6
#: Ultimo valor del ciclo. Al superarlo, la secuencia vuelve a 000001: seis
#: digitos no alcanzan para ser unicos indefinidamente, y eso es inherente al
#: formato, no una limitacion de esta implementacion.
STAN_MAXIMO = 10**LARGO_STAN - 1


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ReferenciaTarjeta:
    """Como el resto del sistema nombra una tarjeta: por identificador, no por PAN."""

    card_id: str
    pan_enmascarado: str


@dataclass(frozen=True)
class TarjetaPrueba:
    """Tarjeta del catalogo de pruebas.

    Es el unico lugar del sistema donde vive el PAN completo, y solo dentro del
    archivo SQLite local, que no se versiona.

    Los ocho campos de laboratorio (titular en adelante) son datos propios de
    la tarjeta, todavia sin validar y sin transmitirse por ISO: ninguno de
    ellos viaja hoy en el 0100, ninguno esta en `ESPECIFICACION_GENERICA`, y
    `card_sequence_number` no es lo mismo que `card_id` -uno identifica la fila
    en este catalogo, el otro seria el numero de secuencia de la tarjeta
    fisica-. `pin_block_laboratorio` es un valor de laboratorio con forma de
    PIN Block, no un PIN Block criptograficamente valido: este proyecto no
    tiene ninguna clave de cifrado detras. El PIN en claro nunca se modela
    aqui ni en ningun otro lugar del sistema.
    """

    card_id: str
    pan: str
    expiracion: str
    descripcion: str = ""
    sintetica: bool = True
    activa: bool = True
    titular: str = ""
    service_code: str = ""
    discretionary_data: str = ""
    cvv: str = ""
    cvv2: str = ""
    icvv: str = ""
    card_sequence_number: str = ""
    pin_block_laboratorio: str = ""

    @property
    def pan_enmascarado(self) -> str:
        return enmascarar_pan(self.pan)

    def referencia(self) -> ReferenciaTarjeta:
        return ReferenciaTarjeta(card_id=self.card_id, pan_enmascarado=self.pan_enmascarado)

    def __str__(self) -> str:
        return f"TarjetaPrueba(card_id={self.card_id}, pan={self.pan_enmascarado})"

    __repr__ = __str__


@dataclass(frozen=True)
class DatosCompra:
    """Lo que se completa para armar una compra.

    `card_id` y `monto` son de primera clase porque tienen lógica propia: el
    primero dispara la derivación de los campos 2 y 14 desde la tarjeta: el
    segundo se formatea a las doce posiciones que exige el campo 4. Todo lo
    demás que un perfil declare editable para el MTI —moneda, terminal, código
    de proceso, campos opcionales— vive en `campos_manuales`: agregar un campo
    editable nuevo al perfil no debe obligar a agregar una propiedad aquí.
    """

    card_id: str
    monto: Decimal
    campos_manuales: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "campos_manuales", MappingProxyType(dict(self.campos_manuales)))


@dataclass(frozen=True)
class DatosEcho:
    """Lo que se completa para armar un Network Management / Echo Test (0800).

    Sin `card_id` ni `monto`: no hay tarjeta ni importe involucrados en un
    echo -a diferencia de `DatosCompra`, no tiene ningun campo de primera
    clase con logica propia. `campos_manuales` sigue el mismo contrato
    (unica puerta para fijar un valor editable, hoy solo DE70), para que el
    mecanismo de variables dinamicas (Fase A) y el de escenarios funcionen
    exactamente igual que con compra, sin un segundo camino.
    """

    campos_manuales: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "campos_manuales", MappingProxyType(dict(self.campos_manuales)))


@dataclass(frozen=True)
class DatosCompraFinanciera:
    """Lo que se completa para armar una compra financiera (0200, B4).

    Mismos tres campos que `DatosCompra`, y a proposito: `card_id`/`monto`
    tienen la misma logica propia (derivar DE2/DE14 de la tarjeta, formatear
    DE4) para CUALQUIER operacion que mueva fondos con una tarjeta, sea
    0100 o 0200 -por eso `domain/armado.py` comparte la capa estructural
    entre ambas en vez de duplicarla-. Es un dataclass propio, no un alias de
    `DatosCompra`, porque son la entrada de dos OPERACIONES distintas
    (autorizacion vs. transaccion financiera, ver `OPERACION_COMPRA_FINANCIERA`):
    confundirlas bajo el mismo tipo volveria a acoplar operacion con MTI,
    exactamente lo que B4 existe para evitar.
    """

    card_id: str
    monto: Decimal
    campos_manuales: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "campos_manuales", MappingProxyType(dict(self.campos_manuales)))


@dataclass(frozen=True)
class DatosReversoFinanciero:
    """Lo minimo para pedir un reverso financiero (0400, B7): la identidad
    de la ejecucion origen, nada mas.

    A diferencia de `DatosCompra`/`DatosCompraFinanciera`, NO tiene
    `campos_manuales`: un reverso no es un constructor libre -todo campo del
    0400 se deriva del snapshot de la ejecucion origen (`ReferenciaEjecucion`,
    B6) o se genera automaticamente (nuevo STAN, nuevo momento), nunca de
    texto que alguien escriba a mano (B7, punto 5). La elegibilidad de
    `ejecucion_origen_id` (hoy, solo una 0200 aprobada -ver
    `domain.elegibilidad_reverso`-) se revalida siempre en el orquestador:
    nunca se confia en que quien llama ya la valido.
    """

    ejecucion_origen_id: int


@dataclass(frozen=True)
class ExpectativaCampo:
    """Una condicion sobre un campo de la respuesta.

    `valor` solo aplica a `tipo="igual"`; para `"presente"`/`"ausente"` no hay
    un valor que comparar, solo si el campo aparecio o no.
    """

    tipo: str  # "igual" | "presente" | "ausente"
    valor: str | None = None


@dataclass(frozen=True)
class Expectativas:
    """Lo que un escenario espera de su ejecucion. Dos criterios independientes.

    `estado` es una expectativa SEMANTICA: compara contra `EstadoEjecucion`,
    que ya resulto de aplicar RN-1 (catalogo configurado) y RN-3
    (correlacion) -asi que "aprobada" sigue significando "el catalogo de HOY
    la acepta", no un codigo fijo. `campos` son expectativas LITERALES sobre
    valores concretos de la respuesta: un escenario puede pedir
    `estado=aprobada` y ADEMAS `campo 39 igual a "00"` a la vez, y ambos se
    evaluan por separado -si el catalogo aprobara tambien el "05", la primera
    podria pasar mientras la segunda falla, y las dos cosas son correctas.
    """

    estado: EstadoEjecucion | None = None
    campos: Mapping[str, ExpectativaCampo] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "campos", MappingProxyType(dict(self.campos)))


class EstadoEvaluacion(str, Enum):
    """Si la ejecucion cumplio la expectativa del escenario. NO es `EstadoEjecucion`:
    ese dice que paso con la transaccion; este dice si eso era lo esperado.
    """

    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True)
class DiscrepanciaExpectativa:
    """Un punto concreto en el que lo recibido no coincidio con lo esperado.

    Estructurada -no un string- para que un bloque futuro (regresion) pueda
    agrupar y contar fallos sin volver a parsear texto. La capa web la
    traduce a un mensaje legible; el dominio no redacta prosa.
    """

    criterio: str          # "estado" | "campo"
    campo: str | None      # numero de campo; None si criterio="estado"
    tipo: str | None       # tipo de la expectativa de campo; None si criterio="estado"
    esperado: str | None
    recibido: str | None


@dataclass(frozen=True)
class ResultadoEvaluacion:
    """Resultado de comparar una ejecucion contra las expectativas de su escenario."""

    estado: EstadoEvaluacion
    discrepancias: tuple[DiscrepanciaExpectativa, ...] = ()


@dataclass(frozen=True)
class Escenario:
    """Una transaccion reutilizable: la intencion, no una corrida concreta.

    Congela los valores EFECTIVOS de todos los campos editables del perfil
    para ese MTI en el momento de guardar -defaults incluidos, no solo lo que
    el usuario haya tocado-: si mañana el perfil cambia un default, este
    escenario no debe cambiar de comportamiento en silencio.

    Nunca contiene PAN (referencia la tarjeta por `card_id`, igual que
    `DatosCompra` y `Ejecucion`) ni host/puerto/timeout (referencia la
    conexion por `conexion_id`, igual que el constructor). `monto` queda
    separado de `campos_manuales` a proposito: DE4 no es un campo editable
    segun `PoliticaCamposMti` -lo arma `armar_compra` en su capa
    estructural-, asi que nunca podria vivir junto a los campos que si
    gobierna esa politica.

    `card_id`/`monto` son `None` para una operacion sin tarjeta ni monto (B3,
    2026-09-13: Echo es la primera) -mismo criterio ya aplicado a
    `Ejecucion` en B2-. `application.escenarios.ServicioEscenarios` decide,
    a partir de que campos exige el perfil para ese MTI (`"2" in
    perfil.obligatorios(mti)`, `"4" in ...`), si vale la pena exigirlos: este
    dataclass no impone la regla, solo permite representarla sin un sentinel
    inventado.

    `operacion` es la intencion funcional (ver `OPERACION_POR_MTI`), separada
    del MTI: hoy son 1:1, pero el campo ya existe para cuando dejen de serlo.

    `expectativas` es opcional: un escenario sin expectativas sigue siendo
    valido -simplemente no hay nada que evaluar, y eso no es lo mismo que
    "aprobado" (ver `domain.expectativas.evaluar_expectativas`).
    """

    escenario_id: str
    nombre: str
    perfil: str
    mti: str
    conexion_id: str
    card_id: str | None = None
    monto: Decimal | None = None
    operacion: str = OPERACION_COMPRA
    campos_manuales: Mapping[str, str] = field(default_factory=dict)
    expectativas: Expectativas | None = None
    activo: bool = True
    creado_en: datetime = field(default_factory=_ahora)
    actualizado_en: datetime = field(default_factory=_ahora)

    def __post_init__(self) -> None:
        object.__setattr__(self, "campos_manuales", MappingProxyType(dict(self.campos_manuales)))


@dataclass(frozen=True)
class DestinoTcp:
    """Destino configurable del envio. Todavia no se conecta a nada."""

    host: str
    puerto: int

    def __post_init__(self) -> None:
        if not 1 <= self.puerto <= 65535:
            raise ValueError(f"puerto fuera de rango: {self.puerto}")

    def __str__(self) -> str:
        return f"{self.host}:{self.puerto}"


@dataclass(frozen=True)
class DestinoGuardado:
    """Destino de prueba administrado, persistido en el catalogo de destinos.

    Distinto de `DestinoTcp`: este es la entidad con identidad propia
    (`destino_id`), nombre y estado activo/inactivo, la que administra la
    pantalla de destinos. `DestinoTcp` sigue siendo el valor minimo que el
    transporte necesita para conectar, y una ejecucion sigue guardando
    `destino_host`/`destino_puerto` como valores propios: desactivar o editar
    un `DestinoGuardado` no debe alterar el historial ya registrado.
    """

    destino_id: str
    nombre: str
    host: str
    puerto: int
    activo: bool = True
    #: Limite de tiempo propio de esta conexion. Reemplaza, para las compras
    #: que la usan, el limite global de `Configuracion.tiempo_limite`: cada
    #: conexion administrada lleva el suyo.
    timeout: float = 10.0
    creado_en: datetime = field(default_factory=_ahora)

    def a_destino_tcp(self) -> DestinoTcp:
        return DestinoTcp(host=self.host, puerto=self.puerto)


@dataclass(frozen=True)
class MensajeIso:
    """Mensaje ISO 8583 en terminos del dominio: un MTI y sus campos.

    No sabe como se codifica. La representacion en bytes es responsabilidad del
    codec, que recibe el perfil como parametro.
    """

    mti: str
    campos: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "campos", MappingProxyType(dict(self.campos)))

    def numeros_presentes(self) -> frozenset[str]:
        return frozenset(n for n, v in self.campos.items() if v != "")

    def enmascarado(self) -> MensajeIso:
        return MensajeIso(self.mti, enmascarar_campos(dict(self.campos), CAMPOS_SENSIBLES))

    def __str__(self) -> str:
        return f"MensajeIso(mti={self.mti}, campos={sorted(self.campos)})"

    __repr__ = __str__


@dataclass(frozen=True)
class CampoInterpretado:
    """Un campo ISO tal como quedo tras decodificar.

    Conserva el valor, los bytes crudos y la descripcion del perfil: es lo que
    alimentara el isoscopio.
    """

    numero: str
    valor: str
    crudo: str
    descripcion: str


@dataclass(frozen=True)
class MensajeInterpretado:
    """Resultado de decodificar un mensaje, campo por campo."""

    mti: str
    campos: Mapping[str, CampoInterpretado] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "campos", MappingProxyType(dict(self.campos)))

    def como_mensaje(self) -> MensajeIso:
        """Vista de dominio, sin los detalles de codificacion."""
        return MensajeIso(self.mti, {n: c.valor for n, c in self.campos.items()})

    def valor(self, numero: str) -> str | None:
        campo = self.campos.get(numero)
        return campo.valor if campo else None

    def enmascarado(self) -> MensajeInterpretado:
        """Copia con los campos de tarjeta enmascarados, apta para mostrar o guardar."""
        return MensajeInterpretado(
            self.mti,
            {
                numero: (
                    campo
                    if numero not in CAMPOS_SENSIBLES
                    else CampoInterpretado(
                        numero=campo.numero,
                        valor=enmascarar_pan(campo.valor),
                        crudo=enmascarar_pan(campo.crudo),
                        descripcion=campo.descripcion,
                    )
                )
                for numero, campo in self.campos.items()
            },
        )

    def __str__(self) -> str:
        return f"MensajeInterpretado(mti={self.mti}, campos={sorted(self.campos)})"

    __repr__ = __str__


@dataclass(frozen=True)
class TiempoAgotado:
    """Se agoto el limite esperando una respuesta completa.

    Es **exactamente** RN-2, y nada mas. Solo se devuelve cuando se cumplen las
    cuatro premisas, todas observables **desde este cliente**:

    1. la conexion TCP se establecio;
    2. la escritura y el drenaje locales terminaron sin error;
    3. se empezo a esperar una respuesta;
    4. no llego una respuesta completa dentro del limite.

    LO QUE ESTO NO AFIRMA
    =====================
    Que el drenaje local terminara sin error **no demuestra** que la aplicacion
    remota recibiera ni proceso el mensaje: `drain()` habla del buffer local, no
    del par. Por eso esta prohibido describir este estado como "la solicitud fue
    transmitida", "si se envio" o "el destino recibio".

    Si alguna de las tres primeras no se cumple, el resultado es otro:
    `FalloDeConexion` o `FalloDeTransmision`.

    No es una excepcion: es un resultado esperado del transporte, y RN-2 exige
    contarlo aparte de un rechazo explicito del switch.
    """

    limite_segundos: float


@dataclass(frozen=True)
class FalloDeConexion:
    """No se pudo establecer la sesion TCP.

    **Solo** para eso: rechazo, ruta inexistente, nombre irresoluble o tiempo
    agotado mientras se conectaba. Si la conexion llego a establecerse, cualquier
    fallo posterior es `FalloDeTransmision`, no esto.

    Aqui si es demostrable que nada se transmitio, porque no hubo sesion por la
    cual transmitir.

    Es un resultado y no una excepcion, igual que `TiempoAgotado`: para una
    herramienta de pruebas, que el destino no este disponible es una observacion
    que hay que registrar, no una anomalia que haya que propagar.
    """

    detalle: str


@dataclass(frozen=True)
class FalloDeTransmision:
    """Hubo sesion TCP y el intercambio termino de forma **indeterminada**.

    Cubre que falle o se agote el drenaje del envio, que el canal se rompa
    mientras se esperaba la respuesta, y que el desenmarcado no pueda completar un
    mensaje despues de haberse establecido la comunicacion.

    LO QUE NO SE PUEDE AFIRMAR
    ==========================
    **No se puede afirmar cuantos bytes recibio o proceso el destino.**
    `StreamWriter.write()` solo encola en el buffer local y `drain()` habla de ese
    buffer, no de la aplicacion remota; TCP no le dice al programa cuanto proceso
    el par. Asi que ante este resultado pudieron llegar cero bytes, algunos o
    todos, y no hay forma de distinguirlo.

    Por eso esta prohibido describirlo como "nunca salio", "no se envio" o "cero
    bytes llegaron": para una herramienta de pruebas de pagos, afirmar que no se
    envio algo que pudo haberse enviado es el error mas caro posible.
    """

    detalle: str


@dataclass(frozen=True)
class ResultadoValidacion:
    """Salida de la validacion previa al envio (RN-4)."""

    valido: bool
    faltantes: tuple[str, ...] = ()
    motivos: tuple[str, ...] = ()

    @classmethod
    def ok(cls) -> ResultadoValidacion:
        return cls(valido=True)

    def __bool__(self) -> bool:
        return self.valido


class EstadoEjecucion(str, Enum):
    """Desenlace de una ejecucion. Seis estados, cada uno con una causa distinta.

    Llego una respuesta del autorizador:
      APROBADA   el codigo del campo 39 esta aprobado en el catalogo (RN-1)
      RECHAZADA  llego respuesta y su codigo no es una aprobacion
      INVALIDA   llego respuesta pero no corresponde a la solicitud (RN-3), o no
                 se pudo interpretar

    No llego una respuesta utilizable, y los cuatro casos se distinguen por lo
    que cada uno permite **demostrar**:

      NO_ENVIADA         no se llego a intentar transmision por la red.
                         Demostrable: RN-4, el codec no pudo codificar, o el
                         framing de salida rechazo el payload antes de conectar
      ERROR_CONEXION     no se establecio la sesion TCP. Demostrable: no hubo
                         canal por el cual transmitir
      ERROR_TRANSMISION  hubo sesion TCP y el intercambio quedo **indeterminado**.
                         NO es demostrable que nada se transmitiera
      TIMEOUT            se envio, el drenaje completo, y no llego respuesta
                         dentro del limite. Es RN-2, y solo esto es RN-2

    Estan separados porque presentarlos juntos daria un diagnostico equivocado:
    "no llegue a conectar", "conecte y no se sabe que recibio" y "el switch no
    contesta" se investigan de forma distinta, y la del medio es la unica que
    obliga a sospechar que la transaccion pudo haberse procesado.
    """

    APROBADA = "aprobada"
    RECHAZADA = "rechazada"
    INVALIDA = "invalida"
    TIMEOUT = "timeout"
    ERROR_CONEXION = "error_conexion"
    ERROR_TRANSMISION = "error_transmision"
    NO_ENVIADA = "no_enviada"


@dataclass
class Ejecucion:
    """Registro persistible de un intento de ejecucion (compra u otra operacion).

    Referencia la tarjeta por ``card_id``. No tiene campo para el PAN completo:
    los mensajes se guardan ya enmascarados.

    ``card_id``/``monto``/``moneda`` son ``None`` para una operacion sin
    tarjeta ni monto (B2, 2026-09-12: Network Management/Echo es la primera).
    Movidos despues de ``stan``/``estado`` -que toda ejecucion tiene, sin
    excepcion- porque un dataclass no admite un campo sin default despues de
    uno con default. Ningun llamador construye `Ejecucion` posicionalmente
    (todos usan keywords), asi que este reordenamiento no rompe nada.
    """

    stan: str
    estado: EstadoEjecucion
    mti_solicitud: str = MTI_COMPRA
    card_id: str | None = None
    monto: Decimal | None = None
    moneda: str | None = None
    mti_respuesta: str | None = None
    codigo_respuesta: str | None = None
    destino_host: str | None = None
    destino_puerto: int | None = None
    solicitud_enmascarada: str | None = None
    respuesta_enmascarada: str | None = None
    #: Representacion estructurada de los mismos mensajes, ya enmascarados. Las
    #: dos columnas de texto se conservan por compatibilidad y legibilidad; estas
    #: son las que permiten recuperar campo por campo sin depender de un
    #: separador sin escape. Quedan en `None` en las filas escritas antes de que
    #: existieran, y en la respuesta cuando no llego ninguna.
    solicitud_json: str | None = None
    respuesta_json: str | None = None
    latencia_ms: int | None = None
    #: Si esta ejecucion partio de un escenario guardado, su identificador y su
    #: nombre en ese momento. El nombre se copia aqui -no se resuelve con un
    #: join en cada lectura- por la misma razon que `destino_host` copia el
    #: host de la conexion usada: editar o renombrar el escenario despues no
    #: debe alterar como luce una ejecucion ya registrada. No es un dato
    #: sensible, asi que copiarlo no es un riesgo de PAN.
    escenario_id: str | None = None
    escenario_nombre: str | None = None
    #: Snapshot de la evaluacion expected-vs-actual, congelado al ejecutar.
    #: `evaluacion_estado` es "pass"/"fail"/`None` -`None` significa que el
    #: escenario no tenia expectativas, NUNCA "aprobado por omision".
    #: `evaluacion_json` guarda la expectativa ORIGINAL usada (no una
    #: referencia al escenario) mas las discrepancias: editar las
    #: expectativas del escenario despues no puede alterar este snapshot.
    evaluacion_estado: str | None = None
    evaluacion_json: str | None = None
    #: Causa concreta del desenlace, ya en texto seguro para mostrar (los
    #: mismos `motivos` que ya se muestran en la pantalla de resultado
    #: inmediato: nombres de campo, codigos de catalogo, texto de socket -
    #: nunca una excepcion cruda ni un mensaje ISO completo). `None` en dos
    #: casos que no deben confundirse: una ejecucion APROBADA (no hay motivo
    #: que registrar) y una fila anterior a que este campo existiera (no es
    #: demostrable que no lo tuviera, simplemente no se conserva).
    motivo_detalle: str | None = None
    creada_en: datetime = field(default_factory=_ahora)
    id: int | None = None
    #: Referencia a la ejecucion de la que ESTA se deriva (B6, 2026-09-13):
    #: la relacion interna origen->derivada que un futuro reverso (0400/0410)
    #: usara, sin depender de STAN/RRN -que pueden repetirse o no ser unicos-.
    #: `None` para cualquier ejecucion independiente (la inmensa mayoria hoy:
    #: B6 no crea ninguna derivada real todavia, solo el modelo). Un mismo
    #: origen puede tener VARIAS derivadas -no es 1:1-: nada aqui lo impide,
    #: la cardinalidad 1->N surge de que cualquier cantidad de filas puede
    #: compartir el mismo `ejecucion_origen_id`. Nunca se resuelve con un
    #: JOIN en cada lectura -mismo criterio que `escenario_id`/`escenario_nombre`-:
    #: es un puntero de navegacion, no una fuente de datos; los datos seguros
    #: de la ejecucion origen viajan aparte, en `ReferenciaEjecucion`
    #: (`application/referencia_ejecucion.py`), construida SOLO con campos ya
    #: enmascarados/no sensibles.
    ejecucion_origen_id: int | None = None


@dataclass(frozen=True)
class FiltroHistorial:
    """Criterios de busqueda sobre el historial de ejecuciones.

    Todo campo vacio/`None` significa "sin restriccion en ese criterio" -nunca
    "cero resultados"-. Vive en el dominio (no en `application`) porque lo
    comparten el puerto `RepositorioEjecuciones` y su adaptador SQLite, y el
    dominio no puede depender de `application`.

    `evaluacion` es literal, no `EstadoEvaluacion`: admite el valor especial
    ``"sin_expectativas"`` -que no es un estado de `EstadoEvaluacion`- para
    poder filtrar exactamente por "no tenia expectativas", distinto de
    PASS/FAIL.
    """

    desde: str = ""  # fecha ISO "AAAA-MM-DD", inclusive
    hasta: str = ""  # idem, inclusive
    estado: EstadoEjecucion | None = None
    evaluacion: str = ""  # "" | "pass" | "fail" | "sin_expectativas"
    card_id: str = ""
    destino: str = ""  # subcadena de "host:puerto"
    stan: str = ""

    def vacio(self) -> bool:
        return not any((
            self.desde, self.hasta, self.estado, self.evaluacion,
            self.card_id, self.destino, self.stan,
        ))


@dataclass(frozen=True)
class ResultadoCompra:
    """Lo que el orquestador devuelve tras ejecutar un recorrido completo.

    Lleva todo lo que la interfaz web y el isoscopio necesitaran mas adelante,
    ya enmascarado. No expone bytes crudos con datos de tarjeta.
    """

    ejecucion: Ejecucion
    solicitud: MensajeIso
    respuesta: MensajeInterpretado | None = None
    motivos: tuple[str, ...] = ()

    @property
    def estado(self) -> EstadoEjecucion:
        return self.ejecucion.estado

    @property
    def aprobada(self) -> bool:
        return self.ejecucion.estado is EstadoEjecucion.APROBADA


@dataclass(frozen=True)
class Suite:
    """Un grupo reutilizable de escenarios, en un orden fijo.

    SUITE = agrupacion reusable; CORRIDA = una ejecucion historica concreta de
    esa agrupacion en un momento dado (ver `CorridaSuite`). Igual que
    `Escenario`, nunca contiene PAN ni host/puerto/timeout: solo referencia
    escenarios por `escenario_id`. `escenarios` es una tupla, no un conjunto:
    el orden de ejecucion es parte del dato, no un detalle de presentacion.
    """

    suite_id: str
    nombre: str
    descripcion: str = ""
    escenarios: tuple[str, ...] = ()
    activa: bool = True
    creado_en: datetime = field(default_factory=_ahora)
    actualizado_en: datetime = field(default_factory=_ahora)


class EstadoItemCorrida(str, Enum):
    """Resultado de UN escenario dentro de una corrida de suite.

    Deliberadamente distinto de `EstadoEjecucion` (que dice que paso con la
    transaccion) y de `EstadoEvaluacion` (pass/fail de una unica ejecucion):
    este agrega un quinto y un sexto caso que no existen a nivel de una sola
    ejecucion, porque solo tienen sentido cuando se agrupan varios escenarios:

      PASS               se ejecuto, tenia expectativas, se cumplieron
      FAIL               se ejecuto, tenia expectativas, no se cumplieron
      ERROR              no se pudo ejecutar (escenario no disponible) o fallo
                         tecnicamente de forma inesperada
      SIN_EXPECTATIVAS  se ejecuto sin problema, pero el escenario no definia
                         que esperaba -nunca se cuenta como PASS ni como FAIL
      NO_EJECUTADO       todavia no se intento; solo sobrevive si la corrida
                         se interrumpio antes de llegar a este item
    """

    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    SIN_EXPECTATIVAS = "sin_expectativas"
    NO_EJECUTADO = "no_ejecutado"


class EstadoCorridaSuite(str, Enum):
    """Ciclo de vida de una corrida: si termino de correr, no que resultado dio.

    Separado de `ResultadoGlobalSuite` por el mismo motivo que
    `EstadoEjecucion` esta separado de `EstadoEvaluacion`: una corrida puede
    estar EN_CURSO sin tener todavia ningun resultado que mostrar, y mezclar
    ambas preguntas en una sola columna reproduciria la ambiguedad que el
    Bloque 3 ya corrigio una vez.
    """

    EN_CURSO = "en_curso"
    FINALIZADA = "finalizada"


class ResultadoGlobalSuite(str, Enum):
    """Resultado agregado de una corrida ya FINALIZADA. `None` mientras EN_CURSO.

    PASS significa exactamente "todos los escenarios de la corrida tenian
    expectativas y todos cumplieron" -nunca un PASS por mezcla ni por omision-.
    Ver `domain.suites.calcular_resultado_global` para el algoritmo exacto.
    """

    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    INCOMPLETA = "incompleta"
    SIN_EXPECTATIVAS = "sin_expectativas"


@dataclass
class CorridaSuite:
    """Ejecucion historica concreta de una `Suite`. No frozen: `corrida_id` se
    asigna despues de insertar, igual que `Ejecucion.id`.

    `suite_nombre` se copia al crear la corrida -no se resuelve con un join en
    cada lectura-: renombrar la suite despues no debe alterar como luce una
    corrida ya registrada. Mismo principio que `Ejecucion.escenario_nombre`.
    """

    suite_id: str
    suite_nombre: str
    total: int
    estado: EstadoCorridaSuite = EstadoCorridaSuite.EN_CURSO
    resultado_global: ResultadoGlobalSuite | None = None
    cantidad_pass: int = 0
    cantidad_fail: int = 0
    cantidad_error: int = 0
    cantidad_sin_expectativas: int = 0
    cantidad_no_ejecutado: int = 0
    iniciada_en: datetime = field(default_factory=_ahora)
    finalizada_en: datetime | None = None
    corrida_id: int | None = None


@dataclass(frozen=True)
class ItemCorridaSuite:
    """Resultado historico de UN escenario dentro de una `CorridaSuite`.

    Autosuficiente: `evaluacion_json` es una copia LITERAL del
    `Ejecucion.evaluacion_json` que produjo ese resultado (solo para
    PASS/FAIL; `None` en cualquier otro caso) -nunca se recalcula ni se
    reconstruye desde el escenario vivo-, asi que el detalle de una corrida
    puede explicar que se esperaba, que se obtuvo y las discrepancias sin
    consultar el escenario ni ejecutar de nuevo Expected vs Actual.
    `ejecucion_id` sigue existiendo, aparte, como enlace de navegacion hacia
    el detalle ISO completo (`/historial/{id}`).
    """

    corrida_id: int
    escenario_id: str
    escenario_nombre: str
    orden: int
    resultado: EstadoItemCorrida
    ejecucion_id: int | None = None
    detalle: str | None = None
    evaluacion_json: str | None = None

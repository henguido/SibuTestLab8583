"""Modelos del dominio para el recorrido de compra 0100/0110.

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

#: Campos ISO que transportan datos de tarjeta y nunca se persisten en claro.
CAMPOS_SENSIBLES = frozenset({"2", "35"})

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
    """

    escenario_id: str
    nombre: str
    perfil: str
    mti: str
    card_id: str
    conexion_id: str
    monto: Decimal
    campos_manuales: Mapping[str, str] = field(default_factory=dict)
    activo: bool = True
    creado_en: datetime = field(default_factory=_ahora)
    actualizado_en: datetime = field(default_factory=_ahora)

    def __post_init__(self) -> None:
        object.__setattr__(self, "campos_manuales", MappingProxyType(dict(self.campos_manuales)))

    def a_datos_compra(self) -> DatosCompra:
        return DatosCompra(
            card_id=self.card_id, monto=self.monto, campos_manuales=self.campos_manuales
        )


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
    """Registro persistible de un intento de compra.

    Referencia la tarjeta por ``card_id``. No tiene campo para el PAN completo:
    los mensajes se guardan ya enmascarados.
    """

    card_id: str
    monto: Decimal
    moneda: str
    stan: str
    estado: EstadoEjecucion
    mti_solicitud: str = MTI_COMPRA
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
    creada_en: datetime = field(default_factory=_ahora)
    id: int | None = None


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

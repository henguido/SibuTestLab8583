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
    """

    card_id: str
    pan: str
    expiracion: str
    descripcion: str = ""
    sintetica: bool = True

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
    """Lo que se completa para armar una compra."""

    card_id: str
    monto: Decimal
    moneda: str = "188"
    terminal: str = "TERM0001"


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
    """El destino no respondio dentro del limite.

    No es una excepcion: es un resultado esperado del transporte, y RN-2 exige
    contarlo aparte de un rechazo explicito del switch.
    """

    limite_segundos: float


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
    """Desenlace de una ejecucion.

    TIMEOUT existe aparte de RECHAZADA porque RN-2 exige contarlos por separado.
    NO_ENVIADA corresponde a RN-4: el mensaje nunca salio.
    """

    APROBADA = "aprobada"
    RECHAZADA = "rechazada"
    INVALIDA = "invalida"
    TIMEOUT = "timeout"
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
    latencia_ms: int | None = None
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

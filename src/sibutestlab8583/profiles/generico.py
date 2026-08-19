"""Perfil generico de demostracion.

ATENCION - ORIGEN DE ESTOS CAMPOS
=================================
Los campos y su formato son una DECISION TECNICA DE ESTE PROYECTO para tener un
mensaje de compra tecnicamente utilizable en la demostracion academica.

NO son la especificacion de Visa, de Mastercard ni de ninguna otra marca, y no
deben presentarse como tales. PROYECTO.md fija el alcance y las reglas de negocio
pero no define campos ISO; ante esa ausencia se eligio el conjunto minimo descrito
abajo. Los perfiles de marca solo se implementaran cuando existan en el proyecto
los documentos autorizados que definan esos formatos.

Un PerfilDeMarca define formato, codificacion y campos obligatorios por MTI. NO
define que codigo cuenta como aprobado: eso es CatalogoDeRespuestas, un eje
independiente.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping

from ..domain.modelos import MTI_COMPRA, MTI_RESPUESTA_COMPRA

NOMBRE_PERFIL_GENERICO = "generico"


@dataclass(frozen=True)
class PerfilDeMarca:
    """Formato ISO y campos obligatorios por MTI.

    ``especificacion`` es lo que se le entrega a pyiso8583 tal cual; el codec la
    recibe como parametro y por eso nunca necesita saber a que marca corresponde.
    """

    nombre: str
    especificacion: Mapping[str, Mapping[str, Any]]
    obligatorios_por_mti: Mapping[str, frozenset[str]]

    def __post_init__(self) -> None:
        object.__setattr__(self, "especificacion", MappingProxyType(dict(self.especificacion)))
        object.__setattr__(
            self, "obligatorios_por_mti", MappingProxyType(dict(self.obligatorios_por_mti))
        )

    def soporta(self, mti: str) -> bool:
        return mti in self.obligatorios_por_mti

    def obligatorios(self, mti: str) -> frozenset[str]:
        """Campos exigidos para ese MTI. Alimenta RN-4, antes de codificar."""
        if mti not in self.obligatorios_por_mti:
            raise ValueError(f"el perfil {self.nombre!r} no soporta el MTI {mti!r}")
        return self.obligatorios_por_mti[mti]


def _fijo(largo: int, descripcion: str) -> dict[str, Any]:
    return {
        "data_enc": "ascii",
        "len_enc": "ascii",
        "len_type": 0,
        "max_len": largo,
        "desc": descripcion,
    }


def _llvar(maximo: int, descripcion: str) -> dict[str, Any]:
    return {
        "data_enc": "ascii",
        "len_enc": "ascii",
        "len_type": 2,
        "max_len": maximo,
        "desc": descripcion,
    }


# Especificacion en ASCII, con bitmap tambien en ASCII para que el mensaje sea
# legible en el isoscopio durante la demostracion. Solo incluye campos que el
# recorrido de compra 0100/0110 usa.
ESPECIFICACION_GENERICA: dict[str, dict[str, Any]] = {
    "h": _fijo(0, "Sin cabecera"),
    "t": _fijo(4, "Tipo de mensaje (MTI)"),
    "p": _fijo(16, "Bitmap primario"),
    "2": _llvar(19, "Numero de tarjeta (PAN)"),
    "3": _fijo(6, "Codigo de proceso"),
    "4": _fijo(12, "Monto de la transaccion"),
    "7": _fijo(10, "Fecha y hora de transmision (MMDDhhmmss)"),
    "11": _fijo(6, "Numero de trazabilidad (STAN)"),
    "12": _fijo(6, "Hora local (hhmmss)"),
    "13": _fijo(4, "Fecha local (MMDD)"),
    "14": _fijo(4, "Fecha de vencimiento (AAMM)"),
    "22": _fijo(3, "Modo de captura en el punto de venta"),
    "37": _fijo(12, "Numero de referencia de recuperacion"),
    "38": _fijo(6, "Codigo de autorizacion"),
    "39": _fijo(2, "Codigo de respuesta"),
    "41": _fijo(8, "Identificador del terminal"),
    "49": _fijo(3, "Codigo de moneda (ISO 4217 numerico)"),
}

# Obligatorios de la solicitud de compra: lo minimo para que el mensaje describa
# una compra concreta (que tarjeta, cuanto, en que moneda, en que terminal, con
# que trazabilidad).
OBLIGATORIOS_0100 = frozenset({"2", "3", "4", "7", "11", "14", "22", "41", "49"})

# Obligatorios de la respuesta: el codigo de respuesta mas los campos que deben
# volver iguales para poder correlacionar y comprobar la respuesta (RN-3).
OBLIGATORIOS_0110 = frozenset({"3", "4", "7", "11", "39", "41"})

#: Codigo de proceso que identifica una compra en este perfil generico.
CODIGO_PROCESO_COMPRA = "000000"

PERFIL_GENERICO = PerfilDeMarca(
    nombre=NOMBRE_PERFIL_GENERICO,
    especificacion=ESPECIFICACION_GENERICA,
    obligatorios_por_mti={
        MTI_COMPRA: OBLIGATORIOS_0100,
        MTI_RESPUESTA_COMPRA: OBLIGATORIOS_0110,
    },
)


def perfil_activo() -> PerfilDeMarca:
    """Perfil en uso. Hoy solo existe el generico."""
    return PERFIL_GENERICO

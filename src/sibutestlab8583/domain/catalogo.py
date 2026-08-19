"""Catalogo de codigos de respuesta.

Determina que codigo del campo 39 cuenta como aprobado (RN-1). Es un eje de
configuracion INDEPENDIENTE del PerfilDeMarca, que define formato y campos.
Nunca deben acoplarse.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Iterable, Mapping

NOMBRE_CATALOGO_GENERICO = "generico"


@dataclass(frozen=True)
class CodigoRespuesta:
    codigo: str
    descripcion: str
    aprobado: bool


@dataclass(frozen=True)
class CatalogoDeRespuestas:
    nombre: str
    codigos: Mapping[str, CodigoRespuesta]

    def __post_init__(self) -> None:
        object.__setattr__(self, "codigos", MappingProxyType(dict(self.codigos)))

    @classmethod
    def desde(cls, nombre: str, codigos: Iterable[CodigoRespuesta]) -> CatalogoDeRespuestas:
        return cls(nombre=nombre, codigos={c.codigo: c for c in codigos})

    def conoce(self, codigo: str) -> bool:
        return codigo in self.codigos

    def es_aprobado(self, codigo: str) -> bool:
        """RN-1: aprobado es lo que ESTE catalogo marca como aprobado.

        Un codigo desconocido nunca se aprueba.
        """
        entrada = self.codigos.get(codigo)
        return entrada is not None and entrada.aprobado

    def descripcion(self, codigo: str) -> str:
        entrada = self.codigos.get(codigo)
        return entrada.descripcion if entrada else "codigo desconocido"


# Catalogo generico aprobado para la demostracion academica (PROYECTO.md seccion 4).
# Solo 00 es una aprobacion; los otros cinco son rechazos con distinto motivo.
# NO es el catalogo de ninguna marca.
CATALOGO_GENERICO = CatalogoDeRespuestas.desde(
    NOMBRE_CATALOGO_GENERICO,
    [
        CodigoRespuesta("00", "Aprobada", aprobado=True),
        CodigoRespuesta("05", "No autorizada", aprobado=False),
        CodigoRespuesta("14", "Tarjeta invalida", aprobado=False),
        CodigoRespuesta("51", "Fondos insuficientes", aprobado=False),
        CodigoRespuesta("54", "Tarjeta vencida", aprobado=False),
        CodigoRespuesta("94", "Transaccion duplicada", aprobado=False),
    ],
)

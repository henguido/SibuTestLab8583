"""Raiz de composicion: el unico lugar donde se arma la infraestructura real.

Aqui se juntan perfil, catalogo, codec, framing, transporte y repositorios. La
web depende de este modulo y **no crea infraestructura dentro de sus endpoints**;
asi la capa de interfaz no necesita importar `aiosqlite`, `pyiso8583` ni
`asyncio`.

No hay estado global mutable: se construye una `Composicion` y se pasa. Las
pruebas construyen la suya con una ruta temporal, o la sustituyen entera.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .adapters.host_simulado import HostSimulado
from .adapters.iso8583.codec import CodecIso8583
from .adapters.persistence.esquema import ruta_base_datos
from .adapters.persistence.sqlite_repos import (
    RepositorioEjecucionesSQLite,
    RepositorioTarjetasSQLite,
)
from .adapters.transporte.framing_demo import FramingDemostracion
from .adapters.transporte.tcp import TIEMPO_LIMITE_POR_DEFECTO, TransporteTcp
from .application.consultas import ServicioConsultas
from .application.orquestador import Orquestador
from .domain.catalogo import CATALOGO_GENERICO
from .domain.modelos import DestinoTcp
from .profiles.generico import CODIGO_PROCESO_COMPRA, perfil_activo

VARIABLE_HOST = "SIBU_HOST_DESTINO"
VARIABLE_PUERTO = "SIBU_PUERTO_DESTINO"
VARIABLE_TIEMPO_LIMITE = "SIBU_TIEMPO_LIMITE"

HOST_POR_DEFECTO = "127.0.0.1"
PUERTO_POR_DEFECTO = 8583


@dataclass(frozen=True)
class Configuracion:
    """Todo lo configurable del despliegue, en un solo objeto."""

    ruta_base_datos: Path
    host_destino: str = HOST_POR_DEFECTO
    puerto_destino: int = PUERTO_POR_DEFECTO
    tiempo_limite: float = TIEMPO_LIMITE_POR_DEFECTO

    @classmethod
    def desde_entorno(cls) -> "Configuracion":
        return cls(
            ruta_base_datos=ruta_base_datos(),
            host_destino=os.environ.get(VARIABLE_HOST, HOST_POR_DEFECTO),
            puerto_destino=int(os.environ.get(VARIABLE_PUERTO, PUERTO_POR_DEFECTO)),
            tiempo_limite=float(
                os.environ.get(VARIABLE_TIEMPO_LIMITE, TIEMPO_LIMITE_POR_DEFECTO)
            ),
        )

    @property
    def destino_por_defecto(self) -> DestinoTcp:
        return DestinoTcp(host=self.host_destino, puerto=self.puerto_destino)


class Composicion:
    """Fabrica de piezas ya cableadas."""

    def __init__(self, configuracion: Configuracion) -> None:
        self.configuracion = configuracion
        self._perfil = perfil_activo()
        self._catalogo = CATALOGO_GENERICO
        self._codec = CodecIso8583()
        self._framing = FramingDemostracion()
        self._tarjetas = RepositorioTarjetasSQLite(configuracion.ruta_base_datos)
        self._ejecuciones = RepositorioEjecucionesSQLite(configuracion.ruta_base_datos)

    @property
    def consultas(self) -> ServicioConsultas:
        return ServicioConsultas(self._tarjetas, self._ejecuciones)

    @property
    def descripciones_de_campos(self) -> Mapping[str, str]:
        """Numero de campo -> descripcion, tomada del perfil activo.

        La interfaz la usa para rotular el isoscopio de la solicitud sin
        necesidad de conocer el perfil.
        """
        return {
            numero: definicion.get("desc", f"Campo {numero}")
            for numero, definicion in self._perfil.especificacion.items()
            if numero.isdigit()
        }

    def orquestador(self, destino: DestinoTcp) -> Orquestador:
        """Un orquestador apuntando al destino indicado.

        Se construye por peticion porque el destino lo elige el usuario en el
        formulario. Es cableado barato: los repositorios abren su conexion por
        operacion.
        """
        return Orquestador(
            codec=self._codec,
            perfil=self._perfil,
            catalogo=self._catalogo,
            transporte=TransporteTcp(
                self._framing, tiempo_limite=self.configuracion.tiempo_limite
            ),
            repositorio_ejecuciones=self._ejecuciones,
            repositorio_tarjetas=self._tarjetas,
            destino=destino,
            codigo_proceso=CODIGO_PROCESO_COMPRA,
            tiempo_limite=self.configuracion.tiempo_limite,
        )

    def host_simulado(self, codigo_respuesta: str = "00") -> HostSimulado:
        """Host de demostracion, para el comando `sibu-host-demo`.

        La aplicacion web NO lo levanta: la arquitectura lo mantiene como
        proceso aparte y la demostracion usa dos terminales.
        """
        return HostSimulado(
            self._codec, self._perfil, self._framing, codigo_respuesta=codigo_respuesta
        )

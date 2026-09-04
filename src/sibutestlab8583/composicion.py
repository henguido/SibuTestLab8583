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
    GeneradorStanSQLite,
    RepositorioCatalogosSQLite,
    RepositorioDestinosSQLite,
    RepositorioEjecucionesSQLite,
    RepositorioEscenariosSQLite,
    RepositorioTarjetasSQLite,
)
from .adapters.transporte.framing_demo import FramingDemostracion
from .adapters.transporte.tcp import (
    TIEMPO_LIMITE_POR_DEFECTO,
    TransporteTcp,
    VerificadorDeConexionTcp,
)
from .application.consultas import ServicioConsultas
from .application.conexiones import ServicioConexiones
from .application.escenarios import ServicioEscenarios
from .application.orquestador import Orquestador
from .application.tarjetas import ServicioTarjetas
from .domain.catalogo import NOMBRE_CATALOGO_GENERICO
from .domain.modelos import DestinoTcp
from .profiles.generico import perfil_activo

VARIABLE_HOST = "SIBU_HOST_DESTINO"
VARIABLE_PUERTO = "SIBU_PUERTO_DESTINO"
VARIABLE_TIEMPO_LIMITE = "SIBU_TIEMPO_LIMITE"
VARIABLE_CATALOGO = "SIBU_CATALOGO"

HOST_POR_DEFECTO = "127.0.0.1"
PUERTO_POR_DEFECTO = 8583


@dataclass(frozen=True)
class Configuracion:
    """Todo lo configurable del despliegue, en un solo objeto."""

    ruta_base_datos: Path
    host_destino: str = HOST_POR_DEFECTO
    puerto_destino: int = PUERTO_POR_DEFECTO
    tiempo_limite: float = TIEMPO_LIMITE_POR_DEFECTO
    catalogo_activo: str = NOMBRE_CATALOGO_GENERICO

    @classmethod
    def desde_entorno(cls) -> "Configuracion":
        return cls(
            ruta_base_datos=ruta_base_datos(),
            host_destino=os.environ.get(VARIABLE_HOST, HOST_POR_DEFECTO),
            puerto_destino=int(os.environ.get(VARIABLE_PUERTO, PUERTO_POR_DEFECTO)),
            tiempo_limite=float(
                os.environ.get(VARIABLE_TIEMPO_LIMITE, TIEMPO_LIMITE_POR_DEFECTO)
            ),
            catalogo_activo=os.environ.get(VARIABLE_CATALOGO, NOMBRE_CATALOGO_GENERICO),
        )

    @property
    def destino_por_defecto(self) -> DestinoTcp:
        return DestinoTcp(host=self.host_destino, puerto=self.puerto_destino)


class Composicion:
    """Fabrica de piezas ya cableadas."""

    def __init__(self, configuracion: Configuracion) -> None:
        self.configuracion = configuracion
        self._perfil = perfil_activo()
        self._codec = CodecIso8583()
        self._framing = FramingDemostracion()
        self._tarjetas = RepositorioTarjetasSQLite(configuracion.ruta_base_datos)
        self._ejecuciones = RepositorioEjecucionesSQLite(configuracion.ruta_base_datos)
        self._catalogos = RepositorioCatalogosSQLite(configuracion.ruta_base_datos)
        self._destinos = RepositorioDestinosSQLite(configuracion.ruta_base_datos)
        self._escenarios = RepositorioEscenariosSQLite(configuracion.ruta_base_datos)
        self._verificador_conexion = VerificadorDeConexionTcp()
        # El STAN vive en la base, no en memoria: debe seguir siendo unico
        # aunque el orquestador se construya de nuevo en cada peticion.
        self._stan = GeneradorStanSQLite(configuracion.ruta_base_datos)

    @property
    def consultas(self) -> ServicioConsultas:
        return ServicioConsultas(self._tarjetas, self._ejecuciones)

    @property
    def administracion_tarjetas(self) -> ServicioTarjetas:
        return ServicioTarjetas(self._tarjetas)

    @property
    def administracion_conexiones(self) -> ServicioConexiones:
        return ServicioConexiones(self._destinos, self._verificador_conexion)

    @property
    def administracion_escenarios(self) -> ServicioEscenarios:
        return ServicioEscenarios(self._escenarios, self._tarjetas, self._destinos, self._perfil)

    @property
    def perfil(self):
        """Perfil de marca activo, de solo lectura para la web.

        No es una fuga de la infraestructura: la web ya recibía datos
        derivados del perfil (`descripciones_de_campos`); esto solo extiende
        esa misma consulta a qué campos son editables, derivados o
        automáticos para un MTI, que es información de producto, no un
        detalle de codificación.
        """
        return self._perfil

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

    async def orquestador(
        self, destino: DestinoTcp, *, tiempo_limite: float | None = None
    ) -> Orquestador:
        """Un orquestador apuntando al destino indicado.

        `tiempo_limite` es el de la conexion administrada elegida (cada una
        lleva el suyo); si no se indica, se usa el limite global de
        `Configuracion` -asi las llamadas que todavia no resuelven una
        conexion (el host simulado de demostracion, por ejemplo) siguen
        funcionando sin cambios-.

        Se construye por peticion porque el destino lo elige el usuario en el
        formulario. Es cableado barato: los repositorios abren su conexion por
        operacion. El catalogo de respuestas se lee de la base en cada
        construccion, y no se cachea en la instancia: editar la tabla
        `codigos_respuesta` debe reflejarse sin reiniciar la aplicacion.
        """
        limite = self.configuracion.tiempo_limite if tiempo_limite is None else tiempo_limite
        catalogo = await self._catalogos.catalogo_respuestas(self.configuracion.catalogo_activo)
        return Orquestador(
            codec=self._codec,
            perfil=self._perfil,
            catalogo=catalogo,
            transporte=TransporteTcp(self._framing, tiempo_limite=limite),
            repositorio_ejecuciones=self._ejecuciones,
            repositorio_tarjetas=self._tarjetas,
            generador_stan=self._stan,
            destino=destino,
            tiempo_limite=limite,
        )

    def host_simulado(self, codigo_respuesta: str = "00") -> HostSimulado:
        """Host de demostracion, para el comando `sibu-host-demo`.

        La aplicacion web NO lo levanta: la arquitectura lo mantiene como
        proceso aparte y la demostracion usa dos terminales.
        """
        return HostSimulado(
            self._codec, self._perfil, self._framing, codigo_respuesta=codigo_respuesta
        )

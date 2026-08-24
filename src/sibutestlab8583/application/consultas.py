"""Consultas de lectura para la interfaz.

Existe para que la web no toque repositorios ni adaptadores. En particular,
`tarjetas()` devuelve un objeto que **no tiene** el PAN completo: aunque la
plantilla quisiera mostrarlo, no lo tiene disponible. Es la forma mas barata de
garantizar que el navegador nunca lo reciba, mejor que confiar en que cada
plantilla se acuerde de enmascarar.

Esto no impide el procesamiento: el orquestador obtiene el PAN completo por su
cuenta, del repositorio de tarjetas, para construir el 0100 y transmitirlo. La
restriccion es sobre lo que llega al navegador, no sobre lo que el servidor
puede usar.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..domain.modelos import Ejecucion
from ..domain.puertos import RepositorioEjecuciones, RepositorioTarjetas
from .serializacion import MensajeSerializado, interpretar


@dataclass(frozen=True)
class TarjetaListada:
    """Lo unico que la interfaz necesita saber de una tarjeta."""

    card_id: str
    pan_enmascarado: str
    descripcion: str
    sintetica: bool


@dataclass(frozen=True)
class DetalleEjecucion:
    """Una ejecucion pasada con sus dos mensajes ya interpretados.

    El trabajo de decidir entre la representacion estructurada y la de texto
    heredada se hace aqui, no en la web ni en la plantilla: es una regla de
    lectura de datos persistidos, no de presentacion.

    `solicitud` y `respuesta` son siempre `MensajeSerializado`, incluso cuando no
    hay nada que leer: en ese caso llegan con `origen` ausente. Devolver el mismo
    tipo en todos los casos evita que la plantilla tenga que distinguir entre
    None y vacio.
    """

    ejecucion: Ejecucion
    solicitud: MensajeSerializado
    respuesta: MensajeSerializado


class ServicioConsultas:
    def __init__(
        self,
        repositorio_tarjetas: RepositorioTarjetas,
        repositorio_ejecuciones: RepositorioEjecuciones,
    ) -> None:
        self._tarjetas = repositorio_tarjetas
        self._ejecuciones = repositorio_ejecuciones

    async def tarjetas(self) -> Sequence[TarjetaListada]:
        """Tarjetas disponibles, siempre enmascaradas."""
        return [
            TarjetaListada(
                card_id=t.card_id,
                pan_enmascarado=t.pan_enmascarado,
                descripcion=t.descripcion,
                sintetica=t.sintetica,
            )
            for t in await self._tarjetas.listar()
        ]

    async def ejecuciones_recientes(self, limite: int = 20) -> Sequence[Ejecucion]:
        return await self._ejecuciones.listar(limite)

    async def detalle_ejecucion(self, id_ejecucion: int) -> DetalleEjecucion | None:
        """Una ejecucion pasada, con sus mensajes interpretados.

        Devuelve `None` si no existe, para que la web decida como presentarlo;
        lanzar aqui obligaria a la capa de interfaz a capturar una excepcion para
        algo que es un resultado normal: un identificador que no esta.

        La prioridad entre representaciones la resuelve `interpretar()`: usa la
        estructurada cuando existe y cae al texto heredado cuando no. Las filas
        anteriores a la persistencia estructurada se leen igual, y quedan
        marcadas como no demostrablemente fieles.
        """
        ejecucion = await self._ejecuciones.obtener(id_ejecucion)
        if ejecucion is None:
            return None
        return DetalleEjecucion(
            ejecucion=ejecucion,
            solicitud=interpretar(
                ejecucion.solicitud_json, ejecucion.solicitud_enmascarada
            ),
            respuesta=interpretar(
                ejecucion.respuesta_json, ejecucion.respuesta_enmascarada
            ),
        )

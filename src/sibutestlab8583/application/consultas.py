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


@dataclass(frozen=True)
class TarjetaListada:
    """Lo unico que la interfaz necesita saber de una tarjeta."""

    card_id: str
    pan_enmascarado: str
    descripcion: str
    sintetica: bool


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

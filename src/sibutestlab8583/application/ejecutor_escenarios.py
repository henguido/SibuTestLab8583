"""Reejecucion de un escenario guardado: una unica capacidad reutilizada tanto
por "Ejecutar" en la pantalla de escenarios como por `CorredorDeSuites`.

Antes de este modulo, `POST /escenarios/{id}/ejecutar` era la unica
implementacion de "escenario_id -> ejecucion real", y el Bloque 4 hubiera
tenido que reimplementarla para correr una suite. En cambio, ambos
consumidores llaman a `EjecutorDeEscenarios.ejecutar`, y la logica de
resolucion (obtener, validar activo, diagnosticar, resolver conexion, armar
`DatosCompra`, construir el `Orquestador` con el timeout de esa conexion)
vive en un solo lugar.

No reimplementa nada de RN-1..RN-4 ni de Expected vs Actual: arma los datos y
delega en `Orquestador.ejecutar_compra`, exactamente como ya hacia la ruta.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from ..domain.modelos import DatosCompra, DestinoTcp, ResultadoCompra
from .conexiones import ServicioConexiones
from .escenarios import EscenarioNoEncontrado, ServicioEscenarios
from .orquestador import Orquestador


class EscenarioNoEjecutable(Exception):
    """El escenario existe pero no se puede ejecutar ahora: esta inactivo, o
    su diagnostico (tarjeta/conexion no disponible, incompatible con el
    perfil actual) lo bloquea. El mensaje es siempre texto seguro, sin datos
    de tarjeta ni detalles tecnicos.
    """


class EjecutorDeEscenarios:
    """`escenario_id` -> una ejecucion real, con toda la resolucion que hace
    falta antes de llamar a `Orquestador.ejecutar_compra`.
    """

    def __init__(
        self,
        administracion_escenarios: ServicioEscenarios,
        administracion_conexiones: ServicioConexiones,
        fabrica_orquestador: Callable[[DestinoTcp, float], Awaitable[Orquestador]],
    ) -> None:
        self._escenarios = administracion_escenarios
        self._conexiones = administracion_conexiones
        self._fabrica_orquestador = fabrica_orquestador

    async def ejecutar(self, escenario_id: str) -> ResultadoCompra:
        escenario = await self._escenarios.obtener(escenario_id)
        if escenario is None:
            raise EscenarioNoEncontrado(escenario_id)

        if not escenario.activo:
            raise EscenarioNoEjecutable(f"el escenario {escenario_id!r} está inactivo")

        diagnostico = await self._escenarios.diagnosticar(escenario)
        if diagnostico.bloqueado:
            raise EscenarioNoEjecutable(
                f"el escenario {escenario_id!r} no está disponible para ejecutarse"
            )

        conexion = await self._conexiones.obtener_activa(escenario.conexion_id)
        destino = DestinoTcp(host=conexion.host, puerto=conexion.puerto)
        datos = DatosCompra(
            card_id=escenario.card_id,
            monto=escenario.monto,
            campos_manuales=escenario.campos_manuales,
        )
        orquestador = await self._fabrica_orquestador(destino, conexion.timeout)
        return await orquestador.ejecutar_compra(
            datos,
            escenario_id=escenario.escenario_id,
            escenario_nombre=escenario.nombre,
            expectativas=escenario.expectativas,
        )

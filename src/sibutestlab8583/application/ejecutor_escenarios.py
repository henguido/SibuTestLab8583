"""Reejecucion de un escenario guardado: una unica capacidad reutilizada tanto
por "Ejecutar" en la pantalla de escenarios como por `CorredorDeSuites`.

Antes de este modulo, `POST /escenarios/{id}/ejecutar` era la unica
implementacion de "escenario_id -> ejecucion real", y el Bloque 4 hubiera
tenido que reimplementarla para correr una suite. En cambio, ambos
consumidores llaman a `EjecutorDeEscenarios.ejecutar`, y la logica de
resolucion (obtener, validar activo, diagnosticar, resolver conexion, armar
los datos de la operacion, construir el `Orquestador` con el timeout de esa
conexion) vive en un solo lugar.

No reimplementa nada de RN-1..RN-4 ni de Expected vs Actual: arma los datos y
delega en el metodo del `Orquestador` que corresponda, exactamente como ya
hacia la ruta para compra.

MULTI-MTI (B3, 2026-09-13): `_ADAPTADORES_POR_MTI` es una tabla pequena,
MTI -> (constructor de datos, nombre del metodo del Orquestador a llamar) -
nunca un `if escenario.mti == ...` que crezca sin limite. Agregar una
operacion nueva es agregar una entrada a esta tabla, no una rama mas.
`CorredorDeSuites` no cambia una linea: solo conoce `escenario_id ->
ResultadoCompra`, nunca `DatosCompra`/`DatosEcho` directamente.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from ..domain.modelos import (
    DatosCompra,
    DatosCompraFinanciera,
    DatosEcho,
    DestinoTcp,
    MTI_COMPRA,
    MTI_COMPRA_FINANCIERA,
    MTI_ECHO,
    ResultadoCompra,
)
from .conexiones import ServicioConexiones
from .escenarios import EscenarioAdministrado, EscenarioNoEncontrado, ServicioEscenarios
from .orquestador import Orquestador


def _datos_compra(escenario: EscenarioAdministrado) -> DatosCompra:
    return DatosCompra(
        card_id=escenario.card_id, monto=escenario.monto, campos_manuales=escenario.campos_manuales
    )


def _datos_echo(escenario: EscenarioAdministrado) -> DatosEcho:
    return DatosEcho(campos_manuales=escenario.campos_manuales)


def _datos_compra_financiera(escenario: EscenarioAdministrado) -> DatosCompraFinanciera:
    return DatosCompraFinanciera(
        card_id=escenario.card_id, monto=escenario.monto, campos_manuales=escenario.campos_manuales
    )


#: MTI -> (constructor de `DatosX` a partir del escenario, nombre del metodo
#: del Orquestador que lo ejecuta). La unica fuente de "que operacion sabe
#: reejecutar el sistema hoy"; un MTI que no este aqui revienta con un
#: mensaje explicito, nunca con un intento silencioso de tratarlo como compra.
_ADAPTADORES_POR_MTI: dict[str, tuple[Callable[[EscenarioAdministrado], object], str]] = {
    MTI_COMPRA: (_datos_compra, "ejecutar_compra"),
    MTI_ECHO: (_datos_echo, "ejecutar_network_echo"),
    MTI_COMPRA_FINANCIERA: (_datos_compra_financiera, "ejecutar_compra_financiera"),
}


class OperacionNoSoportada(Exception):
    """El escenario tiene un MTI para el que todavia no hay una operacion de
    ejecucion registrada en `_ADAPTADORES_POR_MTI`."""


class EscenarioNoEjecutable(Exception):
    """El escenario existe pero no se puede ejecutar ahora: esta inactivo, o
    su diagnostico (tarjeta/conexion no disponible, incompatible con el
    perfil actual) lo bloquea. El mensaje es siempre texto seguro, sin datos
    de tarjeta ni detalles tecnicos.
    """


class EjecutorDeEscenarios:
    """`escenario_id` -> una ejecucion real, con toda la resolucion que hace
    falta antes de llamar al metodo del `Orquestador` que corresponda a la
    operacion de ese escenario (ver `_ADAPTADORES_POR_MTI`).
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

        adaptador = _ADAPTADORES_POR_MTI.get(escenario.mti)
        if adaptador is None:
            raise OperacionNoSoportada(
                f"el escenario {escenario_id!r} usa el MTI {escenario.mti!r}, que todavía no "
                "tiene una operación de ejecución soportada"
            )
        construir_datos, nombre_metodo = adaptador

        conexion = await self._conexiones.obtener_activa(escenario.conexion_id)
        destino = DestinoTcp(host=conexion.host, puerto=conexion.puerto)
        datos = construir_datos(escenario)
        orquestador = await self._fabrica_orquestador(destino, conexion.timeout)
        metodo = getattr(orquestador, nombre_metodo)
        return await metodo(
            datos,
            escenario_id=escenario.escenario_id,
            escenario_nombre=escenario.nombre,
            expectativas=escenario.expectativas,
        )

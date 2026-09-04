"""Una tarjeta desactivada no debe poder usarse para una ejecucion nueva.

Dos puntos de aplicacion independientes, y esta prueba cubre ambos: el nivel
UI (`ServicioConsultas.tarjetas()`, que alimenta el selector del constructor)
y el nivel de servidor (`Orquestador.ejecutar_compra`, que rechaza incluso un
`card_id` recibido directamente y no solo el que la UI ofrecio). El segundo es
el que de verdad importa: sin el, bastaria con enviar un `card_id` inactivo a
mano para saltarse el primero.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from conftest import TransporteFalso, construir_orquestador
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO
from sibutestlab8583.adapters.persistence.sqlite_repos import RepositorioTarjetasSQLite
from sibutestlab8583.application.consultas import ServicioConsultas
from sibutestlab8583.application.orquestador import TarjetaDesconocida
from sibutestlab8583.application.tarjetas import ServicioTarjetas
from sibutestlab8583.domain.modelos import DatosCompra


async def test_una_tarjeta_desactivada_no_aparece_en_la_lista_de_seleccion(base):
    await ServicioTarjetas(RepositorioTarjetasSQLite(base)).cambiar_estado(
        CARD_ID_DEMO, activa=False
    )
    consultas = ServicioConsultas(RepositorioTarjetasSQLite(base), repositorio_ejecuciones=None)
    ids = [t.card_id for t in await consultas.tarjetas()]
    assert CARD_ID_DEMO not in ids


async def test_desactivar_no_borra_la_tarjeta_solo_la_retira_de_la_seleccion(base):
    repo = RepositorioTarjetasSQLite(base)
    await ServicioTarjetas(repo).cambiar_estado(CARD_ID_DEMO, activa=False)
    assert await repo.obtener(CARD_ID_DEMO) is not None


async def test_ejecutar_compra_con_una_tarjeta_desactivada_se_rechaza(base):
    """El rechazo aplica aunque el card_id llegue directo, sin pasar por la UI."""
    await ServicioTarjetas(RepositorioTarjetasSQLite(base)).cambiar_estado(
        CARD_ID_DEMO, activa=False
    )
    orquestador = construir_orquestador(base, TransporteFalso(codigo="00"))
    with pytest.raises(TarjetaDesconocida):
        await orquestador.ejecutar_compra(
            DatosCompra(card_id=CARD_ID_DEMO, monto=Decimal("10.00"))
        )


async def test_ejecutar_compra_con_una_tarjeta_desactivada_no_toca_el_transporte(base):
    await ServicioTarjetas(RepositorioTarjetasSQLite(base)).cambiar_estado(
        CARD_ID_DEMO, activa=False
    )
    transporte = TransporteFalso(codigo="00")
    orquestador = construir_orquestador(base, transporte)
    with pytest.raises(TarjetaDesconocida):
        await orquestador.ejecutar_compra(
            DatosCompra(card_id=CARD_ID_DEMO, monto=Decimal("10.00"))
        )
    assert not transporte.fue_invocado

"""Secuencia del numero de trazabilidad (campo 11).

Cubre el defecto corregido: el STAN se repetia en cada peticion porque el
contador nacia dentro de cada `Orquestador`, y la web construye uno por
peticion. Las pruebas usan la implementacion SQLite real; un doble escondería
justamente el problema que se esta comprobando.
"""

from __future__ import annotations

import asyncio
import sqlite3
from decimal import Decimal

import pytest

from conftest import TransporteFalso, construir_orquestador
from sibutestlab8583.adapters.persistence.esquema import (
    CARD_ID_DEMO,
    SECUENCIA_STAN,
    inicializar,
)
from sibutestlab8583.adapters.persistence.sqlite_repos import (
    GeneradorStanSQLite,
    RepositorioEjecucionesSQLite,
    SecuenciaNoInicializada,
)
from sibutestlab8583.domain.modelos import LARGO_STAN, STAN_MAXIMO, DatosCompra


# ------------------------------------------------------ el generador solo ----


async def test_entrega_valores_distintos_y_crecientes(base):
    generador = GeneradorStanSQLite(base)
    obtenidos = [await generador.siguiente() for _ in range(5)]
    assert obtenidos == ["000001", "000002", "000003", "000004", "000005"]


async def test_siempre_seis_digitos(base):
    generador = GeneradorStanSQLite(base)
    for _ in range(3):
        stan = await generador.siguiente()
        assert len(stan) == LARGO_STAN
        assert stan.isdigit()


async def test_una_instancia_nueva_continua_la_secuencia(base):
    """El estado vive en la base, no en el objeto."""
    assert await GeneradorStanSQLite(base).siguiente() == "000001"
    assert await GeneradorStanSQLite(base).siguiente() == "000002"
    # Tercera instancia, misma base: sigue avanzando.
    assert await GeneradorStanSQLite(base).siguiente() == "000003"


async def test_la_inicializacion_repetida_no_reinicia_la_secuencia(base):
    generador = GeneradorStanSQLite(base)
    await generador.siguiente()
    await generador.siguiente()

    await inicializar(base)  # segunda vez, como haria sibu-init-db

    assert await generador.siguiente() == "000003", "sibu-init-db no debe reiniciar el STAN"
    with sqlite3.connect(base) as conexion:
        filas = conexion.execute(
            "SELECT COUNT(*) FROM secuencias WHERE nombre = ?", (SECUENCIA_STAN,)
        ).fetchone()[0]
    assert filas == 1, "la secuencia no debe duplicarse"


async def test_al_llegar_al_maximo_vuelve_a_empezar(base):
    """Seis digitos no alcanzan para siempre: el ciclo es explicito."""
    with sqlite3.connect(base) as conexion:
        conexion.execute(
            "UPDATE secuencias SET valor = ? WHERE nombre = ?",
            (STAN_MAXIMO - 1, SECUENCIA_STAN),
        )

    generador = GeneradorStanSQLite(base)
    assert await generador.siguiente() == str(STAN_MAXIMO)  # 999999
    assert await generador.siguiente() == "000001", "tras el maximo, reinicia el ciclo"
    assert await generador.siguiente() == "000002"


async def test_sin_secuencia_falla_con_un_mensaje_util(base):
    with sqlite3.connect(base) as conexion:
        conexion.execute("DELETE FROM secuencias WHERE nombre = ?", (SECUENCIA_STAN,))
    with pytest.raises(SecuenciaNoInicializada, match="sibu-init-db"):
        await GeneradorStanSQLite(base).siguiente()


# ------------------------------------------------------------ concurrencia ----


async def test_solicitudes_concurrentes_reciben_stan_distintos(base):
    """La prueba que el defecto original no habria superado.

    Se usa el generador SQLite real y peticiones simultaneas: si la operacion
    no fuera atomica, dos tareas leerian el mismo valor antes de escribir y
    entregarian el mismo STAN.
    """
    generador = GeneradorStanSQLite(base)
    cuantos = 25

    obtenidos = await asyncio.gather(*(generador.siguiente() for _ in range(cuantos)))

    assert len(set(obtenidos)) == cuantos, f"STAN repetidos: {sorted(obtenidos)}"
    assert sorted(obtenidos) == [str(n).rjust(LARGO_STAN, "0") for n in range(1, cuantos + 1)]


async def test_generadores_distintos_sobre_la_misma_base_no_colisionan(base):
    """Simula peticiones concurrentes, cada una con su propia composicion."""
    cuantos = 20
    obtenidos = await asyncio.gather(
        *(GeneradorStanSQLite(base).siguiente() for _ in range(cuantos))
    )
    assert len(set(obtenidos)) == cuantos, f"STAN repetidos: {sorted(obtenidos)}"


# --------------------------------------------- el recorrido de extremo a extremo


async def test_compras_consecutivas_persisten_stan_distintos(base):
    """El caso reportado: varias compras seguidas ya no comparten el STAN."""
    for monto in ("150.00", "275.50", "99.99"):
        await construir_orquestador(base, TransporteFalso(codigo="00")).ejecutar_compra(
            DatosCompra(card_id=CARD_ID_DEMO, monto=Decimal(monto))
        )

    guardadas = await RepositorioEjecucionesSQLite(base).listar()
    stans = [e.stan for e in guardadas]

    assert len(stans) == 3
    assert len(set(stans)) == 3, f"las compras comparten STAN: {stans}"
    assert all(len(s) == LARGO_STAN for s in stans)


async def test_el_stan_viaja_en_el_campo_11_de_la_solicitud(base):
    """No basta con generarlo: tiene que llegar al mensaje."""
    transporte = TransporteFalso(codigo="00")
    resultado = await construir_orquestador(base, transporte).ejecutar_compra(
        DatosCompra(card_id=CARD_ID_DEMO, monto=Decimal("10.00"))
    )
    assert resultado.solicitud.campos["11"] == resultado.ejecucion.stan

"""La base se inicializa, los repositorios funcionan y el PAN no se duplica."""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from sibutestlab8583.adapters.persistence.esquema import (
    CARD_ID_DEMO,
    PAN_DEMO,
    inicializar,
)
from sibutestlab8583.adapters.persistence.sqlite_repos import (
    RepositorioCatalogosSQLite,
    RepositorioEjecucionesSQLite,
    RepositorioTarjetasSQLite,
)
from sibutestlab8583.domain.catalogo import NOMBRE_CATALOGO_GENERICO
from sibutestlab8583.domain.datos_sinteticos import pan_sintetico
from sibutestlab8583.domain.modelos import Ejecucion, EstadoEjecucion, TarjetaPrueba


@pytest.fixture
async def base(tmp_path):
    """Base recien inicializada, aislada por prueba."""
    return await inicializar(tmp_path / "prueba.db")


async def test_la_inicializacion_crea_las_tablas(base):
    with sqlite3.connect(base) as conexion:
        tablas = {
            f[0] for f in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert {"tarjetas_prueba", "codigos_respuesta", "ejecuciones"} <= tablas


async def test_la_inicializacion_es_idempotente(tmp_path):
    ruta = tmp_path / "repetida.db"
    await inicializar(ruta)

    tarjetas = RepositorioTarjetasSQLite(ruta)
    await tarjetas.guardar(
        TarjetaPrueba(card_id="CONSERVAR", pan=pan_sintetico("2222"), expiracion="3012")
    )

    # Segunda ejecucion: no debe fallar ni borrar lo anterior.
    await inicializar(ruta)

    assert await tarjetas.obtener("CONSERVAR") is not None
    catalogo = await RepositorioCatalogosSQLite(ruta).catalogo_respuestas(
        NOMBRE_CATALOGO_GENERICO
    )
    assert len(catalogo.codigos) == 6


async def test_el_catalogo_sembrado_coincide_con_el_aprobado(base):
    catalogo = await RepositorioCatalogosSQLite(base).catalogo_respuestas(
        NOMBRE_CATALOGO_GENERICO
    )
    assert set(catalogo.codigos) == {"00", "05", "14", "51", "54", "94"}
    assert catalogo.es_aprobado("00")
    assert not catalogo.es_aprobado("51")


async def test_la_tarjeta_de_demostracion_es_sintetica(base):
    tarjeta = await RepositorioTarjetasSQLite(base).obtener(CARD_ID_DEMO)
    assert tarjeta is not None
    assert tarjeta.sintetica
    assert tarjeta.pan_enmascarado == "************6666"


async def test_guardar_y_recuperar_una_tarjeta(base):
    repo = RepositorioTarjetasSQLite(base)
    await repo.guardar(
        TarjetaPrueba(
            card_id="T-002",
            pan=pan_sintetico("3333"),
            expiracion="3105",
            descripcion="sintetica",
        )
    )
    recuperada = await repo.obtener("T-002")
    assert recuperada is not None
    assert recuperada.pan == pan_sintetico("3333")
    assert recuperada.pan_enmascarado == "************3333"
    assert len(await repo.listar()) == 2  # la demo y esta


async def test_guardar_y_recuperar_una_ejecucion(base):
    repo = RepositorioEjecucionesSQLite(base)
    id_ejecucion = await repo.guardar(
        Ejecucion(
            card_id=CARD_ID_DEMO,
            monto=Decimal("150.00"),
            moneda="188",
            stan="000001",
            estado=EstadoEjecucion.APROBADA,
            codigo_respuesta="00",
            mti_respuesta="0110",
        )
    )
    recuperada = await repo.obtener(id_ejecucion)
    assert recuperada is not None
    assert recuperada.card_id == CARD_ID_DEMO
    assert recuperada.monto == Decimal("150.00")
    assert recuperada.estado is EstadoEjecucion.APROBADA


async def test_una_ejecucion_referencia_card_id_y_no_duplica_el_pan(base):
    """La regla de gobernanza, comprobada contra el esquema y contra los datos."""
    repo = RepositorioEjecucionesSQLite(base)
    await repo.guardar(
        Ejecucion(
            card_id=CARD_ID_DEMO,
            monto=Decimal("150.00"),
            moneda="188",
            stan="000002",
            estado=EstadoEjecucion.APROBADA,
            solicitud_enmascarada="0100 ... 2=************6666 ...",
        )
    )

    with sqlite3.connect(base) as conexion:
        columnas = {f[1] for f in conexion.execute("PRAGMA table_info(ejecuciones)")}
        filas = conexion.execute("SELECT * FROM ejecuciones").fetchall()

    assert "card_id" in columnas
    assert "pan" not in columnas, "ejecuciones no debe tener columna de PAN"

    for fila in filas:
        for valor in fila:
            assert PAN_DEMO not in str(valor), "el PAN completo no puede aparecer en ejecuciones"


async def test_una_ejecucion_exige_una_tarjeta_existente(base):
    repo = RepositorioEjecucionesSQLite(base)
    with pytest.raises(sqlite3.IntegrityError):
        await repo.guardar(
            Ejecucion(
                card_id="NO-EXISTE",
                monto=Decimal("1.00"),
                moneda="188",
                stan="000003",
                estado=EstadoEjecucion.NO_ENVIADA,
            )
        )

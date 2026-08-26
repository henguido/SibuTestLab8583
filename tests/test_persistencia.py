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


async def test_la_tarjeta_de_demostracion_de_una_base_nueva_esta_activa(base):
    tarjeta = await RepositorioTarjetasSQLite(base).obtener(CARD_ID_DEMO)
    assert tarjeta is not None
    assert tarjeta.activa is True


async def test_guardar_una_tarjeta_inactiva_y_recuperarla(base):
    repo = RepositorioTarjetasSQLite(base)
    await repo.guardar(
        TarjetaPrueba(
            card_id="T-INACTIVA",
            pan=pan_sintetico("4444"),
            expiracion="3006",
            activa=False,
        )
    )
    recuperada = await repo.obtener("T-INACTIVA")
    assert recuperada is not None
    assert recuperada.activa is False


async def test_listar_conserva_el_estado_activo_de_cada_tarjeta(base):
    repo = RepositorioTarjetasSQLite(base)
    await repo.guardar(
        TarjetaPrueba(
            card_id="T-LISTA-INACTIVA", pan=pan_sintetico("5555"), expiracion="3007", activa=False
        )
    )
    listadas = {t.card_id: t.activa for t in await repo.listar()}
    assert listadas["T-LISTA-INACTIVA"] is False
    assert listadas[CARD_ID_DEMO] is True


async def test_guardar_de_nuevo_una_tarjeta_reactiva_su_estado(base):
    """El UPSERT actualiza `activa`, no solo la crea la primera vez."""
    repo = RepositorioTarjetasSQLite(base)
    tarjeta = TarjetaPrueba(
        card_id="T-REACTIVAR", pan=pan_sintetico("7777"), expiracion="3008", activa=False
    )
    await repo.guardar(tarjeta)
    assert (await repo.obtener("T-REACTIVAR")).activa is False

    await repo.guardar(
        TarjetaPrueba(
            card_id="T-REACTIVAR", pan=pan_sintetico("7777"), expiracion="3008", activa=True
        )
    )
    assert (await repo.obtener("T-REACTIVAR")).activa is True


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


# ------------------------------ sub-bloque 5: campos de laboratorio de la tarjeta --


def test_un_constructor_anterior_sigue_funcionando_y_los_campos_nuevos_quedan_vacios():
    """Compatibilidad del modelo: nadie construye TarjetaPrueba posicionalmente."""
    tarjeta = TarjetaPrueba(
        card_id="COMPATIBLE-01",
        pan=pan_sintetico("1230"),
        expiracion="3012",
    )
    assert tarjeta.titular == ""
    assert tarjeta.service_code == ""
    assert tarjeta.discretionary_data == ""
    assert tarjeta.cvv == ""
    assert tarjeta.cvv2 == ""
    assert tarjeta.icvv == ""
    assert tarjeta.card_sequence_number == ""
    assert tarjeta.pin_block_laboratorio == ""


async def test_guardar_y_recuperar_los_ocho_campos_de_laboratorio(base):
    repo = RepositorioTarjetasSQLite(base)
    tarjeta = TarjetaPrueba(
        card_id="LAB-01",
        pan=pan_sintetico("1231"),
        expiracion="3012",
        titular="LABORATORIO SIBU",
        service_code="201",
        discretionary_data="00000000",
        cvv="123",
        cvv2="456",
        icvv="789",
        card_sequence_number="01",
        pin_block_laboratorio="0000AAAABBBBCCCC",  # forma de laboratorio, no un PIN Block real
    )
    await repo.guardar(tarjeta)

    recuperada = await repo.obtener("LAB-01")
    assert recuperada is not None
    for campo in (
        "titular", "service_code", "discretionary_data", "cvv", "cvv2", "icvv",
        "card_sequence_number", "pin_block_laboratorio",
    ):
        assert getattr(recuperada, campo) == getattr(tarjeta, campo), campo

    listadas = {t.card_id: t for t in await repo.listar()}
    listada = listadas["LAB-01"]
    for campo in (
        "titular", "service_code", "discretionary_data", "cvv", "cvv2", "icvv",
        "card_sequence_number", "pin_block_laboratorio",
    ):
        assert getattr(listada, campo) == getattr(tarjeta, campo), campo


async def test_el_upsert_actualiza_los_campos_de_laboratorio_sin_afectar_el_resto(base):
    repo = RepositorioTarjetasSQLite(base)
    original = TarjetaPrueba(
        card_id="LAB-02",
        pan=pan_sintetico("1232"),
        expiracion="3012",
        descripcion="original",
        sintetica=True,
        activa=True,
        titular="PRIMER TITULAR",
        service_code="101",
        discretionary_data="11111111",
        cvv="111",
        cvv2="222",
        icvv="333",
        card_sequence_number="01",
        pin_block_laboratorio="1111AAAA",
    )
    await repo.guardar(original)

    actualizada_valores = TarjetaPrueba(
        card_id="LAB-02",
        pan=original.pan,
        expiracion=original.expiracion,
        descripcion=original.descripcion,
        sintetica=original.sintetica,
        activa=original.activa,
        titular="SEGUNDO TITULAR",
        service_code="202",
        discretionary_data="22222222",
        cvv="444",
        cvv2="555",
        icvv="666",
        card_sequence_number="02",
        pin_block_laboratorio="2222BBBB",
    )
    await repo.guardar(actualizada_valores)

    recuperada = await repo.obtener("LAB-02")
    assert recuperada.titular == "SEGUNDO TITULAR"
    assert recuperada.service_code == "202"
    assert recuperada.discretionary_data == "22222222"
    assert recuperada.cvv == "444"
    assert recuperada.cvv2 == "555"
    assert recuperada.icvv == "666"
    assert recuperada.card_sequence_number == "02"
    assert recuperada.pin_block_laboratorio == "2222BBBB"

    # Lo que no se toco en este upsert sigue intacto.
    assert recuperada.pan == original.pan
    assert recuperada.expiracion == original.expiracion
    assert recuperada.descripcion == "original"
    assert recuperada.sintetica is True
    assert recuperada.activa is True


async def test_una_base_nueva_trae_las_ocho_columnas_de_laboratorio_vacias(base):
    """La tarjeta de demostracion, sembrada por `inicializar()`, no las define."""
    tarjeta = await RepositorioTarjetasSQLite(base).obtener(CARD_ID_DEMO)
    assert tarjeta is not None
    assert tarjeta.titular == ""
    assert tarjeta.service_code == ""
    assert tarjeta.discretionary_data == ""
    assert tarjeta.cvv == ""
    assert tarjeta.cvv2 == ""
    assert tarjeta.icvv == ""
    assert tarjeta.card_sequence_number == ""
    assert tarjeta.pin_block_laboratorio == ""


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

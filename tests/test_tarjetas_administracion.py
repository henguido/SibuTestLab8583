"""Administracion de tarjetas de prueba: `ServicioTarjetas` contra SQLite real.

No se prueba aqui la capa web: eso vive en `test_web_configuracion.py`. Aqui
se prueba el servicio de aplicacion y su persistencia real, incluida la
politica de PAN (largo, Luhn, confirmacion QA) y que activar/desactivar no
toque el historial de ejecuciones.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from conftest import TransporteFalso, construir_orquestador
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO
from sibutestlab8583.adapters.persistence.sqlite_repos import RepositorioTarjetasSQLite
from sibutestlab8583.application.tarjetas import (
    DatosEdicionTarjeta,
    DatosNuevaTarjeta,
    ServicioTarjetas,
    TarjetaNoEncontrada,
)
from sibutestlab8583.domain.datos_sinteticos import es_luhn_valido, pan_sintetico
from sibutestlab8583.domain.modelos import DatosCompra

PAN_SINTETICO = pan_sintetico("4111")


def _pan_valido_luhn(sufijo: str, *, longitud: int = 16) -> str:
    """PAN que SI supera Luhn, construido en ejecucion. Nunca un literal.

    Se usa para probar el camino "QA autorizada": el proyecto ya decidio que
    ese camino existe y hace falta un numero que de verdad pase la
    verificacion para probarlo, sin volver a escribir un literal versionado.
    """
    cuerpo = "1" * (longitud - len(sufijo) - 1) + sufijo
    for digito in "0123456789":
        candidato = cuerpo + digito
        if es_luhn_valido(candidato):
            return candidato
    raise AssertionError("no se encontro un digito verificador valido")


def _servicio(base) -> ServicioTarjetas:
    return ServicioTarjetas(RepositorioTarjetasSQLite(base))


# --------------------------------------------------------------- listar/leer --


async def test_listar_incluye_la_tarjeta_de_demostracion(base):
    tarjetas = await _servicio(base).listar()
    ids = [t.card_id for t in tarjetas]
    assert CARD_ID_DEMO in ids


async def test_obtener_una_tarjeta_inexistente_devuelve_none(base):
    assert await _servicio(base).obtener("NO-EXISTE") is None


# ------------------------------------------------------------------- crear ---


async def test_crear_una_tarjeta_sintetica_no_exige_confirmacion(base):
    creada = await _servicio(base).crear(
        DatosNuevaTarjeta(
            card_id="NUEVA-01", descripcion="Prueba", pan=PAN_SINTETICO, expiracion="3012"
        )
    )
    assert creada.sintetica
    assert creada.activa
    assert creada.pan_enmascarado.endswith("4111")


async def test_crear_una_tarjeta_qa_autorizada_con_confirmacion(base):
    pan_real = _pan_valido_luhn("4321")
    creada = await _servicio(base).crear(
        DatosNuevaTarjeta(
            card_id="NUEVA-QA",
            descripcion="QA",
            pan=pan_real,
            expiracion="3012",
            confirma_qa=True,
        )
    )
    assert not creada.sintetica


async def test_crear_una_tarjeta_qa_sin_confirmar_se_rechaza(base):
    pan_real = _pan_valido_luhn("4322")
    with pytest.raises(ValueError, match="ambiente de pruebas autorizado"):
        await _servicio(base).crear(
            DatosNuevaTarjeta(
                card_id="RECHAZAR-QA", descripcion="QA", pan=pan_real, expiracion="3012"
            )
        )


#: Casos de PAN invalido. Los de largo excesivo se construyen en ejecucion
#: -nunca como literal- para no violar la misma guardia de PAN que este
#: archivo tiene que respetar.
PANES_INVALIDOS = (
    "no-es-un-numero",
    "12345",  # menos de 12 digitos
    "9" * 20,  # mas de 19 digitos
)


@pytest.mark.parametrize("pan", PANES_INVALIDOS)
async def test_crear_con_pan_invalido_se_rechaza(base, pan):
    with pytest.raises(ValueError):
        await _servicio(base).crear(
            DatosNuevaTarjeta(card_id="X", descripcion="d", pan=pan, expiracion="3012")
        )


@pytest.mark.parametrize("expiracion", ["", "abcd", "301", "30133", "0000", "3013"])
async def test_crear_con_vencimiento_invalido_se_rechaza(base, expiracion):
    with pytest.raises(ValueError):
        await _servicio(base).crear(
            DatosNuevaTarjeta(
                card_id="X", descripcion="d", pan=PAN_SINTETICO, expiracion=expiracion
            )
        )


async def test_crear_sin_card_id_se_rechaza(base):
    with pytest.raises(ValueError):
        await _servicio(base).crear(
            DatosNuevaTarjeta(card_id="", descripcion="d", pan=PAN_SINTETICO, expiracion="3012")
        )


async def test_crear_con_card_id_duplicado_se_rechaza(base):
    servicio = _servicio(base)
    datos = DatosNuevaTarjeta(
        card_id="DUP-01", descripcion="Primera", pan=PAN_SINTETICO, expiracion="3012"
    )
    await servicio.crear(datos)
    with pytest.raises(ValueError, match="Ya existe"):
        await servicio.crear(datos)


# ------------------------------------------------------------------ editar ---


async def test_editar_descripcion_y_vencimiento(base):
    servicio = _servicio(base)
    await servicio.crear(
        DatosNuevaTarjeta(card_id="EDITAR-01", descripcion="Antes", pan=PAN_SINTETICO, expiracion="3001")
    )
    actualizada = await servicio.actualizar(
        "EDITAR-01",
        DatosEdicionTarjeta(descripcion="Después", expiracion="3105"),
    )
    assert actualizada.descripcion == "Después"
    assert actualizada.expiracion == "3105"


async def test_editar_sin_pan_nuevo_conserva_el_pan_y_su_tipo(base):
    servicio = _servicio(base)
    creada = await servicio.crear(
        DatosNuevaTarjeta(card_id="CONSERVAR-01", descripcion="d", pan=PAN_SINTETICO, expiracion="3012")
    )
    actualizada = await servicio.actualizar(
        "CONSERVAR-01",
        DatosEdicionTarjeta(descripcion="d2", expiracion="3012", pan_nuevo=""),
    )
    assert actualizada.pan_enmascarado == creada.pan_enmascarado
    assert actualizada.sintetica == creada.sintetica


async def test_editar_con_pan_nuevo_lo_reemplaza_y_recalcula_el_tipo(base):
    servicio = _servicio(base)
    await servicio.crear(
        DatosNuevaTarjeta(card_id="REEMPLAZAR-01", descripcion="d", pan=PAN_SINTETICO, expiracion="3012")
    )
    pan_real = _pan_valido_luhn("9911")
    actualizada = await servicio.actualizar(
        "REEMPLAZAR-01",
        DatosEdicionTarjeta(
            descripcion="d", expiracion="3012", pan_nuevo=pan_real, confirma_qa=True
        ),
    )
    assert actualizada.pan_enmascarado.endswith(pan_real[-4:])
    assert not actualizada.sintetica


async def test_editar_aplica_la_misma_validacion_de_pan_que_crear(base):
    servicio = _servicio(base)
    await servicio.crear(
        DatosNuevaTarjeta(card_id="VALIDA-01", descripcion="d", pan=PAN_SINTETICO, expiracion="3012")
    )
    pan_real = _pan_valido_luhn("8871")
    with pytest.raises(ValueError, match="ambiente de pruebas autorizado"):
        await servicio.actualizar(
            "VALIDA-01",
            DatosEdicionTarjeta(descripcion="d", expiracion="3012", pan_nuevo=pan_real),
        )


async def test_editar_una_tarjeta_inexistente_falla_con_su_propia_excepcion(base):
    with pytest.raises(TarjetaNoEncontrada):
        await _servicio(base).actualizar(
            "NO-EXISTE", DatosEdicionTarjeta(descripcion="d", expiracion="3012")
        )


async def test_el_card_id_no_es_parte_de_los_datos_de_edicion(base):
    """`DatosEdicionTarjeta` no tiene campo `card_id`: es estructuralmente inmutable."""
    assert not hasattr(DatosEdicionTarjeta(descripcion="d", expiracion="3012"), "card_id")


# ------------------------------------------------------- activar/desactivar --


async def test_desactivar_no_borra_la_fila_ni_el_pan(base):
    servicio = _servicio(base)
    await servicio.crear(
        DatosNuevaTarjeta(card_id="TOGGLE-01", descripcion="d", pan=PAN_SINTETICO, expiracion="3012")
    )
    desactivada = await servicio.cambiar_estado("TOGGLE-01", activa=False)
    assert desactivada.activa is False

    recuperada = await servicio.obtener("TOGGLE-01")
    assert recuperada is not None
    assert recuperada.pan_enmascarado == desactivada.pan_enmascarado


async def test_activar_una_tarjeta_inactiva_la_vuelve_a_dejar_disponible(base):
    servicio = _servicio(base)
    await servicio.crear(
        DatosNuevaTarjeta(card_id="TOGGLE-02", descripcion="d", pan=PAN_SINTETICO, expiracion="3012")
    )
    await servicio.cambiar_estado("TOGGLE-02", activa=False)
    reactivada = await servicio.cambiar_estado("TOGGLE-02", activa=True)
    assert reactivada.activa is True


async def test_cambiar_estado_de_una_tarjeta_inexistente_falla(base):
    with pytest.raises(TarjetaNoEncontrada):
        await _servicio(base).cambiar_estado("NO-EXISTE", activa=False)


async def test_desactivar_no_modifica_una_ejecucion_que_referencia_la_tarjeta(base):
    """Requisito explicito: el historial no cambia cuando se desactiva la tarjeta."""
    resultado = await construir_orquestador(base, TransporteFalso(codigo="00")).ejecutar_compra(
        DatosCompra(card_id=CARD_ID_DEMO, monto=Decimal("10.00"))
    )
    with sqlite3.connect(base) as conexion:
        conexion.row_factory = sqlite3.Row
        antes = dict(
            conexion.execute(
                "SELECT * FROM ejecuciones WHERE id = ?", (resultado.ejecucion.id,)
            ).fetchone()
        )

    await _servicio(base).cambiar_estado(CARD_ID_DEMO, activa=False)

    with sqlite3.connect(base) as conexion:
        conexion.row_factory = sqlite3.Row
        despues = dict(
            conexion.execute(
                "SELECT * FROM ejecuciones WHERE id = ?", (resultado.ejecucion.id,)
            ).fetchone()
        )
    assert antes == despues


# --------------------------------------------------------------- persistencia --


async def test_los_cambios_sobreviven_a_una_nueva_instancia_del_servicio(base):
    await _servicio(base).crear(
        DatosNuevaTarjeta(card_id="PERSISTE-01", descripcion="d", pan=PAN_SINTETICO, expiracion="3012")
    )
    await _servicio(base).cambiar_estado("PERSISTE-01", activa=False)

    # Instancia nueva, mismo archivo de base: nada vive en memoria del servicio.
    recuperada = await _servicio(base).obtener("PERSISTE-01")
    assert recuperada is not None
    assert recuperada.activa is False

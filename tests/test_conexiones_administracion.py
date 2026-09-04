"""Administracion de conexiones: `ServicioConexiones` contra SQLite real.

No se prueba aqui la capa web: eso vive en `test_web_configuracion.py`. Aqui
se prueba el servicio de aplicacion y su persistencia real, incluida la
validacion de identificador/host/puerto/timeout, que desactivar no borre la
fila ni afecte el historial, y "probar conexion" contra un socket real.

"Conexion" es el nombre de dominio/UI de este bloque; la tabla y el
repositorio siguen llamandose `destinos`, de una fase anterior -ver
`test_destinos.py`, que sigue cubriendo esa capa de persistencia sin cambios-.
"""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from sibutestlab8583.adapters.persistence.esquema import DESTINO_ID_DEMO
from sibutestlab8583.adapters.persistence.sqlite_repos import RepositorioDestinosSQLite
from sibutestlab8583.adapters.transporte.tcp import VerificadorDeConexionTcp
from sibutestlab8583.application.conexiones import (
    ConexionNoEncontrada,
    DatosEdicionConexion,
    DatosNuevaConexion,
    ServicioConexiones,
    TIMEOUT_POR_DEFECTO,
)


def _servicio(base) -> ServicioConexiones:
    return ServicioConexiones(RepositorioDestinosSQLite(base), VerificadorDeConexionTcp())


# --------------------------------------------------------------- listar/leer --


async def test_listar_incluye_la_conexion_de_demostracion(base):
    conexiones = await _servicio(base).listar()
    ids = [c.conexion_id for c in conexiones]
    assert DESTINO_ID_DEMO in ids


async def test_obtener_una_conexion_inexistente_devuelve_none(base):
    assert await _servicio(base).obtener("NO-EXISTE") is None


async def test_listar_activas_excluye_las_desactivadas(base):
    servicio = _servicio(base)
    await servicio.crear(
        DatosNuevaConexion(conexion_id="QA-01", nombre="QA", host="10.0.0.1", puerto="9583")
    )
    await servicio.cambiar_estado("QA-01", activa=False)

    activas = [c.conexion_id for c in await servicio.listar_activas()]
    todas = [c.conexion_id for c in await servicio.listar()]
    assert "QA-01" not in activas
    assert "QA-01" in todas


async def test_obtener_activa_devuelve_none_si_esta_desactivada(base):
    servicio = _servicio(base)
    await servicio.crear(
        DatosNuevaConexion(conexion_id="QA-02", nombre="QA", host="10.0.0.1", puerto="9583")
    )
    await servicio.cambiar_estado("QA-02", activa=False)
    assert await servicio.obtener_activa("QA-02") is None


async def test_obtener_activa_devuelve_none_si_no_existe(base):
    assert await _servicio(base).obtener_activa("NO-EXISTE") is None


async def test_obtener_activa_devuelve_la_conexion_si_esta_activa(base):
    servicio = _servicio(base)
    creada = await servicio.crear(
        DatosNuevaConexion(conexion_id="QA-03", nombre="QA", host="10.0.0.1", puerto="9583")
    )
    encontrada = await servicio.obtener_activa("QA-03")
    assert encontrada == creada


# ------------------------------------------------------------------- crear ---


async def test_crear_una_conexion_nueva_usa_el_timeout_por_defecto_si_no_se_indica(base):
    creada = await _servicio(base).crear(
        DatosNuevaConexion(
            conexion_id="NUEVA-01", nombre="Switch QA", host="192.0.2.10", puerto="9583"
        )
    )
    assert creada.activa
    assert creada.host == "192.0.2.10"
    assert creada.puerto == 9583
    assert creada.timeout == TIMEOUT_POR_DEFECTO


async def test_crear_una_conexion_con_timeout_propio(base):
    creada = await _servicio(base).crear(
        DatosNuevaConexion(
            conexion_id="NUEVA-02", nombre="QA", host="10.0.0.1", puerto="9583", timeout="25"
        )
    )
    assert creada.timeout == 25.0


async def test_crear_con_identificador_duplicado_se_rechaza(base):
    servicio = _servicio(base)
    datos = DatosNuevaConexion(
        conexion_id="DUP-01", nombre="Primero", host="10.0.0.1", puerto="9000"
    )
    await servicio.crear(datos)
    with pytest.raises(ValueError, match="Ya existe"):
        await servicio.crear(datos)


async def test_crear_sin_identificador_se_rechaza(base):
    with pytest.raises(ValueError):
        await _servicio(base).crear(
            DatosNuevaConexion(conexion_id="", nombre="d", host="10.0.0.1", puerto="9000")
        )


@pytest.mark.parametrize("conexion_id", ["con espacio", "con/slash", "con.punto"])
async def test_crear_con_identificador_de_caracteres_no_admitidos_se_rechaza(base, conexion_id):
    with pytest.raises(ValueError):
        await _servicio(base).crear(
            DatosNuevaConexion(
                conexion_id=conexion_id, nombre="d", host="10.0.0.1", puerto="9000"
            )
        )


async def test_crear_sin_nombre_se_rechaza(base):
    with pytest.raises(ValueError):
        await _servicio(base).crear(
            DatosNuevaConexion(conexion_id="X", nombre="", host="10.0.0.1", puerto="9000")
        )


async def test_crear_sin_host_se_rechaza(base):
    with pytest.raises(ValueError):
        await _servicio(base).crear(
            DatosNuevaConexion(conexion_id="X", nombre="d", host="", puerto="9000")
        )


@pytest.mark.parametrize("puerto", ["", "abc", "0", "70000", "-1"])
async def test_crear_con_puerto_invalido_se_rechaza(base, puerto):
    with pytest.raises(ValueError):
        await _servicio(base).crear(
            DatosNuevaConexion(conexion_id="X", nombre="d", host="10.0.0.1", puerto=puerto)
        )


@pytest.mark.parametrize("timeout", ["abc", "0", "-1"])
async def test_crear_con_timeout_invalido_se_rechaza(base, timeout):
    with pytest.raises(ValueError):
        await _servicio(base).crear(
            DatosNuevaConexion(
                conexion_id="X", nombre="d", host="10.0.0.1", puerto="9000", timeout=timeout
            )
        )


# ------------------------------------------------------------------ editar ---


async def test_editar_nombre_host_puerto_y_timeout(base):
    servicio = _servicio(base)
    await servicio.crear(
        DatosNuevaConexion(
            conexion_id="EDITAR-01", nombre="Antes", host="10.0.0.1", puerto="9000"
        )
    )
    actualizada = await servicio.actualizar(
        "EDITAR-01",
        DatosEdicionConexion(nombre="Después", host="10.0.0.2", puerto="9001", timeout="20"),
    )
    assert actualizada.nombre == "Después"
    assert actualizada.host == "10.0.0.2"
    assert actualizada.puerto == 9001
    assert actualizada.timeout == 20.0


async def test_editar_sin_timeout_usa_el_default(base):
    servicio = _servicio(base)
    await servicio.crear(
        DatosNuevaConexion(
            conexion_id="EDITAR-02", nombre="d", host="10.0.0.1", puerto="9000", timeout="30"
        )
    )
    actualizada = await servicio.actualizar(
        "EDITAR-02", DatosEdicionConexion(nombre="d", host="10.0.0.1", puerto="9000")
    )
    assert actualizada.timeout == TIMEOUT_POR_DEFECTO


async def test_editar_aplica_la_misma_validacion_que_crear(base):
    servicio = _servicio(base)
    await servicio.crear(
        DatosNuevaConexion(conexion_id="VALIDA-01", nombre="d", host="10.0.0.1", puerto="9000")
    )
    with pytest.raises(ValueError):
        await servicio.actualizar(
            "VALIDA-01", DatosEdicionConexion(nombre="d", host="10.0.0.1", puerto="no-numero")
        )


async def test_editar_una_conexion_inexistente_falla_con_su_propia_excepcion(base):
    with pytest.raises(ConexionNoEncontrada):
        await _servicio(base).actualizar(
            "NO-EXISTE", DatosEdicionConexion(nombre="d", host="10.0.0.1", puerto="9000")
        )


async def test_el_conexion_id_no_es_parte_de_los_datos_de_edicion(base):
    """`DatosEdicionConexion` no tiene campo `conexion_id`: es estructuralmente inmutable."""
    assert not hasattr(
        DatosEdicionConexion(nombre="d", host="10.0.0.1", puerto="9000"), "conexion_id"
    )


# ------------------------------------------------------- activar/desactivar --


async def test_desactivar_no_borra_la_fila(base):
    servicio = _servicio(base)
    await servicio.crear(
        DatosNuevaConexion(conexion_id="TOGGLE-01", nombre="d", host="10.0.0.1", puerto="9000")
    )
    desactivada = await servicio.cambiar_estado("TOGGLE-01", activa=False)
    assert desactivada.activa is False

    recuperada = await servicio.obtener("TOGGLE-01")
    assert recuperada is not None
    assert recuperada.host == desactivada.host


async def test_activar_una_conexion_inactiva_la_vuelve_a_dejar_disponible(base):
    servicio = _servicio(base)
    await servicio.crear(
        DatosNuevaConexion(conexion_id="TOGGLE-02", nombre="d", host="10.0.0.1", puerto="9000")
    )
    await servicio.cambiar_estado("TOGGLE-02", activa=False)
    reactivada = await servicio.cambiar_estado("TOGGLE-02", activa=True)
    assert reactivada.activa is True


async def test_cambiar_estado_de_una_conexion_inexistente_falla(base):
    with pytest.raises(ConexionNoEncontrada):
        await _servicio(base).cambiar_estado("NO-EXISTE", activa=False)


async def test_desactivar_no_modifica_una_ejecucion_que_referencia_la_conexion(base):
    """Igual que con tarjetas: el historial no cambia cuando se desactiva una conexion.

    Una ejecucion guarda `destino_host`/`destino_puerto` como valores propios
    (`domain/modelos.DestinoGuardado`), no una referencia a esta tabla, asi
    que desactivar la conexion nunca puede alterar una fila ya persistida.
    """
    servicio = _servicio(base)
    creada = await servicio.crear(
        DatosNuevaConexion(conexion_id="REF-01", nombre="d", host="10.0.0.1", puerto="9000")
    )
    desactivada = await servicio.cambiar_estado("REF-01", activa=False)
    assert replace(creada, activa=False) == desactivada


# --------------------------------------------------------------- persistencia --


async def test_los_cambios_sobreviven_a_una_nueva_instancia_del_servicio(base):
    await _servicio(base).crear(
        DatosNuevaConexion(conexion_id="PERSISTE-01", nombre="d", host="10.0.0.1", puerto="9000")
    )
    await _servicio(base).cambiar_estado("PERSISTE-01", activa=False)

    recuperada = await _servicio(base).obtener("PERSISTE-01")
    assert recuperada is not None
    assert recuperada.activa is False


# ------------------------------------------------------------- probar conexion --


async def test_probar_una_conexion_inexistente_falla_con_su_propia_excepcion(base):
    with pytest.raises(ConexionNoEncontrada):
        await _servicio(base).probar("NO-EXISTE")


async def test_probar_una_conexion_disponible_da_true(base):
    servidor = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    puerto = servidor.sockets[0].getsockname()[1]
    async with servidor:
        servicio = _servicio(base)
        await servicio.crear(
            DatosNuevaConexion(
                conexion_id="PROBAR-OK",
                nombre="d",
                host="127.0.0.1",
                puerto=str(puerto),
                timeout="2",
            )
        )
        assert await servicio.probar("PROBAR-OK") is True


async def test_probar_una_conexion_sin_nada_escuchando_da_false(base):
    servicio = _servicio(base)
    await servicio.crear(
        DatosNuevaConexion(
            conexion_id="PROBAR-MAL",
            nombre="d",
            # Puerto reservado que en la practica no tiene nada escuchando.
            host="127.0.0.1",
            puerto="1",
            timeout="0.3",
        )
    )
    assert await servicio.probar("PROBAR-MAL") is False


async def test_probar_no_persiste_ninguna_ejecucion(base):
    """"Probar conexion" no debe dejar rastro en el historial de ejecuciones."""
    import sqlite3

    servidor = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    puerto = servidor.sockets[0].getsockname()[1]
    async with servidor:
        servicio = _servicio(base)
        await servicio.crear(
            DatosNuevaConexion(
                conexion_id="PROBAR-SIN-RASTRO",
                nombre="d",
                host="127.0.0.1",
                puerto=str(puerto),
                timeout="2",
            )
        )
        await servicio.probar("PROBAR-SIN-RASTRO")

    with sqlite3.connect(base) as conexion:
        total = conexion.execute("SELECT COUNT(*) FROM ejecuciones").fetchone()[0]
    assert total == 0

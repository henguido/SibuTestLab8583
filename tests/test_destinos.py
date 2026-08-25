"""Sub-bloque 2 (Fase 1 · Configuracion): catalogo de destinos administrados.

Solo persistencia: esquema, semilla y el puerto/adaptador minimo. Sin rutas
web, sin formularios, sin selector de destino en la compra.
"""

from __future__ import annotations

import sqlite3

from sibutestlab8583.adapters.persistence.esquema import (
    DESTINO_HOST_DEMO,
    DESTINO_ID_DEMO,
    DESTINO_PUERTO_DEMO,
    inicializar,
)
from sibutestlab8583.adapters.persistence.sqlite_repos import RepositorioDestinosSQLite
from sibutestlab8583.domain.modelos import DestinoGuardado


async def test_la_inicializacion_crea_la_tabla_destinos(base):
    with sqlite3.connect(base) as conexion:
        tablas = {
            f[0] for f in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "destinos" in tablas


async def test_el_destino_local_demo_queda_sembrado(base):
    destino = await RepositorioDestinosSQLite(base).obtener(DESTINO_ID_DEMO)
    assert destino is not None
    assert destino.host == DESTINO_HOST_DEMO
    assert destino.puerto == DESTINO_PUERTO_DEMO
    assert destino.activo


async def test_sembrar_destinos_es_idempotente(tmp_path):
    ruta = tmp_path / "repetida.db"
    await inicializar(ruta)
    await inicializar(ruta)  # segunda vez, no debe duplicar ni fallar

    destinos = await RepositorioDestinosSQLite(ruta).listar()
    assert [d.destino_id for d in destinos].count(DESTINO_ID_DEMO) == 1


async def test_guardar_y_recuperar_un_destino_nuevo(base):
    repo = RepositorioDestinosSQLite(base)
    await repo.guardar(
        DestinoGuardado(
            destino_id="QA-01",
            nombre="Switch de pruebas QA",
            host="192.0.2.10",
            puerto=9583,
        )
    )
    recuperado = await repo.obtener("QA-01")
    assert recuperado is not None
    assert recuperado.host == "192.0.2.10"
    assert recuperado.puerto == 9583
    assert recuperado.activo


async def test_guardar_es_un_upsert_por_destino_id(base):
    repo = RepositorioDestinosSQLite(base)
    await repo.guardar(
        DestinoGuardado(destino_id="QA-02", nombre="Original", host="10.0.0.1", puerto=8000)
    )
    await repo.guardar(
        DestinoGuardado(
            destino_id="QA-02", nombre="Renombrado", host="10.0.0.2", puerto=8001, activo=False
        )
    )

    destinos = await repo.listar()
    coincidencias = [d for d in destinos if d.destino_id == "QA-02"]
    assert len(coincidencias) == 1
    actualizado = coincidencias[0]
    assert actualizado.nombre == "Renombrado"
    assert actualizado.host == "10.0.0.2"
    assert actualizado.puerto == 8001
    assert not actualizado.activo


async def test_listar_incluye_activos_e_inactivos_en_orden(base):
    """El filtro por activo es responsabilidad de un consumidor futuro, no del repositorio."""
    repo = RepositorioDestinosSQLite(base)
    await repo.guardar(
        DestinoGuardado(destino_id="Z-INACTIVO", nombre="Z", host="h", puerto=1, activo=False)
    )
    await repo.guardar(DestinoGuardado(destino_id="A-ACTIVO", nombre="A", host="h", puerto=1))

    destinos = await repo.listar()
    ids = [d.destino_id for d in destinos]
    assert "Z-INACTIVO" in ids
    assert "A-ACTIVO" in ids
    assert ids == sorted(ids)


async def test_a_destino_tcp_proyecta_solo_host_y_puerto(base):
    destino = await RepositorioDestinosSQLite(base).obtener(DESTINO_ID_DEMO)
    destino_tcp = destino.a_destino_tcp()
    assert destino_tcp.host == destino.host
    assert destino_tcp.puerto == destino.puerto


async def test_obtener_destino_inexistente_devuelve_none(base):
    assert await RepositorioDestinosSQLite(base).obtener("NO-EXISTE") is None

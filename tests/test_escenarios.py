"""Bloque 2: catalogo de escenarios guardados.

Solo persistencia: esquema y el repositorio minimo. Sin rutas web, sin
formularios. Reutiliza `CARD_ID_DEMO`/`DESTINO_ID_DEMO`, ya sembrados por
`inicializar()`, como tarjeta y conexion validas para las filas de prueba.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

from sibutestlab8583.adapters.persistence.esquema import (
    CARD_ID_DEMO,
    DESTINO_ID_DEMO,
    inicializar,
)
from sibutestlab8583.adapters.persistence.sqlite_repos import RepositorioEscenariosSQLite
from sibutestlab8583.domain.modelos import Escenario


def _escenario(escenario_id: str, **overrides) -> Escenario:
    base = dict(
        escenario_id=escenario_id,
        nombre="Compra básica",
        perfil="generico",
        mti="0100",
        card_id=CARD_ID_DEMO,
        conexion_id=DESTINO_ID_DEMO,
        monto=Decimal("150.00"),
        campos_manuales={"3": "000000", "37": "REF-QA-01"},
    )
    base.update(overrides)
    return Escenario(**base)


async def test_la_inicializacion_crea_la_tabla_escenarios(base):
    with sqlite3.connect(base) as conexion:
        tablas = {
            f[0] for f in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "escenarios" in tablas


async def test_inicializar_no_siembra_ningun_escenario_de_demostracion(base):
    """A diferencia de tarjetas y conexiones, no hace falta un escenario semilla."""
    assert await RepositorioEscenariosSQLite(base).listar() == []


async def test_guardar_y_recuperar_un_escenario_nuevo(base):
    repo = RepositorioEscenariosSQLite(base)
    await repo.guardar(_escenario("ESC-01"))

    recuperado = await repo.obtener("ESC-01")
    assert recuperado is not None
    assert recuperado.nombre == "Compra básica"
    assert recuperado.card_id == CARD_ID_DEMO
    assert recuperado.conexion_id == DESTINO_ID_DEMO
    assert recuperado.monto == Decimal("150.00")
    assert dict(recuperado.campos_manuales) == {"3": "000000", "37": "REF-QA-01"}
    assert recuperado.activo


async def test_guardar_es_un_upsert_por_escenario_id(base):
    repo = RepositorioEscenariosSQLite(base)
    await repo.guardar(_escenario("ESC-02", nombre="Original"))
    await repo.guardar(_escenario("ESC-02", nombre="Renombrado", activo=False))

    escenarios = await repo.listar()
    coincidencias = [e for e in escenarios if e.escenario_id == "ESC-02"]
    assert len(coincidencias) == 1
    assert coincidencias[0].nombre == "Renombrado"
    assert not coincidencias[0].activo


async def test_guardar_no_toca_creado_en_al_actualizar(base):
    repo = RepositorioEscenariosSQLite(base)
    original = _escenario("ESC-03")
    await repo.guardar(original)
    await repo.guardar(_escenario("ESC-03", nombre="Editado", creado_en=original.creado_en))

    recuperado = await repo.obtener("ESC-03")
    assert recuperado.creado_en == original.creado_en


async def test_listar_incluye_activos_e_inactivos_ordenados_por_nombre(base):
    repo = RepositorioEscenariosSQLite(base)
    await repo.guardar(_escenario("ESC-Z", nombre="Z inactivo", activo=False))
    await repo.guardar(_escenario("ESC-A", nombre="A activo"))

    nombres = [e.nombre for e in await repo.listar()]
    assert nombres == sorted(nombres)
    assert "Z inactivo" in nombres
    assert "A activo" in nombres


async def test_obtener_un_escenario_inexistente_devuelve_none(base):
    assert await RepositorioEscenariosSQLite(base).obtener("NO-EXISTE") is None


async def test_un_escenario_sin_campos_manuales_persiste_un_mapa_vacio(base):
    repo = RepositorioEscenariosSQLite(base)
    await repo.guardar(_escenario("ESC-04", campos_manuales={}))

    recuperado = await repo.obtener("ESC-04")
    assert dict(recuperado.campos_manuales) == {}


async def test_campos_json_guarda_la_version_y_los_campos(base):
    """El formato en disco es el documentado: {"version": 1, "campos": {...}}."""
    import json

    repo = RepositorioEscenariosSQLite(base)
    await repo.guardar(_escenario("ESC-05", campos_manuales={"49": "188"}))

    with sqlite3.connect(base) as conexion:
        conexion.row_factory = sqlite3.Row
        fila = conexion.execute(
            "SELECT campos_json FROM escenarios WHERE escenario_id = ?", ("ESC-05",)
        ).fetchone()
    bruto = json.loads(fila["campos_json"])
    assert bruto == {"version": 1, "campos": {"49": "188"}}


async def test_inicializar_es_idempotente_sobre_escenarios(tmp_path):
    ruta = tmp_path / "repetida.db"
    await inicializar(ruta)
    await inicializar(ruta)  # segunda vez: no debe fallar ni duplicar nada

    with sqlite3.connect(ruta) as conexion:
        tablas = {
            f[0] for f in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    assert "escenarios" in tablas

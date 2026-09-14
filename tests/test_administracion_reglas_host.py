"""`ServicioReglasHost`: crear/actualizar/duplicar/cambiar_estado/listar,
contra SQLite real (Fase D1, 2026-09-14).
"""

from __future__ import annotations

import pytest

from sibutestlab8583.adapters.persistence.sqlite_repos import RepositorioReglasHostSQLite
from sibutestlab8583.application.reglas_host import (
    DatosNuevaRegla,
    ReglaHostNoEncontrada,
    ServicioReglasHost,
)
from sibutestlab8583.domain.reglas_host import CAMPO_MTI, CondicionRegla
from sibutestlab8583.profiles.generico import PERFIL_GENERICO


def _datos(nombre="Regla", prioridad=10, condiciones=None, **kw):
    return DatosNuevaRegla(
        nombre=nombre, prioridad=prioridad,
        condiciones=condiciones or [CondicionRegla(CAMPO_MTI, "igual", "0200")],
        de39="00", **kw,
    )


async def test_crear_y_obtener_una_regla_real(base):
    servicio = ServicioReglasHost(RepositorioReglasHostSQLite(base), PERFIL_GENERICO)
    creada = await servicio.crear(_datos())
    assert creada.regla_id is not None

    recargada = await servicio.obtener(creada.regla_id)
    assert recargada is not None
    assert recargada.nombre == "Regla"
    assert recargada.prioridad == 10
    assert recargada.condiciones[0].campo == CAMPO_MTI


async def test_crear_rechaza_una_regla_invalida_sin_persistirla(base):
    servicio = ServicioReglasHost(RepositorioReglasHostSQLite(base), PERFIL_GENERICO)
    with pytest.raises(ValueError, match="sensible"):
        await servicio.crear(_datos(condiciones=[CondicionRegla("2", "igual", "x")]))
    assert await servicio.listar() == []


async def test_listar_ordena_por_prioridad(base):
    servicio = ServicioReglasHost(RepositorioReglasHostSQLite(base), PERFIL_GENERICO)
    await servicio.crear(_datos(nombre="B", prioridad=20))
    await servicio.crear(_datos(nombre="A", prioridad=5))
    listado = await servicio.listar()
    assert [r.nombre for r in listado] == ["A", "B"]


async def test_actualizar_una_regla_existente(base):
    servicio = ServicioReglasHost(RepositorioReglasHostSQLite(base), PERFIL_GENERICO)
    creada = await servicio.crear(_datos(nombre="Original"))
    actualizada = await servicio.actualizar(creada.regla_id, _datos(nombre="Editada", prioridad=99))
    assert actualizada.nombre == "Editada"
    assert actualizada.prioridad == 99
    assert actualizada.regla_id == creada.regla_id


async def test_actualizar_una_regla_inexistente_falla(base):
    servicio = ServicioReglasHost(RepositorioReglasHostSQLite(base), PERFIL_GENERICO)
    with pytest.raises(ReglaHostNoEncontrada):
        await servicio.actualizar("RULE-fantasma", _datos())


async def test_duplicar_una_regla(base):
    servicio = ServicioReglasHost(RepositorioReglasHostSQLite(base), PERFIL_GENERICO)
    creada = await servicio.crear(_datos(nombre="Original"))
    copia = await servicio.duplicar(creada.regla_id)
    assert copia.regla_id != creada.regla_id
    assert copia.nombre == "Original (copia)"
    assert len(await servicio.listar()) == 2


async def test_cambiar_estado_activa_e_inactiva(base):
    servicio = ServicioReglasHost(RepositorioReglasHostSQLite(base), PERFIL_GENERICO)
    creada = await servicio.crear(_datos())
    assert creada.activa is True
    desactivada = await servicio.cambiar_estado(creada.regla_id, activa=False)
    assert desactivada.activa is False
    reactivada = await servicio.cambiar_estado(creada.regla_id, activa=True)
    assert reactivada.activa is True

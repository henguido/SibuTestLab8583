"""`ServicioSuites` contra SQLite real: listar, buscar, crear, editar,
duplicar, activar/desactivar. Analogo a `test_escenarios_administracion.py`.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, DESTINO_ID_DEMO
from sibutestlab8583.adapters.persistence.sqlite_repos import (
    RepositorioEscenariosSQLite,
    RepositorioSuitesSQLite,
)
from sibutestlab8583.application.suites import (
    DatosEdicionSuite,
    DatosNuevaSuite,
    ServicioSuites,
    SuiteNoEncontrada,
)
from sibutestlab8583.domain.modelos import Escenario


def _servicio(base) -> ServicioSuites:
    return ServicioSuites(RepositorioSuitesSQLite(base), RepositorioEscenariosSQLite(base))


async def _sembrar_escenario(base, escenario_id: str) -> None:
    await RepositorioEscenariosSQLite(base).guardar(
        Escenario(
            escenario_id=escenario_id, nombre=f"Escenario {escenario_id}", perfil="generico",
            mti="0100", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO, monto=Decimal("10.00"),
        )
    )


# --------------------------------------------------------------- listar/leer --


async def test_listar_arranca_vacio(base):
    assert await _servicio(base).listar() == []


async def test_obtener_una_suite_inexistente_devuelve_none(base):
    assert await _servicio(base).obtener("NO-EXISTE") is None


async def test_obtener_activa_devuelve_none_si_esta_desactivada(base):
    servicio = _servicio(base)
    creada = await servicio.crear(DatosNuevaSuite(nombre="X"))
    await servicio.cambiar_estado(creada.suite_id, activa=False)
    assert await servicio.obtener_activa(creada.suite_id) is None
    assert await servicio.obtener(creada.suite_id) is not None


async def test_buscar_filtra_por_substring_de_nombre_sin_distinguir_mayusculas(base):
    servicio = _servicio(base)
    await servicio.crear(DatosNuevaSuite(nombre="Regresion nocturna"))
    await servicio.crear(DatosNuevaSuite(nombre="Certificacion de release"))
    resultado = await servicio.listar(buscar="regresion")
    assert [s.nombre for s in resultado] == ["Regresion nocturna"]
    assert len(await servicio.listar()) == 2


# ------------------------------------------------------------------- crear ---


async def test_crear_asigna_un_suite_id_autogenerado(base):
    creada = await _servicio(base).crear(DatosNuevaSuite(nombre="X"))
    assert creada.suite_id
    assert creada.suite_id.startswith("SUI-")


async def test_crear_dos_veces_da_ids_distintos(base):
    servicio = _servicio(base)
    a = await servicio.crear(DatosNuevaSuite(nombre="X"))
    b = await servicio.crear(DatosNuevaSuite(nombre="X"))
    assert a.suite_id != b.suite_id


async def test_crear_sin_nombre_se_rechaza(base):
    with pytest.raises(ValueError):
        await _servicio(base).crear(DatosNuevaSuite(nombre=""))


async def test_crear_con_un_escenario_inexistente_se_rechaza(base):
    with pytest.raises(ValueError, match="no existe"):
        await _servicio(base).crear(DatosNuevaSuite(nombre="X", escenarios=("NO-EXISTE",)))


async def test_crear_con_un_escenario_repetido_se_rechaza(base):
    await _sembrar_escenario(base, "ESC-01")
    with pytest.raises(ValueError, match="repetid"):
        await _servicio(base).crear(
            DatosNuevaSuite(nombre="X", escenarios=("ESC-01", "ESC-01"))
        )


async def test_crear_con_escenarios_validos_persiste_el_orden(base):
    await _sembrar_escenario(base, "ESC-A")
    await _sembrar_escenario(base, "ESC-B")
    creada = await _servicio(base).crear(
        DatosNuevaSuite(nombre="X", escenarios=("ESC-B", "ESC-A"))
    )
    assert creada.escenarios == ("ESC-B", "ESC-A")


async def test_crear_con_un_escenario_inactivo_se_permite(base):
    """Guardar es siempre posible; solo la ejecucion se condiciona -mismo
    criterio que ya aplica un escenario con tarjeta inactiva.
    """
    from dataclasses import replace

    await _sembrar_escenario(base, "ESC-INACTIVO")
    repo_escenarios = RepositorioEscenariosSQLite(base)
    escenario = await repo_escenarios.obtener("ESC-INACTIVO")
    await repo_escenarios.guardar(replace(escenario, activo=False))

    creada = await _servicio(base).crear(DatosNuevaSuite(nombre="X", escenarios=("ESC-INACTIVO",)))
    assert creada.escenarios == ("ESC-INACTIVO",)


# ------------------------------------------------------------------ editar ---


async def test_actualizar_reemplaza_enteros_nombre_descripcion_y_escenarios(base):
    await _sembrar_escenario(base, "ESC-1")
    await _sembrar_escenario(base, "ESC-2")
    servicio = _servicio(base)
    creada = await servicio.crear(
        DatosNuevaSuite(nombre="X", descripcion="original", escenarios=("ESC-1",))
    )
    actualizada = await servicio.actualizar(
        creada.suite_id,
        DatosEdicionSuite(nombre="X renombrada", descripcion="nueva", escenarios=("ESC-2",)),
    )
    assert actualizada.nombre == "X renombrada"
    assert actualizada.descripcion == "nueva"
    assert actualizada.escenarios == ("ESC-2",), "no debe conservar ESC-1"


async def test_actualizar_una_suite_inexistente_falla_con_su_propia_excepcion(base):
    with pytest.raises(SuiteNoEncontrada):
        await _servicio(base).actualizar("NO-EXISTE", DatosEdicionSuite(nombre="X"))


# ---------------------------------------------------------------- duplicar ---


async def test_duplicar_crea_una_copia_independiente_con_nombre_sufijado(base):
    await _sembrar_escenario(base, "ESC-D")
    servicio = _servicio(base)
    creada = await servicio.crear(DatosNuevaSuite(nombre="Original", escenarios=("ESC-D",)))
    copia = await servicio.duplicar(creada.suite_id)

    assert copia.suite_id != creada.suite_id
    assert copia.nombre == "Original (copia)"
    assert copia.escenarios == ("ESC-D",)
    assert copia.activa

    await servicio.actualizar(copia.suite_id, DatosEdicionSuite(nombre="Copia editada"))
    original_sin_cambios = await servicio.obtener(creada.suite_id)
    assert original_sin_cambios.nombre == "Original"


async def test_duplicar_una_suite_inexistente_falla(base):
    with pytest.raises(SuiteNoEncontrada):
        await _servicio(base).duplicar("NO-EXISTE")


# ------------------------------------------------------- activar/desactivar --


async def test_desactivar_no_borra_la_fila(base):
    servicio = _servicio(base)
    creada = await servicio.crear(DatosNuevaSuite(nombre="X"))
    desactivada = await servicio.cambiar_estado(creada.suite_id, activa=False)
    assert desactivada.activa is False
    assert await servicio.obtener(creada.suite_id) is not None


async def test_reactivar_una_suite_inactiva(base):
    servicio = _servicio(base)
    creada = await servicio.crear(DatosNuevaSuite(nombre="X"))
    await servicio.cambiar_estado(creada.suite_id, activa=False)
    reactivada = await servicio.cambiar_estado(creada.suite_id, activa=True)
    assert reactivada.activa is True


async def test_cambiar_estado_de_una_suite_inexistente_falla(base):
    with pytest.raises(SuiteNoEncontrada):
        await _servicio(base).cambiar_estado("NO-EXISTE", activa=False)

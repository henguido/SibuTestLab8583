"""`scripts/sembrar_suite_demo.py`: siembra idempotente del escenario y la
suite reservados para demostraciones de CI.

No es parte del paquete instalado (vive en `scripts/`, no en `src/`): se carga
por ruta con `importlib`, igual que `test_ci_esperar_host.py`.
"""

from __future__ import annotations

import importlib.util
import io
from contextlib import redirect_stdout
from decimal import Decimal
from pathlib import Path

import pytest

from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, DESTINO_ID_DEMO, inicializar
from sibutestlab8583.application.escenarios import DatosNuevoEscenario
from sibutestlab8583.application.suites import DatosNuevaSuite
from sibutestlab8583.cli import ejecutar_cli
from sibutestlab8583.composicion import Composicion, Configuracion

_RUTA = Path(__file__).resolve().parent.parent / "scripts" / "sembrar_suite_demo.py"
_SPEC = importlib.util.spec_from_file_location("sembrar_suite_demo", _RUTA)
assert _SPEC is not None and _SPEC.loader is not None
sembrar_suite_demo = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(sembrar_suite_demo)


async def _composicion(tmp_path) -> Composicion:
    ruta = tmp_path / "ci.db"
    await inicializar(ruta)
    return Composicion(Configuracion(ruta_base_datos=ruta))


async def test_primera_ejecucion_crea_un_escenario_y_una_suite(tmp_path):
    composicion = await _composicion(tmp_path)

    suite_id = await sembrar_suite_demo.sembrar(composicion)

    escenarios = await composicion.administracion_escenarios.listar()
    suites = await composicion.administracion_suites.listar()
    assert [e.nombre for e in escenarios] == [sembrar_suite_demo.NOMBRE_ESCENARIO_DEMO]
    assert [s.nombre for s in suites] == [sembrar_suite_demo.NOMBRE_SUITE_DEMO]
    assert suites[0].suite_id == suite_id
    assert suites[0].escenarios == (escenarios[0].escenario_id,)


async def test_segunda_ejecucion_contra_la_misma_db_reutiliza_no_duplica(tmp_path):
    composicion = await _composicion(tmp_path)

    primer_id = await sembrar_suite_demo.sembrar(composicion)
    segundo_id = await sembrar_suite_demo.sembrar(composicion)

    assert primer_id == segundo_id
    escenarios = await composicion.administracion_escenarios.listar()
    suites = await composicion.administracion_suites.listar()
    assert len(escenarios) == 1, "no debe duplicar el escenario demo"
    assert len(suites) == 1, "no debe duplicar la suite demo"


async def test_ambiguedad_por_nombre_reservado_falla_con_mensaje_claro(tmp_path):
    """Si YA existe mas de una coincidencia exacta con el nombre reservado
    -por ejemplo, alguien lo creo dos veces a mano desde la web-, el script no
    debe elegir ninguna al azar ni tocar nada ajeno."""
    composicion = await _composicion(tmp_path)
    for _ in range(2):
        await composicion.administracion_escenarios.crear(
            DatosNuevoEscenario(
                nombre=sembrar_suite_demo.NOMBRE_ESCENARIO_DEMO,
                card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO, monto=Decimal("10.00"),
            )
        )

    with pytest.raises(sembrar_suite_demo.AmbiguedadDeSiembra):
        await sembrar_suite_demo.sembrar(composicion)

    # No debe haber creado ninguna suite a pesar del fallo.
    assert await composicion.administracion_suites.listar() == []


async def test_multiples_suites_con_nombre_reservado_lanza_ambiguedad_sin_tocar_nada(tmp_path):
    """Mismo principio que la ambiguedad de escenarios, del lado de las
    suites: si YA existen dos suites distintas con exactamente el nombre
    reservado -por ejemplo, creadas a mano dos veces desde la web-, el script
    no debe elegir ninguna al azar, ni crear una tercera, ni tocar las que ya
    existen."""
    composicion = await _composicion(tmp_path)
    primera = await composicion.administracion_suites.crear(
        DatosNuevaSuite(nombre=sembrar_suite_demo.NOMBRE_SUITE_DEMO)
    )
    segunda = await composicion.administracion_suites.crear(
        DatosNuevaSuite(nombre=sembrar_suite_demo.NOMBRE_SUITE_DEMO)
    )
    assert primera.suite_id != segunda.suite_id, "deben ser dos suites DISTINTAS, no la misma"

    with pytest.raises(sembrar_suite_demo.AmbiguedadDeSiembra):
        await sembrar_suite_demo.sembrar(composicion)

    suites = await composicion.administracion_suites.listar()
    # No eligio ninguna al azar (la excepcion ya lo confirma) y no creo una
    # tercera: siguen existiendo EXACTAMENTE las dos mismas, sin una nueva.
    assert {s.suite_id for s in suites} == {primera.suite_id, segunda.suite_id}
    # Tampoco modifico las dos existentes: mismo nombre/descripcion/escenarios/
    # estado que al crearlas, ninguna quedo con al escenario recien resuelto.
    assert set(suites) == {primera, segunda}


def test_main_no_imprime_suite_id_si_hay_ambiguedad_de_suites(tmp_path, monkeypatch, capsys):
    """La ambiguedad de suites debe fallar de forma RUIDOSA por la CLI real
    (`main()`), nunca imprimir `SUITE_ID=...` como si hubiera tenido exito -un
    pipeline que capture esa linea a ciegas no debe quedarse con un id
    inventado."""
    import asyncio

    ruta = tmp_path / "ci.db"
    asyncio.run(inicializar(ruta))
    monkeypatch.setenv("SIBU_DB_PATH", str(ruta))

    async def _sembrar_ambiguedad() -> None:
        composicion = Composicion(Configuracion.desde_entorno())
        for _ in range(2):
            await composicion.administracion_suites.crear(
                DatosNuevaSuite(nombre=sembrar_suite_demo.NOMBRE_SUITE_DEMO)
            )

    asyncio.run(_sembrar_ambiguedad())

    codigo = sembrar_suite_demo.main()

    assert codigo != 0
    salida = capsys.readouterr()
    assert not salida.out.strip(), f"stdout no debe imprimir nada en un fallo: {salida.out!r}"
    assert "SUITE_ID=" not in salida.out
    assert "SUITE_ID=" not in salida.err
    assert "suites llamadas" in salida.err


def test_main_imprime_exactamente_una_linea_suite_id(tmp_path, monkeypatch):
    ruta = tmp_path / "ci.db"
    import asyncio

    asyncio.run(inicializar(ruta))
    monkeypatch.setenv("SIBU_DB_PATH", str(ruta))

    salida = io.StringIO()
    with redirect_stdout(salida):
        codigo = sembrar_suite_demo.main()

    assert codigo == 0
    lineas = salida.getvalue().splitlines()
    assert len(lineas) == 1, f"stdout debe tener EXACTAMENTE una linea, salio: {lineas!r}"
    assert lineas[0].startswith("SUITE_ID=")


def test_la_suite_sembrada_tiene_expectativa_y_es_ejecutable(tmp_path, monkeypatch):
    """Sincrona a proposito: `ejecutar_cli` hace su propio `asyncio.run(...)`
    internamente (igual que en produccion, donde `main()` la llama sin loop
    previo); llamarla desde un test `async def` anidaria un segundo
    `asyncio.run` dentro del loop que ya administra pytest-asyncio, lo que
    `cli.py` capturaria como un fallo tecnico generico (codigo 6), nunca como
    el ERROR de conexion real que esta prueba quiere observar.
    """
    import asyncio

    ruta = tmp_path / "ci.db"
    asyncio.run(inicializar(ruta))
    monkeypatch.setenv("SIBU_DB_PATH", str(ruta))
    # Sin esto, en un entorno donde el puerto demo no responde con un rechazo
    # inmediato (varia segun plataforma/firewall), la conexion fallida podria
    # tardar hasta el timeout por defecto -aqui no importa CUANTO tarda en
    # fallar, solo que la suite sea ejecutable, asi que se acota a proposito.
    monkeypatch.setenv("SIBU_TIEMPO_LIMITE", "0.5")
    composicion = Composicion(Configuracion.desde_entorno())

    suite_id = asyncio.run(sembrar_suite_demo.sembrar(composicion))
    escenarios = asyncio.run(composicion.administracion_escenarios.listar())
    assert escenarios[0].expectativas is not None

    # Ejecutable de punta a punta por el mismo camino que usa la CLI real. Sin
    # un host demo real escuchando en el entorno de pruebas, se espera ERROR
    # (no una excepcion) -evidencia suficiente de que la suite esta bien
    # formada y es ejecutable, nunca 5 (no ejecutable) ni 6 (fallo de la CLI).
    codigo = ejecutar_cli(["run-suite", suite_id, "--format", "json"], composicion=composicion)
    assert codigo in (0, 1, 2)

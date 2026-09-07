"""`sibu-run-suite` / `python -m sibutestlab8583.cli`: ejecucion de una suite
sin navegador, apta para CI.

Casi todo se prueba EN PROCESO llamando a `ejecutar_cli(argv, composicion=...)`
directamente -mismo motivo que el resto del proyecto evita subprocesos reales
para lo que se puede probar mas rapido y con la misma fidelidad-. `_ComposicionPrueba`
usa SQLite real y el `Orquestador` REAL (nunca reimplementado por la CLI), con
`TransporteFalso` en lugar de una conexion TCP real -mismo patron ya usado en
`test_corredor_suites.py`, para no reinventar como se produce un PASS/FAIL/ERROR
real-. Un solo test al final usa `subprocess` de verdad, para probar que el
empaquetado (`python -m sibutestlab8583.cli`) funciona tal cual se instala.
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from dataclasses import replace
from decimal import Decimal

from conftest import TransporteFalso, construir_orquestador

from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, DESTINO_ID_DEMO, inicializar
from sibutestlab8583.adapters.persistence.sqlite_repos import (
    RepositorioCorridasSuiteSQLite,
    RepositorioDestinosSQLite,
    RepositorioEscenariosSQLite,
    RepositorioSuitesSQLite,
    RepositorioTarjetasSQLite,
)
from sibutestlab8583.application.conexiones import ServicioConexiones
from sibutestlab8583.application.corredor_suites import CorredorDeSuites
from sibutestlab8583.application.ejecutor_escenarios import EjecutorDeEscenarios
from sibutestlab8583.application.escenarios import DatosNuevoEscenario, ServicioEscenarios
from sibutestlab8583.application.suites import DatosNuevaSuite, ServicioSuites
from sibutestlab8583.cli import ejecutar_cli
from sibutestlab8583.domain.modelos import EstadoEjecucion, ExpectativaCampo, Expectativas
from sibutestlab8583.profiles.generico import PERFIL_GENERICO

DESCRIPCIONES = {"39": "Código de respuesta", "41": "Identificador del terminal"}


class _ComposicionPrueba:
    """Solo lo que `cli.py` toca: `administracion_suites`, `corredor_suites`,
    `corridas_suite`, `descripciones_de_campos`. El corredor usa el
    `Orquestador` real con `TransporteFalso` -no un doble de la ejecucion-,
    para que un PASS/FAIL/ERROR aqui sea el mismo que produciria la web.
    """

    def __init__(self, base, transporte):
        escenarios = ServicioEscenarios(
            RepositorioEscenariosSQLite(base), RepositorioTarjetasSQLite(base),
            RepositorioDestinosSQLite(base), PERFIL_GENERICO,
        )
        conexiones = ServicioConexiones(RepositorioDestinosSQLite(base))

        async def fabrica(destino, tiempo_limite):
            return construir_orquestador(base, transporte, destino=destino, tiempo_limite=tiempo_limite)

        ejecutor = EjecutorDeEscenarios(escenarios, conexiones, fabrica)
        self.administracion_escenarios = escenarios
        self.administracion_suites = ServicioSuites(
            RepositorioSuitesSQLite(base), RepositorioEscenariosSQLite(base)
        )
        self.corridas_suite = RepositorioCorridasSuiteSQLite(base)
        self.corredor_suites = CorredorDeSuites(
            self.administracion_suites, escenarios, self.corridas_suite, ejecutor,
        )
        self.descripciones_de_campos = DESCRIPCIONES


def _preparar_suite(base, nombre_suite: str, escenarios_spec: list[dict]) -> str:
    """Crea los escenarios y la suite descrita por `escenarios_spec`
    (`{"nombre":..., "expectativas": Expectativas|None, "activo": bool}`),
    en el orden dado. Devuelve el `suite_id`.
    """
    async def _armar() -> str:
        servicio_escenarios = ServicioEscenarios(
            RepositorioEscenariosSQLite(base), RepositorioTarjetasSQLite(base),
            RepositorioDestinosSQLite(base), PERFIL_GENERICO,
        )
        ids = []
        for spec in escenarios_spec:
            creado = await servicio_escenarios.crear(
                DatosNuevoEscenario(
                    nombre=spec["nombre"], card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO,
                    monto=Decimal("10.00"), expectativas=spec.get("expectativas"),
                )
            )
            if not spec.get("activo", True):
                await servicio_escenarios.cambiar_estado(creado.escenario_id, activo=False)
            ids.append(creado.escenario_id)
        servicio_suites = ServicioSuites(
            RepositorioSuitesSQLite(base), RepositorioEscenariosSQLite(base)
        )
        suite = await servicio_suites.crear(DatosNuevaSuite(nombre=nombre_suite, escenarios=tuple(ids)))
        return suite.suite_id

    return asyncio.run(_armar())


def _base(tmp_path):
    ruta = tmp_path / "cli.db"
    asyncio.run(inicializar(ruta))
    return ruta


# --------------------------------------------------------- resultado 0-4 ----


def test_run_suite_todo_pass_sale_0_y_muestra_el_resumen(tmp_path, capsys):
    base = _base(tmp_path)
    suite_id = _preparar_suite(base, "Suite PASS", [
        {"nombre": "E1", "expectativas": Expectativas(estado=EstadoEjecucion.APROBADA)},
    ])
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo="00"))

    codigo = ejecutar_cli(["run-suite", suite_id], composicion=composicion)

    assert codigo == 0
    salida = capsys.readouterr()
    assert "Suite: Suite PASS" in salida.out
    assert "Resultado: PASS" in salida.out
    assert "[PASS] E1" in salida.out
    assert salida.err == ""


def test_run_suite_con_fail_sale_1_y_muestra_la_discrepancia(tmp_path, capsys):
    base = _base(tmp_path)
    suite_id = _preparar_suite(base, "Suite FAIL", [
        {"nombre": "E1", "expectativas": Expectativas(
            campos={"39": ExpectativaCampo(tipo="igual", valor="99")}
        )},
    ])
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo="00"))

    codigo = ejecutar_cli(["run-suite", suite_id], composicion=composicion)

    assert codigo == 1
    salida = capsys.readouterr()
    assert "Resultado: FAIL" in salida.out
    assert "[FAIL] E1" in salida.out
    assert "«99»" in salida.out and "«00»" in salida.out


def test_run_suite_con_escenario_inactivo_sale_2(tmp_path, capsys):
    base = _base(tmp_path)
    suite_id = _preparar_suite(base, "Suite ERROR", [
        {"nombre": "E1", "expectativas": Expectativas(estado=EstadoEjecucion.APROBADA)},
        {"nombre": "E2 inactivo", "activo": False},
    ])
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo="00"))

    codigo = ejecutar_cli(["run-suite", suite_id], composicion=composicion)

    assert codigo == 2
    salida = capsys.readouterr()
    assert "Resultado: ERROR" in salida.out
    assert "[ERROR] E2 inactivo" in salida.out
    assert "[PASS] E1" in salida.out, "el otro escenario si debio ejecutarse"


def test_run_suite_mezcla_pass_y_sin_expectativas_sale_3(tmp_path, capsys):
    base = _base(tmp_path)
    suite_id = _preparar_suite(base, "Suite Incompleta", [
        {"nombre": "E1", "expectativas": Expectativas(estado=EstadoEjecucion.APROBADA)},
        {"nombre": "E2"},
    ])
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo="00"))

    codigo = ejecutar_cli(["run-suite", suite_id], composicion=composicion)

    assert codigo == 3
    assert "Resultado: INCOMPLETA" in capsys.readouterr().out


def test_run_suite_todos_sin_expectativas_sale_4(tmp_path, capsys):
    base = _base(tmp_path)
    suite_id = _preparar_suite(base, "Suite Sin Expectativas", [{"nombre": "E1"}])
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo="00"))

    codigo = ejecutar_cli(["run-suite", suite_id], composicion=composicion)

    assert codigo == 4
    salida = capsys.readouterr()
    assert "Resultado: SIN EXPECTATIVAS" in salida.out
    assert "[SIN EXPECTATIVAS] E1" in salida.out


# ----------------------------------------------------- suite no ejecutable --


def test_run_suite_inexistente_sale_5(tmp_path, capsys):
    base = _base(tmp_path)
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo="00"))

    codigo = ejecutar_cli(["run-suite", "SUI-no-existe"], composicion=composicion)

    assert codigo == 5
    salida = capsys.readouterr()
    assert salida.out == ""
    assert "error" in salida.err.lower()


def test_run_suite_inactiva_sale_5(tmp_path):
    base = _base(tmp_path)
    suite_id = _preparar_suite(base, "Suite inactiva", [{"nombre": "E1"}])
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo="00"))
    asyncio.run(composicion.administracion_suites.cambiar_estado(suite_id, activa=False))

    codigo = ejecutar_cli(["run-suite", suite_id], composicion=composicion)

    assert codigo == 5


def test_run_suite_vacia_sale_5(tmp_path):
    base = _base(tmp_path)
    suite_id = _preparar_suite(base, "Suite vacia", [])
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo="00"))

    codigo = ejecutar_cli(["run-suite", suite_id], composicion=composicion)

    assert codigo == 5


# --------------------------------------------------------------- --nombre ---


def test_run_suite_por_nombre_unico_ejecuta(tmp_path, capsys):
    base = _base(tmp_path)
    _preparar_suite(base, "Nombre único", [
        {"nombre": "E1", "expectativas": Expectativas(estado=EstadoEjecucion.APROBADA)},
    ])
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo="00"))

    codigo = ejecutar_cli(["run-suite", "--nombre", "Nombre único"], composicion=composicion)

    assert codigo == 0
    assert "Suite: Nombre único" in capsys.readouterr().out


def test_run_suite_por_nombre_inexistente_sale_5(tmp_path, capsys):
    base = _base(tmp_path)
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo="00"))

    codigo = ejecutar_cli(["run-suite", "--nombre", "No existe"], composicion=composicion)

    assert codigo == 5
    assert "no existe" in capsys.readouterr().err.lower()


def test_run_suite_por_nombre_duplicado_sale_5_y_lista_los_ids(tmp_path, capsys):
    base = _base(tmp_path)
    id1 = _preparar_suite(base, "Duplicada", [{"nombre": "E1"}])
    id2 = _preparar_suite(base, "Duplicada", [{"nombre": "E1"}])
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo="00"))

    codigo = ejecutar_cli(["run-suite", "--nombre", "Duplicada"], composicion=composicion)

    assert codigo == 5
    error = capsys.readouterr().err
    assert "no es único" in error or "no es unico" in error
    assert id1 in error and id2 in error
    # Nunca ejecuta arbitrariamente la primera coincidencia.
    assert asyncio.run(composicion.corridas_suite.listar()) == []


# ------------------------------------------------------------- uso/config --


def test_run_suite_sin_id_ni_nombre_sale_6(capsys):
    codigo = ejecutar_cli(["run-suite"], composicion=object())
    assert codigo == 6
    assert "error" in capsys.readouterr().err.lower()


def test_run_suite_con_id_y_nombre_a_la_vez_sale_6(capsys):
    codigo = ejecutar_cli(
        ["run-suite", "SUI-x", "--nombre", "X"], composicion=object()
    )
    assert codigo == 6


def test_format_invalido_sale_6_sin_traceback(capsys):
    codigo = ejecutar_cli(["run-suite", "SUI-x", "--format", "xml"], composicion=object())
    assert codigo == 6
    error = capsys.readouterr().err
    assert "Traceback" not in error


def test_subcomando_inexistente_sale_6(capsys):
    codigo = ejecutar_cli(["no-existe"], composicion=object())
    assert codigo == 6


def test_sin_subcomando_sale_6(capsys):
    codigo = ejecutar_cli([], composicion=object())
    assert codigo == 6


# ------------------------------------------------------------- fallo tecnico --


def test_un_fallo_inesperado_nunca_imprime_str_de_la_excepcion(tmp_path, capsys, monkeypatch):
    base = _base(tmp_path)
    suite_id = _preparar_suite(base, "X", [{"nombre": "E1"}])
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo="00"))

    async def _reventar(suite_id):
        raise RuntimeError("detalle-tecnico-interno-que-no-debe-imprimirse")

    monkeypatch.setattr(composicion.corredor_suites, "ejecutar", _reventar)

    codigo = ejecutar_cli(["run-suite", suite_id], composicion=composicion)

    assert codigo == 6
    error = capsys.readouterr().err
    assert "detalle-tecnico-interno" not in error
    assert "Traceback" not in error


# --------------------------------------------------------------- Ctrl+C -----


def test_interrupcion_sale_130_con_mensaje_seguro(tmp_path, capsys, monkeypatch):
    base = _base(tmp_path)
    suite_id = _preparar_suite(base, "X", [{"nombre": "E1"}])
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo="00"))

    async def _interrumpir(suite_id):
        raise KeyboardInterrupt

    monkeypatch.setattr(composicion.corredor_suites, "ejecutar", _interrumpir)

    codigo = ejecutar_cli(["run-suite", suite_id], composicion=composicion)

    assert codigo == 130
    error = capsys.readouterr().err
    assert "EN CURSO" in error
    assert "Suites -> Corridas" in error
    assert "list-suites" not in error, "no debe prometer localizar la corrida por ahi"


# ------------------------------------------------------------------- JSON ---


def test_format_json_tiene_el_esquema_esperado_y_evaluacion_literal(tmp_path, capsys):
    base = _base(tmp_path)
    suite_id = _preparar_suite(base, "Suite JSON", [
        {"nombre": "E1", "expectativas": Expectativas(
            campos={"39": ExpectativaCampo(tipo="igual", valor="99")}
        )},
    ])
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo="00"))

    codigo = ejecutar_cli(["run-suite", suite_id, "--format", "json"], composicion=composicion)
    assert codigo == 1

    datos = json.loads(capsys.readouterr().out)
    assert datos["version"] == 1
    assert datos["suite_id"] == suite_id
    assert datos["suite_nombre"] == "Suite JSON"
    assert datos["resultado"] == "fail"
    assert datos["contadores"] == {
        "total": 1, "pass": 0, "fail": 1, "error": 0,
        "sin_expectativas": 0, "no_ejecutado": 0,
    }
    assert isinstance(datos["duracion_s"], (int, float))
    assert datos["iniciada_en"].count("-") == 2  # ISO 8601, forma minima

    [item] = datos["items"]
    assert item["resultado"] == "fail"
    assert item["evaluacion"]["discrepancias"][0]["campo"] == "39"

    # La fuente es literalmente el snapshot del item, no un recalculo.
    items_reales = asyncio.run(composicion.corridas_suite.obtener_items(datos["corrida_id"]))
    assert item["evaluacion"] == json.loads(items_reales[0].evaluacion_json)


#: Claves EXACTAS del esquema `run-suite --format json` tal como quedo
#: publicado en Bloque 5 (VERSION_JSON_CLI=1) -congelado aqui literal, no
#: derivado de `exportacion_corridas` (Bloque 7), para que un cambio futuro de
#: ESE modulo no pueda "arrastrar" silenciosamente el contrato ya publicado de
#: la CLI sin que este test lo note.
_CLAVES_CORRIDA_JSON_BLOQUE_5 = {
    "version", "suite_id", "suite_nombre", "corrida_id", "estado", "resultado",
    "iniciada_en", "finalizada_en", "duracion_s", "contadores", "items",
}
_CLAVES_ITEM_JSON_BLOQUE_5 = {
    "orden", "escenario_id", "escenario_nombre", "resultado", "detalle",
    "ejecucion_id", "evaluacion",
}


def test_el_esquema_json_de_run_suite_no_cambio_desde_que_bloque_7_reutiliza_el_serializador(
    tmp_path, capsys
):
    """`run-suite --format json` ahora delega en `application/exportacion_corridas.py`
    (Bloque 7) en vez de construir el dict localmente -ver `cli.py::_run_suite`-.
    Este test es el candado de regresion contra ese refactor: si alguna vez el
    modulo neutral agrega/quita/renombra una clave (por ejemplo para una
    necesidad futura de `export-run`), este test debe fallar antes que
    cualquier pipeline de CI existente note un JSON con forma distinta.
    """
    base = _base(tmp_path)
    suite_id = _preparar_suite(base, "Suite esquema congelado", [
        {"nombre": "E1", "expectativas": Expectativas(estado=EstadoEjecucion.APROBADA)},
    ])
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo="00"))

    codigo = ejecutar_cli(["run-suite", suite_id, "--format", "json"], composicion=composicion)
    assert codigo == 0

    datos = json.loads(capsys.readouterr().out)
    assert set(datos.keys()) == _CLAVES_CORRIDA_JSON_BLOQUE_5
    assert set(datos["items"][0].keys()) == _CLAVES_ITEM_JSON_BLOQUE_5


def test_json_nunca_contiene_pan_ni_mensajes_iso_crudos(tmp_path, capsys):
    base = _base(tmp_path)
    suite_id = _preparar_suite(base, "Suite JSON segura", [
        {"nombre": "E1", "expectativas": Expectativas(estado=EstadoEjecucion.APROBADA)},
    ])
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo="00"))

    ejecutar_cli(["run-suite", suite_id, "--format", "json"], composicion=composicion)
    crudo = capsys.readouterr().out

    assert "solicitud_json" not in crudo
    assert "respuesta_json" not in crudo
    assert "solicitud_enmascarada" not in crudo
    import re

    assert not re.search(r"(?<!\d)\d{12,19}(?!\d)", crudo), "no debe aparecer nada con forma de PAN"


def test_json_de_una_corrida_en_curso_no_rompe_y_duracion_es_null():
    """El serializador no debe romper si recibe una corrida sin finalizar,
    aunque `run-suite` normal siempre cierre la corrida antes de imprimir.

    `run-suite --format json` delega en `application/exportacion_corridas.py`
    (Bloque 7) desde que ese modulo neutral existe -mismo esquema de antes,
    ninguna clave cambio (ver el comentario sobre "resultado" en ese modulo).
    """
    from sibutestlab8583.application.exportacion_corridas import reporte_de_corrida
    from sibutestlab8583.domain.modelos import CorridaSuite

    corrida = CorridaSuite(suite_id="SUI-x", suite_nombre="X", total=0, corrida_id=1)
    datos = reporte_de_corrida(corrida, [])
    assert datos["duracion_s"] is None
    assert datos["finalizada_en"] is None
    assert datos["resultado"] is None


# ------------------------------------------------------------- list-suites --


def test_list_suites_texto_y_json(tmp_path, capsys):
    base = _base(tmp_path)
    _preparar_suite(base, "Suite A", [{"nombre": "E1"}])
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo="00"))

    assert ejecutar_cli(["list-suites"], composicion=composicion) == 0
    assert "Suite A" in capsys.readouterr().out

    assert ejecutar_cli(["list-suites", "--format", "json"], composicion=composicion) == 0
    datos = json.loads(capsys.readouterr().out)
    assert datos["version"] == 1
    assert datos["suites"][0]["nombre"] == "Suite A"
    assert datos["suites"][0]["cantidad_escenarios"] == 1


def test_list_suites_vacio_no_falla():
    composicion_vacia = _ComposicionPrueba.__new__(_ComposicionPrueba)

    class _SinSuites:
        async def listar(self):
            return []

    composicion_vacia.administracion_suites = _SinSuites()
    assert ejecutar_cli(["list-suites"], composicion=composicion_vacia) == 0


# ------------------------------------------------------- host demo nunca --


def test_la_cli_nunca_importa_ni_referencia_el_host_simulado():
    """No debe existir ningun camino para que `run-suite`/`list-suites`
    levanten `sibu-host-demo` por su cuenta: la CLI solo consume conexiones
    ya configuradas, igual que la web.
    """
    import sibutestlab8583.cli as modulo_cli

    fuente = open(modulo_cli.__file__, encoding="utf-8").read()
    assert "host_simulado" not in fuente
    assert "HostSimulado" not in fuente


# --------------------------------------------------------- smoke subprocess --


def test_smoke_subprocess_python_dash_m(tmp_path):
    """Unico test con un subproceso real: prueba que el empaquetado
    (`python -m sibutestlab8583.cli`) de verdad resuelve y sale con el
    codigo correcto -toda la logica ya se probo en proceso arriba-.
    """
    ruta = tmp_path / "smoke.db"
    asyncio.run(inicializar(ruta))

    resultado = subprocess.run(
        [sys.executable, "-m", "sibutestlab8583.cli", "list-suites"],
        capture_output=True, text=True,
        env={**__import__("os").environ, "SIBU_DB_PATH": str(ruta)},
    )

    assert resultado.returncode == 0
    assert "No hay suites guardadas." in resultado.stdout

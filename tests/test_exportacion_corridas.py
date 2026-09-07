"""`application/exportacion_corridas.py`: reporte portable (JSON/CSV) de una
corrida de suite ya persistida -Bloque 7-.

Reutiliza el andamiaje de `test_cli.py` (`_base`, `_preparar_suite`,
`_ComposicionPrueba`, `DESCRIPCIONES`) -mismo patron ya usado entre
`test_web.py`/`test_web_suites.py`- para no reinventar como se produce un
PASS/FAIL/ERROR real: SQLite real + `Orquestador` real + `TransporteFalso`.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import re
from dataclasses import replace
from decimal import Decimal

from conftest import TransporteFalso
from test_cli import DESCRIPCIONES, _ComposicionPrueba, _base, _preparar_suite

from sibutestlab8583.adapters.persistence.sqlite_repos import (
    RepositorioEscenariosSQLite,
    RepositorioSuitesSQLite,
)
from sibutestlab8583.application.exportacion_corridas import (
    VERSION_REPORTE_CORRIDA,
    ENCABEZADO_CSV,
    reporte_a_csv,
    reporte_a_json,
    reporte_de_corrida,
)
from sibutestlab8583.application.suites import DatosEdicionSuite
from sibutestlab8583.domain.modelos import (
    CorridaSuite,
    EstadoCorridaSuite,
    EstadoEjecucion,
    EstadoItemCorrida,
    ExpectativaCampo,
    Expectativas,
    ItemCorridaSuite,
)

CODIGO_APROBADO = "00"
CODIGO_RECHAZADO = "05"


def _correr(base, nombre_suite, escenarios_spec):
    """Arma la suite descrita y la corre de verdad; devuelve (corrida, items)."""
    suite_id = _preparar_suite(base, nombre_suite, escenarios_spec)
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo=CODIGO_APROBADO))

    async def _ejecutar():
        corrida = await composicion.corredor_suites.ejecutar(suite_id)
        items = await composicion.corridas_suite.obtener_items(corrida.corrida_id)
        return corrida, items

    return asyncio.run(_ejecutar()), composicion


# --------------------------------------------------------- estados de item --


def test_corrida_pass_se_refleja_en_el_reporte(tmp_path):
    base = _base(tmp_path)
    (corrida, items), _ = _correr(base, "Suite PASS", [
        {"nombre": "E1", "expectativas": Expectativas(estado=EstadoEjecucion.APROBADA)},
    ])
    datos = reporte_de_corrida(corrida, items)
    assert datos["resultado"] == "pass"
    assert datos["items"][0]["resultado"] == "pass"
    assert datos["items"][0]["evaluacion"]["resultado"] == "pass"


def test_corrida_fail_incluye_la_discrepancia_estructurada(tmp_path):
    base = _base(tmp_path)
    (corrida, items), _ = _correr(base, "Suite FAIL", [
        {"nombre": "E1", "expectativas": Expectativas(
            campos={"39": ExpectativaCampo(tipo="igual", valor=CODIGO_RECHAZADO)}
        )},
    ])
    datos = reporte_de_corrida(corrida, items)
    assert datos["resultado"] == "fail"
    [item] = datos["items"]
    assert item["resultado"] == "fail"
    [discrepancia] = item["evaluacion"]["discrepancias"]
    assert discrepancia["campo"] == "39"

    texto_csv = reporte_a_csv(corrida, items, DESCRIPCIONES)
    filas = list(csv.reader(io.StringIO(texto_csv)))
    fila_item = filas[1]
    assert fila_item[ENCABEZADO_CSV.index("resultado")] == "fail"
    assert "39" in fila_item[ENCABEZADO_CSV.index("discrepancias")]


def test_corrida_error_no_tiene_evaluacion_pero_si_detalle(tmp_path):
    base = _base(tmp_path)
    (corrida, items), _ = _correr(base, "Suite ERROR", [
        {"nombre": "E1", "activo": False,
         "expectativas": Expectativas(estado=EstadoEjecucion.APROBADA)},
    ])
    datos = reporte_de_corrida(corrida, items)
    assert datos["resultado"] == "error"
    [item] = datos["items"]
    assert item["resultado"] == "error"
    assert item["evaluacion"] is None
    assert item["detalle"]


def test_corrida_sin_expectativas_no_cuenta_como_pass_ni_fail(tmp_path):
    base = _base(tmp_path)
    (corrida, items), _ = _correr(base, "Suite SIN EXPECTATIVAS", [{"nombre": "E1"}])
    datos = reporte_de_corrida(corrida, items)
    assert datos["resultado"] == "sin_expectativas"
    [item] = datos["items"]
    assert item["resultado"] == "sin_expectativas"
    assert item["evaluacion"] is None


# --------------------------------------------------- inmutabilidad historica --


def await_(coro):
    return asyncio.run(coro)


def test_editar_escenario_expectativa_y_suite_despues_no_cambia_la_corrida_historica(tmp_path):
    """A-E del checkpoint: (A) exportar la corrida, (B) editar el nombre del
    escenario, (C) editar su expectativa, (D) editar la suite, (E) volver a
    exportar la MISMA corrida historica -el reporte debe seguir siendo
    identico en todo lo que proviene del snapshot, no solo en `suite_nombre`.

    Usa una expectativa que FALLA (no aprobada) a proposito: solo asi
    `evaluacion`/`discrepancias` tienen contenido real que verificar -con
    `estado=APROBADA` y transporte que aprueba, discrepancias siempre seria
    una lista vacia y el test no probaria nada sobre ese campo.
    """
    base = _base(tmp_path)
    (corrida, items_antes), composicion = _correr(base, "Suite inmutable", [
        {"nombre": "E1", "expectativas": Expectativas(
            campos={"39": ExpectativaCampo(tipo="igual", valor=CODIGO_RECHAZADO)}
        )},
    ])
    reporte_antes = reporte_de_corrida(corrida, items_antes)

    # (B) y (C): edita nombre Y expectativa del escenario despues de la corrida.
    repo_escenarios = RepositorioEscenariosSQLite(base)
    escenario = await_(repo_escenarios.obtener(items_antes[0].escenario_id))
    await_(repo_escenarios.guardar(replace(
        escenario, nombre="E1 renombrado",
        expectativas=Expectativas(estado=EstadoEjecucion.APROBADA),
    )))

    # (D): edita la suite (nombre y membresia) despues de la corrida.
    await_(composicion.administracion_suites.actualizar(
        corrida.suite_id, DatosEdicionSuite(nombre="Suite renombrada", escenarios=())
    ))

    # (E): vuelve a leer y exportar la MISMA corrida historica.
    corrida_relectura = await_(composicion.corridas_suite.obtener(corrida.corrida_id))
    items_despues = await_(composicion.corridas_suite.obtener_items(corrida.corrida_id))
    reporte_despues = reporte_de_corrida(corrida_relectura, items_despues)

    # Igualdad estructural completa primero -la forma mas fuerte posible-,
    # y despues cada campo pedido explicitamente, para que quede legible cual
    # invariante protege cada assert si alguno llegara a fallar.
    assert reporte_despues == reporte_antes
    item_antes, item_despues = reporte_antes["items"][0], reporte_despues["items"][0]
    assert reporte_despues["suite_nombre"] == reporte_antes["suite_nombre"] == "Suite inmutable"
    assert item_despues["escenario_nombre"] == item_antes["escenario_nombre"] == "E1"
    assert item_despues["orden"] == item_antes["orden"]
    assert item_despues["evaluacion"] == item_antes["evaluacion"]
    assert item_despues["evaluacion"]["discrepancias"] == item_antes["evaluacion"]["discrepancias"]
    assert item_antes["evaluacion"]["discrepancias"] != []  # el caso es realmente un FAIL con contenido


# ----------------------------------------------------------- orden e ids ----


def test_el_orden_de_los_items_se_preserva(tmp_path):
    base = _base(tmp_path)
    (corrida, items), _ = _correr(base, "Suite multi", [
        {"nombre": "Zeta", "expectativas": Expectativas(estado=EstadoEjecucion.APROBADA)},
        {"nombre": "Alfa", "expectativas": Expectativas(estado=EstadoEjecucion.APROBADA)},
        {"nombre": "Medio", "expectativas": Expectativas(estado=EstadoEjecucion.APROBADA)},
    ])
    datos = reporte_de_corrida(corrida, items)
    nombres = [item["escenario_nombre"] for item in datos["items"]]
    ordenes = [item["orden"] for item in datos["items"]]
    assert nombres == ["Zeta", "Alfa", "Medio"]  # orden de la suite, no alfabetico
    assert ordenes == [1, 2, 3]


def test_ejecucion_id_null_en_json_y_vacio_en_csv_para_un_error(tmp_path):
    base = _base(tmp_path)
    (corrida, items), _ = _correr(base, "Suite con error", [
        {"nombre": "E1", "activo": False,
         "expectativas": Expectativas(estado=EstadoEjecucion.APROBADA)},
    ])
    datos = json.loads(reporte_a_json(corrida, items))
    assert datos["items"][0]["ejecucion_id"] is None

    filas = list(csv.reader(io.StringIO(reporte_a_csv(corrida, items, DESCRIPCIONES))))
    assert filas[1][ENCABEZADO_CSV.index("ejecucion_id")] == ""


# ------------------------------------------------------------- formatos -----


def test_json_incluye_la_version_del_esquema(tmp_path):
    base = _base(tmp_path)
    (corrida, items), _ = _correr(base, "Suite version", [{"nombre": "E1"}])
    datos = json.loads(reporte_a_json(corrida, items))
    assert datos["version"] == VERSION_REPORTE_CORRIDA


def test_csv_es_determinista(tmp_path):
    base = _base(tmp_path)
    (corrida, items), _ = _correr(base, "Suite CSV determinista", [
        {"nombre": "E1", "expectativas": Expectativas(estado=EstadoEjecucion.APROBADA)},
        {"nombre": "E2"},
    ])
    primero = reporte_a_csv(corrida, items, DESCRIPCIONES)
    segundo = reporte_a_csv(corrida, items, DESCRIPCIONES)
    assert primero == segundo


def test_caracteres_utf8_se_preservan_en_json_y_csv(tmp_path):
    base = _base(tmp_path)
    (corrida, items), _ = _correr(base, "Suite ñoño", [
        {"nombre": "Café español ☕", "expectativas": Expectativas(estado=EstadoEjecucion.APROBADA)},
    ])
    texto_json = reporte_a_json(corrida, items)
    assert "Café español ☕" in texto_json  # ensure_ascii=False: nunca \uXXXX
    assert "\\u00e9" not in texto_json

    texto_csv = reporte_a_csv(corrida, items, DESCRIPCIONES)
    assert "Café español ☕" in texto_csv


def test_nombres_con_coma_comillas_y_salto_de_linea_sobreviven_el_csv(tmp_path):
    nombre_raro = 'E1, "el raro"\ncon salto'
    base = _base(tmp_path)
    (corrida, items), _ = _correr(base, "Suite rara", [
        {"nombre": nombre_raro, "expectativas": Expectativas(estado=EstadoEjecucion.APROBADA)},
    ])
    texto_csv = reporte_a_csv(corrida, items, DESCRIPCIONES)
    filas = list(csv.reader(io.StringIO(texto_csv)))
    assert filas[1][ENCABEZADO_CSV.index("escenario_nombre")] == nombre_raro


# ------------------------------------------------------- corrida en curso ---


def test_corrida_en_curso_no_rompe_y_deja_null_lo_que_no_hay_todavia():
    """Objeto en memoria, sin persistir -una corrida real de `CorredorDeSuites`
    siempre cierra antes de devolver, pero una corrida interrumpida por un
    crash del proceso puede quedar EN_CURSO en la base con items NO_EJECUTADO.
    """
    corrida = CorridaSuite(
        suite_id="SUI-x", suite_nombre="X", total=1,
        estado=EstadoCorridaSuite.EN_CURSO, corrida_id=7,
    )
    item = ItemCorridaSuite(
        corrida_id=7, escenario_id="ESC-1", escenario_nombre="E1", orden=1,
        resultado=EstadoItemCorrida.NO_EJECUTADO,
    )
    datos = reporte_de_corrida(corrida, [item])
    assert datos["estado"] == "en_curso"
    assert datos["resultado"] is None
    assert datos["finalizada_en"] is None
    assert datos["duracion_s"] is None
    assert datos["items"][0]["resultado"] == "no_ejecutado"
    assert datos["items"][0]["evaluacion"] is None


# -------------------------------------------------------------- seguridad ---


def test_el_modulo_no_importa_ningun_repositorio_de_tarjetas():
    """Garantia por construccion, no solo por comportamiento: si el modulo
    algun dia importara `RepositorioTarjetas`/`RepositorioTarjetasSQLite`,
    seria evidencia de que alguien intento leer datos de tarjeta para armar
    el reporte -algo que este modulo no debe poder hacer ni por accidente.
    """
    import ast

    import sibutestlab8583.application.exportacion_corridas as modulo

    fuente = open(modulo.__file__, encoding="utf-8").read()
    arbol = ast.parse(fuente)
    nombres_importados = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom):
            nombres_importados.update(alias.name for alias in nodo.names)
        elif isinstance(nodo, ast.Import):
            nombres_importados.update(alias.name for alias in nodo.names)
    assert not any("tarjeta" in nombre.lower() for nombre in nombres_importados), nombres_importados


def test_el_reporte_nunca_contiene_pan_ni_mensajes_iso_crudos(tmp_path):
    base = _base(tmp_path)
    (corrida, items), _ = _correr(base, "Suite segura", [
        {"nombre": "E1", "expectativas": Expectativas(estado=EstadoEjecucion.APROBADA)},
    ])
    crudo = reporte_a_json(corrida, items) + reporte_a_csv(corrida, items, DESCRIPCIONES)
    assert not re.search(r"(?<!\d)\d{12,19}(?!\d)", crudo), "no debe aparecer nada con forma de PAN"
    for clave_prohibida in ("solicitud_json", "respuesta_json", "track1", "track2"):
        assert clave_prohibida not in crudo

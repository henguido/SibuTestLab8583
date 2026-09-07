"""`sibu-run-suite export-run CORRIDA_ID`: exporta el reporte de una corrida
de suite YA PERSISTIDA -Bloque 7-. Nunca la ejecuta de nuevo.

Reutiliza el andamiaje de `test_cli.py` (mismo patron: `_base`,
`_preparar_suite`, `_ComposicionPrueba`, SQLite real + `TransporteFalso`).
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import subprocess
import sys

import pytest
from conftest import TransporteFalso
from test_cli import _ComposicionPrueba, _base, _preparar_suite

from sibutestlab8583.adapters.persistence.esquema import inicializar
from sibutestlab8583.cli import (
    CODIGO_CORRIDA_NO_ENCONTRADA,
    CODIGO_ERROR_CLI,
    CODIGO_EXPORT_OK,
    MENSAJE_EVALUACION_CORRUPTA,
    ejecutar_cli,
)
from sibutestlab8583.domain.modelos import EstadoEjecucion, ExpectativaCampo, Expectativas

CODIGO_APROBADO = "00"


def _correr_suite(base, nombre_suite, escenarios_spec) -> int:
    """Arma y corre una suite de verdad; devuelve el `corrida_id` real."""
    suite_id = _preparar_suite(base, nombre_suite, escenarios_spec)
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo=CODIGO_APROBADO))
    codigo = ejecutar_cli(["run-suite", suite_id], composicion=composicion)
    assert codigo in (0, 1, 2, 3, 4)  # se ejecuto de verdad, cualquiera sea el resultado

    async def _obtener_id():
        corridas = await composicion.corridas_suite.listar()
        return corridas[0].corrida_id

    return asyncio.run(_obtener_id())


def test_export_run_de_una_corrida_inexistente_falla_con_mensaje_claro(tmp_path, capsys):
    base = _base(tmp_path)
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo=CODIGO_APROBADO))

    codigo = ejecutar_cli(["export-run", "999999", "--format", "json"], composicion=composicion)

    assert codigo == CODIGO_CORRIDA_NO_ENCONTRADA
    assert "999999" in capsys.readouterr().err


def test_export_run_json_a_stdout(tmp_path, capsys):
    base = _base(tmp_path)
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo=CODIGO_APROBADO))
    corrida_id = _correr_suite(base, "Suite export JSON", [
        {"nombre": "E1", "expectativas": Expectativas(estado=EstadoEjecucion.APROBADA)},
    ])
    capsys.readouterr()  # descarta la salida de texto de _correr_suite

    codigo = ejecutar_cli(
        ["export-run", str(corrida_id), "--format", "json"], composicion=composicion
    )

    assert codigo == CODIGO_EXPORT_OK
    datos = json.loads(capsys.readouterr().out)
    assert datos["corrida_id"] == corrida_id
    assert datos["resultado"] == "pass"


def test_export_run_csv_a_stdout(tmp_path, capsys):
    base = _base(tmp_path)
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo=CODIGO_APROBADO))
    corrida_id = _correr_suite(base, "Suite export CSV", [
        {"nombre": "E1", "expectativas": Expectativas(estado=EstadoEjecucion.APROBADA)},
    ])
    capsys.readouterr()  # descarta la salida de texto de _correr_suite

    codigo = ejecutar_cli(
        ["export-run", str(corrida_id), "--format", "csv"], composicion=composicion
    )

    assert codigo == CODIGO_EXPORT_OK
    salida = capsys.readouterr().out
    assert salida.splitlines()[0].split(",")[0] == "corrida_id"
    assert str(corrida_id) in salida
    # reporte_a_csv() ya termina en "\n" (csv.writer con lineterminator
    # explicito); un print() sin end="" agregaria un segundo "\n" -visible
    # como una fila vacia extra para un csv.reader estricto- (bug real
    # confirmado y corregido en Ciclo 6 del cierre).
    assert salida.endswith("\n")
    assert not salida.endswith("\n\n")
    filas = list(csv.reader(io.StringIO(salida)))
    assert filas[-1] != []


def test_export_run_escribe_a_archivo_en_vez_de_stdout(tmp_path, capsys):
    base = _base(tmp_path)
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo=CODIGO_APROBADO))
    corrida_id = _correr_suite(base, "Suite export archivo", [
        {"nombre": "E1", "expectativas": Expectativas(estado=EstadoEjecucion.APROBADA)},
    ])
    destino = tmp_path / "reporte.json"
    capsys.readouterr()  # descarta la salida de texto de _correr_suite

    codigo = ejecutar_cli(
        ["export-run", str(corrida_id), "--format", "json", "--out", str(destino)],
        composicion=composicion,
    )

    assert codigo == CODIGO_EXPORT_OK
    assert capsys.readouterr().out == "", "con --out no debe imprimir nada a stdout"
    datos = json.loads(destino.read_text(encoding="utf-8"))
    assert datos["corrida_id"] == corrida_id


def test_export_run_csv_a_archivo_no_traduce_los_saltos_de_linea_en_windows(tmp_path):
    """En Windows, `Path.write_text()` sin `newline=""` traduce cada "\\n" a
    "\\r\\n" (traduccion de fin de linea del modo texto), contradiciendo el
    `lineterminator="\\n"` explicito de `reporte_a_csv` (hallazgo real de
    Ciclo 6 del cierre). Se verifica leyendo el archivo en modo binario -si
    se leyera en modo texto, Python normalizaria la diferencia y el test no
    detectaria nada.
    """
    base = _base(tmp_path)
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo=CODIGO_APROBADO))
    corrida_id = _correr_suite(base, "Suite export CSV archivo", [
        {"nombre": "E1", "expectativas": Expectativas(estado=EstadoEjecucion.APROBADA)},
    ])
    destino = tmp_path / "reporte.csv"

    codigo = ejecutar_cli(
        ["export-run", str(corrida_id), "--format", "csv", "--out", str(destino)],
        composicion=composicion,
    )

    assert codigo == CODIGO_EXPORT_OK
    crudo = destino.read_bytes()
    assert b"\r\n" not in crudo
    assert crudo.count(b"\n") >= 2  # encabezado + al menos una fila de datos


def test_export_run_exit_code_nunca_codifica_el_resultado_de_la_corrida(tmp_path):
    """El exit code de `export-run` es siempre `CODIGO_EXPORT_OK` si la corrida
    existe -a diferencia de `run-suite`, que SI codifica PASS/FAIL/... en su
    exit code. Corre una suite que da FAIL y confirma que exportarla despues
    sigue devolviendo 0, no 1."""
    base = _base(tmp_path)
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo="05"))  # rechazada
    from sibutestlab8583.domain.modelos import EstadoEjecucion as _EE

    corrida_id = _correr_suite(base, "Suite que da FAIL", [
        {"nombre": "E1", "expectativas": Expectativas(estado=_EE.APROBADA)},
    ])

    codigo = ejecutar_cli(["export-run", str(corrida_id)], composicion=composicion)
    assert codigo == CODIGO_EXPORT_OK == 0


def test_export_run_con_evaluacion_json_corrupta_da_mensaje_especifico_no_generico(
    tmp_path, capsys
):
    """Hallazgo real de Ciclo 1 (Agente C): si `evaluacion_json` en la fila
    persistida no es JSON valido, `export-run` fallaba con el mismo mensaje
    generico de configuracion (`MENSAJE_FALLO_TECNICO`, "verifique
    SIBU_DB_PATH...") que un problema de conexion o de base de datos ausente
    -enganoso, porque el problema real es una fila corrupta, no la
    configuracion. Corregido en Ciclo 6: un mensaje distinto y honesto.
    """
    import sqlite3

    base = _base(tmp_path)
    corrida_id = _correr_suite(base, "Suite con evaluacion corrupta", [
        {"nombre": "E1", "expectativas": Expectativas(estado=EstadoEjecucion.APROBADA)},
    ])
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo=CODIGO_APROBADO))

    conexion = sqlite3.connect(base)
    conexion.execute(
        "UPDATE corrida_suite_items SET evaluacion_json = ? WHERE corrida_id = ?",
        ("{esto no es json valido", corrida_id),
    )
    conexion.commit()
    conexion.close()

    codigo = ejecutar_cli(["export-run", str(corrida_id)], composicion=composicion)

    assert codigo == CODIGO_ERROR_CLI
    error = capsys.readouterr().err
    assert MENSAJE_EVALUACION_CORRUPTA in error
    # No es el mensaje generico de "verifique la configuracion" -ese mensaje
    # sugeriria (enganosamente) revisar SIBU_DB_PATH o correr sibu-init-db.
    assert "ejecute sibu-init-db" not in error


def test_export_run_no_ejecuta_la_suite_de_nuevo(tmp_path):
    """Correr `export-run` dos veces seguidas debe devolver EXACTAMENTE el
    mismo reporte -si volviera a ejecutar la suite, el STAN/ejecucion_id
    cambiarian entre una llamada y otra."""
    base = _base(tmp_path)
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo=CODIGO_APROBADO))
    corrida_id = _correr_suite(base, "Suite estable", [
        {"nombre": "E1", "expectativas": Expectativas(estado=EstadoEjecucion.APROBADA)},
    ])

    import io
    from contextlib import redirect_stdout

    salidas = []
    for _ in range(2):
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            codigo = ejecutar_cli(
                ["export-run", str(corrida_id), "--format", "json"], composicion=composicion
            )
        assert codigo == CODIGO_EXPORT_OK
        salidas.append(buffer.getvalue())

    assert salidas[0] == salidas[1]


def test_smoke_subprocess_export_run(tmp_path):
    """Unico test de este archivo con un subproceso real -mismo criterio que
    `test_cli.py::test_smoke_subprocess_python_dash_m`-: confirma que el
    subcomando resuelve tambien empaquetado como `python -m`."""
    import sibutestlab8583.cli as modulo_cli

    ruta = tmp_path / "smoke_export.db"
    asyncio.run(inicializar(ruta))

    resultado = subprocess.run(
        [sys.executable, "-m", "sibutestlab8583.cli", "export-run", "999999"],
        capture_output=True, text=True,
        env={**__import__("os").environ, "SIBU_DB_PATH": str(ruta)},
    )

    assert resultado.returncode == CODIGO_CORRIDA_NO_ENCONTRADA
    assert "999999" in resultado.stderr


def test_entry_point_real_export_run_devuelve_utf8_valido(tmp_path):
    """Ejecuta el script `sibu-run-suite` INSTALADO de verdad (no `python -m`),
    subcomando `export-run`, sobre una corrida con una discrepancia que
    produce un mensaje con tildes (`mensaje_de_discrepancia`), y confirma que
    el stdout decodifica como UTF-8 sin bytes invalidos -mismo criterio y
    mismo riesgo que ya cubre `test_auditoria_cobertura.py::
    test_entry_point_real_sibu_run_suite_devuelve_utf8_valido` para
    `run-suite`, pero para `export-run`, que es un subcomando distinto y
    hasta ahora sin esta cobertura: el fix de encoding en `main()` (linea
    323-331 de `cli.py`) aplica por igual a todos los subcomandos, pero eso
    no estaba confirmado empiricamente para este en particular.

    Reutiliza el patron de localizar el ejecutable instalado (no reimplementa
    nada de `shutil.which`/`Path.with_name`, mismo codigo que el test de
    `run-suite`) en vez de levantar infraestructura de test nueva.
    """
    import os
    import shutil
    from pathlib import Path

    nombre = "sibu-run-suite.exe" if sys.platform == "win32" else "sibu-run-suite"
    candidato = Path(sys.executable).with_name(nombre)
    ejecutable = str(candidato) if candidato.exists() else shutil.which("sibu-run-suite")
    if ejecutable is None:
        pytest.skip("sibu-run-suite no esta instalado en este entorno (paquete no instalado en modo editable)")

    ruta = tmp_path / "entrypoint_export.db"
    asyncio.run(inicializar(ruta))

    # Misma suite "con tildes" que ya usa el test analogo de run-suite: una
    # expectativa que FALLA, para que el texto de salida (CSV, discrepancias
    # legibles) incluya un mensaje con tildes real, no solo nombres.
    corrida_id = _correr_suite(ruta, "Suite con tildes (export)", [
        {"nombre": "Falla con acentos ñ", "expectativas": Expectativas(
            campos={"39": ExpectativaCampo(tipo="igual", valor="99")}
        )},
    ])

    resultado = subprocess.run(
        [ejecutable, "export-run", str(corrida_id), "--format", "csv"],
        capture_output=True,
        env={**os.environ, "SIBU_DB_PATH": str(ruta)},
    )

    # Nunca decodificar mal: si el launcher no configurara UTF-8 en Windows,
    # esto lanzaria UnicodeDecodeError con la codepagina por defecto.
    texto = resultado.stdout.decode("utf-8")
    assert resultado.returncode == CODIGO_EXPORT_OK
    assert "Falla con acentos ñ" in texto
    assert "Código de respuesta" in texto or "39" in texto

"""Comando `sibu-run-suite` / `python -m sibutestlab8583.cli`: ejecuta una
suite de regresion sin navegador, para invocarla desde CI, y exporta el
reporte de una corrida ya persistida (Bloque 7).

No reimplementa nada: pide la misma `Composicion` que ya arma la web
(`Configuracion.desde_entorno()`), y delega la ejecucion entera en
`composicion.corredor_suites.ejecutar(suite_id)` -el mismo `CorredorDeSuites`
que ya usa `POST /suites/{id}/ejecutar`-. Esta capa solo resuelve argumentos,
formatea la salida (texto o JSON) a partir del snapshot ya persistido
(`ItemCorridaSuite.evaluacion_json`), y traduce el resultado a un codigo de
salida. Nunca vuelve a evaluar Expected vs Actual, nunca recalcula
`resultado_global`, nunca toca RN-1..RN-4.

`export-run` reutiliza `application/exportacion_corridas.py` -el mismo modulo
neutral que en el futuro podria reutilizar una ruta web de descarga, sin que
ninguna de las dos importe a la otra.

Deliberadamente NO levanta `sibu-host-demo`: si la conexion configurada no
responde, eso es un ERROR por escenario que el corredor ya sabe aislar -no
algo que esta CLI deba "arreglar" arrancando un proceso por su cuenta.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Sequence

from .application import exportacion_corridas
from .application.corredor_suites import SuiteNoEjecutable
from .application.presentacion_evaluacion import mensaje_de_discrepancia
from .composicion import Composicion, Configuracion

#: Version del esquema de `--format json`. Formato propio de esta CLI,
#: independiente de VERSION_EXPECTATIVAS/VERSION_CAMPOS_ESCENARIO/VERSION_FORMATO:
#: cada uno versiona una cosa distinta y evoluciona por separado.
VERSION_JSON_CLI = 1

#: Codigos de salida. 0-4 son un mapeo directo de `ResultadoGlobalSuite`;
#: 5 y 6 separan los otros dos "cubos" que no son un resultado de corrida:
#: una suite que ni siquiera llego a correr (5), y un fallo tecnico/de uso de
#: la propia CLI (6). 130 es la convencion Unix para SIGINT (128+2), fuera de
#: este rango a proposito para que un pipeline la distinga de inmediato de un
#: resultado funcional real.
CODIGOS_RESULTADO = {
    "pass": 0,
    "fail": 1,
    "error": 2,
    "incompleta": 3,
    "sin_expectativas": 4,
}
CODIGO_SUITE_NO_EJECUTABLE = 5
CODIGO_ERROR_CLI = 6
CODIGO_INTERRUMPIDO = 130

#: `export-run` tiene su PROPIO contrato de codigo de salida, deliberadamente
#: separado del de arriba: no "corre" nada, solo exporta un reporte de una
#: corrida ya persistida, asi que su exit code responde a "¿se pudo generar
#: el reporte?", nunca al resultado (PASS/FAIL/...) de esa corrida -mezclar
#: ambas preguntas confundiria un comando de solo lectura con uno que hace
#: que un pipeline dependa del resultado de una suite que ni siquiera corrio
#: en este invocacion.
CODIGO_EXPORT_OK = 0
CODIGO_CORRIDA_NO_ENCONTRADA = 1

MENSAJE_INTERRUMPIDO = (
    "Interrumpido. La corrida puede haber quedado EN CURSO. Revísela en "
    "Suites -> Corridas en la interfaz web."
)
MENSAJE_FALLO_TECNICO = (
    "error: fallo técnico inesperado. Verifique la configuración "
    "(SIBU_DB_PATH, la conexión de la suite) o ejecute sibu-init-db."
)
MENSAJE_EVALUACION_CORRUPTA = (
    "error: el reporte no se pudo generar porque los datos de evaluación "
    "guardados para esta corrida no son JSON válido. No es un problema de "
    "configuración (SIBU_DB_PATH está bien); la base de datos tiene una "
    "fila corrupta."
)


class _ErrorDeArgumentosCLI(Exception):
    """Un uso invalido de la CLI. Se traduce a `CODIGO_ERROR_CLI`, nunca a
    los `sys.exit(2)`/traceback que `argparse` produce por defecto.
    """


class _ArgumentParserControlado(argparse.ArgumentParser):
    """Intercepta los errores de uso de `argparse` para que terminen en el
    codigo de salida propio de esta CLI (6), no en el 2 por defecto.
    """

    def error(self, message: str) -> None:  # noqa: D102 - override de argparse
        raise _ErrorDeArgumentosCLI(message)


def _construir_parser() -> argparse.ArgumentParser:
    parser = _ArgumentParserControlado(
        prog="sibu-run-suite",
        description="Ejecuta una suite de regresion sin navegador (apta para CI).",
    )
    subcomandos = parser.add_subparsers(dest="comando")

    listar = subcomandos.add_parser("list-suites", help="Lista las suites guardadas.")
    listar.add_argument("--format", choices=("text", "json"), default="text")

    ejecutar = subcomandos.add_parser("run-suite", help="Ejecuta una suite completa.")
    ejecutar.add_argument("suite_id", nargs="?", default=None, help="Identificador de la suite.")
    ejecutar.add_argument(
        "--nombre", default=None,
        help="Nombre EXACTO de la suite, alternativa a suite_id (mutuamente excluyentes).",
    )
    ejecutar.add_argument("--format", choices=("text", "json"), default="text")

    exportar = subcomandos.add_parser(
        "export-run", help="Exporta el reporte de una corrida de suite ya persistida."
    )
    exportar.add_argument("corrida_id", type=int, help="Identificador numerico de la corrida.")
    exportar.add_argument("--format", choices=("json", "csv"), default="json")
    exportar.add_argument(
        "--out", default=None,
        help="Ruta de archivo donde escribir el reporte; si se omite, se imprime a stdout.",
    )

    return parser


def ejecutar_cli(argv: Sequence[str], *, composicion: Composicion | None = None) -> int:
    """Punto de entrada testeable: nunca llama `sys.exit`, siempre devuelve
    el codigo de salida como `int`. `main()` es la unica funcion que lo
    convierte en la salida real del proceso.

    `composicion`, si se pasa, reemplaza a `Composicion(Configuracion.desde_entorno())`
    -unicamente para que las pruebas puedan inyectar la misma clase de doble
    que ya usa `test_web.py` (SQLite real + transporte falso), sin levantar
    un host TCP real ni un subproceso por cada caso. En produccion nunca se
    pasa: `main()` la deja en `None`.
    """
    try:
        args = _construir_parser().parse_args(list(argv))
    except _ErrorDeArgumentosCLI as error:
        print(f"error: {error}", file=sys.stderr)
        return CODIGO_ERROR_CLI
    except SystemExit as salida:
        # `--help`/`-h` sale por aqui con code 0; cualquier otro uso invalido
        # ya fue interceptado arriba por `_ArgumentParserControlado.error`.
        return salida.code if isinstance(salida.code, int) else 0

    if args.comando is None:
        print(
            "error: indique un subcomando (list-suites | run-suite | export-run).",
            file=sys.stderr,
        )
        return CODIGO_ERROR_CLI

    if args.comando == "run-suite":
        tiene_id = bool(args.suite_id)
        tiene_nombre = bool(args.nombre)
        if tiene_id == tiene_nombre:  # ninguno o ambos
            print(
                "error: indique exactamente uno de: SUITE_ID o --nombre.",
                file=sys.stderr,
            )
            return CODIGO_ERROR_CLI

    if composicion is None:
        composicion = Composicion(Configuracion.desde_entorno())

    try:
        if args.comando == "list-suites":
            return asyncio.run(_list_suites(composicion, args.format))
        if args.comando == "export-run":
            return asyncio.run(_export_run(composicion, args))
        return asyncio.run(_run_suite(composicion, args))
    except KeyboardInterrupt:
        print(MENSAJE_INTERRUMPIDO, file=sys.stderr)
        return CODIGO_INTERRUMPIDO
    except json.JSONDecodeError:
        # evaluacion_json corrupto en la fila persistida -distinto de un
        # problema de configuracion, no debe confundirse con el mensaje
        # generico de abajo (hallazgo real de Ciclo 1, Agente C).
        print(MENSAJE_EVALUACION_CORRUPTA, file=sys.stderr)
        return CODIGO_ERROR_CLI
    except Exception:
        # Nunca str(excepcion)/repr/traceback: un fallo no controlado no debe
        # filtrar detalles tecnicos ni datos crudos a la salida de la CLI.
        print(MENSAJE_FALLO_TECNICO, file=sys.stderr)
        return CODIGO_ERROR_CLI


async def _resolver_suite_id(composicion: Composicion, args) -> str | None:
    """`suite_id` directo, o resuelto por `--nombre` EXACTO. `None` si no se
    pudo resolver -el llamador debe tratarlo como suite no ejecutable-.
    """
    if args.suite_id:
        return args.suite_id

    candidatas = [s for s in await composicion.administracion_suites.listar() if s.nombre == args.nombre]
    if len(candidatas) == 1:
        return candidatas[0].suite_id
    if not candidatas:
        print(f"error: no existe ninguna suite con el nombre {args.nombre!r}.", file=sys.stderr)
    else:
        ids = ", ".join(s.suite_id for s in candidatas)
        print(
            f"error: el nombre {args.nombre!r} no es único ({len(candidatas)} suites lo usan: "
            f"{ids}). Use el suite_id.",
            file=sys.stderr,
        )
    return None


async def _run_suite(composicion: Composicion, args) -> int:
    suite_id = await _resolver_suite_id(composicion, args)
    if suite_id is None:
        return CODIGO_SUITE_NO_EJECUTABLE

    try:
        corrida = await composicion.corredor_suites.ejecutar(suite_id)
    except SuiteNoEjecutable as error:
        print(f"error: {error}", file=sys.stderr)
        return CODIGO_SUITE_NO_EJECUTABLE

    items = await composicion.corridas_suite.obtener_items(corrida.corrida_id)
    descripciones = composicion.descripciones_de_campos

    if args.format == "json":
        print(exportacion_corridas.reporte_a_json(corrida, items))
    else:
        print(_corrida_a_texto(corrida, items, descripciones))

    resultado = corrida.resultado_global.value if corrida.resultado_global else "error"
    return CODIGOS_RESULTADO.get(resultado, CODIGO_ERROR_CLI)


async def _export_run(composicion: Composicion, args) -> int:
    """Exporta el reporte de una corrida YA PERSISTIDA -nunca la ejecuta de
    nuevo-. A diferencia de `run-suite`, el exit code de este subcomando
    nunca codifica el resultado de la corrida (ver `CODIGO_EXPORT_OK`).
    """
    corrida = await composicion.corridas_suite.obtener(args.corrida_id)
    if corrida is None:
        print(f"error: no existe ninguna corrida con id {args.corrida_id}.", file=sys.stderr)
        return CODIGO_CORRIDA_NO_ENCONTRADA

    items = await composicion.corridas_suite.obtener_items(corrida.corrida_id)
    descripciones = composicion.descripciones_de_campos

    if args.format == "csv":
        texto = exportacion_corridas.reporte_a_csv(corrida, items, descripciones)
    else:
        texto = exportacion_corridas.reporte_a_json(corrida, items)

    if args.out:
        # Escritura directa a archivo -sin pasar por stdout- para que un
        # pipeline no dependa de una redireccion de shell para conservar el
        # reporte; UTF-8 explicito, igual criterio que `main()` para stdout.
        # newline="" preserva el "\n" literal que reporte_a_csv/reporte_a_json
        # ya produjeron -sin esto, en Windows write_text() traduce cada "\n"
        # a "\r\n" (traduccion de fin de linea del modo texto), contradiciendo
        # el `lineterminator="\n"` explicito de reporte_a_csv (hallazgo
        # confirmado en Ciclo 6 del cierre).
        Path(args.out).write_text(texto, encoding="utf-8", newline="")
    elif args.format == "csv":
        # reporte_a_csv() ya termina en "\n" (csv.writer con lineterminator
        # explicito); print(texto) agregaria un segundo salto de linea al
        # final, visible como una fila vacia extra para un csv.reader estricto.
        print(texto, end="")
    else:
        print(texto)
    return CODIGO_EXPORT_OK


async def _list_suites(composicion: Composicion, formato: str) -> int:
    suites = await composicion.administracion_suites.listar()
    if formato == "json":
        print(json.dumps(
            {
                "version": VERSION_JSON_CLI,
                "suites": [
                    {
                        "suite_id": s.suite_id,
                        "nombre": s.nombre,
                        "activa": s.activa,
                        "cantidad_escenarios": len(s.escenarios),
                    }
                    for s in suites
                ],
            },
            ensure_ascii=False,
        ))
        return 0
    if not suites:
        print("No hay suites guardadas.")
        return 0
    for suite in suites:
        estado = "activa" if suite.activa else "inactiva"
        print(f"{suite.suite_id}  [{estado}]  {len(suite.escenarios)} escenario(s)  {suite.nombre}")
    return 0


# ------------------------------------------------------------ formateo -----


_ETIQUETAS_RESULTADO_GLOBAL = {
    "pass": "PASS", "fail": "FAIL", "error": "ERROR",
    "incompleta": "INCOMPLETA", "sin_expectativas": "SIN EXPECTATIVAS",
}
_ETIQUETAS_RESULTADO_ITEM = {
    "pass": "PASS", "fail": "FAIL", "error": "ERROR",
    "sin_expectativas": "SIN EXPECTATIVAS", "no_ejecutado": "NO EJECUTADO",
}


def _corrida_a_texto(corrida, items, descripciones) -> str:
    resultado = corrida.resultado_global.value if corrida.resultado_global else "en_curso"
    duracion = exportacion_corridas.duracion_s(corrida)
    lineas = [
        f"Suite: {corrida.suite_nombre}",
        f"Corrida: {corrida.corrida_id}",
        f"Resultado: {_ETIQUETAS_RESULTADO_GLOBAL.get(resultado, resultado.upper())}",
        f"Duración: {duracion:.2f} s" if duracion is not None else "Duración: (en curso)",
        "",
        f"PASS: {corrida.cantidad_pass}",
        f"FAIL: {corrida.cantidad_fail}",
        f"ERROR: {corrida.cantidad_error}",
        f"SIN EXPECTATIVAS: {corrida.cantidad_sin_expectativas}",
        "",
    ]
    for item in items:
        etiqueta = _ETIQUETAS_RESULTADO_ITEM.get(item.resultado.value, item.resultado.value.upper())
        lineas.append(f"[{etiqueta}] {item.escenario_nombre}")
        if item.detalle:
            lineas.append(f"       {item.detalle}")
        if item.evaluacion_json:
            datos = json.loads(item.evaluacion_json)
            for discrepancia in datos.get("discrepancias", []):
                lineas.append(f"       {mensaje_de_discrepancia(discrepancia, descripciones)}")
    return "\n".join(lineas)


def main() -> None:
    # En Windows, `sys.stdout`/`sys.stderr` heredan la pagina de codigos de la
    # consola (no UTF-8) al redirigirse a un archivo o a un pipe de CI: sin
    # esto, cualquier tilde o comilla angular en la salida (por ejemplo en
    # `--format json`) se escribe con bytes invalidos. `reconfigure` no existe
    # en flujos ya envueltos por algunas terminales; se ignora si falta.
    for flujo in (sys.stdout, sys.stderr):
        if hasattr(flujo, "reconfigure"):
            flujo.reconfigure(encoding="utf-8")
    sys.exit(ejecutar_cli(sys.argv[1:]))


if __name__ == "__main__":
    main()

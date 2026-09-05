"""Comando `sibu-run-suite` / `python -m sibutestlab8583.cli`: ejecuta una
suite de regresion sin navegador, para invocarla desde CI.

No reimplementa nada: pide la misma `Composicion` que ya arma la web
(`Configuracion.desde_entorno()`), y delega la ejecucion entera en
`composicion.corredor_suites.ejecutar(suite_id)` -el mismo `CorredorDeSuites`
que ya usa `POST /suites/{id}/ejecutar`-. Esta capa solo resuelve argumentos,
formatea la salida (texto o JSON) a partir del snapshot ya persistido
(`ItemCorridaSuite.evaluacion_json`), y traduce el resultado a un codigo de
salida. Nunca vuelve a evaluar Expected vs Actual, nunca recalcula
`resultado_global`, nunca toca RN-1..RN-4.

Deliberadamente NO levanta `sibu-host-demo`: si la conexion configurada no
responde, eso es un ERROR por escenario que el corredor ya sabe aislar -no
algo que esta CLI deba "arreglar" arrancando un proceso por su cuenta.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Sequence

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

MENSAJE_INTERRUMPIDO = (
    "Interrumpido. La corrida puede haber quedado EN CURSO. Revísela en "
    "Suites -> Corridas en la interfaz web."
)
MENSAJE_FALLO_TECNICO = (
    "error: fallo técnico inesperado. Verifique la configuración "
    "(SIBU_DB_PATH, la conexión de la suite) o ejecute sibu-init-db."
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
        print("error: indique un subcomando (list-suites | run-suite).", file=sys.stderr)
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
        return asyncio.run(_run_suite(composicion, args))
    except KeyboardInterrupt:
        print(MENSAJE_INTERRUMPIDO, file=sys.stderr)
        return CODIGO_INTERRUMPIDO
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
        print(json.dumps(_corrida_a_json(corrida, items), ensure_ascii=False))
    else:
        print(_corrida_a_texto(corrida, items, descripciones))

    resultado = corrida.resultado_global.value if corrida.resultado_global else "error"
    return CODIGOS_RESULTADO.get(resultado, CODIGO_ERROR_CLI)


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


def _duracion_s(corrida) -> float | None:
    """`None` si la corrida no esta finalizada -no deberia ocurrir en un
    `run-suite` normal (el corredor siempre cierra antes de devolver), pero
    el serializador no debe romper si alguna vez recibe una corrida EN_CURSO.
    """
    if corrida.finalizada_en is None:
        return None
    return (corrida.finalizada_en - corrida.iniciada_en).total_seconds()


def _corrida_a_json(corrida, items) -> dict:
    """Construido campo por campo -nunca `dataclasses.asdict()`-, para que el
    esquema quede estable y no dependa de la forma interna de `CorridaSuite`.
    """
    return {
        "version": VERSION_JSON_CLI,
        "suite_id": corrida.suite_id,
        "suite_nombre": corrida.suite_nombre,
        "corrida_id": corrida.corrida_id,
        "estado": corrida.estado.value,
        "resultado": corrida.resultado_global.value if corrida.resultado_global else None,
        "iniciada_en": corrida.iniciada_en.isoformat(),
        "finalizada_en": corrida.finalizada_en.isoformat() if corrida.finalizada_en else None,
        "duracion_s": _duracion_s(corrida),
        "contadores": {
            "total": corrida.total,
            "pass": corrida.cantidad_pass,
            "fail": corrida.cantidad_fail,
            "error": corrida.cantidad_error,
            "sin_expectativas": corrida.cantidad_sin_expectativas,
            "no_ejecutado": corrida.cantidad_no_ejecutado,
        },
        "items": [_item_a_json(item) for item in items],
    }


def _item_a_json(item) -> dict:
    return {
        "orden": item.orden,
        "escenario_id": item.escenario_id,
        "escenario_nombre": item.escenario_nombre,
        "resultado": item.resultado.value,
        "detalle": item.detalle,
        "ejecucion_id": item.ejecucion_id,
        # El snapshot literal del propio item -json.loads, nunca recalculado
        # ni releido de un escenario vivo-. `None` para ERROR/SIN_EXPECTATIVAS/
        # NO_EJECUTADO, donde `evaluacion_json` ya es `None`.
        "evaluacion": json.loads(item.evaluacion_json) if item.evaluacion_json else None,
    }


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
    duracion = _duracion_s(corrida)
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

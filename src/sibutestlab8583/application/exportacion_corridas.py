"""Bloque 7: reporte portable y autosuficiente de UNA corrida de suite ya
persistida -exportable como JSON o CSV, sin depender de la base viva mas alla
de leer la corrida en si, ni de la interfaz web.

Servicio neutral de aplicacion: ni `cli.py` ni la web se importan entre si.
Ambos ya convergen en `application/presentacion_evaluacion.py` para lo mismo
(ver su docstring); este modulo sigue exactamente ese precedente para que
`export-run` (CLI) y una futura ruta web de descarga puedan reutilizar la
MISMA logica sin que ninguna de las dos dependa de la otra.

Nunca reconstruye nada desde el escenario vivo, la suite viva ni las
expectativas actuales: recibe ya cargados un `CorridaSuite` y su
`Sequence[ItemCorridaSuite]` (el llamador los obtiene del repositorio), y solo
lee lo que esos snapshots ya persisten -`ItemCorridaSuite.evaluacion_json` es
una copia LITERAL, nunca se re-evalua Expected vs Actual aqui-. Por
construccion, esta funcion no recibe ni consulta ningun repositorio de
tarjetas ni de escenarios: no hay forma de que termine leyendo un PAN.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Mapping, Sequence

from .presentacion_evaluacion import mensaje_de_discrepancia

#: Version del esquema de exportacion. Propia de este modulo, independiente de
#: VERSION_JSON_CLI (`cli.py`) y de VERSION_EXPECTATIVAS/VERSION_FORMATO
#: (`domain/expectativas.py`/`serializacion.py`): cada una versiona una cosa
#: distinta y evoluciona por separado.
VERSION_REPORTE_CORRIDA = 1

#: Encabezado exacto y orden estable de columnas del CSV -una fila por item-.
#: Los campos de la corrida se repiten en cada fila (denormalizado a
#: proposito) para que el CSV sea autosuficiente: alguien que reciba solo ese
#: archivo no necesita un segundo archivo con los metadatos de la corrida.
ENCABEZADO_CSV = (
    "corrida_id", "suite_id", "suite_nombre", "corrida_estado", "corrida_resultado",
    "orden", "escenario_id", "escenario_nombre", "resultado", "detalle",
    "ejecucion_id", "evaluacion_estado", "discrepancias",
)


def duracion_s(corrida) -> float | None:
    """`None` si la corrida no esta finalizada -una corrida EN_CURSO (p. ej.
    interrumpida por un crash del proceso) no tiene duracion definida todavia.
    """
    if corrida.finalizada_en is None:
        return None
    return (corrida.finalizada_en - corrida.iniciada_en).total_seconds()


def _evaluacion_de_item(item) -> dict | None:
    """El snapshot de evaluacion tal cual quedo persistido -`None` para
    ERROR/SIN_EXPECTATIVAS/NO_EJECUTADO, donde `evaluacion_json` ya es `None`-.
    """
    return json.loads(item.evaluacion_json) if item.evaluacion_json else None


def _item_a_dict(item) -> dict:
    return {
        "orden": item.orden,
        "escenario_id": item.escenario_id,
        "escenario_nombre": item.escenario_nombre,
        "resultado": item.resultado.value,
        "detalle": item.detalle,
        "ejecucion_id": item.ejecucion_id,
        "evaluacion": _evaluacion_de_item(item),
    }


def reporte_de_corrida(corrida, items: Sequence) -> dict:
    """El reporte completo como `dict` -construido campo por campo, nunca
    `dataclasses.asdict()`, para que el esquema quede estable y no dependa de
    la forma interna de `CorridaSuite`/`ItemCorridaSuite`. Mismo criterio que
    ya usa `cli.py::_corrida_a_json` para `run-suite --format json`.
    """
    return {
        "version": VERSION_REPORTE_CORRIDA,
        "corrida_id": corrida.corrida_id,
        "suite_id": corrida.suite_id,
        "suite_nombre": corrida.suite_nombre,
        "estado": corrida.estado.value,
        # Clave "resultado" -no "resultado_global"- a proposito: preserva
        # exacto el esquema ya publicado por `run-suite --format json` desde
        # Bloque 5 (VERSION_JSON_CLI=1), que este modulo ahora construye. Un
        # cambio de nombre aqui romperia en silencio cualquier pipeline de CI
        # que ya parsee ese campo.
        "resultado": corrida.resultado_global.value if corrida.resultado_global else None,
        "iniciada_en": corrida.iniciada_en.isoformat(),
        "finalizada_en": corrida.finalizada_en.isoformat() if corrida.finalizada_en else None,
        "duracion_s": duracion_s(corrida),
        "contadores": {
            "total": corrida.total,
            "pass": corrida.cantidad_pass,
            "fail": corrida.cantidad_fail,
            "error": corrida.cantidad_error,
            "sin_expectativas": corrida.cantidad_sin_expectativas,
            "no_ejecutado": corrida.cantidad_no_ejecutado,
        },
        "items": [_item_a_dict(item) for item in items],
    }


def reporte_a_json(corrida, items: Sequence) -> str:
    return json.dumps(reporte_de_corrida(corrida, items), ensure_ascii=False)


def _discrepancias_legibles(item, descripciones: Mapping[str, str]) -> str:
    """Discrepancias como texto humano, unidas por "; " -mismo mensaje que ya
    usa `cli.py::_corrida_a_texto` y la web (`mensaje_de_discrepancia`), para
    que el CSV sea legible sin tener que parsear JSON anidado. Es la unica
    columna del CSV con texto compuesto en vez de un valor atomico: se
    justifica porque su contenido YA es una lista de mensajes pensados para
    lectura humana, no una estructura arbitraria.
    """
    evaluacion = _evaluacion_de_item(item)
    if not evaluacion:
        return ""
    mensajes = [
        mensaje_de_discrepancia(d, descripciones) for d in evaluacion.get("discrepancias", [])
    ]
    return "; ".join(mensajes)


def filas_csv(corrida, items: Sequence, descripciones: Mapping[str, str]) -> list[list[str]]:
    """Las filas del CSV, encabezado incluido, como listas de strings -para
    que quien quiera escribirlas con otro escritor (o probarlas sin pasar por
    el modulo `csv`) pueda hacerlo directo."""
    filas = [list(ENCABEZADO_CSV)]
    resultado_corrida = corrida.resultado_global.value if corrida.resultado_global else ""
    for item in items:
        evaluacion = _evaluacion_de_item(item)
        filas.append([
            str(corrida.corrida_id),
            corrida.suite_id,
            corrida.suite_nombre,
            corrida.estado.value,
            resultado_corrida,
            str(item.orden),
            item.escenario_id,
            item.escenario_nombre,
            item.resultado.value,
            item.detalle or "",
            str(item.ejecucion_id) if item.ejecucion_id is not None else "",
            evaluacion.get("resultado", "") if evaluacion else "",
            _discrepancias_legibles(item, descripciones),
        ])
    return filas


def reporte_a_csv(corrida, items: Sequence, descripciones: Mapping[str, str]) -> str:
    """CSV completo como texto -una fila por item, columnas estables
    (`ENCABEZADO_CSV`). `lineterminator="\\n"` a proposito: el modulo `csv`
    usa `\\r\\n` por defecto, lo que produciria fin de linea mixto si el
    llamador despues hace `print(texto)` (que ya agrega su propio `\\n`) o
    escribe el resultado tal cual a un archivo de texto.
    """
    buffer = io.StringIO()
    escritor = csv.writer(buffer, lineterminator="\n")
    escritor.writerows(filas_csv(corrida, items, descripciones))
    return buffer.getvalue()

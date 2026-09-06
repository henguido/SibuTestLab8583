"""Guardia de seguridad ESPECIFICA DE CI sobre el artefacto `corrida.json`
antes de publicarlo.

No es una garantia nueva: `sibu-run-suite --format json` ya construye su
salida campo por campo (`cli.py::_corrida_a_json`/`_item_a_json`) a partir de
`ItemCorridaSuite.evaluacion_json`, que por diseño de Bloque 3/4 nunca
contiene PAN ni los mensajes ISO crudos. Esto es una segunda comprobacion,
barata y especifica del artefacto que se sube a CI -mismo espiritu que la
guardia PAN de la suite de pruebas (`tests/test_datos_sinteticos.py`), pero
verificando el ARCHIVO que se publica, no el repositorio.

No busca nombres libres de escenario/campo como garantia de que "no hay PAN":
esa no es una prueba valida (un nombre puede decir cualquier cosa). La
afirmacion real sigue siendo la de siempre: el sistema no extrae ni copia PAN
desde tarjetas/mensajes hacia ningun snapshot persistido -esto solo confirma
que ese snapshot, tal como quedo escrito en el artefacto, no contradice esa
afirmacion.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

#: Igual patron que la guardia PAN de la suite (`tests/test_datos_sinteticos.py`),
#: acotado con lookaround para no contar un numero mas largo (por ejemplo un
#: id interno) como si fuera un PAN.
PATRON_PAN = re.compile(r"(?<!\d)\d{12,19}(?!\d)")

#: Claves/textos que NUNCA deberian aparecer en el JSON de una corrida: si
#: aparecen, es evidencia de que algo aguas arriba empezo a filtrar mensajes
#: ISO crudos o datos de tarjeta hacia el snapshot -un defecto real, no una
#: falsa alarma de este script.
CLAVES_PROHIBIDAS = (
    "solicitud_json",
    "respuesta_json",
    "solicitud_enmascarada",
    "respuesta_enmascarada",
    "pan_completo",
    "track1",
    "track2",
)


def hallazgos_en(contenido: str) -> list[str]:
    """Lista de problemas encontrados en `contenido`; vacia si esta limpio."""
    problemas: list[str] = []
    for numero, linea in enumerate(contenido.splitlines(), start=1):
        for coincidencia in PATRON_PAN.findall(linea):
            problemas.append(f"línea {numero}: secuencia de {len(coincidencia)} dígitos")
        minuscula = linea.lower()
        for clave in CLAVES_PROHIBIDAS:
            if clave in minuscula:
                problemas.append(f"línea {numero}: contiene {clave!r}")
    return problemas


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print("uso: verificar_artefacto_seguro.py <archivo>", file=sys.stderr)
        return 2

    ruta = Path(args[0])
    try:
        contenido = ruta.read_text(encoding="utf-8")
    except OSError as error:
        print(f"error: no se pudo leer {ruta}: {error}", file=sys.stderr)
        return 2

    problemas = hallazgos_en(contenido)
    if problemas:
        print(f"error: {ruta} no es seguro para publicar como artefacto:", file=sys.stderr)
        for problema in problemas:
            print(f"  {problema}", file=sys.stderr)
        return 1

    print(f"{ruta}: sin PAN ni claves prohibidas, apto para publicar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

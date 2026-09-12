"""`adapters/host_simulado/cli.py`: parseo de argumentos de `sibu-host-demo`.

Unico gap de cobertura real detectado en la auditoria de calidad de tests de
la jornada de agentes (hallazgo QA-002, ver docs/roadmap/SIBU_3.md): el
entry point real (`pyproject.toml`) no tenia ningun test dedicado. Se cubre
aqui solo `_argumentos` -defaults y overrides-, con el mismo patron que ya
usa `tests/test_ci_esperar_host.py` para el script equivalente. `_servir`/
`main` no se cubren con un test de arranque real: ya existe smoke-test de
socket real para el entry point analogo (`sibu-run-suite`) en
`test_auditoria_cobertura.py`, y levantar un servidor TCP real aqui solo para
probar el parseo de argumentos seria una prueba lenta que no agrega
confianza sobre lo que este archivo realmente necesitaba cubrir.
"""

from __future__ import annotations

import pytest

from sibutestlab8583.adapters.host_simulado.cli import _argumentos
from sibutestlab8583.composicion import HOST_POR_DEFECTO, PUERTO_POR_DEFECTO


def test_argumentos_usa_los_defaults_de_composicion_sin_flags():
    argumentos = _argumentos([])
    assert argumentos.host == HOST_POR_DEFECTO
    assert argumentos.puerto == PUERTO_POR_DEFECTO
    assert argumentos.codigo == "00"


def test_host_y_puerto_son_parametrizables_por_argumentos():
    argumentos = _argumentos(["--host", "example.test", "--puerto", "9595"])
    assert argumentos.host == "example.test"
    assert argumentos.puerto == 9595


def test_codigo_es_parametrizable_por_argumentos():
    argumentos = _argumentos(["--codigo", "51"])
    assert argumentos.codigo == "51"


def test_puerto_no_numerico_revienta_con_error_de_argparse():
    with pytest.raises(SystemExit):
        _argumentos(["--puerto", "no-es-un-numero"])

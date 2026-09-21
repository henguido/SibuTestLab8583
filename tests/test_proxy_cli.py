"""`adapters/proxy/cli.py`: parseo de argumentos de `sibu-proxy` -mismo
patron y mismo alcance que `test_host_simulado_cli.py`: solo `_argumentos`
(defaults y overrides), no un arranque real de servidor aqui (eso ya lo
cubren los E2E de `test_proxy_e2e.py`, que SI levantan el proxy real)."""

from __future__ import annotations

import pytest

from sibutestlab8583.adapters.proxy.cli import PUERTO_PROXY_POR_DEFECTO, _argumentos
from sibutestlab8583.composicion import HOST_POR_DEFECTO


def test_argumentos_usa_los_defaults_sin_flags():
    argumentos = _argumentos([])
    assert argumentos.host == HOST_POR_DEFECTO
    assert argumentos.puerto == PUERTO_PROXY_POR_DEFECTO
    assert argumentos.upstream_host is None
    assert argumentos.upstream_puerto is None


def test_puerto_de_escucha_es_distinto_del_puerto_por_defecto_del_host_simulado():
    """El proxy y `sibu-host-demo` deben poder correr a la vez (demo de
    tres terminales) sin chocar de puerto por defecto."""
    from sibutestlab8583.composicion import PUERTO_POR_DEFECTO
    assert PUERTO_PROXY_POR_DEFECTO != PUERTO_POR_DEFECTO


def test_upstream_es_parametrizable_por_argumentos():
    argumentos = _argumentos(["--upstream-host", "example.test", "--upstream-puerto", "9595"])
    assert argumentos.upstream_host == "example.test"
    assert argumentos.upstream_puerto == 9595


def test_puerto_no_numerico_revienta_con_error_de_argparse():
    with pytest.raises(SystemExit):
        _argumentos(["--puerto", "no-es-un-numero"])

"""E2E con PROCESOS reales de `sibu-host-demo` y `sibu-proxy` (Fase E1,
2026-09-21) -mismo patron que `test_d2_restart_real.py` para D2: procesos
del sistema operativo de verdad, lanzados con `python -m ...` (no depende
de que el directorio `Scripts` este en el PATH del shell que corre pytest),
no instancias de clase dentro del proceso de la prueba.

Pila real completa: cliente (Orquestador real) -> `sibu-proxy` (proceso
real) -> `sibu-host-demo` (proceso real)."""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

from conftest import construir_orquestador
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.adapters.transporte.tcp import TransporteTcp
from sibutestlab8583.domain.modelos import DatosEcho, DestinoTcp, EstadoEjecucion

_PATRON_ESCUCHA_HOST = re.compile(r"escuchando en (\S+):(\d+)")
_PATRON_ESCUCHA_PROXY = re.compile(r"escuchando en (\S+):(\d+), upstream")
_TIMEOUT_ARRANQUE = 10.0


def _lanzar(modulo: str, argumentos: list[str], base: Path) -> subprocess.Popen:
    entorno = dict(os.environ)
    entorno["SIBU_DB_PATH"] = str(base)
    entorno["PYTHONUNBUFFERED"] = "1"
    return subprocess.Popen(
        [sys.executable, "-m", modulo, *argumentos],
        env=entorno, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )


def _esperar_puerto(proceso: subprocess.Popen, patron: re.Pattern) -> int:
    limite = time.monotonic() + _TIMEOUT_ARRANQUE
    while time.monotonic() < limite:
        if proceso.poll() is not None:
            salida = proceso.stdout.read() if proceso.stdout else ""
            raise RuntimeError(f"el proceso termino antes de escuchar:\n{salida}")
        linea = proceso.stdout.readline()
        coincidencia = patron.search(linea)
        if coincidencia:
            return int(coincidencia.group(2))
    raise TimeoutError("el proceso no informo estar escuchando a tiempo")


def _detener(proceso: subprocess.Popen) -> None:
    if proceso.poll() is None:
        proceso.terminate()
        try:
            proceso.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proceso.kill()
            proceso.wait(timeout=5)


async def test_echo_real_a_traves_de_dos_procesos_reales(base):
    """Primera E2E del encargo (punto 24), con PROCESOS reales de extremo a
    extremo: `sibu-host-demo` y `sibu-proxy`, cada uno su propio PID."""
    proceso_host = _lanzar(
        "sibutestlab8583.adapters.host_simulado.cli", ["--host", "127.0.0.1", "--puerto", "0"], base,
    )
    try:
        puerto_host = _esperar_puerto(proceso_host, _PATRON_ESCUCHA_HOST)

        proceso_proxy = _lanzar(
            "sibutestlab8583.adapters.proxy.cli",
            ["--host", "127.0.0.1", "--puerto", "0",
             "--upstream-host", "127.0.0.1", "--upstream-puerto", str(puerto_host)],
            base,
        )
        try:
            assert proceso_proxy.pid != proceso_host.pid
            puerto_proxy = _esperar_puerto(proceso_proxy, _PATRON_ESCUCHA_PROXY)

            transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
            orquestador = construir_orquestador(
                base, transporte, destino=DestinoTcp(host="127.0.0.1", puerto=puerto_proxy),
                tiempo_limite=2.0,
            )
            resultado = await orquestador.ejecutar_network_echo(DatosEcho())
        finally:
            _detener(proceso_proxy)
    finally:
        _detener(proceso_host)

    assert resultado.estado is EstadoEjecucion.APROBADA

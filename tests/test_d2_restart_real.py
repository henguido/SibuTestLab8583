"""Cierre del gap de restart de D2 (2026-09-14): la seccion J del checkpoint
D2 senalo explicitamente que la persistencia del contador de aplicaciones
solo se habia verificado por analogia con `secuencias.valor` (STAN), nunca
con una prueba literal de reinicio de proceso. Esta prueba cierra ese punto.

Un PROCESO NUEVO de `sibu-host-demo` (no una instancia reiniciada dentro del
mismo proceso de la prueba) debe ver el mismo estado de una regla `max_
aplicaciones` que dejo un proceso anterior, ya muerto, en la misma base
SQLite -exactamente el escenario que el propietario pidio cerrar.

Se invoca el modulo con `python -m ...` (no el entry point `sibu-host-demo`)
para no depender de que el directorio `Scripts` este en el PATH del shell
que corre pytest -el artefacto de PATH ya documentado en otras fases de
este proyecto; el modulo es el mismo codigo que instala el entry point,
asi que el proceso lanzado es identico en comportamiento.
"""

from __future__ import annotations

import os
import re
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.adapters.transporte.tcp import TransporteTcp
from sibutestlab8583.application.reglas_host import DatosNuevaRegla, ServicioReglasHost
from sibutestlab8583.adapters.persistence.sqlite_repos import RepositorioReglasHostSQLite
from sibutestlab8583.domain.modelos import DatosEcho, DestinoTcp, EstadoEjecucion
from sibutestlab8583.domain.reglas_host import (
    CAMPO_MTI,
    ComportamientoRegla,
    CondicionRegla,
    TipoComportamiento,
)
from sibutestlab8583.profiles.generico import PERFIL_GENERICO

from conftest import construir_orquestador

_PATRON_ESCUCHA = re.compile(r"escuchando en (\S+):(\d+)")
_TIMEOUT_ARRANQUE = 10.0


def _lanzar_host_subproceso(base: Path) -> subprocess.Popen:
    """Un proceso NUEVO de verdad -no una instancia de clase dentro del
    proceso de la prueba-, ejecutando el mismo modulo que `sibu-host-demo`.
    `--puerto 0` deja que el sistema operativo asigne un puerto efimero
    libre, evitando conflictos con un `sibu-host-demo` real que el usuario
    pueda tener corriendo en el 8583 por su cuenta."""
    entorno = dict(os.environ)
    entorno["SIBU_DB_PATH"] = str(base)
    entorno["PYTHONUNBUFFERED"] = "1"
    return subprocess.Popen(
        [sys.executable, "-m", "sibutestlab8583.adapters.host_simulado.cli",
         "--host", "127.0.0.1", "--puerto", "0"],
        env=entorno, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )


def _esperar_puerto(proceso: subprocess.Popen) -> int:
    """Lee stdout linea a linea hasta ver el aviso real de arranque -nunca
    un sleep fijo: si el proceso tarda mas o menos, la prueba se adapta."""
    limite = time.monotonic() + _TIMEOUT_ARRANQUE
    while time.monotonic() < limite:
        if proceso.poll() is not None:
            salida = proceso.stdout.read() if proceso.stdout else ""
            raise RuntimeError(f"El proceso del host termino antes de escuchar:\n{salida}")
        linea = proceso.stdout.readline()
        coincidencia = _PATRON_ESCUCHA.search(linea)
        if coincidencia:
            return int(coincidencia.group(2))
    raise TimeoutError("El host simulado no informo estar escuchando a tiempo")


def _detener_proceso(proceso: subprocess.Popen) -> None:
    if proceso.poll() is None:
        proceso.terminate()
        try:
            proceso.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proceso.kill()
            proceso.wait(timeout=5)


def _puerto_sigue_escuchando(host: str, puerto: int) -> bool:
    try:
        with socket.create_connection((host, puerto), timeout=0.5):
            return True
    except OSError:
        return False


async def _echo(base: Path, host: str, puerto: int, tiempo_limite: float):
    transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=tiempo_limite)
    orquestador = construir_orquestador(
        base, transporte, destino=DestinoTcp(host=host, puerto=puerto),
        tiempo_limite=tiempo_limite,
    )
    return await orquestador.ejecutar_network_echo(DatosEcho())


async def test_restart_real_del_proceso_preserva_el_contador_de_aplicaciones(base):
    """Prueba de fuego del cierre de D2: crea las dos reglas del encargo
    (timeout limitado a 1 aplicacion + fallback normal), levanta un PROCESO
    real de `sibu-host-demo`, consume la regla limitada, MATA el proceso,
    confirma que ya no escucha, levanta un proceso NUEVO sobre la MISMA
    base SQLite, y confirma que el estado (contador agotado) sobrevivio."""
    servicio = ServicioReglasHost(RepositorioReglasHostSQLite(base), PERFIL_GENERICO)
    regla_timeout = await servicio.crear(DatosNuevaRegla(
        nombre="Timeout primer intento (restart D2)", prioridad=10,
        condiciones=[CondicionRegla(CAMPO_MTI, "igual", "0800")],
        de39="00", comportamiento=ComportamientoRegla(tipo=TipoComportamiento.TIMEOUT.value),
        max_aplicaciones=1,
    ))
    regla_fallback = await servicio.crear(DatosNuevaRegla(
        nombre="Normal despues (restart D2)", prioridad=20,
        condiciones=[CondicionRegla(CAMPO_MTI, "igual", "0800")],
        de39="00",
    ))

    # --- Proceso 1: consume la regla limitada -----------------------------
    proceso_1 = _lanzar_host_subproceso(base)
    try:
        puerto_1 = _esperar_puerto(proceso_1)

        r1 = await _echo(base, "127.0.0.1", puerto_1, tiempo_limite=0.5)
        assert r1.estado is EstadoEjecucion.TIMEOUT
    finally:
        _detener_proceso(proceso_1)

    # --- El proceso murio de verdad: ya no escucha en ese puerto -----------
    assert proceso_1.poll() is not None
    assert not _puerto_sigue_escuchando("127.0.0.1", puerto_1)

    # --- El contador quedo persistido en SQLite, sin ningun proceso vivo ---
    conexion = sqlite3.connect(str(base))
    try:
        fila = conexion.execute(
            "SELECT aplicaciones_consumidas FROM reglas_host_estado WHERE regla_id = ?",
            (regla_timeout.regla_id,),
        ).fetchone()
        assert fila == (1,)
    finally:
        conexion.close()

    # --- Proceso 2: PID nuevo, mismo archivo SQLite ------------------------
    proceso_2 = _lanzar_host_subproceso(base)
    try:
        assert proceso_2.pid != proceso_1.pid
        puerto_2 = _esperar_puerto(proceso_2)

        r2 = await _echo(base, "127.0.0.1", puerto_2, tiempo_limite=2.0)
        assert r2.estado is EstadoEjecucion.APROBADA  # la regla agotada cedio al fallback
    finally:
        _detener_proceso(proceso_2)

    # --- El contador NO subio de nuevo: la regla seguia agotada ------------
    conexion = sqlite3.connect(str(base))
    try:
        fila = conexion.execute(
            "SELECT aplicaciones_consumidas FROM reglas_host_estado WHERE regla_id = ?",
            (regla_timeout.regla_id,),
        ).fetchone()
        assert fila == (1,)

        eventos = conexion.execute(
            "SELECT regla_id, match_number FROM reglas_host_eventos ORDER BY evento_id"
        ).fetchall()
        assert eventos == [
            (regla_timeout.regla_id, 1),
            (regla_fallback.regla_id, None),
        ]

        violaciones = conexion.execute("PRAGMA foreign_key_check").fetchall()
        assert violaciones == []
    finally:
        conexion.close()

"""Espera hasta que un host:puerto TCP acepte conexiones, o falla con un
mensaje claro tras un timeout.

Pensado para el paso de un pipeline de CI que recien lanzo `sibu-host-demo`
en segundo plano y necesita saber cuando ya esta escuchando antes de disparar
`sibu-run-suite`: sin este paso, la suite correria contra un puerto que
todavia no acepta conexiones y cada escenario terminaria en ERROR por una
carrera de arranque, no por un problema real que valga la pena reportar.

Solo libreria estandar -ningun CI necesita instalar nada adicional para
correrlo-. Mismo patron de chequeo TCP ya documentado en
`.claude/skills/levantar-demo/SKILL.md` para la verificacion manual del host
simulado; este script lo deja reutilizable como paso de pipeline, no solo
como ejemplo de codigo dentro de un skill.

No es parte del paquete instalado (`sibutestlab8583`): vive en `scripts/`
porque es una utilidad de pipeline, no logica de producto -mismo criterio que
ya aplica `demo.cmd`, que tampoco es una via de instalacion alternativa.
"""

from __future__ import annotations

import argparse
import socket
import sys
import time

HOST_POR_DEFECTO = "127.0.0.1"
PUERTO_POR_DEFECTO = 8583
TIMEOUT_POR_DEFECTO = 15.0
INTERVALO_POR_DEFECTO = 0.2


def _argumentos(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="ci_esperar_host",
        description=(
            "Espera hasta que host:puerto acepte conexiones TCP, o falla "
            "tras un timeout (exit code != 0)."
        ),
    )
    parser.add_argument("--host", default=HOST_POR_DEFECTO, help="host a sondear")
    parser.add_argument(
        "--puerto", type=int, default=PUERTO_POR_DEFECTO, help="puerto a sondear"
    )
    parser.add_argument(
        "--timeout", type=float, default=TIMEOUT_POR_DEFECTO,
        help="segundos totales de espera antes de darse por vencido",
    )
    parser.add_argument(
        "--intervalo", type=float, default=INTERVALO_POR_DEFECTO,
        help="segundos entre cada intento de conexion",
    )
    return parser.parse_args(argv)


def puerto_acepta_conexion(host: str, puerto: int, *, timeout: float = 1.0) -> bool:
    """Un unico intento de conexion. `True` solo si se establece de verdad -
    nunca se interpreta un timeout de socket como "todavia no, reintentar
    despues": eso lo decide `esperar()`, no este intento individual."""
    try:
        with socket.create_connection((host, puerto), timeout=timeout):
            return True
    except OSError:
        return False


def esperar(
    host: str, puerto: int, *, timeout: float, intervalo: float = INTERVALO_POR_DEFECTO
) -> bool:
    """Sondea `host:puerto` hasta `timeout` segundos en total. `True` apenas
    una conexion se establece; `False` si se agota el tiempo sin exito -nunca
    lanza, para que el llamador decida el mensaje y el codigo de salida."""
    limite = time.monotonic() + timeout
    intento_timeout = min(1.0, intervalo) if intervalo > 0 else 1.0
    while time.monotonic() < limite:
        if puerto_acepta_conexion(host, puerto, timeout=intento_timeout):
            return True
        time.sleep(intervalo)
    return puerto_acepta_conexion(host, puerto, timeout=intento_timeout)


def main(argv: list[str] | None = None) -> int:
    args = _argumentos(sys.argv[1:] if argv is None else argv)
    if esperar(args.host, args.puerto, timeout=args.timeout, intervalo=args.intervalo):
        print(f"{args.host}:{args.puerto} responde.")
        return 0
    print(
        f"error: {args.host}:{args.puerto} no aceptó conexiones dentro de "
        f"{args.timeout:.0f}s.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())

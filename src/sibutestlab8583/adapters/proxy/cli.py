"""Comando `sibu-proxy`: levanta el proxy ISO 8583 transparente como proceso
aparte -mismo patron que `sibu-host-demo` (`adapters/host_simulado/cli.py`).

La aplicacion web no lo arranca. La demostracion completa usa tres
terminales:

    Terminal 1:  sibu-host-demo
    Terminal 2:  sibu-proxy --upstream-puerto 8583
    Terminal 3:  uvicorn sibutestlab8583.web.app:app --reload
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib

from ...composicion import HOST_POR_DEFECTO, Composicion, Configuracion
from ...domain.modelos import DestinoTcp

#: Puerto de escucha por defecto del proxy -distinto de
#: `composicion.PUERTO_POR_DEFECTO` (8583, el del host simulado): ambos
#: procesos deben poder correr a la vez en la demostracion de tres
#: terminales sin chocar.
PUERTO_PROXY_POR_DEFECTO = 8584


def _argumentos(argv: list[str] | None = None) -> argparse.Namespace:
    """`argv=None` (el caso real de `main()`) delega en `sys.argv`; un
    `argv` explicito solo existe para que las pruebas construyan argumentos
    sin tocar `sys.argv` global -mismo patron que `host_simulado/cli.py`."""
    analizador = argparse.ArgumentParser(
        prog="sibu-proxy",
        description="Proxy TCP ISO 8583 transparente: reenvia frames entre un cliente y un upstream.",
    )
    analizador.add_argument("--host", default=HOST_POR_DEFECTO, help="interfaz de escucha")
    analizador.add_argument(
        "--puerto", type=int, default=PUERTO_PROXY_POR_DEFECTO, help="puerto de escucha"
    )
    analizador.add_argument(
        "--upstream-host", default=None,
        help="host del upstream (por defecto, SIBU_HOST_DESTINO o su default)",
    )
    analizador.add_argument(
        "--upstream-puerto", type=int, default=None,
        help="puerto del upstream (por defecto, SIBU_PUERTO_DESTINO o su default)",
    )
    return analizador.parse_args(argv)


async def _servir(host: str, puerto: int, upstream_host: str | None, upstream_puerto: int | None) -> None:
    configuracion = Configuracion.desde_entorno()
    destino_upstream = DestinoTcp(
        host=upstream_host or configuracion.host_destino,
        puerto=upstream_puerto or configuracion.puerto_destino,
    )
    proxy = Composicion(configuracion).proxy(destino_upstream)
    direccion, puerto_real = await proxy.iniciar(host, puerto)
    print(f"Proxy escuchando en {direccion}:{puerto_real}, upstream {destino_upstream}.")
    print("Ctrl+C para detener.")
    try:
        await asyncio.Event().wait()
    finally:
        await proxy.detener()
        print(f"\nDetenido. Sesiones atendidas: {proxy.sesiones_atendidas}")


def main() -> None:
    argumentos = _argumentos()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_servir(
            argumentos.host, argumentos.puerto, argumentos.upstream_host, argumentos.upstream_puerto
        ))


if __name__ == "__main__":
    main()

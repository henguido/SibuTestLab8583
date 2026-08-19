"""Comando `sibu-host-demo`: levanta el host simulado como proceso aparte.

La aplicacion web no lo arranca. La arquitectura lo mantiene separado, y la
demostracion usa dos terminales:

    Terminal 1:  sibu-host-demo
    Terminal 2:  uvicorn sibutestlab8583.web.app:app --reload
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib

from ...composicion import Composicion, Configuracion

PUERTO_POR_DEFECTO = 8583


def _argumentos() -> argparse.Namespace:
    analizador = argparse.ArgumentParser(
        prog="sibu-host-demo",
        description="Host simulado que responde 0110 a una compra 0100.",
    )
    analizador.add_argument("--host", default="127.0.0.1", help="interfaz de escucha")
    analizador.add_argument(
        "--puerto", type=int, default=PUERTO_POR_DEFECTO, help="puerto de escucha"
    )
    analizador.add_argument(
        "--codigo",
        default="00",
        help="codigo de respuesta del campo 39 (00 aprueba; 05, 14, 51, 54 y 94 rechazan)",
    )
    return analizador.parse_args()


async def _servir(host: str, puerto: int, codigo: str) -> None:
    simulado = Composicion(Configuracion.desde_entorno()).host_simulado(codigo_respuesta=codigo)
    direccion, puerto_real = await simulado.iniciar(host, puerto)
    print(f"Host simulado escuchando en {direccion}:{puerto_real}")
    print(f"Responde el codigo {codigo}. Ctrl+C para detener.")
    try:
        await asyncio.Event().wait()
    finally:
        await simulado.detener()
        print(f"\nDetenido. Solicitudes atendidas: {simulado.solicitudes_recibidas}")


def main() -> None:
    argumentos = _argumentos()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(_servir(argumentos.host, argumentos.puerto, argumentos.codigo))


if __name__ == "__main__":
    main()

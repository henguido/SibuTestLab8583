"""D-1: RN-1 debe responder al catalogo persistido en SQLite, no a una constante.

Antes de esta iteracion, `Composicion.orquestador()` construia el orquestador
con `CATALOGO_GENERICO` (una constante en memoria, definida en
`domain/catalogo.py`), y `RepositorioCatalogosSQLite` no tenia ningun
consumidor en produccion: cambiar la tabla `codigos_respuesta` no cambiaba el
comportamiento de RN-1. Estas pruebas construyen el sistema con la
composicion REAL (no con `construir_orquestador` de `conftest.py`, que sigue
cableando la constante a proposito para las pruebas de reglas de negocio) y
comprueban, en las dos direcciones, que RN-1 respeta lo que dice la base.
"""

from __future__ import annotations

import sqlite3

from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.esquema import inicializar
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.composicion import Composicion, Configuracion
from sibutestlab8583.domain.modelos import DestinoTcp, EstadoEjecucion
from sibutestlab8583.profiles.generico import PERFIL_GENERICO


def _host(codigo_respuesta: str) -> HostSimulado:
    return HostSimulado(
        CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), codigo_respuesta=codigo_respuesta
    )


def _fijar_aprobacion(ruta, codigo: str, *, aprobado: bool) -> None:
    """Edita el catalogo ya sembrado, como lo haria un administrador via SQL."""
    with sqlite3.connect(ruta) as conexion:
        conexion.execute(
            "UPDATE codigos_respuesta SET aprobado = ? WHERE catalogo = 'generico' AND codigo = ?",
            (int(aprobado), codigo),
        )
        conexion.commit()


async def _ejecutar_con_composicion_real(ruta, host: HostSimulado, datos_compra):
    composicion = Composicion(Configuracion(ruta_base_datos=ruta))
    async with host:
        destino = DestinoTcp(host=host.host, puerto=host.puerto)
        orquestador = await composicion.orquestador(destino)
        return await orquestador.ejecutar_compra(datos_compra)


async def test_codigo_00_marcado_como_rechazado_en_sqlite_da_rechazada(tmp_path, datos_compra):
    """Direccion 1: un codigo normalmente aprobado, si se rechaza en la base, rechaza."""
    ruta = await inicializar(tmp_path / "catalogo.db")
    _fijar_aprobacion(ruta, "00", aprobado=False)

    resultado = await _ejecutar_con_composicion_real(ruta, _host("00"), datos_compra)

    assert resultado.estado is EstadoEjecucion.RECHAZADA
    assert not resultado.aprobada


async def test_codigo_normalmente_rechazado_marcado_como_aprobado_en_sqlite_da_aprobada(
    tmp_path, datos_compra
):
    """Direccion 2: un codigo normalmente rechazado, si se aprueba en la base, aprueba."""
    ruta = await inicializar(tmp_path / "catalogo.db")
    _fijar_aprobacion(ruta, "51", aprobado=True)

    resultado = await _ejecutar_con_composicion_real(ruta, _host("51"), datos_compra)

    assert resultado.estado is EstadoEjecucion.APROBADA
    assert resultado.aprobada


async def test_sin_editar_el_catalogo_el_comportamiento_de_la_semilla_no_cambia(
    tmp_path, datos_compra
):
    """La semilla sigue siendo la misma: 00 aprueba, los demas no, sin tocar nada."""
    ruta = await inicializar(tmp_path / "catalogo.db")

    aprobado = await _ejecutar_con_composicion_real(ruta, _host("00"), datos_compra)
    rechazado = await _ejecutar_con_composicion_real(ruta, _host("05"), datos_compra)

    assert aprobado.estado is EstadoEjecucion.APROBADA
    assert rechazado.estado is EstadoEjecucion.RECHAZADA

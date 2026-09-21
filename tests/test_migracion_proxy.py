"""Migracion aditiva del esquema del Proxy (Fase E1, 2026-09-21):
`proxy_sesiones`/`proxy_mensajes` nacen con cualquier base nueva y la
inicializacion es idempotente -mismo patron que `test_migracion_reglas_host.
py` para D1/D2."""

from __future__ import annotations

import sqlite3

from sibutestlab8583.adapters.persistence.esquema import inicializar


async def test_una_base_nueva_ya_nace_con_las_tablas_del_proxy(base):
    with sqlite3.connect(base) as conexion:
        nombres = {
            fila[0]
            for fila in conexion.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
    assert "proxy_sesiones" in nombres
    assert "proxy_mensajes" in nombres


async def test_inicializar_es_idempotente_sobre_las_tablas_del_proxy(base):
    await inicializar(base)
    await inicializar(base)
    with sqlite3.connect(base) as conexion:
        columnas_sesiones = {r[1] for r in conexion.execute("PRAGMA table_info(proxy_sesiones)")}
        columnas_mensajes = {r[1] for r in conexion.execute("PRAGMA table_info(proxy_mensajes)")}
    assert columnas_sesiones == {
        "session_id", "cliente_host", "cliente_puerto", "upstream_host",
        "upstream_puerto", "estado", "motivo_cierre", "inicio", "fin",
    }
    assert columnas_mensajes == {
        "mensaje_id", "session_id", "direccion", "orden", "longitud",
        "mti", "interpretable", "creado_en",
    }


async def test_proxy_mensajes_tiene_fk_hacia_proxy_sesiones(base):
    with sqlite3.connect(base) as conexion:
        conexion.execute("PRAGMA foreign_keys = ON")
        try:
            conexion.execute(
                "INSERT INTO proxy_mensajes"
                " (session_id, direccion, orden, longitud, mti, interpretable, creado_en)"
                " VALUES ('no-existe', 'cliente_a_upstream', 1, 10, '0800', 1, '2026-09-21T00:00:00+00:00')"
            )
            conexion.commit()
            fallo = False
        except sqlite3.IntegrityError:
            fallo = True
    assert fallo

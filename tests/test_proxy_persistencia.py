"""Persistencia de sesiones/mensajes del Proxy (Fase E1, 2026-09-21):
`crear`/`actualizar` sobre la misma fila, listar por sesion en orden, y la
garantia estructural de que `MensajeProxyCapturado` nunca puede cargar el
payload (ver `domain/proxy.py`)."""

from __future__ import annotations

from sibutestlab8583.adapters.persistence.sqlite_repos import (
    RepositorioMensajesProxySQLite,
    RepositorioSesionesProxySQLite,
)
from sibutestlab8583.domain.proxy import (
    DireccionMensajeProxy,
    EstadoSesionProxy,
    MensajeProxyCapturado,
    MotivoCierreProxy,
    SesionProxy,
)


def _sesion(session_id="S1"):
    return SesionProxy(
        session_id=session_id, cliente_host="127.0.0.1", cliente_puerto=51000,
        upstream_host="127.0.0.1", upstream_puerto=8583,
    )


async def test_crear_persiste_estado_conectando(base):
    repo = RepositorioSesionesProxySQLite(base)
    await repo.crear(_sesion())
    guardada = await repo.obtener("S1")
    assert guardada.estado is EstadoSesionProxy.CONECTANDO
    assert guardada.motivo_cierre is None
    assert guardada.fin is None


async def test_actualizar_es_siempre_la_misma_fila_nunca_una_nueva(base):
    repo = RepositorioSesionesProxySQLite(base)
    sesion = _sesion()
    await repo.crear(sesion)

    sesion.estado = EstadoSesionProxy.ACTIVA
    await repo.actualizar(sesion)
    sesion.estado = EstadoSesionProxy.CERRADA
    sesion.motivo_cierre = MotivoCierreProxy.EOF_CLIENTE
    from datetime import datetime, timezone
    sesion.fin = datetime.now(timezone.utc)
    await repo.actualizar(sesion)

    todas = await repo.listar()
    assert len(todas) == 1
    guardada = await repo.obtener("S1")
    assert guardada.estado is EstadoSesionProxy.CERRADA
    assert guardada.motivo_cierre is MotivoCierreProxy.EOF_CLIENTE
    assert guardada.fin is not None


async def test_listar_ordena_las_mas_recientes_primero(base):
    repo = RepositorioSesionesProxySQLite(base)
    await repo.crear(_sesion("S1"))
    await repo.crear(_sesion("S2"))
    todas = await repo.listar()
    assert {s.session_id for s in todas} == {"S1", "S2"}


async def test_mensajes_se_listan_por_sesion_en_orden(base):
    sesiones = RepositorioSesionesProxySQLite(base)
    await sesiones.crear(_sesion("S1"))
    mensajes = RepositorioMensajesProxySQLite(base)
    await mensajes.registrar(MensajeProxyCapturado(
        session_id="S1", direccion=DireccionMensajeProxy.CLIENTE_A_UPSTREAM,
        orden=2, longitud=10, mti="0800", interpretable=True,
    ))
    await mensajes.registrar(MensajeProxyCapturado(
        session_id="S1", direccion=DireccionMensajeProxy.UPSTREAM_A_CLIENTE,
        orden=1, longitud=20, mti=None, interpretable=False,
    ))
    filas = await mensajes.listar_por_sesion("S1")
    assert [f.orden for f in filas] == [1, 2]
    assert filas[0].mti is None
    assert filas[0].interpretable is False
    assert filas[1].mti == "0800"


async def test_mensaje_proxy_capturado_no_tiene_ningun_campo_para_el_payload():
    """Garantia ESTRUCTURAL (no de convencion): el dataclass no declara
    ningun campo `payload`/`raw`/`Mapping` que pudiera aceptar el contenido
    de un mensaje -mismo principio que `EventoReglaHost` en D1/D2."""
    campos = set(MensajeProxyCapturado.__dataclass_fields__)
    assert campos == {
        "session_id", "direccion", "orden", "longitud", "mti",
        "interpretable", "mensaje_id", "creado_en",
    }

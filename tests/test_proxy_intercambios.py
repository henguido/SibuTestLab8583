"""Correlacion de intercambios del Proxy (Fase E2, 2026-09-21):
`derivar_intercambios` es PURA -sin I/O, nunca persiste el intercambio,
ver el modulo `domain.proxy`- y nunca inventa una pareja por posicion."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sibutestlab8583.domain.proxy import (
    DireccionMensajeProxy,
    MensajeProxyCapturado,
    derivar_intercambios,
)

_T0 = datetime.now(timezone.utc)
C = DireccionMensajeProxy.CLIENTE_A_UPSTREAM
U = DireccionMensajeProxy.UPSTREAM_A_CLIENTE


def _m(mensaje_id, direccion, mti, *, interpretable=True, segundos=0, stan=None, rrn=None):
    return MensajeProxyCapturado(
        session_id="S", direccion=direccion, orden=1, longitud=10, mti=mti,
        interpretable=interpretable, mensaje_id=mensaje_id,
        creado_en=_T0 + timedelta(seconds=segundos), stan=stan, rrn=rrn,
    )


def test_correlaciona_0200_0210_por_mti_y_orden_temporal():
    mensajes = [_m(1, C, "0200", segundos=0), _m(2, U, "0210", segundos=1)]
    (intercambio,) = derivar_intercambios(mensajes)
    assert intercambio.correlacionado
    assert intercambio.respuesta.mensaje_id == 2


def test_correlaciona_0800_0810():
    mensajes = [_m(1, C, "0800", segundos=0), _m(2, U, "0810", segundos=1)]
    (intercambio,) = derivar_intercambios(mensajes)
    assert intercambio.correlacionado
    assert intercambio.respuesta.mti == "0810"


def test_solicitud_sin_respuesta_queda_no_correlacionada():
    """Punto 3 del encargo: nunca inventar pareja -un timeout/desconexion
    del upstream deja la solicitud sin respuesta, no con una inventada."""
    mensajes = [_m(1, C, "0200", segundos=0)]
    (intercambio,) = derivar_intercambios(mensajes)
    assert not intercambio.correlacionado
    assert intercambio.respuesta is None


def test_respuesta_huerfana_no_se_fuerza_a_una_solicitud_de_otro_mti():
    """Una respuesta que no calza con NINGUNA solicitud pendiente (MTI
    distinto) nunca se empareja con la mas cercana por posicion."""
    mensajes = [_m(1, C, "0800", segundos=0), _m(2, U, "0210", segundos=1)]
    (intercambio,) = derivar_intercambios(mensajes)
    assert not intercambio.correlacionado


def test_mensaje_no_interpretable_nunca_se_correlaciona():
    mensajes = [_m(1, C, None, interpretable=False, segundos=0), _m(2, U, None, interpretable=False, segundos=1)]
    (intercambio,) = derivar_intercambios(mensajes)
    assert not intercambio.correlacionado
    assert intercambio.solicitud.interpretable is False


def test_no_correlaciona_por_orden_cuando_el_orden_es_por_direccion():
    """El `orden` de `MensajeProxyCapturado` es un contador POR DIRECCION
    (ver `adapters.proxy.servidor`), nunca un indice global de la sesion:
    dos mensajes con el mismo `orden=1` en direcciones distintas NO deben
    asumirse correlacionados solo por eso -aqui el MTI de la respuesta no
    calza con lo esperado para la solicitud, y debe quedar sin pareja."""
    mensajes = [
        MensajeProxyCapturado(session_id="S", direccion=C, orden=1, longitud=10, mti="0800", mensaje_id=1, creado_en=_T0),
        MensajeProxyCapturado(session_id="S", direccion=U, orden=1, longitud=10, mti="0210", mensaje_id=2, creado_en=_T0 + timedelta(seconds=1)),
    ]
    (intercambio,) = derivar_intercambios(mensajes)
    assert not intercambio.correlacionado


def test_multiples_intercambios_en_una_sesion_full_duplex():
    mensajes = [
        _m(1, C, "0800", segundos=0), _m(2, C, "0200", segundos=1),
        _m(3, U, "0210", segundos=2), _m(4, U, "0810", segundos=3),
    ]
    intercambios = {i.solicitud.mensaje_id: i for i in derivar_intercambios(mensajes)}
    assert intercambios[1].respuesta.mensaje_id == 4  # 0800 -> 0810
    assert intercambios[2].respuesta.mensaje_id == 3  # 0200 -> 0210
    assert all(i.correlacionado for i in intercambios.values())


def test_una_respuesta_ya_consumida_no_se_reutiliza_para_otra_solicitud():
    """Dos solicitudes del mismo MTI, una sola respuesta: solo la primera
    (por tiempo) debe quedar correlacionada -la respuesta no se duplica."""
    mensajes = [
        _m(1, C, "0800", segundos=0), _m(2, C, "0800", segundos=1),
        _m(3, U, "0810", segundos=2),
    ]
    intercambios = derivar_intercambios(mensajes)
    correlacionados = [i for i in intercambios if i.correlacionado]
    assert len(correlacionados) == 1
    assert correlacionados[0].solicitud.mensaje_id == 1


# --- E2.1: correlacion robusta con STAN/RRN (2026-09-21) --------------------


def test_e2_1_respuestas_invertidas_se_correlacionan_por_stan_no_por_fifo():
    """Caso obligatorio A del encargo E2.1: dos 0200 en vuelo a la vez,
    full-duplex, con las respuestas llegando en el orden CONTRARIO al de
    las solicitudes. Un algoritmo puramente temporal (FIFO) emparejaria mal
    -A con la primera respuesta que llega (STAN 102)-; el STAN debe pesar
    mas que la posicion temporal."""
    mensajes = [
        _m(1, C, "0200", segundos=0, stan="000101"),  # solicitud A
        _m(2, C, "0200", segundos=1, stan="000102"),  # solicitud B
        _m(3, U, "0210", segundos=2, stan="000102"),  # respuesta B (llega primero)
        _m(4, U, "0210", segundos=3, stan="000101"),  # respuesta A (llega despues)
    ]
    intercambios = {i.solicitud.mensaje_id: i for i in derivar_intercambios(mensajes)}
    assert intercambios[1].correlacionado
    assert intercambios[1].respuesta.mensaje_id == 4  # A (stan 101) <-> resp stan 101
    assert intercambios[2].correlacionado
    assert intercambios[2].respuesta.mensaje_id == 3  # B (stan 102) <-> resp stan 102


def test_e2_1_mismo_mti_sin_correladores_queda_ambiguo():
    """Caso obligatorio B: dos solicitudes del mismo MTI, dos respuestas
    candidatas, NINGUNA trae un correlador -no hay forma confiable de
    saber cual es cual, y no debe adivinarse por FIFO."""
    mensajes = [
        _m(1, C, "0800", segundos=0), _m(2, C, "0800", segundos=1),
        _m(3, U, "0810", segundos=2), _m(4, U, "0810", segundos=3),
    ]
    intercambios = {i.solicitud.mensaje_id: i for i in derivar_intercambios(mensajes)}
    assert not intercambios[1].correlacionado
    assert not intercambios[2].correlacionado


def test_e2_1_captura_historica_sin_correladores_sigue_funcionando():
    """Caso obligatorio C: un unico par solicitud/respuesta sin stan/rrn
    (captura anterior a E2.1) debe seguir correlacionando por MTI + tiempo,
    exactamente como antes -compatibilidad hacia atras, punto 6 del
    encargo."""
    mensajes = [_m(1, C, "0200", segundos=0), _m(2, U, "0210", segundos=1)]
    (intercambio,) = derivar_intercambios(mensajes)
    assert intercambio.correlacionado
    assert intercambio.respuesta.mensaje_id == 2


def test_e2_1_no_exige_rrn_si_la_solicitud_no_lo_trae():
    """Punto 4 del encargo: nunca exigir DE37 si la solicitud no lo trae
    -alcanza con el STAN para desambiguar."""
    mensajes = [
        _m(1, C, "0200", segundos=0, stan="000101"),
        _m(2, U, "0210", segundos=1, stan="000101", rrn="RRN-A01"),
    ]
    (intercambio,) = derivar_intercambios(mensajes)
    assert intercambio.correlacionado


def test_e2_1_rrn_desambigua_cuando_no_hay_stan():
    """El RRN puede desambiguar por si solo cuando el STAN no esta
    disponible en la solicitud."""
    mensajes = [
        _m(1, C, "0200", segundos=0, rrn="RRN-A01"),
        _m(2, C, "0200", segundos=1, rrn="RRN-B02"),
        _m(3, U, "0210", segundos=2, rrn="RRN-B02"),
        _m(4, U, "0210", segundos=3, rrn="RRN-A01"),
    ]
    intercambios = {i.solicitud.mensaje_id: i for i in derivar_intercambios(mensajes)}
    assert intercambios[1].respuesta.mensaje_id == 4
    assert intercambios[2].respuesta.mensaje_id == 3

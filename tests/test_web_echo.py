"""Rutas web de Echo de red (0800/0810, B2): GET /echo (formulario + vista
previa), POST /echo (cambiar conexion/actualizar vista previa sin ejecutar),
POST /echo/ejecutar (ejecucion real).

Mismo estilo que `test_web.py` para compra: `ComposicionFalsa`/`OrquestadorFalso`
como dobles, sin SQLite ni TCP reales -esos ya estan cubiertos por
`tests/test_echo_e2e.py`-. Cubre ademas los dos hallazgos de la auditoria
manual en navegador: el campo oculto `conexion_id` (sin el, "Ejecutar echo"
fallaba con "seleccione una conexión") y el titulo del isoscopio (debia leer
el MTI real, no un literal "0100"/"0110" heredado de compra).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from sibutestlab8583.domain.modelos import (
    CampoInterpretado,
    Ejecucion,
    EstadoEjecucion,
    MensajeInterpretado,
    MensajeIso,
    MTI_ECHO,
    MTI_RESPUESTA_ECHO,
    ResultadoCompra,
)
from sibutestlab8583.web.app import crear_app

from test_web import CARD_ID_DEMO, ComposicionFalsa, DESTINO_ID_DEMO

MOMENTO = datetime(2026, 9, 13, 0, 0, 0, tzinfo=timezone.utc)


def _resultado_echo(estado, *, codigo="00", con_respuesta=True):
    from sibutestlab8583.application.serializacion import (
        a_json_respuesta,
        a_json_solicitud,
        a_texto,
    )

    solicitud = MensajeIso(MTI_ECHO, {"7": "0913000000", "11": "000099", "70": "301"})
    respuesta = None
    if con_respuesta:
        respuesta = MensajeInterpretado(
            MTI_RESPUESTA_ECHO,
            {
                "7": CampoInterpretado("7", "0913000000", "0913000000", ""),
                "11": CampoInterpretado("11", "000099", "000099", ""),
                "39": CampoInterpretado("39", codigo, codigo, "Código de respuesta"),
                "70": CampoInterpretado("70", "301", "301", ""),
            },
        )
    ejecucion = Ejecucion(
        id=99,
        card_id=None,
        monto=None,
        moneda=None,
        stan="000099",
        estado=estado,
        mti_solicitud=MTI_ECHO,
        mti_respuesta=MTI_RESPUESTA_ECHO if con_respuesta else None,
        codigo_respuesta=codigo,
        destino_host="127.0.0.1",
        destino_puerto=8583,
        solicitud_enmascarada=a_texto(solicitud),
        respuesta_enmascarada=a_texto(respuesta.como_mensaje()) if respuesta else None,
        solicitud_json=a_json_solicitud(solicitud, "generico"),
        respuesta_json=a_json_respuesta(respuesta, "generico") if respuesta else None,
        latencia_ms=3,
        creada_en=MOMENTO,
    )
    return ResultadoCompra(
        ejecucion=ejecucion, solicitud=solicitud, respuesta=respuesta, motivos=(),
    )


def _cliente(**kwargs) -> TestClient:
    return TestClient(crear_app(ComposicionFalsa(**kwargs)))


def test_la_pantalla_de_echo_responde():
    respuesta = _cliente().get("/echo")
    assert respuesta.status_code == 200
    assert "Echo de red" in respuesta.text


def test_la_pantalla_de_echo_no_muestra_campos_de_compra():
    texto = _cliente().get("/echo").text.lower()
    for prohibido in ('name="card_id"', 'name="monto"', "tarjeta y monto"):
        assert prohibido not in texto


def test_la_pantalla_de_echo_muestra_la_vista_previa_con_mti_0800():
    texto = _cliente().get("/echo").text
    assert "0800" in texto
    assert "301" in texto  # default de laboratorio de DE70


def test_el_boton_ejecutar_lleva_el_conexion_id_actual_como_campo_oculto():
    """Regresion del hallazgo de auditoria manual: sin este campo oculto,
    "Ejecutar echo" siempre fallaba con "seleccione una conexión", incluso
    con una conexion activa ya elegida."""
    texto = _cliente().get("/echo").text
    assert f'name="conexion_id" value="{DESTINO_ID_DEMO}"' in texto


def test_un_echo_aprobado_muestra_el_resultado():
    respuesta = _cliente(resultado=_resultado_echo(EstadoEjecucion.APROBADA)).post(
        "/echo/ejecutar", data={"conexion_id": DESTINO_ID_DEMO, "de70": ""}
    )
    assert respuesta.status_code == 200
    assert "Transacción aprobada" in respuesta.text
    assert "000099" in respuesta.text


def test_el_resultado_de_echo_muestra_el_mti_real_no_el_de_compra():
    """Regresion del hallazgo de auditoria manual: el titulo del isoscopio
    estaba hardcodeado a '0100'/'0110' en resultado.html."""
    texto = _cliente(resultado=_resultado_echo(EstadoEjecucion.APROBADA)).post(
        "/echo/ejecutar", data={"conexion_id": DESTINO_ID_DEMO, "de70": ""}
    ).text
    assert "Isoscopio · solicitud 0800" in texto
    assert "Isoscopio · respuesta 0810" in texto
    assert "Isoscopio · solicitud 0100" not in texto


def test_el_resultado_de_echo_no_ofrece_guardar_como_escenario():
    """Esa reconstruccion (_reconstruir_desde_ejecucion) hoy solo sabe
    reconstruir una compra -deuda documentada para B3-: el bloque no debe
    ofrecerse para un resultado de echo."""
    texto = _cliente(resultado=_resultado_echo(EstadoEjecucion.APROBADA)).post(
        "/echo/ejecutar", data={"conexion_id": DESTINO_ID_DEMO, "de70": ""}
    ).text
    assert "Guardar como escenario" not in texto
    assert "Editar y volver a ejecutar" not in texto


def test_el_resultado_de_echo_vuelve_a_echo_no_a_compra():
    texto = _cliente(resultado=_resultado_echo(EstadoEjecucion.APROBADA)).post(
        "/echo/ejecutar", data={"conexion_id": DESTINO_ID_DEMO, "de70": ""}
    ).text
    assert 'href="/echo">' in texto


def test_monto_y_tarjeta_se_muestran_vacios_no_como_texto_none():
    """Regresion: Ejecucion.card_id/monto son None para echo; sin manejo
    explicito, Jinja2 renderiza el texto literal "None"."""
    texto = _cliente(resultado=_resultado_echo(EstadoEjecucion.APROBADA)).post(
        "/echo/ejecutar", data={"conexion_id": DESTINO_ID_DEMO, "de70": ""}
    ).text
    assert ">None<" not in texto
    assert "None" not in texto


def test_ejecutar_echo_sin_conexion_activa_revienta_con_error_legible():
    respuesta = _cliente(destinos=[]).post(
        "/echo/ejecutar", data={"conexion_id": "no-existe", "de70": ""}
    )
    assert respuesta.status_code == 400
    assert "Seleccione una conexión activa" in respuesta.text


def test_de70_personalizado_se_refleja_en_la_vista_previa():
    texto = _cliente().post(
        "/echo", data={"ir_a_conexion": "", "de70": "001"}
    ).text
    assert "001" in texto

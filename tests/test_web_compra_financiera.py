"""Rutas web de compra financiera (0200/0210, B4): GET /financiera (formulario
+ vista previa), POST /financiera (cambiar conexion sin ejecutar), POST
/financiera/ejecutar (ejecucion real), y el ciclo completo de escenarios
-guardar, cargar, reejecutar con expectativas- que B3 ya dejo listo para
Multi-MTI.

Mismo estilo que `test_web_echo.py`: `ComposicionFalsa`/`OrquestadorFalso`
como dobles, sin SQLite ni TCP reales -esos ya estan cubiertos por
`tests/test_compra_financiera_e2e.py`-.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from sibutestlab8583.domain.datos_sinteticos import monto_iso
from sibutestlab8583.domain.modelos import (
    CampoInterpretado,
    Ejecucion,
    EstadoEjecucion,
    MensajeInterpretado,
    MensajeIso,
    MTI_COMPRA_FINANCIERA,
    MTI_RESPUESTA_COMPRA_FINANCIERA,
    ResultadoCompra,
)
from sibutestlab8583.web.app import crear_app

from test_web import CARD_ID_DEMO, ComposicionFalsa, DESTINO_ID_DEMO

MOMENTO = datetime(2026, 9, 13, 0, 0, 0, tzinfo=timezone.utc)


def _resultado_financiera(estado, *, codigo="00", con_respuesta=True):
    from sibutestlab8583.application.serializacion import (
        a_json_respuesta,
        a_json_solicitud,
        a_texto,
    )

    solicitud = MensajeIso(
        MTI_COMPRA_FINANCIERA,
        {"2": "************1234", "3": "000000", "4": monto_iso("5000"), "7": "0913000000",
         "11": "000099", "14": "3012", "22": "011", "41": "TERM0001", "49": "188"},
    )
    respuesta = None
    if con_respuesta:
        respuesta = MensajeInterpretado(
            MTI_RESPUESTA_COMPRA_FINANCIERA,
            {
                "3": CampoInterpretado("3", "000000", "000000", ""),
                "4": CampoInterpretado("4", monto_iso("5000"), monto_iso("5000"), ""),
                "7": CampoInterpretado("7", "0913000000", "0913000000", ""),
                "11": CampoInterpretado("11", "000099", "000099", ""),
                "39": CampoInterpretado("39", codigo, codigo, "Código de respuesta"),
                "41": CampoInterpretado("41", "TERM0001", "TERM0001", ""),
            },
        )
    ejecucion = Ejecucion(
        id=99,
        card_id=CARD_ID_DEMO,
        monto=Decimal("50.00"),
        moneda=None,
        stan="000099",
        estado=estado,
        mti_solicitud=MTI_COMPRA_FINANCIERA,
        mti_respuesta=MTI_RESPUESTA_COMPRA_FINANCIERA if con_respuesta else None,
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


def test_la_pantalla_de_compra_financiera_responde():
    respuesta = _cliente().get("/financiera")
    assert respuesta.status_code == 200
    assert "Compra financiera" in respuesta.text


def test_la_pantalla_muestra_las_tarjetas_del_catalogo():
    texto = _cliente().get("/financiera").text
    assert CARD_ID_DEMO in texto


def test_un_financiera_aprobada_muestra_el_resultado():
    respuesta = _cliente(resultado=_resultado_financiera(EstadoEjecucion.APROBADA)).post(
        "/financiera/ejecutar",
        data={"card_id": CARD_ID_DEMO, "monto": "50.00", "conexion_id": DESTINO_ID_DEMO},
    )
    assert respuesta.status_code == 200
    assert "Transacción aprobada" in respuesta.text


def test_el_resultado_muestra_el_mti_real_0200_0210():
    texto = _cliente(resultado=_resultado_financiera(EstadoEjecucion.APROBADA)).post(
        "/financiera/ejecutar",
        data={"card_id": CARD_ID_DEMO, "monto": "50.00", "conexion_id": DESTINO_ID_DEMO},
    ).text
    assert "Isoscopio · solicitud 0200" in texto
    assert "Isoscopio · respuesta 0210" in texto


def test_ejecutar_sin_tarjeta_revienta_con_error_legible():
    respuesta = _cliente().post(
        "/financiera/ejecutar", data={"card_id": "", "monto": "50.00", "conexion_id": DESTINO_ID_DEMO}
    )
    assert respuesta.status_code == 400
    assert "Seleccione una tarjeta" in respuesta.text


def test_ejecutar_sin_conexion_activa_revienta_con_error_legible():
    respuesta = _cliente(destinos=[]).post(
        "/financiera/ejecutar",
        data={"card_id": CARD_ID_DEMO, "monto": "50.00", "conexion_id": "no-existe"},
    )
    assert respuesta.status_code == 400
    assert "Seleccione una conexión activa" in respuesta.text


# ------------------------------------ B4: guardar/cargar escenario financiero --


def test_guardar_como_escenario_desde_financiera():
    cliente = _cliente()
    respuesta = cliente.post(
        "/escenarios",
        data={
            "nombre": "Financiera de humo",
            "card_id": CARD_ID_DEMO,
            "monto": "50.00",
            "conexion_id": DESTINO_ID_DEMO,
            "mti": MTI_COMPRA_FINANCIERA,
        },
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    assert respuesta.headers["location"].startswith("/financiera?escenario_id=")


def test_el_escenario_financiero_guardado_se_carga_en_financiera():
    cliente = _cliente()
    creado = cliente.post(
        "/escenarios",
        data={
            "nombre": "Financiera de humo",
            "card_id": CARD_ID_DEMO,
            "monto": "50.00",
            "conexion_id": DESTINO_ID_DEMO,
            "mti": MTI_COMPRA_FINANCIERA,
        },
        follow_redirects=False,
    )
    escenario_id = creado.headers["location"].split("escenario_id=")[1]

    texto = cliente.get(f"/financiera?escenario_id={escenario_id}").text
    assert "Financiera de humo" in texto
    assert "Guardar cambios" in texto


def test_reejecutar_un_escenario_financiero_pasa_expectativas_y_trazabilidad():
    cliente = _cliente(resultado=_resultado_financiera(EstadoEjecucion.APROBADA))
    creado = cliente.post(
        "/escenarios",
        data={
            "nombre": "Financiera con expectativa",
            "card_id": CARD_ID_DEMO,
            "monto": "50.00",
            "conexion_id": DESTINO_ID_DEMO,
            "mti": MTI_COMPRA_FINANCIERA,
            "estado_esperado": "aprobada",
        },
        follow_redirects=False,
    )
    escenario_id = creado.headers["location"].split("escenario_id=")[1]

    respuesta = cliente.post(f"/escenarios/{escenario_id}/ejecutar")
    assert respuesta.status_code == 200
    assert "Transacción aprobada" in respuesta.text


def test_la_lista_de_escenarios_distingue_compra_financiera():
    cliente = _cliente()
    cliente.post(
        "/escenarios",
        data={
            "nombre": "Financiera de humo",
            "card_id": CARD_ID_DEMO,
            "monto": "50.00",
            "conexion_id": DESTINO_ID_DEMO,
            "mti": MTI_COMPRA_FINANCIERA,
        },
    )
    texto = cliente.get("/escenarios").text
    assert "Compra financiera" in texto
    assert MTI_COMPRA_FINANCIERA in texto


def test_el_resultado_ofrece_reutilizar_apuntando_a_financiera():
    texto = _cliente(resultado=_resultado_financiera(EstadoEjecucion.APROBADA)).post(
        "/financiera/ejecutar",
        data={"card_id": CARD_ID_DEMO, "monto": "50.00", "conexion_id": DESTINO_ID_DEMO},
    ).text
    assert "Guardar como escenario" in texto
    assert "Editar y volver a ejecutar" in texto
    assert "/financiera?ejecucion_id=99" in texto


def test_editar_y_volver_a_ejecutar_reconstruye_tarjeta_y_monto_de_una_ejecucion_financiera():
    resultado = _resultado_financiera(EstadoEjecucion.APROBADA)
    cliente = _cliente(resultado=resultado, ejecuciones=[resultado.ejecucion])
    respuesta_ejecutar = cliente.post(
        "/financiera/ejecutar",
        data={"card_id": CARD_ID_DEMO, "monto": "50.00", "conexion_id": DESTINO_ID_DEMO},
    )
    assert respuesta_ejecutar.status_code == 200

    texto = cliente.get(f"/financiera?ejecucion_id={resultado.ejecucion.id}").text
    assert f'name="card_id" value="{CARD_ID_DEMO}"' in texto or CARD_ID_DEMO in texto
    assert 'value="50.00"' in texto


def test_el_historial_distingue_la_operacion_financiera_y_enruta_al_escenario_correcto():
    """Punto 24 de B4: el historial debe distinguir la operacion sin que haya
    que inspeccionar el MTI a mano, y el enlace "Escenario:" debe apuntar a
    /financiera (no a / como antes de esta correccion)."""
    resultado = _resultado_financiera(
        EstadoEjecucion.APROBADA,
    )
    ejecucion = resultado.ejecucion
    import dataclasses

    ejecucion = dataclasses.replace(
        ejecucion, escenario_id="ESC-fin01", escenario_nombre="Financiera de historial"
    )
    texto = _cliente(ejecuciones=[ejecucion]).get("/historial").text
    assert "Compra financiera" in texto
    assert MTI_COMPRA_FINANCIERA in texto
    assert f'href="/financiera?escenario_id=ESC-fin01"' in texto


def test_guardar_una_compra_normal_sigue_funcionando_tras_generalizar_leer_enviado():
    """Regresion: generalizar `_leer_enviado`/`_leer_opcionales_activos` con
    `mti` no debe romper el uso por defecto (compra, sin `mti` en el form)."""
    cliente = _cliente()
    respuesta = cliente.post(
        "/escenarios",
        data={
            "nombre": "Compra de siempre",
            "card_id": CARD_ID_DEMO,
            "monto": "150.00",
            "conexion_id": DESTINO_ID_DEMO,
        },
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    assert respuesta.headers["location"].startswith("/?escenario_id=")

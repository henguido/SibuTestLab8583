"""Capa web del modulo de Configuracion: portada y administracion de tarjetas.

Usa los mismos dobles que `test_web.py` (`ComposicionFalsa`, con
`ServicioTarjetas` real sobre un repositorio de tarjetas en memoria): lo que
se sustituye es la persistencia, no la validacion de negocio. Las guardias de
seguridad, ortografia y ausencia de JavaScript que ya cubren todas las
pantallas del producto viven en `test_web_interfaz.py` y se extendieron ahi
para cubrir tambien estas pantallas nuevas.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from test_tarjetas_administracion import _pan_valido_luhn
from test_web import ComposicionFalsa, _cliente

from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, DESTINO_ID_DEMO, PAN_DEMO
from sibutestlab8583.domain.datos_sinteticos import pan_sintetico
from sibutestlab8583.domain.modelos import TarjetaPrueba
from sibutestlab8583.web.app import crear_app

PAN_SINTETICO_NUEVO = pan_sintetico("7000")

FORMULARIO_NUEVA_TARJETA = {
    "card_id": "WEB-NUEVA",
    "descripcion": "Creada desde la web",
    "pan": PAN_SINTETICO_NUEVO,
    "expiracion": "3011",
}


# ----------------------------------------------------------------- portada ---


def test_la_portada_muestra_los_tres_modulos():
    html = _cliente().get("/configuracion").text
    assert "Tarjetas de prueba" in html
    assert "Administra las tarjetas disponibles para las pruebas." in html
    assert "Códigos de respuesta" in html
    assert "Configura cómo se interpreta cada código de respuesta recibido." in html
    assert "Conexiones" in html
    assert "Administra las conexiones TCP de prueba: host, puerto y timeout." in html


def test_la_portada_enlaza_a_tarjetas_y_conexiones_pero_no_a_codigos():
    html = _cliente().get("/configuracion").text
    assert 'href="/configuracion/tarjetas"' in html
    assert 'href="/configuracion/conexiones"' in html
    assert html.count("Próximamente") == 1, "solo codigos debe marcarse como pendiente"


# ------------------------------------------------------------------ listado ---


def test_el_listado_muestra_la_tarjeta_de_demostracion_enmascarada():
    html = _cliente().get("/configuracion/tarjetas").text
    assert CARD_ID_DEMO in html
    assert "************6666" in html
    assert PAN_DEMO not in html
    assert "Activa" in html
    assert "Sintética" in html


def test_el_listado_ofrece_editar_y_cambiar_estado():
    html = _cliente().get("/configuracion/tarjetas").text
    assert f"/configuracion/tarjetas/{CARD_ID_DEMO}/editar" in html
    assert f'action="/configuracion/tarjetas/{CARD_ID_DEMO}/estado"' in html
    assert "Desactivar" in html


# -------------------------------------------------------------------- crear ---


def test_el_formulario_de_nueva_tarjeta_no_tiene_card_id_prellenado():
    html = _cliente().get("/configuracion/tarjetas/nueva").text
    assert 'name="card_id"' in html
    assert 'name="pan"' in html
    assert 'name="confirma_qa"' in html


def test_crear_una_tarjeta_sintetica_redirige_y_aparece_en_el_listado():
    cliente = _cliente()
    respuesta = cliente.post(
        "/configuracion/tarjetas", data=FORMULARIO_NUEVA_TARJETA, follow_redirects=False
    )
    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/configuracion/tarjetas"

    listado = cliente.get("/configuracion/tarjetas").text
    assert "WEB-NUEVA" in listado
    assert "Creada desde la web" in listado
    assert "Sintética" in listado


def test_crear_una_tarjeta_qa_autorizada_con_confirmacion():
    cliente = _cliente()
    pan_real = _pan_valido_luhn("5001")
    respuesta = cliente.post(
        "/configuracion/tarjetas",
        data={**FORMULARIO_NUEVA_TARJETA, "card_id": "WEB-QA", "pan": pan_real,
              "confirma_qa": "1"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    listado = cliente.get("/configuracion/tarjetas").text
    assert "QA autorizada" in listado
    assert pan_real not in listado


def test_crear_una_tarjeta_qa_sin_confirmar_se_rechaza_sin_repetir_el_pan():
    pan_real = _pan_valido_luhn("5002")
    respuesta = _cliente().post(
        "/configuracion/tarjetas",
        data={**FORMULARIO_NUEVA_TARJETA, "card_id": "WEB-QA-2", "pan": pan_real},
    )
    assert respuesta.status_code == 400
    assert "ambiente de pruebas autorizado" in respuesta.text
    assert pan_real not in respuesta.text
    assert "Traceback" not in respuesta.text


def test_crear_con_pan_invalido_se_rechaza():
    respuesta = _cliente().post(
        "/configuracion/tarjetas",
        data={**FORMULARIO_NUEVA_TARJETA, "card_id": "WEB-MAL-PAN", "pan": "no-numerico"},
    )
    assert respuesta.status_code == 400
    assert "Revise los datos" in respuesta.text


def test_crear_con_vencimiento_invalido_se_rechaza():
    respuesta = _cliente().post(
        "/configuracion/tarjetas",
        data={**FORMULARIO_NUEVA_TARJETA, "card_id": "WEB-MAL-VTO", "expiracion": "abcd"},
    )
    assert respuesta.status_code == 400
    assert "AAMM" in respuesta.text or "vencimiento" in respuesta.text.lower()


def test_crear_con_card_id_duplicado_se_rechaza():
    cliente = _cliente()
    cliente.post("/configuracion/tarjetas", data=FORMULARIO_NUEVA_TARJETA)
    respuesta = cliente.post("/configuracion/tarjetas", data=FORMULARIO_NUEVA_TARJETA)
    assert respuesta.status_code == 400
    assert "Ya existe" in respuesta.text


def test_un_error_de_creacion_no_repuebla_el_campo_pan():
    respuesta = _cliente().post(
        "/configuracion/tarjetas",
        data={**FORMULARIO_NUEVA_TARJETA, "card_id": "WEB-MAL-PAN-2", "pan": "no-numerico"},
    )
    assert 'name="pan"' in respuesta.text
    assert 'value="no-numerico"' not in respuesta.text
    # El identificador y la descripcion si se conservan: solo el PAN se limpia.
    assert 'value="WEB-MAL-PAN-2"' in respuesta.text


# ------------------------------------------------------------------- editar ---


def test_el_formulario_de_edicion_muestra_el_card_id_como_solo_lectura():
    html = _cliente().get(f"/configuracion/tarjetas/{CARD_ID_DEMO}/editar").text
    assert CARD_ID_DEMO in html
    assert 'name="card_id"' not in html, "el identificador no debe ser un campo editable"


def test_el_formulario_de_edicion_nunca_muestra_el_pan_completo():
    html = _cliente().get(f"/configuracion/tarjetas/{CARD_ID_DEMO}/editar").text
    assert "************6666" in html
    assert PAN_DEMO not in html


def test_editar_una_tarjeta_inexistente_da_un_404_propio():
    respuesta = _cliente().get("/configuracion/tarjetas/NO-EXISTE/editar")
    assert respuesta.status_code == 404
    assert "Tarjeta no encontrada" in respuesta.text
    assert "Traceback" not in respuesta.text


def test_editar_descripcion_y_vencimiento_redirige_y_persiste():
    cliente = _cliente()
    respuesta = cliente.post(
        f"/configuracion/tarjetas/{CARD_ID_DEMO}",
        data={"descripcion": "Descripción nueva", "expiracion": "3105"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    listado = cliente.get("/configuracion/tarjetas").text
    assert "Descripción nueva" in listado
    assert "3105" in listado


def test_editar_sin_nuevo_pan_conserva_el_numero_actual():
    cliente = _cliente()
    cliente.post(
        f"/configuracion/tarjetas/{CARD_ID_DEMO}",
        data={"descripcion": "Sin cambio de numero", "expiracion": "3012", "pan_nuevo": ""},
    )
    listado = cliente.get("/configuracion/tarjetas").text
    assert "************6666" in listado


def test_editar_con_pan_nuevo_lo_reemplaza():
    cliente = _cliente()
    pan_nuevo = pan_sintetico("8123")
    cliente.post(
        f"/configuracion/tarjetas/{CARD_ID_DEMO}",
        data={"descripcion": "Con numero nuevo", "expiracion": "3012", "pan_nuevo": pan_nuevo},
    )
    listado = cliente.get("/configuracion/tarjetas").text
    assert "************8123" in listado
    assert "************6666" not in listado
    assert pan_nuevo not in listado


def test_editar_una_tarjeta_inexistente_da_404_al_publicar():
    respuesta = _cliente().post(
        "/configuracion/tarjetas/NO-EXISTE", data={"descripcion": "d", "expiracion": "3012"}
    )
    assert respuesta.status_code == 404
    assert "Tarjeta no encontrada" in respuesta.text


# ------------------------------------------------------- activar/desactivar --


def test_desactivar_una_tarjeta_cambia_el_estado_en_el_listado():
    cliente = _cliente()
    respuesta = cliente.post(
        f"/configuracion/tarjetas/{CARD_ID_DEMO}/estado",
        data={"activa": "0"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    listado = cliente.get("/configuracion/tarjetas").text
    assert "Inactiva" in listado


def test_activar_una_tarjeta_inactiva():
    tarjeta_inactiva = TarjetaPrueba(
        card_id=CARD_ID_DEMO, pan=PAN_DEMO, expiracion="3012",
        descripcion="Tarjeta de demostración", sintetica=True, activa=False,
    )
    cliente = _cliente(tarjetas=[tarjeta_inactiva])
    cliente.post(f"/configuracion/tarjetas/{CARD_ID_DEMO}/estado", data={"activa": "1"})
    listado = cliente.get("/configuracion/tarjetas").text
    assert "Activa" in listado


def test_cambiar_estado_de_una_tarjeta_inexistente_da_404():
    respuesta = _cliente().post(
        "/configuracion/tarjetas/NO-EXISTE/estado", data={"activa": "0"}
    )
    assert respuesta.status_code == 404


@pytest.mark.parametrize("valor", ["si", "2", "true", "-1", "", "on"])
def test_un_valor_de_estado_manipulado_se_rechaza_sin_convertirse_en_booleano(valor):
    """Un formulario forjado no debe poder cambiar el estado silenciosamente.

    Ni "activa" ni "no activa": el valor recibido no es uno de los dos que la
    interfaz emite (`"0"`/`"1"`), asi que la tarjeta debe quedar exactamente
    como estaba.
    """
    cliente = _cliente()
    respuesta = cliente.post(
        f"/configuracion/tarjetas/{CARD_ID_DEMO}/estado", data={"activa": valor}
    )
    assert respuesta.status_code == 400
    assert "Traceback" not in respuesta.text

    listado = cliente.get("/configuracion/tarjetas").text
    assert "Activa" in listado, "la tarjeta de demostracion debe seguir activa, sin cambios"


# ============================================================= conexiones ===
#
# Mismo patron que las tarjetas: `ComposicionFalsa` con `ServicioConexiones`
# real sobre un repositorio en memoria, asi que la validacion se ejercita de
# verdad. La tabla/repositorio siguen llamandose "destinos" -de una fase
# anterior-, pero rutas, plantillas y textos hablan siempre de "conexion".

FORMULARIO_NUEVA_CONEXION = {
    "conexion_id": "QA-WEB-01",
    "nombre": "Switch QA desde la web",
    "host": "192.0.2.20",
    "puerto": "9583",
}


# ------------------------------------------------------------------ listado ---


def test_el_listado_muestra_la_conexion_de_demostracion():
    html = _cliente().get("/configuracion/conexiones").text
    assert DESTINO_ID_DEMO in html
    assert "Activa" in html


def test_el_listado_ofrece_editar_cambiar_estado_y_probar():
    html = _cliente().get("/configuracion/conexiones").text
    assert f"/configuracion/conexiones/{DESTINO_ID_DEMO}/editar" in html
    assert f'action="/configuracion/conexiones/{DESTINO_ID_DEMO}/estado"' in html
    assert f'action="/configuracion/conexiones/{DESTINO_ID_DEMO}/probar"' in html
    assert "Desactivar" in html
    assert "Probar conexión" in html


def test_el_listado_muestra_sin_verificar_por_defecto():
    html = _cliente().get("/configuracion/conexiones").text
    assert "Sin verificar" in html


# -------------------------------------------------------------------- crear ---


def test_el_formulario_de_nueva_conexion_no_tiene_identificador_prellenado():
    html = _cliente().get("/configuracion/conexiones/nueva").text
    assert 'name="conexion_id"' in html
    assert 'name="host"' in html
    assert 'name="puerto"' in html
    assert 'name="timeout"' in html


def test_crear_una_conexion_redirige_y_aparece_en_el_listado():
    cliente = _cliente()
    respuesta = cliente.post(
        "/configuracion/conexiones", data=FORMULARIO_NUEVA_CONEXION, follow_redirects=False
    )
    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/configuracion/conexiones"

    listado = cliente.get("/configuracion/conexiones").text
    assert "QA-WEB-01" in listado
    assert "Switch QA desde la web" in listado


def test_crear_con_identificador_duplicado_se_rechaza():
    cliente = _cliente()
    cliente.post("/configuracion/conexiones", data=FORMULARIO_NUEVA_CONEXION)
    respuesta = cliente.post("/configuracion/conexiones", data=FORMULARIO_NUEVA_CONEXION)
    assert respuesta.status_code == 400
    assert "Ya existe" in respuesta.text


def test_crear_con_puerto_invalido_se_rechaza():
    respuesta = _cliente().post(
        "/configuracion/conexiones",
        data={**FORMULARIO_NUEVA_CONEXION, "conexion_id": "QA-MAL-PUERTO", "puerto": "no-numero"},
    )
    assert respuesta.status_code == 400
    assert "Revise los datos" in respuesta.text


def test_crear_con_timeout_invalido_se_rechaza():
    respuesta = _cliente().post(
        "/configuracion/conexiones",
        data={**FORMULARIO_NUEVA_CONEXION, "conexion_id": "QA-MAL-TIMEOUT", "timeout": "-5"},
    )
    assert respuesta.status_code == 400
    assert "Revise los datos" in respuesta.text


def test_crear_sin_host_se_rechaza():
    respuesta = _cliente().post(
        "/configuracion/conexiones",
        data={**FORMULARIO_NUEVA_CONEXION, "conexion_id": "QA-SIN-HOST", "host": ""},
    )
    assert respuesta.status_code == 400


# ------------------------------------------------------------------- editar ---


def test_el_formulario_de_edicion_muestra_el_identificador_como_solo_lectura():
    html = _cliente().get(f"/configuracion/conexiones/{DESTINO_ID_DEMO}/editar").text
    assert DESTINO_ID_DEMO in html
    assert 'name="conexion_id"' not in html, "el identificador no debe ser un campo editable"


def test_editar_una_conexion_inexistente_da_un_404_propio():
    respuesta = _cliente().get("/configuracion/conexiones/NO-EXISTE/editar")
    assert respuesta.status_code == 404
    assert "Conexión no encontrada" in respuesta.text
    assert "Traceback" not in respuesta.text


def test_editar_nombre_host_puerto_y_timeout_redirige_y_persiste():
    cliente = _cliente()
    respuesta = cliente.post(
        f"/configuracion/conexiones/{DESTINO_ID_DEMO}",
        data={"nombre": "Local renombrado", "host": "127.0.0.9", "puerto": "9000", "timeout": "15"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    listado = cliente.get("/configuracion/conexiones").text
    assert "Local renombrado" in listado
    assert "127.0.0.9" in listado
    assert "9000" in listado
    assert "15 s" in listado


def test_editar_una_conexion_inexistente_da_404_al_publicar():
    respuesta = _cliente().post(
        "/configuracion/conexiones/NO-EXISTE",
        data={"nombre": "d", "host": "10.0.0.1", "puerto": "9000"},
    )
    assert respuesta.status_code == 404
    assert "Conexión no encontrada" in respuesta.text


# ------------------------------------------------------- activar/desactivar --


def test_desactivar_una_conexion_cambia_el_estado_en_el_listado():
    cliente = _cliente()
    respuesta = cliente.post(
        f"/configuracion/conexiones/{DESTINO_ID_DEMO}/estado",
        data={"activa": "0"},
        follow_redirects=False,
    )
    assert respuesta.status_code == 303
    listado = cliente.get("/configuracion/conexiones").text
    assert "Inactiva" in listado


def test_cambiar_estado_de_una_conexion_inexistente_da_404():
    respuesta = _cliente().post(
        "/configuracion/conexiones/NO-EXISTE/estado", data={"activa": "0"}
    )
    assert respuesta.status_code == 404


@pytest.mark.parametrize("valor", ["si", "2", "true", "-1", "", "on"])
def test_un_valor_de_estado_manipulado_no_cambia_la_conexion(valor):
    cliente = _cliente()
    respuesta = cliente.post(
        f"/configuracion/conexiones/{DESTINO_ID_DEMO}/estado", data={"activa": valor}
    )
    assert respuesta.status_code == 400
    assert "Traceback" not in respuesta.text

    listado = cliente.get("/configuracion/conexiones").text
    assert "Activa" in listado, "la conexion de demostracion debe seguir activa, sin cambios"


def test_una_conexion_desactivada_no_aparece_como_opcion_en_la_pantalla_de_compra():
    """Con la unica conexion desactivada, la pantalla debe caer al estado vacio,
    no ofrecerla de todas formas.
    """
    cliente = _cliente()
    cliente.post(f"/configuracion/conexiones/{DESTINO_ID_DEMO}/estado", data={"activa": "0"})
    html = cliente.get("/").text
    assert f'value="{DESTINO_ID_DEMO}"' not in html
    assert "Sin conexiones activas" in html


# ------------------------------------------------------------ probar conexion --


class _VerificadorFijo:
    """Doble de `VerificadorDeConexion`: siempre devuelve el resultado dado."""

    def __init__(self, disponible: bool) -> None:
        self._disponible = disponible

    async def probar(self, host, puerto, tiempo_limite):
        return self._disponible


def test_probar_una_conexion_disponible():
    composicion = ComposicionFalsa(verificador_conexion=_VerificadorFijo(True))
    cliente = TestClient(crear_app(composicion))
    respuesta = cliente.post(f"/configuracion/conexiones/{DESTINO_ID_DEMO}/probar")
    assert respuesta.status_code == 200
    assert "Disponible" in respuesta.text
    assert "No disponible" not in respuesta.text


def test_probar_una_conexion_no_disponible_no_expone_la_excepcion():
    composicion = ComposicionFalsa(verificador_conexion=_VerificadorFijo(False))
    cliente = TestClient(crear_app(composicion))
    respuesta = cliente.post(f"/configuracion/conexiones/{DESTINO_ID_DEMO}/probar")
    assert respuesta.status_code == 200
    assert "No disponible" in respuesta.text
    assert "Traceback" not in respuesta.text
    assert "Exception" not in respuesta.text


def test_probar_una_conexion_inexistente_da_404():
    respuesta = _cliente().post("/configuracion/conexiones/NO-EXISTE/probar")
    assert respuesta.status_code == 404
    assert "Conexión no encontrada" in respuesta.text

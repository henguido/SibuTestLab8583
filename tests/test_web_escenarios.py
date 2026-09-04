"""Capa web de escenarios: guardar desde el constructor, cargar, editar,
duplicar, activar/desactivar y reejecutar sin pasar por Nueva transacción.

No hay un segundo constructor: "Nuevo escenario"/"Editar" reutilizan
Nueva transacción -este archivo prueba justamente que ese flujo funciona sin
duplicar el HTML del constructor en ningún lado nuevo.

Usa `httpx2.AsyncClient` (no el `TestClient` sincrono) porque varias pruebas
necesitan consultar `composicion.administracion_escenarios` -un objeto
async- en el mismo test que hace las peticiones HTTP.
"""

from __future__ import annotations

from decimal import Decimal

import httpx2
from test_web import ComposicionFalsa, _resultado

from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, DESTINO_ID_DEMO
from sibutestlab8583.domain.modelos import Escenario, EstadoEjecucion, TarjetaPrueba
from sibutestlab8583.web.app import crear_app

FORMULARIO_ESCENARIO = {
    "nombre": "Compra aprobada CRC",
    "card_id": CARD_ID_DEMO,
    "monto": "150.00",
    "conexion_id": DESTINO_ID_DEMO,
}


def _cliente(**kwargs) -> tuple[httpx2.AsyncClient, ComposicionFalsa]:
    composicion = ComposicionFalsa(**kwargs)
    transporte = httpx2.ASGITransport(app=crear_app(composicion))
    cliente = httpx2.AsyncClient(transport=transporte, base_url="http://prueba")
    return cliente, composicion


def _escenario_id_de(respuesta) -> str:
    return respuesta.headers["location"].split("=")[1]


# ------------------------------------------------------------------- crear ---


async def test_guardar_como_escenario_redirige_al_constructor_con_el_nuevo_id():
    cliente, _ = _cliente()
    async with cliente:
        respuesta = await cliente.post("/escenarios", data=FORMULARIO_ESCENARIO)
    assert respuesta.status_code == 303
    assert respuesta.headers["location"].startswith("/?escenario_id=")


async def test_el_escenario_creado_aparece_en_el_listado():
    cliente, _ = _cliente()
    async with cliente:
        await cliente.post("/escenarios", data=FORMULARIO_ESCENARIO)
        listado = (await cliente.get("/escenarios")).text
    assert "Compra aprobada CRC" in listado


async def test_guardar_como_escenario_congela_los_defaults_efectivos():
    """No solo lo que el usuario toco: 3/22/41/49 tambien, aunque vengan del
    default del perfil y el formulario no traiga `campo_3` etc.
    """
    cliente, composicion = _cliente()
    async with cliente:
        respuesta = await cliente.post("/escenarios", data=FORMULARIO_ESCENARIO)
        nuevo_id = _escenario_id_de(respuesta)
        escenario = await composicion.administracion_escenarios.obtener(nuevo_id)
    assert set(escenario.campos_manuales) == {"3", "22", "41", "49"}


async def test_guardar_sin_nombre_se_rechaza():
    cliente, _ = _cliente()
    async with cliente:
        respuesta = await cliente.post(
            "/escenarios", data={**FORMULARIO_ESCENARIO, "nombre": ""}
        )
    assert respuesta.status_code == 400
    assert "Revise los datos" in respuesta.text


async def test_guardar_un_campo_protegido_forzado_a_mano_se_ignora():
    """El servidor no lee `campo_2` del formulario en absoluto: mismo principio
    que ya protege /compra.
    """
    cliente, composicion = _cliente()
    async with cliente:
        respuesta = await cliente.post(
            "/escenarios", data={**FORMULARIO_ESCENARIO, "campo_2": "9" * 16}
        )
        assert respuesta.status_code == 303
        nuevo_id = _escenario_id_de(respuesta)
        escenario = await composicion.administracion_escenarios.obtener(nuevo_id)
    assert "2" not in escenario.campos_manuales


# ------------------------------------------------------------------ cargar ---


async def test_cargar_un_escenario_prellena_el_constructor():
    cliente, composicion = _cliente()
    async with cliente:
        respuesta = await cliente.post(
            "/escenarios", data={**FORMULARIO_ESCENARIO, "monto": "77.50"}
        )
        escenario_id = _escenario_id_de(respuesta)
        html = (await cliente.get(f"/?escenario_id={escenario_id}")).text
    assert f'value="{CARD_ID_DEMO}"' in html
    assert 'value="77.50"' in html
    assert f'value="{DESTINO_ID_DEMO}"' in html or DESTINO_ID_DEMO in html


async def test_cargar_un_escenario_con_tarjeta_no_disponible_no_sustituye_en_silencio():
    cliente, composicion = _cliente(
        tarjetas=[
            TarjetaPrueba(card_id="SOLO-TARJETA", pan="0" * 16, expiracion="3012", activa=True)
        ]
    )
    escenario = Escenario(
        escenario_id="ESC-X",
        nombre="Con tarjeta vieja",
        perfil="generico",
        mti="0100",
        card_id="TARJETA-QUE-NO-EXISTE-EN-EL-CATALOGO",
        conexion_id=DESTINO_ID_DEMO,
        monto=Decimal("10.00"),
    )
    async with cliente:
        await composicion.administracion_escenarios._escenarios.guardar(escenario)
        html = (await cliente.get("/?escenario_id=ESC-X")).text

    assert "La tarjeta usada por este escenario ya no está disponible" in html
    # Ninguna tarjeta activa listada coincide con el card_id del escenario, asi
    # que el radio no se marca -no se sustituyo por la primera disponible-.
    assert 'value="TARJETA-QUE-NO-EXISTE-EN-EL-CATALOGO"' not in html
    assert "disabled" in html


async def test_cargar_un_escenario_con_conexion_no_disponible_no_sustituye_en_silencio():
    cliente, composicion = _cliente()
    escenario = Escenario(
        escenario_id="ESC-Y",
        nombre="Con conexión vieja",
        perfil="generico",
        mti="0100",
        card_id=CARD_ID_DEMO,
        conexion_id="CONEXION-QUE-NO-EXISTE",
        monto=Decimal("10.00"),
    )
    async with cliente:
        await composicion.administracion_escenarios._escenarios.guardar(escenario)
        html = (await cliente.get("/?escenario_id=ESC-Y")).text

    assert "La conexión usada por este escenario ya no está disponible" in html
    assert "disabled" in html


async def test_cargar_un_escenario_inactivo_bloquea_ejecutar_pero_permite_editar():
    cliente, composicion = _cliente()
    escenario = Escenario(
        escenario_id="ESC-INACTIVO",
        nombre="Inactivo",
        perfil="generico",
        mti="0100",
        card_id=CARD_ID_DEMO,
        conexion_id=DESTINO_ID_DEMO,
        monto=Decimal("10.00"),
        activo=False,
    )
    async with cliente:
        await composicion.administracion_escenarios._escenarios.guardar(escenario)
        html = (await cliente.get("/?escenario_id=ESC-INACTIVO")).text

    assert "Este escenario está inactivo" in html
    assert "disabled" in html
    # Pero se puede seguir viendo/editando: el formulario y "Guardar cambios" existen.
    assert "Guardar cambios" in html


async def test_cargar_un_escenario_sano_no_muestra_ningun_bloqueo():
    cliente, composicion = _cliente()
    async with cliente:
        respuesta = await cliente.post("/escenarios", data=FORMULARIO_ESCENARIO)
        nuevo_id = _escenario_id_de(respuesta)
        html = (await cliente.get(f"/?escenario_id={nuevo_id}")).text

    assert "necesita atención" not in html
    assert "Guardar cambios" in html
    assert "Guardar como copia" in html


# ------------------------------------------------------------ guardar cambios --


async def test_guardar_cambios_actualiza_el_mismo_escenario():
    cliente, composicion = _cliente()
    async with cliente:
        respuesta = await cliente.post("/escenarios", data=FORMULARIO_ESCENARIO)
        escenario_id = _escenario_id_de(respuesta)
        await cliente.post(
            f"/escenarios/{escenario_id}", data={**FORMULARIO_ESCENARIO, "monto": "999.99"}
        )
        actualizado = await composicion.administracion_escenarios.obtener(escenario_id)
    assert actualizado.monto == Decimal("999.99")


async def test_guardar_como_copia_crea_un_escenario_distinto():
    cliente, _ = _cliente()
    async with cliente:
        respuesta = await cliente.post("/escenarios", data=FORMULARIO_ESCENARIO)
        original_id = _escenario_id_de(respuesta)
        respuesta_copia = await cliente.post("/escenarios", data=FORMULARIO_ESCENARIO)
        copia_id = _escenario_id_de(respuesta_copia)
    assert original_id != copia_id


# --------------------------------------------------------------- duplicar ---


async def test_duplicar_redirige_al_constructor_con_la_copia():
    cliente, _ = _cliente()
    async with cliente:
        respuesta = await cliente.post("/escenarios", data=FORMULARIO_ESCENARIO)
        escenario_id = _escenario_id_de(respuesta)
        respuesta_duplicar = await cliente.post(f"/escenarios/{escenario_id}/duplicar")
    assert respuesta_duplicar.status_code == 303
    assert respuesta_duplicar.headers["location"].startswith("/?escenario_id=")
    assert respuesta_duplicar.headers["location"] != f"/?escenario_id={escenario_id}"


async def test_duplicar_un_escenario_inexistente_da_404():
    cliente, _ = _cliente()
    async with cliente:
        respuesta = await cliente.post("/escenarios/NO-EXISTE/duplicar")
    assert respuesta.status_code == 404


# ------------------------------------------------------- activar/desactivar --


async def test_desactivar_un_escenario_cambia_su_estado_en_el_listado():
    cliente, _ = _cliente()
    async with cliente:
        respuesta = await cliente.post("/escenarios", data=FORMULARIO_ESCENARIO)
        escenario_id = _escenario_id_de(respuesta)
        await cliente.post(f"/escenarios/{escenario_id}/estado", data={"activo": "0"})
        listado = (await cliente.get("/escenarios")).text
    assert "Inactivo" in listado


async def test_cambiar_estado_de_un_escenario_inexistente_da_404():
    cliente, _ = _cliente()
    async with cliente:
        respuesta = await cliente.post("/escenarios/NO-EXISTE/estado", data={"activo": "0"})
    assert respuesta.status_code == 404


# --------------------------------------------------------------- ejecutar ---


async def test_ejecutar_directo_un_escenario_sano_muestra_el_resultado():
    cliente, composicion = _cliente(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00"))
    async with cliente:
        respuesta_crear = await cliente.post("/escenarios", data=FORMULARIO_ESCENARIO)
        escenario_id = _escenario_id_de(respuesta_crear)
        respuesta = await cliente.post(f"/escenarios/{escenario_id}/ejecutar")
    assert respuesta.status_code == 200
    assert "Transacción aprobada" in respuesta.text
    assert composicion._orquestador.ultimo_escenario_id == escenario_id


async def test_ejecutar_directo_un_escenario_inactivo_no_ejecuta_nada():
    cliente, composicion = _cliente(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00"))
    async with cliente:
        respuesta_crear = await cliente.post("/escenarios", data=FORMULARIO_ESCENARIO)
        escenario_id = _escenario_id_de(respuesta_crear)
        await cliente.post(f"/escenarios/{escenario_id}/estado", data={"activo": "0"})
        respuesta = await cliente.post(f"/escenarios/{escenario_id}/ejecutar")
    assert respuesta.status_code == 400
    assert "Este escenario está inactivo" in respuesta.text
    assert composicion._orquestador.ultimos_datos is None


async def test_ejecutar_directo_un_escenario_inexistente_da_404():
    cliente, _ = _cliente()
    async with cliente:
        respuesta = await cliente.post("/escenarios/NO-EXISTE/ejecutar")
    assert respuesta.status_code == 404


# --------------------------------------------------- ejecutar via constructor --


async def test_ejecutar_desde_el_constructor_con_escenario_cargado_asocia_el_id():
    cliente, composicion = _cliente(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00"))
    async with cliente:
        respuesta_crear = await cliente.post("/escenarios", data=FORMULARIO_ESCENARIO)
        escenario_id = _escenario_id_de(respuesta_crear)
        respuesta = await cliente.post(
            "/compra",
            data={
                "card_id": CARD_ID_DEMO, "monto": "150.00", "conexion_id": DESTINO_ID_DEMO,
                "escenario_id": escenario_id,
            },
        )
    assert respuesta.status_code == 200
    assert composicion._orquestador.ultimo_escenario_id == escenario_id
    assert composicion._orquestador.ultimo_escenario_nombre == "Compra aprobada CRC"


async def test_ejecutar_desde_el_constructor_sin_escenario_no_asocia_nada():
    cliente, composicion = _cliente(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00"))
    async with cliente:
        respuesta = await cliente.post(
            "/compra",
            data={"card_id": CARD_ID_DEMO, "monto": "150.00", "conexion_id": DESTINO_ID_DEMO},
        )
    assert respuesta.status_code == 200
    assert composicion._orquestador.ultimo_escenario_id is None


async def test_ejecutar_desde_el_constructor_con_escenario_inactivo_se_rechaza():
    cliente, composicion = _cliente()
    async with cliente:
        respuesta_crear = await cliente.post("/escenarios", data=FORMULARIO_ESCENARIO)
        escenario_id = _escenario_id_de(respuesta_crear)
        await cliente.post(f"/escenarios/{escenario_id}/estado", data={"activo": "0"})
        respuesta = await cliente.post(
            "/compra",
            data={
                "card_id": CARD_ID_DEMO, "monto": "150.00", "conexion_id": DESTINO_ID_DEMO,
                "escenario_id": escenario_id,
            },
        )
    assert respuesta.status_code == 400
    assert "Este escenario está inactivo" in respuesta.text
    assert composicion._orquestador.ultimos_datos is None


# -------------------------------------------------------------------- listar ---


async def test_listado_vacio_muestra_un_mensaje_propio():
    cliente, _ = _cliente()
    async with cliente:
        html = (await cliente.get("/escenarios")).text
    assert "Todavía no hay escenarios guardados" in html


async def test_buscar_filtra_el_listado():
    cliente, _ = _cliente()
    async with cliente:
        await cliente.post("/escenarios", data={**FORMULARIO_ESCENARIO, "nombre": "Compra CRC"})
        await cliente.post("/escenarios", data={**FORMULARIO_ESCENARIO, "nombre": "Rechazo USD"})
        html = (await cliente.get("/escenarios", params={"buscar": "CRC"})).text
    assert "Compra CRC" in html
    assert "Rechazo USD" not in html


async def test_no_hay_un_segundo_constructor_en_escenarios():
    """El listado de escenarios no incluye la tabla de campos ISO del
    constructor: "Nuevo escenario" enlaza a Nueva transacción, no a un
    formulario propio.
    """
    cliente, _ = _cliente()
    async with cliente:
        html = (await cliente.get("/escenarios")).text
    assert 'href="/"' in html
    assert "Construir transacción" not in html

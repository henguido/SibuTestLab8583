"""Capa web de suites: crear, editar (reemplazo completo de membresía),
duplicar, activar/desactivar, ejecutar, y ver corridas/detalle de corrida.

Usa `httpx2.AsyncClient` por el mismo motivo que `test_web_escenarios.py`:
varias pruebas consultan `composicion.administracion_suites`/`corridas_suite`
-objetos async- en el mismo test que hace las peticiones HTTP.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx2
from test_web import ComposicionFalsa, _resultado

from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, DESTINO_ID_DEMO
from sibutestlab8583.domain.modelos import EstadoEjecucion
from sibutestlab8583.web.app import crear_app
from sibutestlab8583.web.presentacion import filas_seleccion_escenarios

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


def _id_de(respuesta) -> str:
    """El `suite_id` de una redireccion a `/suites/{id}/editar`."""
    return respuesta.headers["location"].rstrip("/").split("/")[-2]


async def _crear_escenario(cliente, **overrides) -> str:
    respuesta = await cliente.post("/escenarios", data={**FORMULARIO_ESCENARIO, **overrides})
    return respuesta.headers["location"].split("=")[1]


# ------------------------------------------------------------------- crear ---


async def test_guardar_una_suite_nueva_redirige_a_editarla():
    cliente, _ = _cliente()
    async with cliente:
        respuesta = await cliente.post("/suites", data={"nombre": "Regresion nocturna"})
    assert respuesta.status_code == 303
    assert "/editar" in respuesta.headers["location"]


async def test_la_suite_creada_aparece_en_el_listado():
    cliente, _ = _cliente()
    async with cliente:
        await cliente.post("/suites", data={"nombre": "Regresion nocturna"})
        listado = (await cliente.get("/suites")).text
    assert "Regresion nocturna" in listado or "Regresión nocturna" in listado


async def test_guardar_sin_nombre_se_rechaza():
    cliente, _ = _cliente()
    async with cliente:
        respuesta = await cliente.post("/suites", data={"nombre": ""})
    assert respuesta.status_code == 400


async def test_crear_con_escenarios_seleccionados_persiste_el_orden():
    cliente, composicion = _cliente()
    async with cliente:
        e1 = await _crear_escenario(cliente, nombre="E1")
        e2 = await _crear_escenario(cliente, nombre="E2")
        respuesta = await cliente.post(
            "/suites",
            data={
                "nombre": "Con escenarios",
                f"incluir_{e2}": "1", f"orden_{e2}": "1",
                f"incluir_{e1}": "1", f"orden_{e1}": "2",
            },
        )
        suite_id = _id_de(respuesta)
        suite = await composicion.administracion_suites.obtener(suite_id)
    assert suite.escenarios == (e2, e1)


async def test_crear_con_ordenes_repetidos_se_rechaza():
    cliente, composicion = _cliente()
    async with cliente:
        e1 = await _crear_escenario(cliente, nombre="E1")
        e2 = await _crear_escenario(cliente, nombre="E2")
        respuesta = await cliente.post(
            "/suites",
            data={
                "nombre": "X",
                f"incluir_{e1}": "1", f"orden_{e1}": "1",
                f"incluir_{e2}": "1", f"orden_{e2}": "1",
            },
        )
        listado = await composicion.administracion_suites.listar()
    assert respuesta.status_code == 400
    assert listado == [], "no debe crear la suite si el orden es invalido"


async def test_un_incluir_forzado_para_un_escenario_inexistente_se_ignora():
    """Mismo principio de seguridad que `_leer_expectativas`: un
    `incluir_{id}` para un `escenario_id` que no esta en el catalogo real
    nunca se mira -no hace falta rechazarlo, no hay forma de que se cuele-.
    """
    cliente, composicion = _cliente()
    async with cliente:
        respuesta = await cliente.post(
            "/suites",
            data={"nombre": "X", "incluir_NO-EXISTE": "1", "orden_NO-EXISTE": "1"},
        )
        assert respuesta.status_code == 303
        suite_id = _id_de(respuesta)
        suite = await composicion.administracion_suites.obtener(suite_id)
    assert suite.escenarios == ()


# ------------------------------------------------------------------ editar ---


async def test_guardar_cambios_reemplaza_entera_la_membresia():
    cliente, composicion = _cliente()
    async with cliente:
        e1 = await _crear_escenario(cliente, nombre="E1")
        e2 = await _crear_escenario(cliente, nombre="E2")
        respuesta = await cliente.post(
            "/suites", data={"nombre": "X", f"incluir_{e1}": "1", f"orden_{e1}": "1"}
        )
        suite_id = _id_de(respuesta)

        await cliente.post(
            f"/suites/{suite_id}",
            data={"nombre": "X editada", f"incluir_{e2}": "1", f"orden_{e2}": "1"},
        )
        suite = await composicion.administracion_suites.obtener(suite_id)
    assert suite.nombre == "X editada"
    assert suite.escenarios == (e2,), "no debe conservar E1"


async def test_editar_una_suite_inexistente_da_404():
    cliente, _ = _cliente()
    async with cliente:
        respuesta = await cliente.post("/suites/NO-EXISTE", data={"nombre": "X"})
    assert respuesta.status_code == 404


async def test_cargar_el_formulario_de_edicion_prellena_la_seleccion():
    cliente, _ = _cliente()
    async with cliente:
        e1 = await _crear_escenario(cliente, nombre="E1")
        respuesta = await cliente.post(
            "/suites", data={"nombre": "X", f"incluir_{e1}": "1", f"orden_{e1}": "1"}
        )
        suite_id = _id_de(respuesta)
        html = (await cliente.get(f"/suites/{suite_id}/editar")).text
    assert f'name="incluir_{e1}"' in html
    assert "checked" in html


async def test_una_suite_nueva_prellena_el_orden_sugerido_por_posicion_en_el_catalogo():
    """El campo de orden de un escenario TODAVIA no incluido no debe quedar
    vacio: se sugiere su posicion en el catalogo, para que marcar varios
    checkboxes seguidos no obligue a escribir cada numero a mano. Sigue
    siendo editable -no fuerza nada-, y como los valores sugeridos son unicos,
    no genera duplicados aunque el usuario no toque ningun campo de orden.
    """
    cliente, _ = _cliente()
    async with cliente:
        await _crear_escenario(cliente, nombre="E1")
        await _crear_escenario(cliente, nombre="E2")
        html = (await cliente.get("/suites/nueva")).text
    assert 'value="1"' in html
    assert 'value="2"' in html


# -------------------------------- autoorden: filas_seleccion_escenarios ---


@dataclass
class _EscenarioDeCatalogo:
    """Duck-type minimo de lo que `filas_seleccion_escenarios` necesita leer
    de cada fila del catalogo (`escenario_id`, `nombre`, `activo`) -no hace
    falta un `Escenario` de dominio completo para probar la funcion pura."""

    escenario_id: str
    nombre: str
    activo: bool = True


_CATALOGO_ABCD = [
    _EscenarioDeCatalogo("A", "A"),
    _EscenarioDeCatalogo("B", "B"),
    _EscenarioDeCatalogo("C", "C"),
    _EscenarioDeCatalogo("D", "D"),
]


def test_el_orden_real_de_un_incluido_se_preserva_exacto_aunque_el_catalogo_no_sea_alfabetico():
    """El orden interno de la suite (C, A) NO sigue el orden alfabetico del
    catalogo (A, B, C, D): confirma que un incluido nunca se recalcula -sigue
    mostrando su posicion real dentro de la suite, no su indice en el
    catalogo."""
    filas = filas_seleccion_escenarios(_CATALOGO_ABCD, escenarios_incluidos=("C", "A"))
    por_id = {fila.escenario_id: fila for fila in filas}
    assert por_id["C"].orden == "1"
    assert por_id["A"].orden == "2"
    assert por_id["C"].incluido and por_id["A"].incluido


def test_las_sugerencias_para_no_incluidos_nunca_colisionan_con_un_orden_real():
    """Caso exacto del bug encontrado en la auditoria: con suite=(C, A) y
    catalogo alfabetico A,B,C,D, sugerir por indice crudo del catalogo le
    daria a B el mismo "2" que ya tiene A. El algoritmo de "menor libre" debe
    saltarselo."""
    filas = filas_seleccion_escenarios(_CATALOGO_ABCD, escenarios_incluidos=("C", "A"))
    ordenes = [fila.orden for fila in filas]
    assert len(ordenes) == len(set(ordenes)), f"ordenes con colision: {ordenes}"
    por_id = {fila.escenario_id: fila for fila in filas}
    assert por_id["B"].orden == "3"
    assert por_id["D"].orden == "4"
    assert not por_id["B"].incluido and not por_id["D"].incluido


def test_las_sugerencias_de_orden_son_deterministas():
    primera = filas_seleccion_escenarios(_CATALOGO_ABCD, escenarios_incluidos=("C", "A"))
    segunda = filas_seleccion_escenarios(_CATALOGO_ABCD, escenarios_incluidos=("C", "A"))
    assert [f.orden for f in primera] == [f.orden for f in segunda]


def test_una_suite_sin_ningun_incluido_sugiere_libres_consecutivos_desde_1():
    """Caso ya cubierto en la web (`test_una_suite_nueva_prellena_...`), aqui
    a nivel de la funcion pura: sin nada ocupado, el "menor libre" coincide
    con la posicion en el catalogo."""
    filas = filas_seleccion_escenarios(_CATALOGO_ABCD, escenarios_incluidos=())
    assert [f.orden for f in filas] == ["1", "2", "3", "4"]


async def test_editar_con_ordenes_repetidos_se_rechaza():
    """La ruta de EDICION (POST /suites/{id}) nunca se habia probado para
    ordenes duplicados -solo la de creacion (`test_crear_con_ordenes_repetidos_se_rechaza`)-.
    Confirma que la validacion del servidor sigue intacta ahi tambien: la
    mejora de autoorden es solo una sugerencia en el HTML, nunca una
    relajacion de `_leer_escenarios_de_suite`."""
    cliente, composicion = _cliente()
    async with cliente:
        e1 = await _crear_escenario(cliente, nombre="E1")
        e2 = await _crear_escenario(cliente, nombre="E2")
        creada = await cliente.post(
            "/suites", data={"nombre": "X", f"incluir_{e1}": "1", f"orden_{e1}": "1"}
        )
        suite_id = _id_de(creada)

        respuesta = await cliente.post(
            f"/suites/{suite_id}",
            data={
                "nombre": "X",
                f"incluir_{e1}": "1", f"orden_{e1}": "1",
                f"incluir_{e2}": "1", f"orden_{e2}": "1",
            },
        )
        suite = await composicion.administracion_suites.obtener(suite_id)
    assert respuesta.status_code == 400
    assert suite.escenarios == (e1,), "no debe modificar la membresia si el orden es invalido"


# --------------------------------------------------------------- duplicar ---


async def test_duplicar_redirige_a_la_copia_con_los_mismos_escenarios():
    cliente, composicion = _cliente()
    async with cliente:
        e1 = await _crear_escenario(cliente, nombre="E1")
        respuesta_crear = await cliente.post(
            "/suites", data={"nombre": "Original", f"incluir_{e1}": "1", f"orden_{e1}": "1"}
        )
        suite_id = _id_de(respuesta_crear)
        respuesta = await cliente.post(f"/suites/{suite_id}/duplicar")
        copia_id = _id_de(respuesta)
        copia = await composicion.administracion_suites.obtener(copia_id)
    assert respuesta.status_code == 303
    assert copia_id != suite_id
    assert copia.nombre == "Original (copia)"
    assert copia.escenarios == (e1,)


async def test_duplicar_una_suite_inexistente_da_404():
    cliente, _ = _cliente()
    async with cliente:
        respuesta = await cliente.post("/suites/NO-EXISTE/duplicar")
    assert respuesta.status_code == 404


# ------------------------------------------------------- activar/desactivar --


async def test_desactivar_una_suite_cambia_su_estado_en_el_listado():
    cliente, _ = _cliente()
    async with cliente:
        respuesta = await cliente.post("/suites", data={"nombre": "X"})
        suite_id = _id_de(respuesta)
        await cliente.post(f"/suites/{suite_id}/estado", data={"activa": "0"})
        listado = (await cliente.get("/suites")).text
    assert "Inactiva" in listado


async def test_cambiar_estado_de_una_suite_inexistente_da_404():
    cliente, _ = _cliente()
    async with cliente:
        respuesta = await cliente.post("/suites/NO-EXISTE/estado", data={"activa": "0"})
    assert respuesta.status_code == 404


# --------------------------------------------------------------- ejecutar ---


async def test_ejecutar_una_suite_redirige_al_detalle_de_la_corrida():
    cliente, composicion = _cliente(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00"))
    async with cliente:
        e1 = await _crear_escenario(cliente, nombre="E1")
        respuesta_crear = await cliente.post(
            "/suites", data={"nombre": "X", f"incluir_{e1}": "1", f"orden_{e1}": "1"}
        )
        suite_id = _id_de(respuesta_crear)
        respuesta = await cliente.post(f"/suites/{suite_id}/ejecutar")
    assert respuesta.status_code == 303
    assert "/suites/corridas/" in respuesta.headers["location"]


async def test_ejecutar_una_suite_vacia_se_rechaza():
    cliente, _ = _cliente()
    async with cliente:
        respuesta_crear = await cliente.post("/suites", data={"nombre": "Vacia"})
        suite_id = _id_de(respuesta_crear)
        respuesta = await cliente.post(f"/suites/{suite_id}/ejecutar")
    assert respuesta.status_code == 400


async def test_ejecutar_una_suite_inexistente_da_400():
    cliente, _ = _cliente()
    async with cliente:
        respuesta = await cliente.post("/suites/NO-EXISTE/ejecutar")
    assert respuesta.status_code == 400


# ----------------------------------------------------------- corridas/detalle --


async def test_el_detalle_de_una_corrida_muestra_pass_y_permite_ver_la_ejecucion():
    cliente, _ = _cliente(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00"))
    async with cliente:
        e1 = await _crear_escenario(cliente, nombre="E1")
        respuesta_crear = await cliente.post(
            "/suites", data={"nombre": "X", f"incluir_{e1}": "1", f"orden_{e1}": "1"}
        )
        suite_id = _id_de(respuesta_crear)
        respuesta_ejecutar = await cliente.post(f"/suites/{suite_id}/ejecutar")
        html = (await cliente.get(respuesta_ejecutar.headers["location"])).text
    assert "E1" in html
    # No basta con `"PASS" in html`/`"FAIL" in html`: el panel "Resumen" de
    # corrida_detalle.html imprime esos dos rotulos SIEMPRE, como encabezados
    # de metrica, sin importar el resultado real -esa asercion seria cierta
    # incluso para una corrida en FAIL puro. El item aqui no tiene
    # expectativas (el escenario se crea sin `estado_esperado`), asi que el
    # dato real e inequivoco es el atributo estructural de la fila del item.
    assert 'data-resultado="sin_expectativas"' in html


async def test_las_corridas_aparecen_en_el_listado_general():
    cliente, _ = _cliente(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00"))
    async with cliente:
        e1 = await _crear_escenario(cliente, nombre="E1")
        respuesta_crear = await cliente.post(
            "/suites", data={"nombre": "Regresion", f"incluir_{e1}": "1", f"orden_{e1}": "1"}
        )
        suite_id = _id_de(respuesta_crear)
        await cliente.post(f"/suites/{suite_id}/ejecutar")
        html = (await cliente.get("/suites/corridas")).text
    assert "Regresion" in html or "Regresión" in html


async def test_una_corrida_inexistente_da_404():
    cliente, _ = _cliente()
    async with cliente:
        respuesta = await cliente.get("/suites/corridas/999999")
    assert respuesta.status_code == 404


async def test_un_id_de_corrida_no_numerico_da_404_y_no_el_422_de_fastapi():
    cliente, _ = _cliente()
    async with cliente:
        respuesta = await cliente.get("/suites/corridas/abc")
    assert respuesta.status_code == 404
    assert '"detail"' not in respuesta.text


async def test_el_detalle_de_corrida_sigue_mostrando_la_discrepancia_original_tras_editar_la_expectativa():
    """El caso puntual pedido: un item FAIL con `evaluacion_json` historico
    (discrepancia real, no inventada) debe seguir mostrando ESA discrepancia
    en `/suites/corridas/{id}` despues de editar las expectativas del
    escenario -la pantalla lee `corrida_suite_items.evaluacion_json`, nunca
    reevalua contra el escenario vivo.
    """
    evaluacion_json_historico = (
        '{"version":1,"resultado":"fail",'
        '"expectativas":{"estado":null,"campos":{"39":{"tipo":"igual","valor":"00"}}},'
        '"discrepancias":[{"criterio":"campo","campo":"39","tipo":"igual",'
        '"esperado":"00","recibido":"05"}]}'
    )
    cliente, composicion = _cliente(
        resultado=_resultado(
            EstadoEjecucion.RECHAZADA, codigo="05",
            evaluacion_estado="fail", evaluacion_json=evaluacion_json_historico,
        )
    )
    async with cliente:
        e1 = await _crear_escenario(cliente, nombre="E1")
        respuesta_crear = await cliente.post(
            "/suites", data={"nombre": "X", f"incluir_{e1}": "1", f"orden_{e1}": "1"}
        )
        suite_id = _id_de(respuesta_crear)
        respuesta_ejecutar = await cliente.post(f"/suites/{suite_id}/ejecutar")
        ubicacion_corrida = respuesta_ejecutar.headers["location"]

        html_antes = (await cliente.get(ubicacion_corrida)).text
        assert "«00»" in html_antes and "«05»" in html_antes

        # Se edita la expectativa del escenario a algo totalmente distinto.
        await cliente.post(
            f"/escenarios/{e1}",
            data={**FORMULARIO_ESCENARIO, "estado_esperado": "aprobada"},
        )

        html_despues = (await cliente.get(ubicacion_corrida)).text

    assert "«00»" in html_despues and "«05»" in html_despues, (
        "la discrepancia historica original debe seguir intacta"
    )
    assert "FAIL" in html_despues

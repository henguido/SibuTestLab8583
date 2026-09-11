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

from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, DESTINO_ID_DEMO, PAN_DEMO
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


# --------------------------------------------------------------- exportar ---
#
# Mejora funcional posterior a la entrega: descargar JSON/CSV desde el
# detalle de una corrida, reutilizando exactamente el mismo reporte que ya
# usa `sibu-run-suite export-run` (`application/exportacion_corridas.py`).


async def _corrida_de_prueba(cliente) -> str:
    e1 = await _crear_escenario(cliente, nombre="E1")
    respuesta_crear = await cliente.post(
        "/suites", data={"nombre": "Exportable", f"incluir_{e1}": "1", f"orden_{e1}": "1"}
    )
    suite_id = _id_de(respuesta_crear)
    respuesta_ejecutar = await cliente.post(f"/suites/{suite_id}/ejecutar")
    return respuesta_ejecutar.headers["location"].rstrip("/").split("/")[-1]


async def test_el_detalle_de_corrida_ofrece_los_dos_botones_de_descarga():
    cliente, _ = _cliente(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00"))
    async with cliente:
        corrida_id = await _corrida_de_prueba(cliente)
        html = (await cliente.get(f"/suites/corridas/{corrida_id}")).text
    assert f"/suites/corridas/{corrida_id}/exportar.json" in html
    assert f"/suites/corridas/{corrida_id}/exportar.csv" in html


async def test_exportar_json_reutiliza_el_mismo_reporte_que_la_cli():
    from sibutestlab8583.application import exportacion_corridas

    cliente, composicion = _cliente(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00"))
    async with cliente:
        corrida_id = await _corrida_de_prueba(cliente)
        respuesta = await cliente.get(f"/suites/corridas/{corrida_id}/exportar.json")

        corrida = await composicion.corridas_suite.obtener(int(corrida_id))
        items = await composicion.corridas_suite.obtener_items(int(corrida_id))
        esperado = exportacion_corridas.reporte_a_json(corrida, items)

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("application/json")
    assert respuesta.text == esperado


async def test_exportar_csv_trae_encabezado_y_content_disposition():
    cliente, _ = _cliente(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00"))
    async with cliente:
        corrida_id = await _corrida_de_prueba(cliente)
        respuesta = await cliente.get(f"/suites/corridas/{corrida_id}/exportar.csv")
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("text/csv")
    assert f'corrida-{corrida_id}.csv' in respuesta.headers["content-disposition"]
    assert respuesta.text.startswith("corrida_id,suite_id,suite_nombre")


async def test_exportar_una_corrida_inexistente_da_404_sin_ejecutar_nada():
    cliente, _ = _cliente()
    async with cliente:
        respuesta = await cliente.get("/suites/corridas/999999/exportar.json")
    assert respuesta.status_code == 404


async def test_exportar_con_id_no_numerico_da_404():
    cliente, _ = _cliente()
    async with cliente:
        respuesta = await cliente.get("/suites/corridas/abc/exportar.csv")
    assert respuesta.status_code == 404


def _contar_filas(ruta_db, tabla: str) -> int:
    import sqlite3

    with sqlite3.connect(ruta_db) as conexion:
        return conexion.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]


async def test_exportar_no_crea_ejecuciones_ni_corridas_nuevas():
    """Exportar es de solo lectura: ni una nueva ejecucion, ni una nueva
    corrida, ni siquiera al pedir los dos formatos varias veces.
    """
    cliente, composicion = _cliente(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00"))
    async with cliente:
        corrida_id = await _corrida_de_prueba(cliente)
        ejecuciones_antes = _contar_filas(composicion._ruta_suites, "ejecuciones")
        corridas_antes = _contar_filas(composicion._ruta_suites, "corridas_suite")

        await cliente.get(f"/suites/corridas/{corrida_id}/exportar.json")
        await cliente.get(f"/suites/corridas/{corrida_id}/exportar.csv")
        await cliente.get(f"/suites/corridas/{corrida_id}/exportar.json")

        ejecuciones_despues = _contar_filas(composicion._ruta_suites, "ejecuciones")
        corridas_despues = _contar_filas(composicion._ruta_suites, "corridas_suite")

    assert ejecuciones_despues == ejecuciones_antes
    assert corridas_despues == corridas_antes


async def test_exportar_no_cambia_aunque_se_edite_el_escenario_despues():
    """El reporte exportado es un snapshot: editar el escenario (u otro
    escenario con el mismo nombre) despues de correr la suite no debe alterar
    ni un byte de lo que ya se exporta -mismo principio que ya prueba
    `test_el_detalle_de_corrida_sigue_mostrando_la_discrepancia_original_tras_editar_la_expectativa`,
    aplicado a la exportacion en vez de al HTML del detalle.
    """
    cliente, _ = _cliente(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00"))
    async with cliente:
        e1 = await _crear_escenario(cliente, nombre="Antes de editar")
        respuesta_crear = await cliente.post(
            "/suites", data={"nombre": "Exportable2", f"incluir_{e1}": "1", f"orden_{e1}": "1"}
        )
        suite_id = _id_de(respuesta_crear)
        respuesta_ejecutar = await cliente.post(f"/suites/{suite_id}/ejecutar")
        corrida_id = respuesta_ejecutar.headers["location"].rstrip("/").split("/")[-1]

        json_antes = (await cliente.get(f"/suites/corridas/{corrida_id}/exportar.json")).text
        csv_antes = (await cliente.get(f"/suites/corridas/{corrida_id}/exportar.csv")).text

        # Se edita el escenario (nombre, tarjeta, monto) DESPUES de la corrida.
        await cliente.post(
            f"/escenarios/{e1}",
            data={**FORMULARIO_ESCENARIO, "nombre": "Después de editar", "monto": "999.99"},
        )
        # Y se desactiva la suite -tampoco debe afectar un reporte ya emitido.
        await cliente.post(f"/suites/{suite_id}/estado", data={"activa": "0"})

        json_despues = (await cliente.get(f"/suites/corridas/{corrida_id}/exportar.json")).text
        csv_despues = (await cliente.get(f"/suites/corridas/{corrida_id}/exportar.csv")).text

    assert json_despues == json_antes
    assert csv_despues == csv_antes
    assert "Antes de editar" in json_antes
    assert "Después de editar" not in json_antes
    assert "999.99" not in json_antes


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


# ---------------------------------------------------- comparar / reintentar --
#
# GESTION AVANZADA DE CORRIDAS: comparacion historica entre dos corridas de
# la misma suite, y reintento selectivo de items en FAIL/ERROR. El doble de
# orquestador (`OrquestadorFalso`) devuelve el MISMO resultado a cualquier
# escenario que corra en un mismo `ComposicionFalsa`: por eso el "mix" de
# resultados en estas pruebas se logra desactivando un escenario ANTES de
# ejecutar (eso da ERROR sin pasar por el orquestador), no variando el
# resultado por escenario.


async def _suite_fail_y_error(cliente, *, nombre_suite="MixtaWeb"):
    """2 escenarios: `e1` activo -da FAIL, por el `resultado` fijo del
    doble-, `e2` desactivado ANTES de correr -da ERROR-. Devuelve
    (suite_id, corrida_id, e1, e2).
    """
    e1 = await _crear_escenario(cliente, nombre="E1")
    e2 = await _crear_escenario(cliente, nombre="E2")
    respuesta_crear = await cliente.post(
        "/suites",
        data={
            "nombre": nombre_suite,
            f"incluir_{e1}": "1", f"orden_{e1}": "1",
            f"incluir_{e2}": "1", f"orden_{e2}": "2",
        },
    )
    suite_id = _id_de(respuesta_crear)
    await cliente.post(f"/escenarios/{e2}/estado", data={"activo": "0"})
    respuesta_ejecutar = await cliente.post(f"/suites/{suite_id}/ejecutar")
    corrida_id = respuesta_ejecutar.headers["location"].rstrip("/").split("/")[-1]
    return suite_id, corrida_id, e1, e2


def _resultado_fail() -> object:
    return _resultado(EstadoEjecucion.RECHAZADA, codigo="05", evaluacion_estado="fail")


async def test_comparar_sin_contra_muestra_selector_con_otras_corridas_de_la_misma_suite():
    cliente, _ = _cliente(resultado=_resultado_fail())
    async with cliente:
        suite_id, corrida_1, e1, e2 = await _suite_fail_y_error(cliente)
        respuesta_2 = await cliente.post(f"/suites/{suite_id}/ejecutar")
        corrida_2 = respuesta_2.headers["location"].rstrip("/").split("/")[-1]

        html = (await cliente.get(f"/suites/corridas/{corrida_1}/comparar")).text

    assert respuesta_2.status_code == 303
    assert f"Corrida #{corrida_2}" in html
    assert "resumen" not in html.lower() or "Escenarios" not in html  # sin `contra`, no hay tabla todavia


async def test_comparar_sin_otras_corridas_muestra_estado_vacio():
    cliente, _ = _cliente(resultado=_resultado_fail())
    async with cliente:
        _, corrida_id, _, _ = await _suite_fail_y_error(cliente)
        html = (await cliente.get(f"/suites/corridas/{corrida_id}/comparar")).text
    assert "No hay otra corrida" in html


async def test_comparar_con_contra_muestra_resumen_y_tabla():
    cliente, _ = _cliente(resultado=_resultado_fail())
    async with cliente:
        suite_id, corrida_1, e1, e2 = await _suite_fail_y_error(cliente)
        respuesta_2 = await cliente.post(f"/suites/{suite_id}/ejecutar")
        corrida_2 = respuesta_2.headers["location"].rstrip("/").split("/")[-1]

        html = (
            await cliente.get(f"/suites/corridas/{corrida_1}/comparar", params={"contra": corrida_2})
        ).text

    assert "Sin cambio" in html
    assert f"A = #{corrida_1}" in html or f"#{corrida_1}" in html
    assert f"#{corrida_2}" in html
    # Ambos escenarios corrieron igual en las dos corridas (mismo doble,
    # mismo resultado fijo, mismo escenario desactivado): todo SIN_CAMBIO.
    assert "empeoro" not in html and "mejoro" not in html


async def test_comparar_corridas_de_suites_distintas_da_error_web():
    cliente, _ = _cliente(resultado=_resultado_fail())
    async with cliente:
        _, corrida_1, _, _ = await _suite_fail_y_error(cliente, nombre_suite="Suite1")
        _, corrida_2, _, _ = await _suite_fail_y_error(cliente, nombre_suite="Suite2")

        respuesta = await cliente.get(
            f"/suites/corridas/{corrida_1}/comparar", params={"contra": corrida_2}
        )

    assert respuesta.status_code == 400
    assert "misma suite" in respuesta.text.lower()


async def test_comparar_corrida_inexistente_da_error_web():
    cliente, _ = _cliente(resultado=_resultado_fail())
    async with cliente:
        _, corrida_1, _, _ = await _suite_fail_y_error(cliente)
        respuesta = await cliente.get(
            f"/suites/corridas/{corrida_1}/comparar", params={"contra": "999999"}
        )
    assert respuesta.status_code == 404


async def test_comparar_id_no_numerico_da_404():
    cliente, _ = _cliente()
    async with cliente:
        respuesta = await cliente.get("/suites/corridas/abc/comparar")
    assert respuesta.status_code == 404


async def test_comparar_nunca_expone_el_pan_completo():
    cliente, _ = _cliente(resultado=_resultado_fail())
    async with cliente:
        suite_id, corrida_1, _, _ = await _suite_fail_y_error(cliente)
        respuesta_2 = await cliente.post(f"/suites/{suite_id}/ejecutar")
        corrida_2 = respuesta_2.headers["location"].rstrip("/").split("/")[-1]
        html = (
            await cliente.get(f"/suites/corridas/{corrida_1}/comparar", params={"contra": corrida_2})
        ).text
    assert PAN_DEMO not in html


async def test_detalle_de_corrida_oculta_reintentar_si_no_hay_fallidos():
    cliente, _ = _cliente(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00", evaluacion_estado="pass"))
    async with cliente:
        corrida_id = await _corrida_de_prueba(cliente)
        html = (await cliente.get(f"/suites/corridas/{corrida_id}")).text
    assert "Reintentar fallidos" not in html


async def test_detalle_de_corrida_ofrece_reintentar_si_hay_fallidos():
    cliente, _ = _cliente(resultado=_resultado_fail())
    async with cliente:
        _, corrida_id, _, _ = await _suite_fail_y_error(cliente)
        html = (await cliente.get(f"/suites/corridas/{corrida_id}")).text
    assert "Reintentar fallidos" in html
    assert f"/suites/corridas/{corrida_id}/comparar" in html


async def test_reintentar_crea_corrida_nueva_y_redirige():
    cliente, composicion = _cliente(resultado=_resultado_fail())
    async with cliente:
        _, corrida_id, e1, e2 = await _suite_fail_y_error(cliente)
        respuesta = await cliente.post(f"/suites/corridas/{corrida_id}/reintentar")

    assert respuesta.status_code == 303
    nueva_id = respuesta.headers["location"].rstrip("/").split("/")[-1]
    assert nueva_id != corrida_id
    items_nueva = await composicion.corridas_suite.obtener_items(int(nueva_id))
    assert {item.escenario_id for item in items_nueva} == {e1, e2}


async def test_reintentar_sin_fallidos_no_crea_corrida_y_muestra_error():
    cliente, composicion = _cliente(
        resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00", evaluacion_estado="pass")
    )
    async with cliente:
        corrida_id = await _corrida_de_prueba(cliente)
        antes = len(await composicion.corridas_suite.listar())

        respuesta = await cliente.post(f"/suites/corridas/{corrida_id}/reintentar")

        assert respuesta.status_code == 400
        assert "FAIL o ERROR" in respuesta.text
        assert len(await composicion.corridas_suite.listar()) == antes


async def test_reintentar_id_no_numerico_da_404():
    cliente, _ = _cliente()
    async with cliente:
        respuesta = await cliente.post("/suites/corridas/abc/reintentar")
    assert respuesta.status_code == 404


async def test_reintentar_corrida_inexistente_da_404():
    cliente, _ = _cliente()
    async with cliente:
        respuesta = await cliente.post("/suites/corridas/999999/reintentar")
    assert respuesta.status_code == 404


async def test_comparar_muestra_solo_en_a_y_solo_en_b_correctamente():
    """Dos corridas de la MISMA suite, pero con membresia distinta: `e2` se
    agrega a la suite DESPUES de la primera corrida. Comparar en un sentido
    da SOLO_EN_B (e2 no estaba en la corrida vieja); comparar en el otro da
    SOLO_EN_A (e2 no esta en la corrida vieja cuando esta es "B").
    """
    cliente, _ = _cliente(resultado=_resultado_fail())
    async with cliente:
        e1 = await _crear_escenario(cliente, nombre="E1 base")
        e2 = await _crear_escenario(cliente, nombre="E2 agregado despues")
        respuesta_crear = await cliente.post(
            "/suites", data={"nombre": "SoloSuite", f"incluir_{e1}": "1", f"orden_{e1}": "1"}
        )
        suite_id = _id_de(respuesta_crear)
        respuesta_1 = await cliente.post(f"/suites/{suite_id}/ejecutar")
        corrida_1 = respuesta_1.headers["location"].rstrip("/").split("/")[-1]

        # Se agrega e2 a la suite ANTES de la segunda corrida.
        await cliente.post(
            f"/suites/{suite_id}",
            data={
                "nombre": "SoloSuite",
                f"incluir_{e1}": "1", f"orden_{e1}": "1",
                f"incluir_{e2}": "1", f"orden_{e2}": "2",
            },
        )
        respuesta_2 = await cliente.post(f"/suites/{suite_id}/ejecutar")
        corrida_2 = respuesta_2.headers["location"].rstrip("/").split("/")[-1]

        # A = corrida_1 (sin e2), B = corrida_2 (con e2) -> e2 SOLO_EN_B.
        respuesta_b = await cliente.get(
            f"/suites/corridas/{corrida_1}/comparar", params={"contra": corrida_2}
        )
        # A = corrida_2 (con e2), B = corrida_1 (sin e2) -> e2 SOLO_EN_A.
        respuesta_a = await cliente.get(
            f"/suites/corridas/{corrida_2}/comparar", params={"contra": corrida_1}
        )

    assert respuesta_b.status_code == 200
    assert respuesta_a.status_code == 200
    html_b, html_a = respuesta_b.text, respuesta_a.text

    # El escenario correcto aparece en ambas vistas.
    assert "E2 agregado despues" in html_b
    assert "E2 agregado despues" in html_a

    # La clasificacion correcta aparece en cada sentido.
    assert "Solo en B" in html_b
    assert "Solo en A" in html_a

    # El lado ausente se muestra vacio/no disponible de forma controlada
    # (el template usa `<span class="vacio">—</span>` cuando `resultado_a`/
    # `resultado_b` es `None`), nunca una celda rota o un valor inventado.
    assert 'class="vacio">—<' in html_b
    assert 'class="vacio">—<' in html_a

    # Nada de traceback ni PAN completo en ninguna de las dos vistas.
    for html in (html_a, html_b):
        assert "Traceback" not in html
        assert PAN_DEMO not in html

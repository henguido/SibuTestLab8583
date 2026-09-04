"""Estructura de la interfaz tras el rediseno.

Estas pruebas vigilan **contratos de interfaz**, no apariencia: que la
navegacion exista y marque la pantalla activa, que los siete desenlaces se
rendericen y se distingan por texto, que el formulario conserve sus campos, que
el historial muestre lo que hay que leer y que el numero de tarjeta completo no
aparezca por ninguna via.

A proposito **no** se comprueba ningun color, ninguna medida ni ninguna clase de
estilo concreta: eso cambiaria en el siguiente ajuste visual sin que nada se
haya roto. Lo que si se comprueba es el texto que lee una persona, el atributo
`data-estado` que lee una herramienta, y la ausencia de datos sensibles.
"""

from __future__ import annotations

import re

import pytest
from test_web import ComposicionFalsa, _cliente, _resultado, FORMULARIO

from sibutestlab8583.adapters.persistence.esquema import (
    CARD_ID_DEMO,
    DESTINO_ID_DEMO,
    PAN_DEMO,
)
from sibutestlab8583.domain.modelos import Ejecucion, EstadoEjecucion, ResultadoCompra
from sibutestlab8583.web.app import RUTA_ESTATICA, crear_app
from sibutestlab8583.web.presentacion import AVISOS, SECCIONES

#: Toda secuencia con largo de tarjeta, para revisar atributos y contenido.
LARGO_DE_TARJETA = re.compile(r"(?<!\d)\d{12,19}(?!\d)")

#: Palabras que en espanol llevan tilde y que el texto visible no debe mostrar
#: sin ella. Los identificadores, clases, tokens y valores de `data-estado` si
#: van en ASCII, asi que la comprobacion se hace **solo sobre el texto**, con las
#: etiquetas HTML ya retiradas.
#: Deliberadamente NO estan aqui "proceso", "intento", "termino", "espero" ni
#: "envio": las cuatro primeras existen sin tilde como sustantivo o presente
#: ("Codigo de proceso", "Todo intento queda registrado"), asi que prohibirlas
#: daria falsos positivos sobre texto correcto.
SIN_TILDE_PROHIBIDAS = (
    "transaccion", "conexion", "transmision", "codigo", "numero", "invalida",
    "demostracion", "sintetica", "sinteticos", "interrumpio", "ejecucion",
    "limite", "catalogo", "operacion", "version", "descripcion", "recuperacion",
    "autorizacion", "numerico", "aprobacion", "sesion", "todavia", "tambien",
    "ningun", "recibio", "establecio", "llego", "viajo", "armo", "ocurrio",
    "aqui", "mas abajo",
)


def _solo_texto(html: str) -> str:
    """El HTML sin sus etiquetas: lo que de verdad lee una persona."""
    return re.sub(r"<[^>]*>", " ", html)


#: Toda pantalla del producto. Es la fuente unica: `_paginas()` la usa para
#: renderizar y las guardias parametrizadas la usan para saber sobre que iterar,
#: de modo que agregar una pantalla la mete en todas las guardias a la vez y no
#: se puede olvidar ninguna.
PANTALLAS = (
    "compra", "resultado", "historial", "detalle", "no_encontrado",
    "configuracion", "config_tarjetas", "config_tarjeta_nueva", "config_tarjeta_editar",
    "config_conexiones", "config_conexion_nueva", "config_conexion_editar",
)


def _paginas() -> dict[str, str]:
    """El HTML de las doce pantallas, con contenido en todas."""
    ejecucion = _resultado(EstadoEjecucion.APROBADA, codigo="00").ejecucion
    cliente = _cliente(
        resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00"), ejecuciones=[ejecucion]
    )
    paginas = {
        "compra": cliente.get("/").text,
        "resultado": cliente.post("/compra", data=FORMULARIO).text,
        "historial": cliente.get("/historial").text,
        "detalle": cliente.get(f"/historial/{ejecucion.id}").text,
        "no_encontrado": cliente.get("/historial/999999").text,
        "configuracion": cliente.get("/configuracion").text,
        "config_tarjetas": cliente.get("/configuracion/tarjetas").text,
        "config_tarjeta_nueva": cliente.get("/configuracion/tarjetas/nueva").text,
        "config_tarjeta_editar": cliente.get(
            f"/configuracion/tarjetas/{CARD_ID_DEMO}/editar"
        ).text,
        "config_conexiones": cliente.get("/configuracion/conexiones").text,
        "config_conexion_nueva": cliente.get("/configuracion/conexiones/nueva").text,
        "config_conexion_editar": cliente.get(
            f"/configuracion/conexiones/{DESTINO_ID_DEMO}/editar"
        ).text,
    }
    assert tuple(paginas) == PANTALLAS, "PANTALLAS y _paginas() se desincronizaron"
    return paginas


# ----------------------------------------------------------- 1. NAVEGACION ---


def test_las_tres_pantallas_comparten_la_identidad_y_el_subtitulo():
    for nombre, html in _paginas().items():
        assert "SibuTestLab" in html, f"falta la identidad en {nombre}"
        assert "Laboratorio de pruebas ISO 8583" in html, f"falta el subtitulo en {nombre}"


@pytest.mark.parametrize("apartado", SECCIONES, ids=lambda s: s.clave)
def test_toda_seccion_declarada_aparece_en_la_navegacion_y_responde(apartado):
    """Ningun enlace de la navegacion puede llevar a una ruta que no exista."""
    cliente = _cliente()
    html = cliente.get("/").text

    assert f'href="{apartado.ruta}"' in html
    assert apartado.texto in html
    assert cliente.get(apartado.ruta).status_code == 200


def test_la_navegacion_no_ofrece_secciones_todavia_no_servidas():
    """`Tarjetas de prueba` esta prevista, pero su ruta aun no existe."""
    html = _cliente().get("/").text
    assert 'href="/tarjetas"' not in html
    assert "Tarjetas de prueba" not in html


@pytest.mark.parametrize(
    "ruta,clave",
    [("/", "compra"), ("/historial", "historial"), ("/configuracion", "configuracion")],
)
def test_cada_pantalla_marca_su_propia_seccion_como_activa(ruta, clave):
    html = _cliente().get(ruta).text
    esperado = next(s for s in SECCIONES if s.clave == clave)

    marcado = re.findall(r'<a class="nav__enlace"[^>]*>', html)
    activos = [etiqueta for etiqueta in marcado if 'aria-current="page"' in etiqueta]

    assert len(activos) == 1, "debe haber exactamente una seccion activa"
    assert esperado.ruta in activos[0]


def test_el_resultado_sigue_dentro_de_la_seccion_de_transaccion():
    html = _cliente(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00")).post(
        "/compra", data=FORMULARIO
    ).text
    activos = [e for e in re.findall(r'<a class="nav__enlace"[^>]*>', html) if "aria-current" in e]
    assert len(activos) == 1
    assert 'href="/"' in activos[0]


# ------------------------------------------------- 2. LOS SIETE DESENLACES ---


@pytest.mark.parametrize("estado", list(EstadoEjecucion), ids=lambda e: e.value)
def test_cada_estado_se_renderiza_con_senal_rotulo_titulo_y_explicacion(estado):
    """Cuatro pistas por desenlace, y el color no es ninguna de las cuatro."""
    con_respuesta = estado in (
        EstadoEjecucion.APROBADA,
        EstadoEjecucion.RECHAZADA,
        EstadoEjecucion.INVALIDA,
    )
    html = _cliente(
        resultado=_resultado(estado, codigo="00" if con_respuesta else None,
                             con_respuesta=con_respuesta)
    ).post("/compra", data=FORMULARIO).text

    aviso = AVISOS[estado]
    assert f'data-estado="{estado.value}"' in html, "el estado exacto debe quedar legible"
    assert aviso.titulo in html
    assert aviso.etiqueta in html, "falta el rotulo corto"
    assert aviso.detalle[:60] in html, "falta la explicacion"
    assert "<svg" in html, "falta la senal grafica"


def test_los_siete_avisos_traen_rotulo_y_senal():
    assert set(AVISOS) == set(EstadoEjecucion)
    for estado, aviso in AVISOS.items():
        assert aviso.etiqueta, f"{estado.value} no tiene rotulo corto"
        assert aviso.senal, f"{estado.value} no tiene senal"


@pytest.mark.parametrize("atributo", ["titulo", "etiqueta", "senal"])
def test_ningun_desenlace_se_confunde_con_otro(atributo):
    """Titulos, rotulos y senales distinguen los siete casos entre si."""
    valores = [getattr(aviso, atributo) for aviso in AVISOS.values()]
    assert len(set(valores)) == len(EstadoEjecucion), f"hay {atributo} repetidos: {valores}"


def test_un_estado_sin_intento_de_red_lo_dice_en_el_resumen():
    """`NO_ENVIADA` no debe mostrar un destino como si se hubiera usado."""
    base = _resultado(EstadoEjecucion.NO_ENVIADA, con_respuesta=False)
    ejecucion = Ejecucion(
        card_id=base.ejecucion.card_id,
        monto=base.ejecucion.monto,
        moneda=base.ejecucion.moneda,
        stan=base.ejecucion.stan,
        estado=EstadoEjecucion.NO_ENVIADA,
        destino_host=None,
        destino_puerto=None,
        creada_en=base.ejecucion.creada_en,
    )
    resultado = ResultadoCompra(
        ejecucion=ejecucion, solicitud=base.solicitud, motivos=("faltan campos: 4",)
    )

    html = _cliente(resultado=resultado).post("/compra", data=FORMULARIO).text
    assert "no se intentó transmisión por la red" in html
    assert "faltan campos: 4" in html


# ------------------------------------------------------------ 3. FORMULARIO ---


def test_el_formulario_conserva_sus_campos_y_su_conexion():
    html = _cliente().get("/").text
    assert 'method="post"' in html and 'action="/compra"' in html
    for campo in ("card_id", "monto", "conexion_id"):
        assert f'name="{campo}"' in html, f"falta el campo {campo}"
    assert "Ejecutar transacción" in html


def test_el_formulario_no_ofrece_ningun_campo_de_red_editable():
    """Host, puerto y timeout se administran solo en Configuración → Conexiones."""
    html = _cliente().get("/").text
    for campo in ("host", "puerto", "timeout"):
        assert f'name="{campo}"' not in html, f"la compra no debe exponer {campo}"


def test_la_conexion_es_una_barra_compacta_sin_panel_propio():
    """La conexion es contexto secundario: sin encabezado grande, sin panel,
    sin el texto explicativo largo, y con host:puerto/estado solo de lectura.
    """
    html = _cliente().get("/").text
    assert '<h2 class="panel__titulo">Conexión</h2>' not in html
    assert "La conexión no se configura aquí" not in html
    assert "Sin verificar" in html
    assert "127.0.0.1:8583" in html
    assert "Cambiar" not in html, "con una sola conexion activa no hace falta el enlace"


def test_construir_transaccion_es_lo_primero_despues_de_la_barra_de_conexion():
    html = _cliente().get("/").text
    assert html.index("conexion-barra") < html.index("Construir transacción")


def test_la_tarjeta_muestra_identificador_numero_enmascarado_y_descripcion():
    html = _cliente().get("/").text
    assert CARD_ID_DEMO in html
    assert "************6666" in html
    assert "Tarjeta de demostración" in html
    assert PAN_DEMO not in html


def test_hay_una_tarjeta_preseleccionada():
    """Sin preseleccion, el primer envio fallaria sin motivo para el usuario.

    La conexion ya no es un grupo de radios -es un valor de solo lectura mas
    un enlace "Cambiar conexion"-, asi que el unico "checked" que debe existir
    es el de la tarjeta.
    """
    html = _cliente().get("/").text
    assert html.count("checked") == 1


def test_todo_control_de_texto_tiene_su_rotulo_asociado():
    html = _cliente().get("/").text
    identificadores = re.findall(r'<input type="text"[^>]*id="([^"]+)"', html)
    assert identificadores, "no se encontro ningun control de texto"
    for identificador in identificadores:
        assert f'for="{identificador}"' in html, f"{identificador} no tiene label"


def test_las_paginas_declaran_idioma_un_solo_h1_y_salto_al_contenido():
    for nombre, html in _paginas().items():
        assert '<html lang="es">' in html, f"{nombre} no declara idioma"
        assert html.count("<h1>") == 1, f"{nombre} no tiene exactamente un h1"
        assert 'href="#contenido"' in html, f"{nombre} no ofrece salto al contenido"


# ------------------------------------------------------------- 4. HISTORIAL ---


def test_el_historial_muestra_las_ocho_columnas_que_hacen_falta():
    ejecucion = _resultado(EstadoEjecucion.APROBADA, codigo="00").ejecucion
    html = _cliente(ejecuciones=[ejecucion]).get("/historial").text

    for encabezado in ("Fecha y hora", "STAN", "Tarjeta", "Monto", "Estado",
                       "Código", "Latencia", "Destino", "Detalle"):
        assert encabezado in html, f"falta la columna {encabezado}"

    assert ejecucion.stan in html, "el STAN debe verse: distingue una ejecucion de otra"
    assert ejecucion.card_id in html
    assert str(ejecucion.monto) in html
    assert ejecucion.moneda in html
    assert AVISOS[ejecucion.estado].etiqueta in html, "el estado debe leerse en palabras"
    assert f'data-estado="{ejecucion.estado.value}"' in html
    assert "7 ms" in html
    assert "127.0.0.1:8583" in html


def test_el_historial_dice_cuantos_registros_hay():
    ejecucion = _resultado(EstadoEjecucion.APROBADA, codigo="00").ejecucion
    assert "1 registro" in _cliente(ejecuciones=[ejecucion]).get("/historial").text
    assert "0 registros" in _cliente().get("/historial").text


def test_las_tablas_se_desplazan_sin_arrastrar_la_pagina():
    """El desplazamiento horizontal vive en el contenedor, no en el cuerpo."""
    for nombre in ("resultado", "historial", "detalle"):
        html = _paginas()[nombre]
        assert 'class="desplazable"' in html, f"{nombre} no acota el desplazamiento"


# -------------------------------------------------------------- 5. SEGURIDAD ---


def test_ninguna_pantalla_expone_el_numero_completo_por_ninguna_via():
    for nombre, html in _paginas().items():
        assert PAN_DEMO not in html, f"{nombre} expone el numero completo"

        for valor in re.findall(r'data-[\w-]+="([^"]*)"', html):
            assert not LARGO_DE_TARJETA.search(valor), f"{nombre}: data-* con largo de tarjeta"

        for oculto in re.findall(r'<input[^>]*type="hidden"[^>]*>', html):
            assert not LARGO_DE_TARJETA.search(oculto), f"{nombre}: campo oculto sospechoso"

        for comentario in re.findall(r"<!--(.*?)-->", html, re.DOTALL):
            assert not LARGO_DE_TARJETA.search(comentario), f"{nombre}: comentario sospechoso"


def test_la_interfaz_no_ejecuta_javascript():
    """No hay guion que pueda filtrar nada: el rediseno es HTML y CSS.

    "Cambiar conexion" se resuelve con `<details>` nativo y enlaces
    `/?conexion_id=...`: no hace falta JavaScript ni para eso ni para nada mas
    en esta pantalla. El servidor nunca confio en un guion para la seguridad
    de la conexion -ver `_interpretar_formulario` en `web/app.py`-, y ahora
    tampoco existe uno para la UX.
    """
    for nombre, html in _paginas().items():
        assert "<script" not in html.lower(), f"{nombre} incluye JavaScript"
        assert "onclick" not in html.lower(), f"{nombre} incluye un manejador en linea"


# --------------------------------------------------------- 5b. ORTOGRAFIA ---


@pytest.mark.parametrize("pantalla", PANTALLAS)
def test_el_texto_visible_lleva_ortografia_espanola_completa(pantalla):
    """El usuario lee espanol, no ASCII.

    Se revisa el texto con las etiquetas ya retiradas: identificadores, clases,
    tokens y valores de `data-estado` se quedan en ASCII a proposito y no deben
    hacer fallar esto.
    """
    texto = _solo_texto(_paginas()[pantalla]).lower()
    hallazgos = [
        palabra
        for palabra in SIN_TILDE_PROHIBIDAS
        if re.search(rf"\b{re.escape(palabra)}\b", texto)
    ]
    assert not hallazgos, f"{pantalla}: texto visible sin tilde -> {hallazgos}"


def test_los_avisos_y_la_navegacion_estan_escritos_en_espanol_pleno():
    """Los rotulos que gobiernan la interfaz, comprobados en su origen."""
    visibles = [s.texto for s in SECCIONES]
    for aviso in AVISOS.values():
        visibles += [aviso.titulo, aviso.detalle, aviso.etiqueta]

    for texto in visibles:
        hallazgos = [
            palabra
            for palabra in SIN_TILDE_PROHIBIDAS
            if re.search(rf"\b{re.escape(palabra)}\b", texto.lower())
        ]
        assert not hallazgos, f"{texto[:50]!r} sin tilde -> {hallazgos}"


def test_los_identificadores_tecnicos_siguen_en_ascii():
    """La ortografia es del texto, no de las claves: nada de tildes en `data-*`."""
    for estado in EstadoEjecucion:
        assert estado.value.isascii(), f"{estado.name} tiene un valor no ASCII"
    for aviso in AVISOS.values():
        assert aviso.tono.isascii(), f"tono no ASCII: {aviso.tono}"
        assert aviso.senal.isascii(), f"senal no ASCII: {aviso.senal}"
    for apartado in SECCIONES:
        assert apartado.clave.isascii() and apartado.ruta.isascii()

    for nombre, html in _paginas().items():
        for atributo, valor in re.findall(r'(data-[\w-]+)="([^"]*)"', html):
            assert valor.isascii(), f"{nombre}: {atributo}={valor!r} no es ASCII"


def test_el_isoscopio_avisa_que_el_campo_va_enmascarado():
    html = _paginas()["resultado"]
    assert "enmascarado" in html
    assert PAN_DEMO not in html


# ------------------------------------------------------------------- 6. CSS ---


def test_la_hoja_de_estilos_se_sirve_y_la_base_la_referencia():
    cliente = _cliente()
    hoja = cliente.get(f"{RUTA_ESTATICA}/sibu.css")

    assert hoja.status_code == 200
    assert "css" in hoja.headers["content-type"]
    assert f'href="{RUTA_ESTATICA}/sibu.css"' in cliente.get("/").text


def test_los_estilos_no_quedaron_dispersos_en_las_plantillas():
    """Una sola hoja: ninguna pantalla trae su propio bloque de estilos."""
    for nombre, html in _paginas().items():
        assert "<style" not in html.lower(), f"{nombre} trae estilos embebidos"


def test_la_hoja_define_los_siete_estados_y_sus_tokens():
    hoja = _cliente().get(f"{RUTA_ESTATICA}/sibu.css").text
    for tono in {aviso.tono for aviso in AVISOS.values()}:
        assert f"--est-{tono}:" in hoja, f"el tono {tono} no tiene token de color"
    for familia in ("--tipo-", "--e1:", "--r-md:", "--s-1:"):
        assert familia in hoja, f"faltan tokens de {familia}"


def test_la_hoja_cubre_tableta_y_movil():
    hoja = _cliente().get(f"{RUTA_ESTATICA}/sibu.css").text
    anchos = re.findall(r"@media \(max-width: (\d+)px\)", hoja)
    assert len(anchos) >= 2, "deben existir al menos dos cortes responsive"
    assert any(int(ancho) <= 600 for ancho in anchos), "falta el corte de movil"


def test_montar_los_estaticos_no_depende_de_la_composicion_real():
    """La app de pruebas y la real montan la misma hoja."""
    app = crear_app(ComposicionFalsa())
    montajes = [ruta.path for ruta in app.routes if hasattr(ruta, "path")]
    assert RUTA_ESTATICA in montajes

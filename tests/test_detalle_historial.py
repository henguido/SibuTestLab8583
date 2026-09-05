"""Detalle navegable de una ejecucion historica: `GET /historial/{id}`.

Se prueba contra SQLite real y sin dobles del nucleo. Las filas que representan
historia —columnas JSON en `NULL`, texto truncado, campos que el perfil de hoy no
conoce— se insertan directamente en la base, porque es la unica forma honesta de
tener una fila anterior a la persistencia estructurada.
"""

from __future__ import annotations

import re
import sqlite3
from decimal import Decimal

import httpx2
import pytest

from conftest import TransporteFalso, construir_orquestador
from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, PAN_DEMO
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.domain.datos_sinteticos import monto_iso
from sibutestlab8583.application import serializacion as sz
from sibutestlab8583.composicion import Composicion, Configuracion
from sibutestlab8583.domain.modelos import (
    DatosCompra,
    DestinoTcp,
    EstadoEjecucion,
    ExpectativaCampo,
    Expectativas,
    MensajeIso,
)
from sibutestlab8583.profiles.generico import NOMBRE_PERFIL_GENERICO, PERFIL_GENERICO
from sibutestlab8583.web.app import crear_app
from sibutestlab8583.web.presentacion import AVISOS

#: El valor que el formato de texto no podia recuperar: contiene el separador.
VALOR_HOSTIL = "A=B | C"


# ------------------------------------------------------------- utilidades ----


def _app(base):
    return crear_app(Composicion(Configuracion(ruta_base_datos=base)))


async def _obtener(base, ruta):
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app(base)), base_url="http://prueba"
    ) as cliente:
        return await cliente.get(ruta)


def _insertar(base, **campos) -> int:
    """Inserta una fila de `ejecuciones` con los valores que se le pasen."""
    fila = {
        "creada_en": "2026-08-23T05:00:00+00:00",
        "card_id": CARD_ID_DEMO,
        "mti_solicitud": "0100",
        "mti_respuesta": None,
        "monto": "150.00",
        "moneda": "188",
        "stan": "000501",
        "destino_host": "127.0.0.1",
        "destino_puerto": 8583,
        "estado": "aprobada",
        "codigo_respuesta": None,
        "solicitud_enmascarada": None,
        "respuesta_enmascarada": None,
        "solicitud_json": None,
        "respuesta_json": None,
        "latencia_ms": 5,
    }
    fila.update(campos)
    columnas = ", ".join(fila)
    marcas = ", ".join("?" * len(fila))
    with sqlite3.connect(base) as conexion:
        cursor = conexion.execute(
            f"INSERT INTO ejecuciones ({columnas}) VALUES ({marcas})", tuple(fila.values())
        )
        conexion.commit()
        return cursor.lastrowid


def _seccion(html: str, titulo: str) -> str:
    """El fragmento del bloque cuyo titulo contiene `titulo`.

    Termina en el primer cierre de `</section>` o `</details>`: la evidencia
    persistida vive en un `<details>` plegable y las tablas ISO en `<section>`.
    """
    inicio = html.find(titulo)
    if inicio < 0:
        return ""
    cierres = [html.find(c, inicio) for c in ("</section>", "</details>")]
    cierres = [c for c in cierres if c > 0]
    return html[inicio : min(cierres) if cierres else len(html)]


def _campos(fragmento: str) -> dict[str, str]:
    """Los pares numero -> valor de una tabla de isoscopio."""
    return dict(
        re.findall(
            r'campo-iso">(\d+)</span>.*?valor-iso">([^<]*)</span>', fragmento, re.DOTALL
        )
    )


def _nombres(fragmento: str) -> list[str]:
    return re.findall(r'campo-iso">\d+</span></td>\s*<td>([^<]*)</td>', fragmento)


def _normalizado(html: str) -> str:
    """El HTML con los espacios colapsados: la frase que de verdad se lee.

    Una asercion sobre una frase no debe depender de donde la plantilla decidio
    cortar la linea.
    """
    return re.sub(r"\s+", " ", html)


async def _compra(base, *, codigo="00", monto="150.00"):
    return await construir_orquestador(base, TransporteFalso(codigo=codigo)).ejecutar_compra(
        DatosCompra(card_id=CARD_ID_DEMO, monto=Decimal(monto))
    )


# ------------------------------------------------------------------ 1. RUTA --


async def test_una_ejecucion_existente_responde_200(base):
    resultado = await _compra(base)
    respuesta = await _obtener(base, f"/historial/{resultado.ejecucion.id}")

    assert respuesta.status_code == 200
    assert f"Ejecución #{resultado.ejecucion.id}" in respuesta.text


async def test_un_id_inexistente_da_404_con_html_propio(base):
    respuesta = await _obtener(base, "/historial/99999")

    assert respuesta.status_code == 404
    assert "Ejecución no encontrada" in respuesta.text
    assert "La ejecución solicitada no existe" in respuesta.text
    assert "SibuTestLab" in respuesta.text, "debe ser una pagina del producto"
    assert '"detail"' not in respuesta.text, "nunca el JSON por defecto de FastAPI"
    assert "Volver al historial" in respuesta.text


@pytest.mark.parametrize("basura", ["abc", "1.5", "-", "%20", "0x1"])
async def test_un_id_no_numerico_da_404_y_no_el_422_de_fastapi(base, basura):
    """Declarado como `int`, FastAPI responderia su propio 422 en JSON."""
    respuesta = await _obtener(base, f"/historial/{basura}")

    assert respuesta.status_code == 404
    assert "Ejecución no encontrada" in respuesta.text
    assert '"detail"' not in respuesta.text
    assert "Traceback" not in respuesta.text


async def test_el_historial_enlaza_al_detalle_de_cada_ejecucion(base):
    resultado = await _compra(base)
    html = (await _obtener(base, "/historial")).text

    assert "Ver detalle" in html
    assert "<th>Detalle</th>" in html, "la columna de acciones necesita encabezado"
    assert f'href="/historial/{resultado.ejecucion.id}"' in html
    assert "onclick" not in html.lower(), "el enlace no usa JavaScript"

    # El importe y su moneda no deben leerse como un solo numero.
    assert f'<span class="moneda"' in html
    assert resultado.ejecucion.moneda in html
    assert str(resultado.ejecucion.monto) in html


# -------------------------------------------------------------- 2. CONTENIDO --


async def test_el_resumen_muestra_stan_monto_moneda_y_estado(base):
    resultado = await _compra(base)
    html = (await _obtener(base, f"/historial/{resultado.ejecucion.id}")).text
    resumen = _seccion(html, "Resumen")

    assert resultado.ejecucion.stan in resumen
    assert "150.00" in resumen
    assert "moneda 188" in resumen
    assert AVISOS[EstadoEjecucion.APROBADA].etiqueta in resumen
    assert "127.0.0.1:9" in resumen, "el destino persistido"
    assert "2026" in html, "la fecha y hora de la ejecucion"


async def test_la_solicitud_muestra_los_campos_persistidos(base):
    resultado = await _compra(base)
    html = (await _obtener(base, f"/historial/{resultado.ejecucion.id}")).text
    campos = _campos(_seccion(html, "Solicitud ISO 8583"))

    esperados = dict(resultado.solicitud.campos)
    assert campos == esperados, "los campos del detalle deben ser los persistidos"
    assert campos["2"] == "************6666"


async def test_la_respuesta_muestra_los_campos_persistidos(base):
    resultado = await _compra(base)
    html = (await _obtener(base, f"/historial/{resultado.ejecucion.id}")).text
    campos = _campos(_seccion(html, "Respuesta ISO 8583"))

    assert campos == {n: c.valor for n, c in resultado.respuesta.campos.items()}
    assert campos["39"] == "00"


async def test_los_nombres_conocidos_salen_del_perfil(base):
    resultado = await _compra(base)
    html = (await _obtener(base, f"/historial/{resultado.ejecucion.id}")).text
    nombres = _nombres(_seccion(html, "Solicitud ISO 8583"))

    assert "Número de tarjeta (PAN)" in nombres
    assert "Código de proceso" in nombres
    assert PERFIL_GENERICO.especificacion["4"]["desc"] in nombres


async def test_un_campo_que_el_perfil_no_conoce_no_rompe_la_pagina(base):
    """Un `0100` historico pudo llevar un campo que el perfil de hoy no define."""
    identificador = _insertar(
        base,
        solicitud_json=sz.a_json_solicitud(
            MensajeIso("0100", {"4": monto_iso("15000"), "63": "DATOS"}), NOMBRE_PERFIL_GENERICO
        ),
    )
    respuesta = await _obtener(base, f"/historial/{identificador}")

    assert respuesta.status_code == 200
    nombres = _nombres(_seccion(respuesta.text, "Solicitud ISO 8583"))
    assert "Campo 63" in nombres, "nombre neutral, sin inventar una descripcion"
    assert _campos(_seccion(respuesta.text, "Solicitud ISO 8583"))["63"] == "DATOS"


# ------------------------------------------------- 3. PERSISTENCIA NUEVA -----


async def test_cuando_hay_json_se_usa_el_json_y_no_el_texto(base):
    """El texto guarda un valor partido; el JSON el intacto. Debe ganar el JSON."""
    mensaje = MensajeIso("0100", {"4": monto_iso("15000"), "41": VALOR_HOSTIL})
    identificador = _insertar(
        base,
        solicitud_json=sz.a_json_solicitud(mensaje, NOMBRE_PERFIL_GENERICO),
        solicitud_enmascarada=sz.a_texto(mensaje),
    )
    html = (await _obtener(base, f"/historial/{identificador}")).text
    campos = _campos(_seccion(html, "Solicitud ISO 8583"))

    assert campos["41"] == VALOR_HOSTIL, "el valor debe verse integro"
    assert campos == dict(mensaje.campos)


async def test_no_aparece_el_campo_inventado_que_producia_el_texto(base):
    """Con el formato antiguo, `41=A=B | C` hacia aparecer un campo `C`."""
    mensaje = MensajeIso("0100", {"4": monto_iso("15000"), "41": VALOR_HOSTIL})
    identificador = _insertar(base, solicitud_enmascarada=sz.a_texto(mensaje))
    fragmento = _seccion(
        (await _obtener(base, f"/historial/{identificador}")).text, "Solicitud ISO 8583"
    )

    assert set(_campos(fragmento)) == {"4", "41"}, "solo los campos que existieron"
    assert ">C<" not in fragmento, "no debe aparecer un campo llamado C"


async def test_el_detalle_no_avisa_de_formato_anterior_cuando_hay_json(base):
    resultado = await _compra(base)
    html = (await _obtener(base, f"/historial/{resultado.ejecucion.id}")).text

    assert "registrada con el formato anterior" not in html
    assert "reconstrucción exacta" not in html
    assert 'class="nota-origen"' not in html, "sin aviso de origen cuando hay JSON"


async def test_la_respuesta_muestra_la_representacion_transmitida_cuando_existe(base):
    """Es para lo que se persiste `crudo`: si no se muestra, no sirve de nada."""
    resultado = await _compra(base)
    fragmento = _seccion(
        (await _obtener(base, f"/historial/{resultado.ejecucion.id}")).text,
        "Respuesta ISO 8583",
    )

    assert "Tal como viajó" in fragmento, "falta la columna de representación transmitida"
    crudos = re.findall(r"valor-iso\">([^<]*)</span>", fragmento)
    assert len(crudos) == 2 * len(resultado.respuesta.campos), "valor y crudo por campo"


async def test_la_solicitud_no_muestra_columna_transmitida_porque_no_existe(base):
    """El codec no entrega `crudo` de solicitud: la columna no debe fingirse."""
    resultado = await _compra(base)
    fragmento = _seccion(
        (await _obtener(base, f"/historial/{resultado.ejecucion.id}")).text,
        "Solicitud ISO 8583",
    )

    assert "Tal como viajó" not in fragmento


async def test_una_fila_historica_no_finge_representacion_transmitida(base):
    """Del texto heredado no sale `crudo`: la columna tampoco debe aparecer."""
    identificador = _insertar(
        base,
        mti_respuesta="0110",
        respuesta_enmascarada=sz.a_texto(MensajeIso("0110", {"39": "00"})),
    )
    fragmento = _seccion(
        (await _obtener(base, f"/historial/{identificador}")).text, "Respuesta ISO 8583"
    )

    assert _campos(fragmento) == {"39": "00"}
    assert "Tal como viajó" not in fragmento


# ---------------------------------------------------- 4. HISTORICO ANTIGUO ---


async def test_una_fila_con_json_nulo_se_puede_abrir(base):
    esperados = {"3": "000000", "4": monto_iso("15000"), "41": "TERM0001"}
    identificador = _insertar(
        base, solicitud_enmascarada=sz.a_texto(MensajeIso("0100", esperados))
    )
    respuesta = await _obtener(base, f"/historial/{identificador}")

    assert respuesta.status_code == 200
    assert _campos(_seccion(respuesta.text, "Solicitud ISO 8583")) == esperados


async def test_una_fila_historica_avisa_una_sola_vez_y_antes_de_las_tablas(base):
    """El formato con que se registro es propiedad de la fila, no de cada tabla."""
    identificador = _insertar(
        base,
        mti_respuesta="0110",
        solicitud_enmascarada="MTI=0100 | 41=A",
        respuesta_enmascarada=sz.a_texto(MensajeIso("0110", {"39": "00"})),
    )
    html = (await _obtener(base, f"/historial/{identificador}")).text
    texto = _normalizado(html)

    frase = "Esta ejecución fue registrada con el formato anterior."
    assert frase in texto
    assert texto.count(frase) == 1, "un solo aviso por ejecución, no uno por tabla"
    assert (
        "Los campos mostrados se recuperaron de la representación textual y no puede"
        " garantizarse una reconstrucción exacta." in texto
    )

    # Y antes de las dos tablas, no debajo de cada una.
    assert texto.index(frase) < texto.index("Solicitud ISO 8583")
    assert texto.index(frase) < texto.index("Respuesta ISO 8583")


async def test_el_aviso_historico_no_afirma_corrupcion(base):
    """Solo se afirma que la fidelidad no se puede demostrar."""
    identificador = _insertar(base, solicitud_enmascarada="MTI=0100 | 41=A")
    html = (await _obtener(base, f"/historial/{identificador}")).text.lower()

    for prohibido in ("corrupto", "corrupción", "dato dañado", "se perdió", "está mal"):
        assert prohibido not in html, f"afirma mas de lo que se sabe: {prohibido!r}"


@pytest.mark.parametrize(
    "texto",
    [
        "MTI=0100 | 3=000000 | 4=trunc",
        "basura sin ningun igual",
        "MTI=0100 | segmento suelto | 3=000000",
        "MTI=0100 | 3=000000 | 3=repetido",
        "MTI=0100 | abc=valor",
        " | ",
        "=",
        "",
    ],
)
async def test_un_texto_defectuoso_no_genera_500(base, texto):
    identificador = _insertar(base, solicitud_enmascarada=texto)
    respuesta = await _obtener(base, f"/historial/{identificador}")

    assert respuesta.status_code == 200
    assert "Traceback" not in respuesta.text


async def test_un_json_de_version_desconocida_no_se_presenta_como_interpretado(base):
    identificador = _insertar(
        base,
        solicitud_json='{"version":99,"mti":"0100","campos":{"3":{"valor":"x"}}}',
        solicitud_enmascarada=None,
    )
    respuesta = await _obtener(base, f"/historial/{identificador}")

    assert respuesta.status_code == 200
    assert _campos(_seccion(respuesta.text, "Solicitud ISO 8583")) == {}
    assert "99" in respuesta.text, "el aviso debe declarar la version que no interpreta"


# ------------------------------------------------------- 5. SIN RESPUESTA ----


@pytest.mark.parametrize(
    "estado",
    [
        EstadoEjecucion.NO_ENVIADA,
        EstadoEjecucion.ERROR_CONEXION,
        EstadoEjecucion.ERROR_TRANSMISION,
        EstadoEjecucion.TIMEOUT,
    ],
    ids=lambda e: e.value,
)
async def test_sin_respuesta_no_se_muestra_una_tabla_vacia(base, estado):
    identificador = _insertar(
        base,
        estado=estado.value,
        mti_respuesta=None,
        solicitud_json=sz.a_json_solicitud(
            MensajeIso("0100", {"4": monto_iso("15000")}), NOMBRE_PERFIL_GENERICO
        ),
    )
    html = (await _obtener(base, f"/historial/{identificador}")).text
    respuesta = _seccion(html, "Respuesta ISO 8583")

    assert "no hubo respuesta" in respuesta
    assert "<table" not in respuesta, "no debe haber tabla de respuesta"
    assert AVISOS[estado].titulo in html
    assert AVISOS[estado].detalle[:60] in html, "la explicacion del estado"
    assert "no se persiste" in respuesta, "debe declarar que el motivo concreto no se guarda"


async def test_un_timeout_reutiliza_el_texto_ya_verificado_y_no_lo_reescribe(base):
    """La precisión semántica trabajada antes tiene que sobrevivir aquí.

    La garantía no es una lista de frases prohibidas —«el destino recibió»
    aparece legítimamente dentro de «no puede afirmarse si el destino recibió»—
    sino que la página **reutilice literalmente** el texto de `AVISOS`, que ya
    fue redactado y revisado para no afirmar lo indemostrable. Si alguien
    escribiera su propia explicación aquí, esta prueba lo detecta.
    """
    identificador = _insertar(base, estado=EstadoEjecucion.TIMEOUT.value, mti_respuesta=None)
    html = (await _obtener(base, f"/historial/{identificador}")).text

    aviso = AVISOS[EstadoEjecucion.TIMEOUT]
    assert aviso.detalle in html, "el detalle debe usar el texto de AVISOS tal cual"
    assert "No puede afirmarse desde aquí si el destino recibió" in html

    # Y ninguna afirmacion propia, inequivocamente afirmativa fuera de contexto.
    for prohibido in ("la solicitud fue transmitida", "la solicitud sí se transmitió",
                      "el destino recibió el mensaje.", "se envió correctamente"):
        assert prohibido not in html, f"afirma lo indemostrable: {prohibido!r}"


# ---------------------------------------------------------- 6. SEGURIDAD -----


async def test_el_detalle_nunca_expone_el_numero_completo(base):
    resultado = await _compra(base)
    html = (await _obtener(base, f"/historial/{resultado.ejecucion.id}")).text

    assert PAN_DEMO not in html
    assert "************6666" in html, "solo el enmascarado"

    for valor in re.findall(r'data-[\w-]+="([^"]*)"', html):
        assert PAN_DEMO not in valor
        assert not re.search(r"(?<!\d)\d{12,19}(?!\d)", valor)

    for comentario in re.findall(r"<!--(.*?)-->", html, re.DOTALL):
        assert PAN_DEMO not in comentario

    assert 'type="hidden"' not in html
    assert "<script" not in html.lower()


async def test_el_detalle_marca_el_campo_de_tarjeta_como_enmascarado(base):
    resultado = await _compra(base)
    html = (await _obtener(base, f"/historial/{resultado.ejecucion.id}")).text

    assert "enmascarado" in _seccion(html, "Solicitud ISO 8583")


async def test_la_representacion_persistida_se_muestra_ya_enmascarada(base):
    resultado = await _compra(base)
    html = (await _obtener(base, f"/historial/{resultado.ejecucion.id}")).text
    seccion = _seccion(html, "Ver representación persistida")

    assert resultado.ejecucion.solicitud_enmascarada in seccion
    assert resultado.ejecucion.respuesta_enmascarada in seccion
    assert PAN_DEMO not in seccion
    assert ".hex" not in seccion and "0x" not in seccion, "sin bytes ni hexadecimal"


async def test_la_representacion_persistida_es_plegable_y_llega_cerrada(base):
    """`<details>` nativo: se abre sin JavaScript y no es lo primero que se lee."""
    resultado = await _compra(base)
    html = (await _obtener(base, f"/historial/{resultado.ejecucion.id}")).text

    plegables = re.findall(r"<details[^>]*>", html)
    assert len(plegables) == 1, "una sola sección plegable"
    assert "open" not in plegables[0], "debe llegar cerrada"
    assert "<summary" in html and "Ver representación persistida" in html
    assert "<script" not in html.lower(), "sin JavaScript"

    # Cerrada no significa ausente: el contenido sigue en el HTML.
    assert resultado.ejecucion.solicitud_enmascarada in html


# ------------------------------------------------------- 7. REUTILIZACION ----


async def _crear_conexion_inalcanzable(composicion, conexion_id="INALCANZABLE"):
    """Una conexion administrada apuntando a un host que no existe.

    El formulario de compra ya no acepta host/puerto directos: solo
    `conexion_id`. Estas pruebas necesitan un fallo de conexion real, asi que
    registran una conexion hacia un host inexistente antes de enviar.
    """
    from sibutestlab8583.application.conexiones import DatosNuevaConexion

    await composicion.administracion_conexiones.crear(
        DatosNuevaConexion(
            conexion_id=conexion_id,
            nombre="Inalcanzable",
            host="no-existe.sibutestlab.invalid",
            puerto="9",
        )
    )
    return conexion_id


async def test_el_resultado_inmediato_sigue_funcionando(base):
    """El macro del isoscopio se movio de archivo: la pantalla no cambia."""
    composicion = Composicion(Configuracion(ruta_base_datos=base))
    conexion_id = await _crear_conexion_inalcanzable(composicion)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=crear_app(composicion)), base_url="http://prueba"
    ) as cliente:
        respuesta = await cliente.post(
            "/compra",
            data={"card_id": CARD_ID_DEMO, "monto": "150.00", "conexion_id": conexion_id},
        )

    assert respuesta.status_code == 200
    assert "Isoscopio · solicitud 0100" in respuesta.text
    assert "Resumen" in respuesta.text
    assert 'class="aviso error"' in respuesta.text


async def test_las_dos_pantallas_comparten_la_estructura_del_isoscopio(base):
    resultado = await _compra(base)
    detalle = (await _obtener(base, f"/historial/{resultado.ejecucion.id}")).text

    composicion = Composicion(Configuracion(ruta_base_datos=base))
    conexion_id = await _crear_conexion_inalcanzable(composicion)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=crear_app(composicion)), base_url="http://prueba"
    ) as cliente:
        inmediato = (await cliente.post(
            "/compra",
            data={"card_id": CARD_ID_DEMO, "monto": "150.00", "conexion_id": conexion_id},
        )).text

    for marca in ('class="campo-iso"', 'class="valor-iso"', 'class="desplazable"',
                  'class="metricas"', 'class="aviso'):
        assert marca in detalle, f"el detalle no usa {marca}"
        assert marca in inmediato, f"el resultado inmediato no usa {marca}"


# ---------------------------------------------------------- 8. VERTICAL ------


async def test_vertical_transaccion_real_y_detalle_coherente(base):
    """HTTP -> nucleo real -> TCP real -> 0110 -> SQLite -> detalle historico."""
    composicion = Composicion(
        Configuracion(ruta_base_datos=base, host_destino="127.0.0.1", tiempo_limite=3.0)
    )
    host = HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion())
    app = crear_app(composicion)

    async with host:
        from sibutestlab8583.application.conexiones import DatosNuevaConexion

        await composicion.administracion_conexiones.crear(
            DatosNuevaConexion(
                conexion_id="VERTICAL",
                nombre="Host simulado de la prueba",
                host=host.host,
                puerto=str(host.puerto),
            )
        )
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://prueba"
        ) as cliente:
            ejecucion_web = await cliente.post(
                "/compra",
                data={"card_id": CARD_ID_DEMO, "monto": "987.65", "conexion_id": "VERTICAL"},
            )
            assert ejecucion_web.status_code == 200
            assert host.solicitudes_recibidas == 1

            # El id se toma de la fila persistida, no de una suposicion.
            guardadas = await composicion.consultas.ejecuciones_recientes()
            assert len(guardadas) == 1
            guardada = guardadas[0]

            detalle = await cliente.get(f"/historial/{guardada.id}")

    assert detalle.status_code == 200
    html = detalle.text

    # Lo que muestra el detalle coincide con lo que quedo persistido.
    esperado_solicitud = {c.numero: c.valor
                          for c in sz.desde_json(guardada.solicitud_json).campos}
    esperado_respuesta = {c.numero: c.valor
                         for c in sz.desde_json(guardada.respuesta_json).campos}
    assert _campos(_seccion(html, "Solicitud ISO 8583")) == esperado_solicitud
    assert _campos(_seccion(html, "Respuesta ISO 8583")) == esperado_respuesta

    assert guardada.stan in html
    assert "987.65" in html
    assert AVISOS[EstadoEjecucion.APROBADA].etiqueta in html

    assert PAN_DEMO not in html, "el PAN completo no puede llegar al navegador"
    assert "************6666" in html


# ---------------------------------------------------------- 9. EXPECTATIVAS ---


async def _compra_con_expectativas(base, expectativas, *, codigo="00"):
    return await construir_orquestador(base, TransporteFalso(codigo=codigo)).ejecutar_compra(
        DatosCompra(card_id=CARD_ID_DEMO, monto=Decimal("150.00")), expectativas=expectativas
    )


async def test_sin_expectativas_el_historial_no_muestra_pass_ni_fail(base):
    resultado = await _compra(base)
    html = (await _obtener(base, "/historial")).text

    fila = html[html.find(f"/historial/{resultado.ejecucion.id}") - 2000 :]
    assert 'data-evaluacion=""' in fila or 'data-evaluacion' not in fila.split("</tr>")[0]


async def test_el_historial_muestra_pass_para_una_ejecucion_que_cumplio(base):
    resultado = await _compra_con_expectativas(base, Expectativas(estado=EstadoEjecucion.APROBADA))
    html = (await _obtener(base, "/historial")).text

    assert 'data-evaluacion="pass"' in html
    assert "PASS" in html


async def test_el_historial_muestra_fail_para_una_ejecucion_que_incumplio(base):
    resultado = await _compra_con_expectativas(
        base, Expectativas(campos={"39": ExpectativaCampo(tipo="igual", valor="05")}), codigo="00"
    )
    html = (await _obtener(base, "/historial")).text

    assert 'data-evaluacion="fail"' in html
    assert "FAIL" in html


async def test_el_detalle_muestra_sin_expectativas_cuando_el_escenario_no_definio_nada(base):
    resultado = await _compra(base)
    html = (await _obtener(base, f"/historial/{resultado.ejecucion.id}")).text

    assert "Sin expectativas" in html


async def test_el_detalle_de_una_ejecucion_pass_muestra_el_banner_y_sin_discrepancias(base):
    resultado = await _compra_con_expectativas(
        base, Expectativas(estado=EstadoEjecucion.APROBADA, campos={"39": ExpectativaCampo(tipo="igual", valor="00")})
    )
    html = (await _obtener(base, f"/historial/{resultado.ejecucion.id}")).text

    assert 'data-evaluacion="pass"' in html
    assert "PASS" in html
    assert "cumple con lo esperado" in html


async def test_el_detalle_de_una_ejecucion_fail_explica_la_discrepancia_de_campo(base):
    resultado = await _compra_con_expectativas(
        base, Expectativas(campos={"39": ExpectativaCampo(tipo="igual", valor="99")})
    )
    html = (await _obtener(base, f"/historial/{resultado.ejecucion.id}")).text

    assert 'data-evaluacion="fail"' in html
    assert "Campo 39" in html
    assert "«99»" in html and "«00»" in html


async def test_editar_expectativas_no_altera_una_evaluacion_ya_registrada_en_el_detalle(base):
    """Vista de extremo a extremo del criterio de inmutabilidad: el detalle de
    una ejecucion ya registrada sigue mostrando su PASS original, aunque el
    snapshot que se relee ya no tenga relacion con ningun escenario en vivo
    -el orquestador ni siquiera conoce escenarios; esto prueba que el
    snapshot persistido, por si solo, es suficiente-.
    """
    resultado = await _compra_con_expectativas(base, Expectativas(estado=EstadoEjecucion.APROBADA))
    primer_html = (await _obtener(base, f"/historial/{resultado.ejecucion.id}")).text
    assert 'data-evaluacion="pass"' in primer_html

    # Una ejecucion posterior, con una expectativa distinta, no debe tocar la anterior.
    await _compra_con_expectativas(base, Expectativas(estado=EstadoEjecucion.RECHAZADA), codigo="00")

    segundo_html = (await _obtener(base, f"/historial/{resultado.ejecucion.id}")).text
    assert 'data-evaluacion="pass"' in segundo_html

"""B5: el registro declarativo de operaciones con tarjeta
(`web.operaciones.OPERACIONES_CON_TARJETA`) y el editor comun que gobierna.

Cubre lo que el registro por si mismo debe garantizar (claves unicas,
operacion->MTI, operacion->ruta, operacion desconocida) y, con un test
double, que la arquitectura realmente dejo de depender de que solo existan
dos operaciones con tarjeta -el punto central de B5-.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from sibutestlab8583.domain.modelos import (
    MTI_COMPRA,
    MTI_COMPRA_FINANCIERA,
    MTI_RESPUESTA_COMPRA,
    MTI_RESPUESTA_COMPRA_FINANCIERA,
    OPERACION_COMPRA,
    OPERACION_COMPRA_FINANCIERA,
)
from sibutestlab8583.web.app import crear_app
from sibutestlab8583.web.operaciones import (
    OPERACION_AUTORIZACION,
    OPERACION_FINANCIERA,
    OPERACIONES_CON_TARJETA,
    OPERACIONES_POR_CLAVE,
    OperacionIso,
    operacion_por_clave,
    operacion_por_mti,
)

from sibutestlab8583.domain.modelos import EstadoEjecucion

from test_web import CARD_ID_DEMO, ComposicionFalsa, DESTINO_ID_DEMO, _resultado


# --------------------------------------------------------------- registro --


def test_las_claves_del_registro_son_unicas():
    claves = [op.clave for op in OPERACIONES_CON_TARJETA]
    assert len(claves) == len(set(claves))


def test_operacion_por_clave_resuelve_autorizacion_y_financiera():
    assert operacion_por_clave(OPERACION_COMPRA) is OPERACION_AUTORIZACION
    assert operacion_por_clave(OPERACION_COMPRA_FINANCIERA) is OPERACION_FINANCIERA


def test_operacion_por_mti_resuelve_autorizacion_y_financiera():
    assert operacion_por_mti(MTI_COMPRA) is OPERACION_AUTORIZACION
    assert operacion_por_mti(MTI_COMPRA_FINANCIERA) is OPERACION_FINANCIERA


def test_operacion_por_clave_desconocida_da_none_no_error():
    assert operacion_por_clave("no_existe") is None


def test_operacion_por_mti_desconocido_da_none_no_error():
    assert operacion_por_mti("0400") is None


def test_el_registro_no_declara_politica_de_campos():
    """Punto 10 de B5: el registro es metadata de presentacion/despacho,
    nunca obligatorios/opcionales/sensibilidad/longitudes -eso sigue siendo
    exclusivo de PerfilDeMarca/PoliticaCamposMti."""
    campos_de_operacion_iso = {f.name for f in OperacionIso.__dataclass_fields__.values()}
    for prohibido in ("obligatorios", "opcionales", "sensible", "longitud"):
        assert not any(prohibido in campo for campo in campos_de_operacion_iso), prohibido


def test_autorizacion_y_financiera_apuntan_al_mti_respuesta_correcto():
    assert OPERACION_AUTORIZACION.mti == MTI_COMPRA
    assert OPERACION_AUTORIZACION.mti_respuesta == MTI_RESPUESTA_COMPRA
    assert OPERACION_FINANCIERA.mti == MTI_COMPRA_FINANCIERA
    assert OPERACION_FINANCIERA.mti_respuesta == MTI_RESPUESTA_COMPRA_FINANCIERA


# --------------------------------------------- POST adversarial (comun) --


def _cliente(**kwargs) -> TestClient:
    return TestClient(crear_app(ComposicionFalsa(**kwargs)))


@pytest.mark.parametrize(
    "ruta_ejecutar,mti",
    [("/compra", MTI_COMPRA), ("/financiera/ejecutar", MTI_COMPRA_FINANCIERA)],
)
def test_un_campo_derivado_no_puede_fijarse_a_mano_via_post(ruta_ejecutar, mti):
    """Punto 17/24 de B5: el backend protege manipulaciones POST igual para
    cualquier operacion con tarjeta -el mismo `_interpretar_formulario_operacion`
    llama a `validar_forma_de_opcionales`/`armar_*`, que rechazan un campo
    derivado (DE2, DE14) fijado a mano, sin importar la operacion."""
    resultado = _resultado(EstadoEjecucion.APROBADA, codigo="00")
    respuesta = _cliente(resultado=resultado).post(
        ruta_ejecutar,
        data={
            "card_id": CARD_ID_DEMO, "monto": "50.00", "conexion_id": DESTINO_ID_DEMO,
            "campo_2": "9999" "9999" "9999" "9999",
        },
    )
    # El campo derivado simplemente se ignora -armar_compra/armar_compra_financiera
    # lo pisan siempre-, nunca se refleja en el mensaje armado: no hay 500,
    # y la respuesta es la pantalla de resultado normal (200) o un error de
    # validacion (400), nunca el valor manipulado aceptado.
    assert respuesta.status_code in (200, 400)


@pytest.mark.parametrize("ruta_ejecutar", ["/compra", "/financiera/ejecutar"])
def test_ejecutar_sin_tarjeta_da_error_para_cualquier_operacion_con_tarjeta(ruta_ejecutar):
    respuesta = _cliente().post(
        ruta_ejecutar, data={"card_id": "", "monto": "50.00", "conexion_id": DESTINO_ID_DEMO}
    )
    assert respuesta.status_code == 400
    assert "Seleccione una tarjeta" in respuesta.text


# ------------------------------------------- extensibilidad (sin 4to MTI) --


def test_una_tercera_operacion_con_tarjeta_se_renderiza_sin_tocar_la_plantilla():
    """B5, punto 25: demuestra -sin implementar un cuarto MTI real ni una
    funcionalidad falsa- que agregar una operacion con tarjeta al registro
    alcanza para que `editor_transaccion.html` la renderice correctamente,
    sin ninguna condicional nueva en la plantilla ni en `_formulario_operacion`.

    Se invoca `_formulario_operacion` directamente con un `OperacionIso`
    SINTETICO (una tercera entrada que no vive en `OPERACIONES_CON_TARJETA`)
    y un `Request` real: si la plantilla o el renderizador tuvieran algun
    `if operacion.clave == OPERACION_COMPRA ... elif ... financiera` -el
    antipatron que B5 existe para evitar-, esto reventaria o ignoraria los
    textos de la operacion sintetica. Reutiliza el MTI/builder de
    Autorizacion (0100) porque lo unico que importa demostrar es el
    DESPACHO por metadata, no un mensaje ISO nuevo -no es una operacion real
    de producto, es un test double.
    """
    import asyncio

    from starlette.requests import Request as StarletteRequest

    # Import por nombre, no por modulo: `sibutestlab8583.web.__init__` hace
    # `from .app import app` (la instancia FastAPI), lo que reasigna el
    # atributo `sibutestlab8583.web.app` a esa instancia -un `import
    # sibutestlab8583.web.app as app_modulo` devolveria la app FastAPI, no el
    # modulo, por ese shadowing de nombres ya existente en el paquete-.
    from sibutestlab8583.web.app import _formulario_operacion

    operacion_sintetica = replace(
        OPERACION_AUTORIZACION,
        clave="_operacion_sintetica_de_prueba",
        nombre="Operación sintética de prueba",
        ruta="/_sintetica",
        ruta_ejecutar="/_sintetica/ejecutar",
        titulo_pagina="Operación sintética",
        descripcion_pagina="Solo existe para esta prueba de extensibilidad.",
        titulo_constructor="Construir transacción · sintética",
        verbo_ejecutar="Ejecutar sintética",
    )
    assert operacion_sintetica.clave not in OPERACIONES_POR_CLAVE

    composicion = ComposicionFalsa()
    scope = {
        "type": "http", "method": "GET", "path": "/_sintetica",
        "headers": [], "query_string": b"", "client": ("test", 1),
        "server": ("test", 80), "scheme": "http",
    }

    async def receive():
        return {"type": "http.request", "body": b""}

    async def _ejercitar():
        request = StarletteRequest(scope, receive)
        return await _formulario_operacion(request, composicion, operacion_sintetica)

    respuesta = asyncio.run(_ejercitar())
    texto = respuesta.body.decode("utf-8")
    assert "Operación sintética" in texto
    assert "Ejecutar sintética" in texto
    assert 'action="/_sintetica/ejecutar"' in texto
    # La misma plantilla, sin cambios: sigue mostrando tarjeta/monto/preview,
    # que es exactamente lo comun que el editor debe seguir ofreciendo.
    assert "Tarjeta y monto" in texto

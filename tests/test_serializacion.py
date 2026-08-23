"""Representacion persistida: escritura estructurada y lectura tolerante.

Estas pruebas son puras: sin base de datos, sin red, sin reloj. Cubren el
defecto que motivo la iteracion —el formato de texto parte un valor que contenga
el separador— y el contrato de la lectura segura: nunca lanzar y nunca inventar.
"""

from __future__ import annotations

import json

import pytest

from sibutestlab8583.application import serializacion as sz
from sibutestlab8583.domain.datos_sinteticos import monto_iso, pan_sintetico
from sibutestlab8583.domain.modelos import (
    MTI_COMPRA,
    MTI_RESPUESTA_COMPRA,
    CampoInterpretado,
    MensajeInterpretado,
    MensajeIso,
)

PERFIL = "generico"
PAN_ENMASCARADO = "************6666"

#: El valor que rompe el formato heredado: contiene el separador y un igual.
#: El campo 41 son ocho caracteres ASCII libres, asi que cabe de verdad.
VALOR_HOSTIL = "A=B | C"


def _solicitud(**extra) -> MensajeIso:
    campos = {"2": PAN_ENMASCARADO, "3": "000000", "4": monto_iso("15000"), "49": "188"}
    campos.update(extra)
    return MensajeIso(MTI_COMPRA, campos)


def _respuesta_interpretada() -> MensajeInterpretado:
    return MensajeInterpretado(
        MTI_RESPUESTA_COMPRA,
        {
            "39": CampoInterpretado("39", "00", "00", "Código de respuesta"),
            "41": CampoInterpretado("41", "TERM0001", "TERM0001", "Identificador del terminal"),
        },
    )


# ------------------------------------------------------ escritura del JSON ----


def test_el_json_declara_version_mti_y_perfil():
    datos = json.loads(sz.a_json_solicitud(_solicitud(), PERFIL))

    assert datos["version"] == sz.VERSION_FORMATO
    assert datos["mti"] == MTI_COMPRA
    assert datos["perfil"] == PERFIL
    assert set(datos["campos"]) == {"2", "3", "4", "49"}


def test_la_solicitud_no_lleva_crudo_porque_no_existe():
    """El codec descarta el documento codificado: no se inventa el dato."""
    datos = json.loads(sz.a_json_solicitud(_solicitud(), PERFIL))
    for entrada in datos["campos"].values():
        assert set(entrada) == {"valor"}


def test_la_respuesta_conserva_crudo_cuando_el_codec_lo_trajo():
    datos = json.loads(sz.a_json_respuesta(_respuesta_interpretada(), PERFIL))

    assert datos["campos"]["39"] == {"valor": "00", "crudo": "00"}
    assert datos["campos"]["41"]["crudo"] == "TERM0001"


def test_un_crudo_vacio_no_se_escribe_como_cadena_vacia():
    """Ausente y vacio no son lo mismo: no se guarda una clave sin contenido."""
    mensaje = MensajeInterpretado(
        MTI_RESPUESTA_COMPRA, {"39": CampoInterpretado("39", "00", "", "Código de respuesta")}
    )
    datos = json.loads(sz.a_json_respuesta(mensaje, PERFIL))
    assert set(datos["campos"]["39"]) == {"valor"}


# --------------------------------------- el defecto que motivo la iteracion ---


def test_el_formato_heredado_parte_un_valor_con_el_separador():
    """Se documenta el defecto, no se corrige: el dato ya se escribio partido."""
    texto = sz.a_texto(_solicitud(**{"41": VALOR_HOSTIL}))
    leido = sz.desde_texto_heredado(texto)

    assert leido.valor("41") == "A=B", "el valor quedo truncado"
    assert not leido.fiel, "no puede declararse fiel"


def test_el_json_recupera_fielmente_un_valor_con_separador_e_igual():
    """Lo mismo, en JSON: la frontera la declara el formato, no la forma."""
    original = _solicitud(**{"41": VALOR_HOSTIL})
    leido = sz.desde_json(sz.a_json_solicitud(original, PERFIL))

    assert leido.fiel
    assert leido.valor("41") == VALOR_HOSTIL
    assert {c.numero: c.valor for c in leido.campos} == dict(original.campos)


@pytest.mark.parametrize(
    "hostil",
    [VALOR_HOSTIL, "X | Y", "A=B", " | ", '{"a":1}', "acentós", "  ", "|", "="],
)
def test_el_json_soporta_cualquier_contenido_de_campo(hostil):
    original = MensajeIso(MTI_COMPRA, {"41": hostil, "49": "188"})
    leido = sz.desde_json(sz.a_json_solicitud(original, PERFIL))

    assert leido.fiel
    assert leido.valor("41") == hostil


# ------------------------------------------------------ ida y vuelta fiel -----


def test_ida_y_vuelta_de_la_solicitud_sin_perdida():
    original = _solicitud(**{"7": "0823053958", "11": "000001", "41": "TERM0001"})
    leido = sz.desde_json(sz.a_json_solicitud(original, PERFIL))

    assert leido.mti == original.mti
    assert leido.perfil == PERFIL
    assert {c.numero: c.valor for c in leido.campos} == dict(original.campos)
    assert [c.numero for c in leido.campos] == sorted(original.campos, key=int)


def test_ida_y_vuelta_de_la_respuesta_conserva_valor_y_crudo():
    original = _respuesta_interpretada()
    leido = sz.desde_json(sz.a_json_respuesta(original, PERFIL))

    assert leido.fiel
    assert leido.mti == original.mti
    for numero, campo in original.campos.items():
        recuperado = next(c for c in leido.campos if c.numero == numero)
        assert recuperado.valor == campo.valor
        assert recuperado.crudo == campo.crudo


# ------------------------------------------------------- lectura tolerante ----


@pytest.mark.parametrize("vacia", [None, ""])
def test_una_representacion_ausente_queda_indisponible(vacia):
    """Ausente es un estado propio: no hay nada que leer y se dice."""
    for leer in (sz.desde_json, sz.desde_texto_heredado):
        resultado = leer(vacia)
        assert resultado.origen == sz.ORIGEN_AUSENTE
        assert not resultado.disponible
        assert not resultado.fiel
        assert resultado.campos == ()
        assert resultado.mti == ""


def test_una_cadena_de_espacios_es_ilegible_pero_no_ausente():
    """Distinto de `None`: hubo algo escrito y no se pudo interpretar."""
    del_json = sz.desde_json("   ")
    assert del_json.origen == sz.ORIGEN_JSON and not del_json.fiel and del_json.avisos

    del_texto = sz.desde_texto_heredado("   ")
    assert del_texto.origen == sz.ORIGEN_TEXTO
    assert del_texto.campos == ()
    assert not del_texto.fiel


@pytest.mark.parametrize(
    "basura",
    [
        "{no es json",
        "[]",
        '"solo una cadena"',
        "null",
        '{"version":1}',
        '{"version":1,"campos":"no es un objeto"}',
        '{"version":1,"campos":{"x":{"valor":"1"}}}',
        '{"version":1,"campos":{"3":"sin valor"}}',
        '{"version":99,"mti":"0100","campos":{}}',
    ],
)
def test_un_json_invalido_no_lanza_y_se_señala(basura):
    resultado = sz.desde_json(basura)
    assert isinstance(resultado, sz.MensajeSerializado)
    assert resultado.avisos, "todo problema debe quedar declarado"


def test_un_json_de_version_desconocida_no_se_interpreta():
    """Leer una estructura que no se conoce seria inventar significado."""
    resultado = sz.desde_json('{"version":99,"mti":"0100","campos":{"3":{"valor":"x"}}}')

    assert not resultado.fiel
    assert resultado.campos == ()
    assert any("99" in aviso for aviso in resultado.avisos)


@pytest.mark.parametrize(
    "basura",
    [
        "MTI=0100 | 3=000000",
        "MTI=0100",
        "sin ningun igual",
        "MTI=0100 | segmento suelto | 3=000000",
        "MTI=0100 | 3=000000 | 3=repetido",
        "MTI=0100 | abc=valor",
        " | ",
        "=",
        "MTI=0100 | 3=000000 | 4=trunc",
    ],
)
def test_el_texto_heredado_nunca_lanza(basura):
    resultado = sz.desde_texto_heredado(basura)
    assert isinstance(resultado, sz.MensajeSerializado)
    assert not resultado.fiel, "el formato heredado nunca puede declararse fiel"


def test_un_texto_heredado_correcto_igual_no_se_declara_fiel():
    """`41=A` es indistinguible de un `41=A | B` truncado. No se puede demostrar."""
    resultado = sz.desde_texto_heredado("MTI=0100 | 3=000000 | 41=A")

    assert resultado.disponible
    assert resultado.valor("41") == "A"
    assert not resultado.fiel
    assert sz.AVISO_HEREDADO in resultado.avisos


def test_los_segmentos_no_interpretables_se_declaran_y_no_se_inventan():
    resultado = sz.desde_texto_heredado("MTI=0100 | basura | 3=000000 | abc=1")

    assert [c.numero for c in resultado.campos] == ["3"], "solo lo interpretable"
    assert any("basura" in a for a in resultado.avisos)
    assert any("abc" in a for a in resultado.avisos)


# ---------------------------------------------------------- prioridad --------


def test_interpretar_prefiere_el_json_cuando_existe():
    texto = sz.a_texto(_solicitud())
    estructurado = sz.a_json_solicitud(_solicitud(**{"41": VALOR_HOSTIL}), PERFIL)

    resultado = sz.interpretar(estructurado, texto)

    assert resultado.origen == sz.ORIGEN_JSON
    assert resultado.fiel
    assert resultado.valor("41") == VALOR_HOSTIL


def test_interpretar_cae_al_texto_cuando_no_hay_json():
    """Filas historicas: solo tienen la representacion anterior."""
    resultado = sz.interpretar(None, sz.a_texto(_solicitud()))

    assert resultado.origen == sz.ORIGEN_TEXTO
    assert not resultado.fiel
    assert resultado.valor("3") == "000000"


def test_interpretar_arrastra_el_aviso_de_un_json_roto():
    resultado = sz.interpretar("{roto", sz.a_texto(_solicitud()))

    assert resultado.origen == sz.ORIGEN_TEXTO
    assert any("JSON" in a or "json" in a for a in resultado.avisos)


def test_interpretar_sin_nada_queda_indisponible():
    resultado = sz.interpretar(None, None)

    assert not resultado.disponible
    assert resultado.campos == ()
    assert not resultado.fiel


# ------------------------------------------------------------- seguridad -----


def test_escribir_un_pan_completo_es_un_error_de_programacion():
    """Ultima barrera: ninguna de las dos representaciones lo deja pasar."""
    pan = pan_sintetico("6666")
    en_claro = MensajeIso(MTI_COMPRA, {"2": pan, "49": "188"})

    for escribir in (sz.a_texto, lambda m: sz.a_json_solicitud(m, PERFIL)):
        with pytest.raises(sz.ErrorDeEnmascarado):
            escribir(en_claro)


def test_un_crudo_con_pan_completo_tampoco_pasa():
    pan = pan_sintetico("6666")
    mensaje = MensajeInterpretado(
        MTI_RESPUESTA_COMPRA, {"2": CampoInterpretado("2", PAN_ENMASCARADO, pan, "PAN")}
    )
    with pytest.raises(sz.ErrorDeEnmascarado):
        sz.a_json_respuesta(mensaje, PERFIL)


def test_ninguna_representacion_del_mensaje_enmascarado_contiene_el_pan():
    pan = pan_sintetico("6666")
    enmascarado = MensajeIso(MTI_COMPRA, {"2": pan, "49": "188"}).enmascarado()

    for texto in (sz.a_texto(enmascarado), sz.a_json_solicitud(enmascarado, PERFIL)):
        assert pan not in texto
        assert "6666" in texto, "los ultimos cuatro digitos si se muestran"

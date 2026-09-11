"""El perfil generico carga y su especificacion sirve de verdad para un 0100/0110.

Comprobar solo que el objeto existe no probaria nada: una especificacion mal
formada tambien se carga. Por eso se verifica contra pyiso8583 que un mensaje
puede codificarse y volver a leerse.
"""

from __future__ import annotations

import iso8583
import pytest

from sibutestlab8583.domain.datos_sinteticos import monto_iso, pan_sintetico
from sibutestlab8583.domain.modelos import MTI_COMPRA, MTI_RESPUESTA_COMPRA
from sibutestlab8583.profiles.generico import (
    CODIGO_PROCESO_COMPRA,
    METADATOS_CAMPOS_0100,
    PERFIL_GENERICO,
    perfil_activo,
)


def test_el_perfil_activo_es_el_generico():
    perfil = perfil_activo()
    assert perfil is PERFIL_GENERICO
    assert perfil.nombre == "generico"


def test_solo_soporta_los_mti_del_alcance_aprobado():
    perfil = perfil_activo()
    assert perfil.soporta(MTI_COMPRA)
    assert perfil.soporta(MTI_RESPUESTA_COMPRA)
    # Fuera de alcance: reverso, retiro, consulta de saldo.
    for mti in ("0200", "0400", "0800"):
        assert not perfil.soporta(mti)
        with pytest.raises(ValueError):
            perfil.obligatorios(mti)


def test_obligatorios_de_la_compra_identifican_la_transaccion():
    obligatorios = perfil_activo().obligatorios(MTI_COMPRA)
    # Que tarjeta, que operacion, cuanto, en que moneda y con que trazabilidad.
    for campo in ("2", "3", "4", "11", "49"):
        assert campo in obligatorios


def test_la_respuesta_exige_el_codigo_de_respuesta():
    obligatorios = perfil_activo().obligatorios(MTI_RESPUESTA_COMPRA)
    assert "39" in obligatorios, "sin campo 39 no se puede aplicar RN-1"


def test_la_especificacion_codifica_y_decodifica_un_0100():
    perfil = perfil_activo()
    solicitud = {
        "t": MTI_COMPRA,
        "2": pan_sintetico("6666"),
        "3": CODIGO_PROCESO_COMPRA,
        "4": monto_iso("15000"),
        "7": "0818120000",
        "11": "000001",
        "14": "3012",
        "22": "051",
        "41": "TERM0001",
        "49": "188",
    }
    crudo, _ = iso8583.encode(dict(solicitud), perfil.especificacion)
    decodificado, _ = iso8583.decode(crudo, perfil.especificacion)

    assert decodificado["t"] == MTI_COMPRA
    for numero, valor in solicitud.items():
        assert decodificado[numero] == valor


def test_la_especificacion_decodifica_un_0110_con_codigo_de_respuesta():
    perfil = perfil_activo()
    respuesta = {
        "t": MTI_RESPUESTA_COMPRA,
        "3": CODIGO_PROCESO_COMPRA,
        "4": monto_iso("15000"),
        "7": "0818120000",
        "11": "000001",
        "39": "00",
        "41": "TERM0001",
    }
    crudo, _ = iso8583.encode(dict(respuesta), perfil.especificacion)
    decodificado, _ = iso8583.decode(crudo, perfil.especificacion)

    assert decodificado["t"] == MTI_RESPUESTA_COMPRA
    assert decodificado["39"] == "00"


def test_la_especificacion_codifica_y_decodifica_los_opcionales_del_bloque_1():
    """Round-trip real contra pyiso8583 -no solo declarados en la
    especificacion- para los cinco opcionales agregados en esta iteracion.
    """
    perfil = perfil_activo()
    solicitud = {
        "t": MTI_COMPRA,
        "2": pan_sintetico("6666"),
        "3": CODIGO_PROCESO_COMPRA,
        "4": monto_iso("15000"),
        "7": "0818120000",
        "11": "000001",
        "14": "3012",
        "18": "5411",
        "22": "051",
        "25": "00",
        "32": "12345678901",
        "41": "TERM0001",
        "42": "MERCH0000000001",
        "43": "ACME STORE" + " " * 30,
        "49": "188",
    }
    crudo, _ = iso8583.encode(dict(solicitud), perfil.especificacion)
    decodificado, _ = iso8583.decode(crudo, perfil.especificacion)
    for numero in ("18", "25", "32", "42", "43"):
        assert decodificado[numero] == solicitud[numero]


def test_los_opcionales_del_bloque_1_no_son_obligatorios_ni_automaticos():
    politica = PERFIL_GENERICO.politica(MTI_COMPRA)
    for numero in ("18", "25", "32", "42", "43"):
        assert politica.origen(numero) == "opcional"
        assert numero not in PERFIL_GENERICO.obligatorios(MTI_COMPRA)


def test_el_perfil_no_se_atribuye_a_ninguna_marca():
    """No hay perfiles de marca hasta tener documentos autorizados."""
    texto = repr(PERFIL_GENERICO.nombre).lower()
    for marca in ("visa", "mastercard", "amex", "american"):
        assert marca not in texto


def test_la_politica_de_campos_solo_referencia_campos_de_la_especificacion():
    """Un numero gobernado por la politica que la especificacion no conoce
    codificaria un campo que pyiso8583 no sabe empacar: seria un error de
    configuracion silencioso hasta el primer intento de armar un mensaje.
    """
    politica = PERFIL_GENERICO.politica(MTI_COMPRA)
    numeros_gobernados = politica.derivados | politica.automaticos | politica.editables
    numeros_de_la_especificacion = set(PERFIL_GENERICO.especificacion) - {"h", "t", "p"}
    assert numeros_gobernados <= numeros_de_la_especificacion


def test_la_politica_de_campos_cubre_todos_los_obligatorios_de_la_compra():
    """Todo campo obligatorio que la politica no gobierna debe, al menos, ser
    uno de los que `armar_compra` fija siempre por fuera de ella. DE4 es el
    unico caso: viene de `DatosCompra.monto` directamente, no de la tarjeta ni
    del reloj/STAN, asi que `PoliticaCamposMti` no lo clasifica -pero sigue
    estando siempre presente en el mensaje armado-.
    """
    politica = PERFIL_GENERICO.politica(MTI_COMPRA)
    numeros_gobernados = politica.derivados | politica.automaticos | politica.editables | {"4"}
    assert PERFIL_GENERICO.obligatorios(MTI_COMPRA) <= numeros_gobernados


# --------------------------------- consistencia especificacion <-> metadata --
#
# `ESPECIFICACION_GENERICA` (lo que consume pyiso8583: max_len/len_type) y
# `METADATOS_CAMPOS_0100` (lo que consume la UI/validacion: longitud_maxima/
# longitud_fija/descripcion) son dos diccionarios escritos a mano por
# separado -son autoritativos para preguntas distintas: uno "como se
# codifica", el otro "como se valida/describe en pantalla"-, sin ninguna
# relacion automatica entre ambos. Nada impide hoy que alguien cambie el
# largo de un campo en uno y se olvide del otro: `validar_forma_de_opcionales`
# rechazaria (o aceptaria) un valor con un criterio que ya no coincide con lo
# que el codec realmente exige. Esta prueba es la red de seguridad: si algun
# dia se desincronizan, falla aqui -con un mensaje que dice exactamente que
# campo y que atributo-, no en produccion como un mensaje de error confuso.


def test_metadatos_0100_coincide_con_la_especificacion_en_longitud_y_descripcion():
    for numero, metadato in METADATOS_CAMPOS_0100.items():
        definicion = PERFIL_GENERICO.especificacion[numero]
        assert metadato.longitud_maxima == definicion["max_len"], (
            f"DE{numero}: METADATOS_CAMPOS_0100 dice longitud {metadato.longitud_maxima} "
            f"pero ESPECIFICACION_GENERICA dice {definicion['max_len']}"
        )
        # len_type 0 = fijo (_fijo); len_type 2 = LLVAR de largo maximo variable (_llvar).
        es_fijo_en_especificacion = definicion["len_type"] == 0
        assert metadato.longitud_fija == es_fijo_en_especificacion, (
            f"DE{numero}: METADATOS_CAMPOS_0100 dice longitud_fija="
            f"{metadato.longitud_fija} pero la especificacion es "
            f"{'fija' if es_fijo_en_especificacion else 'variable (LLVAR)'}"
        )
        assert metadato.descripcion == definicion["desc"], (
            f"DE{numero}: la descripcion de METADATOS_CAMPOS_0100 no coincide "
            f"con la de ESPECIFICACION_GENERICA"
        )


def test_todo_editable_u_opcional_del_perfil_tiene_metadata():
    """Todo campo que la UI puede ofrecer para escribir a mano (editable u
    opcional) debe tener una entrada en `METADATOS_CAMPOS_0100` -si no, la UI
    lo mostraria sin nombre corto/tipo, y `validar_forma_de_opcionales` no
    podria validar un opcional nuevo que se agregue sin esta entrada-.
    """
    politica = PERFIL_GENERICO.politica(MTI_COMPRA)
    numeros_editables_u_opcionales = politica.editables | politica.opcionales
    assert numeros_editables_u_opcionales <= set(METADATOS_CAMPOS_0100)

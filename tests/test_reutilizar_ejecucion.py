"""Reutilizar una transaccion desde su resultado: "Editar y volver a
ejecutar" / "Guardar como escenario" en `resultado.html`, resueltos por
`GET /?ejecucion_id={id}`.

Se prueba contra SQLite real -mismo criterio que `test_detalle_historial.py`-
insertando filas de `ejecuciones` y `destinos` directamente, para poder
ejercer combinaciones (conexion resoluble, ambigua, ausente) sin pasar por
el recorrido de compra completo.
"""

from __future__ import annotations

import re
import sqlite3

import httpx2

from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, PAN_DEMO
from sibutestlab8583.application import serializacion as sz
from sibutestlab8583.composicion import Composicion, Configuracion
from sibutestlab8583.domain.modelos import MensajeIso
from sibutestlab8583.profiles.generico import NOMBRE_PERFIL_GENERICO
from sibutestlab8583.web.app import crear_app


def _app(base):
    return crear_app(Composicion(Configuracion(ruta_base_datos=base)))


async def _obtener(base, ruta):
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=_app(base)), base_url="http://prueba"
    ) as cliente:
        return await cliente.get(ruta)


def _insertar_conexion(base, **campos) -> None:
    fila = {
        "destino_id": "QA-01", "nombre": "QA", "host": "10.20.30.40", "puerto": 9583,
        "activo": 1, "timeout": 10.0, "creado_en": "2026-08-19T12:00:00+00:00",
    }
    fila.update(campos)
    columnas = ", ".join(fila)
    marcas = ", ".join("?" * len(fila))
    with sqlite3.connect(base) as conexion:
        conexion.execute(f"INSERT INTO destinos ({columnas}) VALUES ({marcas})", tuple(fila.values()))
        conexion.commit()


def _insertar_ejecucion(base, **campos) -> int:
    solicitud = MensajeIso("0100", {
        "3": "000000", "22": "051", "37": "REF-ORIGINAL", "41": "TERM0001", "49": "188",
    })
    fila = {
        "creada_en": "2026-08-23T05:00:00+00:00",
        "card_id": CARD_ID_DEMO,
        "mti_solicitud": "0100",
        "mti_respuesta": "0110",
        "monto": "275.50",
        "moneda": "188",
        "stan": "000501",
        "destino_host": "10.20.30.40",
        "destino_puerto": 9583,
        "estado": "aprobada",
        "codigo_respuesta": "00",
        "solicitud_enmascarada": None,
        "respuesta_enmascarada": None,
        "solicitud_json": sz.a_json_solicitud(solicitud, NOMBRE_PERFIL_GENERICO),
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


async def test_editar_y_volver_a_ejecutar_prefilla_el_constructor(base):
    _insertar_conexion(base)
    identificador = _insertar_ejecucion(base)

    respuesta = await _obtener(base, f"/?ejecucion_id={identificador}")
    assert respuesta.status_code == 200
    texto = respuesta.text
    assert "275.50" in texto
    assert "REF-ORIGINAL" in texto
    assert "TERM0001" in texto
    assert 'value="QA-01"' in texto or "QA-01" in texto  # conexion resuelta


async def test_no_reconstruye_pan_en_los_campos_manuales(base):
    """El PAN nunca sale de aqui: solo se recupera `card_id`."""
    _insertar_conexion(base)
    identificador = _insertar_ejecucion(base)
    texto = (await _obtener(base, f"/?ejecucion_id={identificador}")).text
    assert PAN_DEMO not in texto


async def test_conexion_no_resoluble_pide_elegir_una_sin_sustituir_en_silencio(base):
    """El destino persistido no coincide con ninguna conexion activa: se
    explica y se deja sin resolver -no se preselecciona ninguna otra-.
    """
    _insertar_conexion(base, destino_id="OTRA", host="1.2.3.4", puerto=1111)
    identificador = _insertar_ejecucion(base, destino_host="9.9.9.9", destino_puerto=8888)

    respuesta = await _obtener(base, f"/?ejecucion_id={identificador}")
    assert respuesta.status_code == 200
    assert "No se pudo determinar automáticamente" in respuesta.text
    assert "9.9.9.9:8888" in respuesta.text


async def test_ejecucion_sin_transmision_explica_que_no_hay_conexion_que_recuperar(base):
    identificador = _insertar_ejecucion(
        base, estado="no_enviada", destino_host=None, destino_puerto=None, mti_respuesta=None,
    )
    respuesta = await _obtener(base, f"/?ejecucion_id={identificador}")
    assert respuesta.status_code == 200
    assert "no llegó a intentar transmisión" in respuesta.text


async def test_ejecucion_inexistente_se_explica_en_vez_de_fallar(base):
    respuesta = await _obtener(base, "/?ejecucion_id=999999")
    assert respuesta.status_code == 404
    assert "no existe" in respuesta.text.lower()


def _insertar_tarjeta_inactiva(base, card_id: str) -> None:
    with sqlite3.connect(base) as conexion:
        conexion.execute(
            "INSERT INTO tarjetas_prueba"
            " (card_id, pan, pan_enmascarado, expiracion, descripcion, sintetica, activa, creada_en)"
            " VALUES (?, '0', '****0000', '3012', 'Tarjeta desactivada', 1, 0, ?)",
            (card_id, "2026-01-01T00:00:00+00:00"),
        )
        conexion.commit()


async def test_tarjeta_desactivada_desde_entonces_se_explica_y_no_se_puede_ejecutar(base):
    """Hallazgo de revisión: si la tarjeta de una ejecución pasada ya no está
    disponible (desactivada o eliminada), el constructor debía bloquear
    'Ejecutar transacción' -eso ya funcionaba, vía `tarjeta_no_disponible`-,
    pero no explicaba el motivo: la persona veía el botón deshabilitado sin
    saber por qué. Corregido para que muestre un error explícito.
    """
    _insertar_conexion(base)
    _insertar_tarjeta_inactiva(base, "CARD-DESACTIVADA")
    identificador = _insertar_ejecucion(base, card_id="CARD-DESACTIVADA")

    respuesta = await _obtener(base, f"/?ejecucion_id={identificador}")
    assert respuesta.status_code == 200
    texto = respuesta.text
    assert "CARD-DESACTIVADA" in texto
    assert "ya no está disponible" in texto or "no está activa" in texto, (
        "debe explicar que la tarjeta ya no se puede usar, no solo deshabilitar el botón"
    )
    assert "disabled" in texto  # el boton de ejecutar sigue bloqueado


async def test_tarjeta_inexistente_tambien_se_explica(base):
    """Un `card_id` que ni siquiera existe en el catálogo -no solo inactivo-
    debe recibir la misma explicación, nunca un 500 ni un bloqueo silencioso.
    """
    _insertar_conexion(base)
    # La ejecucion referencia una tarjeta que NUNCA se creo en tarjetas_prueba.
    # La FK de SQLite solo se aplica con `PRAGMA foreign_keys=ON`, que esta
    # app activa al escribir pero no necesariamente al leer con sqlite3 crudo;
    # para no depender de eso, se inserta primero la tarjeta y se borra despues,
    # que es indistinguible en la practica de "nunca existio" para el codigo
    # bajo prueba (que solo mira `consultas.tarjetas()`, nunca la FK).
    _insertar_tarjeta_inactiva(base, "CARD-BORRADA")
    identificador = _insertar_ejecucion(base, card_id="CARD-BORRADA")
    with sqlite3.connect(base) as conexion:
        conexion.execute("PRAGMA foreign_keys=OFF")
        conexion.execute("DELETE FROM tarjetas_prueba WHERE card_id='CARD-BORRADA'")
        conexion.commit()

    respuesta = await _obtener(base, f"/?ejecucion_id={identificador}")
    assert respuesta.status_code == 200
    assert "CARD-BORRADA" in respuesta.text
    assert "disabled" in respuesta.text


async def test_tarjeta_y_conexion_no_disponibles_a_la_vez_explica_ambas(base):
    """Los dos problemas pueden coexistir; el mensaje no se queda solo con
    el primero que encuentra.
    """
    _insertar_tarjeta_inactiva(base, "CARD-DESACTIVADA")
    identificador = _insertar_ejecucion(
        base, card_id="CARD-DESACTIVADA", destino_host="9.9.9.9", destino_puerto=8888,
    )
    respuesta = await _obtener(base, f"/?ejecucion_id={identificador}")
    assert respuesta.status_code == 200
    texto = respuesta.text
    assert "CARD-DESACTIVADA" in texto
    assert "9.9.9.9:8888" in texto


def _insertar_escenario(base, escenario_id: str, expected_json: str | None) -> None:
    with sqlite3.connect(base) as conexion:
        conexion.execute(
            "INSERT INTO escenarios"
            " (escenario_id, nombre, perfil, mti, card_id, conexion_id, monto,"
            "  expected_json, creado_en, actualizado_en)"
            " VALUES (?, ?, 'generico', '0100', ?, 'QA-01', '275.50', ?, ?, ?)",
            (
                escenario_id, "Escenario con expectativas", CARD_ID_DEMO, expected_json,
                "2026-08-19T12:00:00+00:00", "2026-08-19T12:00:00+00:00",
            ),
        )
        conexion.commit()


async def test_las_expectativas_se_recuperan_de_la_ejecucion_no_del_escenario_editado(base):
    """El escenario que origino la ejecucion se edita DESPUES -expectativas
    distintas de las que tenia al momento de ejecutar-. La reconstruccion
    debe reflejar lo que esa ejecucion evaluo en su momento (el snapshot en
    `evaluacion_json`), nunca el estado actual del escenario.
    """
    _insertar_conexion(base)
    # El escenario, TAL COMO ESTA HOY, espera "rechazada" -edicion posterior-.
    _insertar_escenario(
        base, "ESC-EXP",
        expected_json='{"version":1,"estado":"rechazada","campos":{}}',
    )
    # Pero la ejecucion que se quiere reutilizar evaluo, EN SU MOMENTO,
    # "aprobada" + campo 39 igual a "00".
    evaluacion_json = (
        '{"version":1,"resultado":"pass",'
        '"expectativas":{"version":1,"estado":"aprobada","campos":'
        '{"39":{"tipo":"igual","valor":"00"}}},'
        '"discrepancias":[]}'
    )
    identificador = _insertar_ejecucion(
        base, escenario_id="ESC-EXP", escenario_nombre="Escenario con expectativas",
        evaluacion_estado="pass", evaluacion_json=evaluacion_json,
    )

    respuesta = await _obtener(base, f"/?ejecucion_id={identificador}")
    assert respuesta.status_code == 200
    texto = respuesta.text

    assert re.search(r'<option value="aprobada"\s+selected', texto), (
        "debe mostrar 'aprobada' (lo que la ejecucion realmente evaluo), no 'rechazada'"
    )
    assert not re.search(r'<option value="rechazada"\s+selected', texto), (
        "no debe mostrar el estado ACTUAL del escenario editado"
    )
    fila_39 = re.search(r'name="tipo_esperado_39".*?</select>', texto, re.DOTALL)
    assert fila_39 is not None
    assert re.search(r'<option value="igual"\s+selected', fila_39.group(0))
    assert 'name="valor_esperado_39"' in texto
    assert 'value="00"' in texto


async def test_ejecucion_sin_expectativas_no_muestra_ninguna(base):
    """Si la ejecucion no tenia expectativas, la reconstruccion no debe
    inventar ninguna -ni heredar las del escenario actual, aunque exista-.
    """
    _insertar_conexion(base)
    _insertar_escenario(
        base, "ESC-SIN-EXP",
        expected_json='{"version":1,"estado":"aprobada","campos":{}}',
    )
    identificador = _insertar_ejecucion(
        base, escenario_id="ESC-SIN-EXP", escenario_nombre="Escenario con expectativas",
        evaluacion_estado=None, evaluacion_json=None,
    )

    respuesta = await _obtener(base, f"/?ejecucion_id={identificador}")
    assert respuesta.status_code == 200
    assert re.search(r'<option value=""\s+selected', respuesta.text), (
        "sin expectativas en la ejecucion: debe quedar 'No especificar', nunca heredar del escenario"
    )


async def test_ejecucion_del_formato_de_texto_heredado_avisa_que_no_es_fiel(base):
    """Hallazgo de revisión: una ejecución anterior a la persistencia
    estructurada (solo `solicitud_enmascarada`, sin `solicitud_json`) no
    puede demostrar que sus campos editables se recuperen exactos -un valor
    pudo quedar partido por el separador `` | `` sin escape (ver
    `MensajeSerializado.fiel`)-. Antes de esta corrección no se avisaba nada:
    se presentaba como si fuera tan confiable como una ejecución reciente.
    """
    _insertar_conexion(base)
    identificador = _insertar_ejecucion(
        base,
        solicitud_json=None,
        solicitud_enmascarada="MTI=0100 | 3=000000 | 22=051 | 37=REF-HEREDADO | 41=TERM0001 | 49=188",
    )

    respuesta = await _obtener(base, f"/?ejecucion_id={identificador}")
    assert respuesta.status_code == 200
    texto = respuesta.text
    assert "formato anterior" in texto
    assert "no puede garantizarse que sean exactos" in texto
    # Aun asi, la mejor aproximacion posible se recupera (no se deja en blanco).
    assert "REF-HEREDADO" in texto


async def test_cada_repeticion_genera_una_ejecucion_nueva(base):
    """Reejecutar desde el constructor prefilled sigue siendo un POST normal
    a /compra: no hay ningun mecanismo que reutilice el id o el STAN
    anteriores. Esto lo comprueba la suite del recorrido de compra
    (`test_web.py`); aqui solo se confirma que la pantalla cargada no expone
    ningun control que "reenvie" la ejecucion original -solo el formulario
    normal, que al someterse crea una fila nueva.
    """
    _insertar_conexion(base)
    identificador = _insertar_ejecucion(base)
    texto = (await _obtener(base, f"/?ejecucion_id={identificador}")).text
    assert 'action="/compra"' in texto
    assert f'name="ejecucion_id"' not in texto  # no se reenvia el id original

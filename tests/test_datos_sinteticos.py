"""Generacion de PAN sinteticos y la regla que impide versionarlos.

La ultima prueba de este archivo convierte una politica del repositorio en una
comprobacion automatica: si alguien pega un numero de tarjeta en el codigo o en
la documentacion, la suite falla. Vigilar esto a mano no escala.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from sibutestlab8583.adapters.persistence.esquema import PAN_DEMO, SUFIJO_DEMO
from sibutestlab8583.domain.datos_sinteticos import (
    LONGITUD_PAN_POR_DEFECTO,
    es_luhn_valido,
    monto_iso,
    pan_sintetico,
)
from sibutestlab8583.domain.enmascarado import enmascarar_pan

RAIZ = Path(__file__).resolve().parent.parent

#: Cualquier corrida de digitos con largo de PAN. Se construye asi, y no como
#: literal, para que esta misma prueba no viole la regla que comprueba.
PATRON_PAN = re.compile(r"[0-9]{12,19}")


def test_genera_un_pan_del_largo_pedido_terminado_en_el_sufijo():
    pan = pan_sintetico("6666")
    assert len(pan) == LONGITUD_PAN_POR_DEFECTO
    assert pan.endswith("6666")
    assert pan.isdigit()


def test_ningun_numero_generado_supera_la_verificacion_de_luhn():
    """La propiedad defendible: no es un numero de tarjeta utilizable.

    No se afirma nada sobre rangos de emisor: las asignaciones nacionales existen
    y no son una garantia que este proyecto pueda dar. La invalidez de Luhn si es
    comprobable.
    """
    for sufijo in ("0000", "0001", "1111", "2222", "3333", "6666", "9999"):
        assert not es_luhn_valido(pan_sintetico(sufijo)), sufijo


def test_el_numero_es_determinista():
    assert pan_sintetico("6666") == pan_sintetico("6666")


def test_dos_sufijos_distintos_dan_tarjetas_distintas():
    assert pan_sintetico("1111") != pan_sintetico("2222")


def test_la_verificacion_de_luhn_reconoce_un_numero_valido():
    """Sin esto, el comprobador podria devolver siempre False y nadie lo notaria."""
    assert es_luhn_valido("18"), "18 es la secuencia mas corta que satisface Luhn"
    assert not es_luhn_valido("19")
    assert not es_luhn_valido("no-numerico")


def test_el_pan_generado_se_enmascara_como_lo_exige_la_politica():
    assert enmascarar_pan(pan_sintetico("6666")) == "*" * 12 + "6666"


def test_rechaza_entradas_invalidas():
    with pytest.raises(ValueError):
        pan_sintetico("no-numerico")
    with pytest.raises(ValueError):
        pan_sintetico("1234", longitud=4)
    with pytest.raises(ValueError):
        pan_sintetico("1234", longitud=99)
    with pytest.raises(ValueError):
        pan_sintetico("1234", relleno="ab")


def test_la_tarjeta_de_demostracion_se_genera_y_no_es_un_literal():
    assert PAN_DEMO == pan_sintetico(SUFIJO_DEMO)
    assert len(PAN_DEMO) == LONGITUD_PAN_POR_DEFECTO


def test_monto_iso_rellena_con_ceros():
    assert monto_iso("15000") == "15000".rjust(12, "0")
    assert len(monto_iso("1")) == 12
    with pytest.raises(ValueError):
        monto_iso("x")


def _archivos_versionados() -> list[Path]:
    salida = subprocess.run(
        ["git", "ls-files"], cwd=RAIZ, capture_output=True, text=True, check=True
    )
    seguimiento = salida.stdout.split()
    sin_seguimiento = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=RAIZ,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return [RAIZ / nombre for nombre in seguimiento + sin_seguimiento]


def test_ningun_archivo_versionable_contiene_un_pan_completo():
    """Git no debe contener PAN completos, ni reales ni sinteticos.

    Un literal de dieciseis digitos es indistinguible de una tarjeta real para
    un escaner de secretos o para una auditoria. Los valores que las pruebas y
    la demostracion necesitan se generan en ejecucion.
    """
    hallazgos: list[str] = []
    for archivo in _archivos_versionados():
        if not archivo.is_file():
            continue
        try:
            contenido = archivo.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binario o ilegible: no puede contener un literal de codigo
        for numero, linea in enumerate(contenido.splitlines(), start=1):
            for hallazgo in PATRON_PAN.findall(linea):
                hallazgos.append(f"{archivo.relative_to(RAIZ)}:{numero}: {len(hallazgo)} digitos")

    assert not hallazgos, "secuencias con largo de PAN en archivos versionables:\n" + "\n".join(
        hallazgos
    )

"""Derivacion pura de Track 1 y Track 2. Ver `domain/tracks.py`.

Los PAN de las pruebas se generan con `pan_sintetico()` en el largo exacto
que hace falta, dentro del rango que el propio helper admite (12 a 19
digitos). Para el caso de 20 digitos -por encima del `LONGITUD_MAXIMA` del
helper, que por eso no puede generarlo- se usa un literal claramente
sintetico compuesto por un unico digito repetido veinte veces (`"9" * 20`):
no es, ni pretende ser, un PAN Luhn-valido -`construir_track1`/`construir_track2`
no validan Luhn, asi que eso no afecta lo que se esta probando aqui-, y su
forma (un solo digito repetido) lo hace evidentemente no un numero real. No
se modifico `pan_sintetico()` para este bloque.
"""

from __future__ import annotations

import pytest

from sibutestlab8583.domain.datos_sinteticos import pan_sintetico
from sibutestlab8583.domain.tracks import (
    LARGO_MAXIMO_TRACK1,
    LARGO_MAXIMO_TRACK2,
    construir_track1,
    construir_track2,
)

PAN = pan_sintetico("4242")
PAN_19 = pan_sintetico("4242", longitud=19)
PAN_20_SINTETICO = "9" * 20  # ver docstring del modulo: no generable por pan_sintetico()

TITULAR = "PEREZ/JUAN"
EXPIRACION = "3012"
SERVICE_CODE = "201"


def _track1_valido(**cambios) -> dict:
    datos = dict(
        pan=PAN, titular=TITULAR, expiracion=EXPIRACION,
        service_code=SERVICE_CODE, discretionary_data="",
    )
    datos.update(cambios)
    return datos


def _track2_valido(**cambios) -> dict:
    datos = dict(
        pan=PAN, expiracion=EXPIRACION, service_code=SERVICE_CODE, discretionary_data="",
    )
    datos.update(cambios)
    return datos


# --------------------------------------------------------------- Track 1 ---


def test_track1_se_construye_con_todos_los_componentes():
    assert construir_track1(**_track1_valido()) == f"B{PAN}^{TITULAR}^{EXPIRACION}{SERVICE_CODE}"


def test_track1_empieza_con_b():
    assert construir_track1(**_track1_valido()).startswith("B")


def test_track1_contiene_exactamente_dos_separadores():
    assert construir_track1(**_track1_valido()).count("^") == 2


def test_track1_no_contiene_sentinels_fisicos():
    track = construir_track1(**_track1_valido())
    assert "%" not in track
    assert "?" not in track


def test_track1_sin_lrc_el_largo_coincide_exactamente_con_la_formula():
    track = construir_track1(**_track1_valido())
    esperado = 1 + len(PAN) + 1 + len(TITULAR) + 1 + 4 + 3
    assert len(track) == esperado


def test_track1_admite_discretionary_data_vacio():
    track = construir_track1(**_track1_valido(discretionary_data=""))
    assert track.endswith(SERVICE_CODE)


@pytest.mark.parametrize(
    "pan,valido",
    [
        (PAN_19, True),
        (PAN_20_SINTETICO, False),
        ("", False),
        ("ABCD", False),
    ],
)
def test_track1_valida_el_pan(pan, valido):
    datos = _track1_valido(pan=pan)
    if valido:
        assert construir_track1(**datos).startswith(f"B{pan}")
    else:
        with pytest.raises(ValueError):
            construir_track1(**datos)


@pytest.mark.parametrize(
    "titular,valido",
    [
        ("PEREZ/JUAN", True),
        ("", False),
        ("PEREZ^JUAN", False),
    ],
)
def test_track1_valida_el_titular(titular, valido):
    datos = _track1_valido(titular=titular)
    if valido:
        construir_track1(**datos)
    else:
        with pytest.raises(ValueError):
            construir_track1(**datos)


@pytest.mark.parametrize(
    "expiracion,valida",
    [
        ("3012", True),
        ("", False),
        ("ABCD", False),
        ("301", False),
        ("30112", False),
        ("3000", False),  # mes 00
        ("3013", False),  # mes 13
    ],
)
def test_track1_valida_la_expiracion(expiracion, valida):
    datos = _track1_valido(expiracion=expiracion)
    if valida:
        construir_track1(**datos)
    else:
        with pytest.raises(ValueError):
            construir_track1(**datos)


@pytest.mark.parametrize(
    "service_code,valido",
    [
        ("201", True),
        ("", False),
        ("20", False),
        ("2011", False),
        ("2A1", False),
    ],
)
def test_track1_valida_el_service_code(service_code, valido):
    datos = _track1_valido(service_code=service_code)
    if valido:
        construir_track1(**datos)
    else:
        with pytest.raises(ValueError):
            construir_track1(**datos)


def test_track1_rechaza_discretionary_data_con_separador():
    with pytest.raises(ValueError):
        construir_track1(**_track1_valido(discretionary_data="A^B"))


def test_track1_de_longitud_exacta_76_es_valido():
    # 1(B) + 19(pan) + 1 + len(titular) + 1 + 4 + 3 + len(disc) == 76
    # => len(titular) + len(disc) == 47
    titular = "A" * 30
    discretionary = "B" * 17
    track = construir_track1(
        pan=PAN_19, titular=titular, expiracion=EXPIRACION,
        service_code=SERVICE_CODE, discretionary_data=discretionary,
    )
    assert len(track) == LARGO_MAXIMO_TRACK1 == 76


def test_track1_de_longitud_77_lanza_error():
    titular = "A" * 30
    discretionary = "B" * 18  # uno mas que el caso valido de arriba
    with pytest.raises(ValueError):
        construir_track1(
            pan=PAN_19, titular=titular, expiracion=EXPIRACION,
            service_code=SERVICE_CODE, discretionary_data=discretionary,
        )


# --------------------------------------------------------------- Track 2 ---


def test_track2_se_construye_con_todos_los_componentes():
    assert construir_track2(**_track2_valido()) == f"{PAN}={EXPIRACION}{SERVICE_CODE}"


def test_track2_contiene_exactamente_un_separador():
    assert construir_track2(**_track2_valido()).count("=") == 1


def test_track2_no_contiene_sentinels_fisicos():
    track = construir_track2(**_track2_valido())
    assert ";" not in track
    assert "?" not in track


def test_track2_sin_lrc_el_largo_coincide_exactamente_con_la_formula():
    track = construir_track2(**_track2_valido())
    assert len(track) == len(PAN) + 1 + 4 + 3


def test_track2_admite_discretionary_data_vacio():
    track = construir_track2(**_track2_valido(discretionary_data=""))
    assert track.endswith(SERVICE_CODE)


def test_track2_rechaza_discretionary_data_no_numerico():
    with pytest.raises(ValueError):
        construir_track2(**_track2_valido(discretionary_data="ABC"))


@pytest.mark.parametrize(
    "pan,valido",
    [
        (PAN_19, True),
        (PAN_20_SINTETICO, False),
        ("", False),
        ("ABCD", False),
    ],
)
def test_track2_valida_el_pan(pan, valido):
    datos = _track2_valido(pan=pan)
    if valido:
        assert construir_track2(**datos).startswith(pan)
    else:
        with pytest.raises(ValueError):
            construir_track2(**datos)


@pytest.mark.parametrize(
    "expiracion,valida",
    [
        ("3012", True),
        ("", False),
        ("ABCD", False),
        ("301", False),
        ("3000", False),
        ("3013", False),
    ],
)
def test_track2_valida_la_expiracion(expiracion, valida):
    datos = _track2_valido(expiracion=expiracion)
    if valida:
        construir_track2(**datos)
    else:
        with pytest.raises(ValueError):
            construir_track2(**datos)


@pytest.mark.parametrize(
    "service_code,valido",
    [
        ("201", True),
        ("", False),
        ("20", False),
        ("2011", False),
        ("2A1", False),
    ],
)
def test_track2_valida_el_service_code(service_code, valido):
    datos = _track2_valido(service_code=service_code)
    if valido:
        construir_track2(**datos)
    else:
        with pytest.raises(ValueError):
            construir_track2(**datos)


def test_track2_de_longitud_exacta_37_es_valido():
    # 19(pan) + 1 + 4 + 3 + len(disc) == 37 => len(disc) == 10
    discretionary = "1" * 10
    track = construir_track2(
        pan=PAN_19, expiracion=EXPIRACION, service_code=SERVICE_CODE,
        discretionary_data=discretionary,
    )
    assert len(track) == LARGO_MAXIMO_TRACK2 == 37


def test_track2_de_longitud_38_lanza_error():
    discretionary = "1" * 11  # uno mas que el caso valido de arriba
    with pytest.raises(ValueError):
        construir_track2(
            pan=PAN_19, expiracion=EXPIRACION, service_code=SERVICE_CODE,
            discretionary_data=discretionary,
        )

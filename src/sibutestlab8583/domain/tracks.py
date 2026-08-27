"""Derivacion pura de las representaciones logicas de Track 1 y Track 2.

Funciones de dominio, sin I/O, sin persistencia, sin conocer SQLite ni web.
No transmiten nada por ISO 8583 todavia: ningun otro modulo del proyecto las
invoca por ahora, y `profiles/generico.py` sigue sin DE35 ni DE45.

Formato adoptado (SibuTestLab, no un byte a byte de la pista fisica):

    Track 1:  B{PAN}^{TITULAR}^{YYMM}{SERVICE_CODE}{DISCRETIONARY_DATA}
    Track 2:  {PAN}={YYMM}{SERVICE_CODE}{DISCRETIONARY_DATA}

Ninguna de las dos incluye los sentinels fisicos (`%`, `;`, `?`) ni el LRC:
son artefactos de la codificacion fisica de la pista, no contenido logico, y
por eso se excluyen de esta representacion -pensada para poder alimentar en
el futuro un DE45 (Track 1) o un DE35 (Track 2), sin haberlos implementado
todavia-.

Sobre los limites de longitud (76 y 37): no son una cifra elegida al azar.
La pista fisica completa, segun ISO/IEC 7813, admite hasta 79 caracteres
(Track 1) y 40 caracteres (Track 2), contando el sentinel inicial, el
sentinel final y el LRC. Como esta representacion nunca codifica esos tres
caracteres, se restan del maximo fisico: 79 - 3 = 76, y 40 - 3 = 37. El
Format Code `B` si se conserva -no es un sentinel, es el codigo de formato de
Track 1, y por eso cuenta dentro del limite en vez de restarse-.

Politica de PAN, sintetica/QA y Luhn: **no se decide aqui**. `construir_pan`
no existe, y las dos funciones de este modulo no validan Luhn ni deciden si
una tarjeta es sintetica o de un ambiente QA autorizado: esa politica sigue
viviendo, sin cambios, en `application/tarjetas.py`.
"""

from __future__ import annotations

#: Longitud logica de cada componente, fija por definicion del formato.
LARGO_EXPIRACION = 4
LARGO_SERVICE_CODE = 3
LARGO_PAN_MAXIMO = 19

#: Ver la explicacion completa en el docstring del modulo: 79-3 y 40-3.
LARGO_MAXIMO_TRACK1 = 76
LARGO_MAXIMO_TRACK2 = 37

FORMAT_CODE_TRACK1 = "B"
SEPARADOR_TRACK1 = "^"
SEPARADOR_TRACK2 = "="

#: Allowlist deliberadamente conservadora para el titular de Track 1: mas
#: restrictiva que lo que el estandar fisico admitiria, elegida por
#: SibuTestLab para que el resultado nunca pueda contener un caracter que
#: rompa la estructura (`^`) ni uno que sea ambiguo de leer.
CARACTERES_TITULAR = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 /-."
)

#: Igual de conservadora para el discretionary data de Track 1: alfanumerico
#: en mayusculas, sin espacios ni separadores.
CARACTERES_DISCRETIONARY_TRACK1 = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
)


def _validar_pan(pan: str) -> str:
    if not pan:
        raise ValueError("el PAN es obligatorio")
    if not pan.isdigit():
        raise ValueError("el PAN debe contener solo digitos")
    if len(pan) > LARGO_PAN_MAXIMO:
        raise ValueError(f"el PAN no puede superar {LARGO_PAN_MAXIMO} digitos")
    return pan


def _validar_expiracion(expiracion: str) -> str:
    if not expiracion:
        raise ValueError("la expiracion es obligatoria")
    if len(expiracion) != LARGO_EXPIRACION or not expiracion.isdigit():
        raise ValueError("la expiracion debe tener el formato YYMM: cuatro digitos")
    mes = int(expiracion[2:])
    if not 1 <= mes <= 12:
        raise ValueError("la expiracion debe traer un mes entre 01 y 12")
    return expiracion


def _validar_service_code(service_code: str) -> str:
    if not service_code:
        raise ValueError("el service code es obligatorio")
    if len(service_code) != LARGO_SERVICE_CODE or not service_code.isdigit():
        raise ValueError(
            f"el service code debe tener exactamente {LARGO_SERVICE_CODE} digitos"
        )
    return service_code


def _validar_titular(titular: str) -> str:
    if not titular:
        raise ValueError("el titular es obligatorio para Track 1")
    if any(caracter not in CARACTERES_TITULAR for caracter in titular):
        raise ValueError(
            "el titular solo admite letras, digitos, espacio, '/', '-' y '.'"
        )
    return titular


def _validar_discretionary_track1(discretionary_data: str) -> str:
    if any(c not in CARACTERES_DISCRETIONARY_TRACK1 for c in discretionary_data):
        raise ValueError("el discretionary data de Track 1 solo admite letras y digitos")
    return discretionary_data


def _validar_discretionary_track2(discretionary_data: str) -> str:
    if discretionary_data and not discretionary_data.isdigit():
        raise ValueError("el discretionary data de Track 2 solo admite digitos")
    return discretionary_data


def construir_track1(
    pan: str,
    titular: str,
    expiracion: str,
    service_code: str,
    discretionary_data: str = "",
) -> str:
    """B{PAN}^{TITULAR}^{YYMM}{SERVICE_CODE}{DISCRETIONARY_DATA}

    Sin sentinels fisicos (`%`, `?`) ni LRC. Maximo `LARGO_MAXIMO_TRACK1`
    caracteres (ver el docstring del modulo). Lanza `ValueError` si falta un
    componente obligatorio, si algun componente no cumple su forma, o si el
    resultado excede el maximo.
    """
    pan = _validar_pan(pan)
    titular = _validar_titular(titular)
    expiracion = _validar_expiracion(expiracion)
    service_code = _validar_service_code(service_code)
    discretionary_data = _validar_discretionary_track1(discretionary_data)

    track = (
        f"{FORMAT_CODE_TRACK1}{pan}{SEPARADOR_TRACK1}{titular}{SEPARADOR_TRACK1}"
        f"{expiracion}{service_code}{discretionary_data}"
    )
    if len(track) > LARGO_MAXIMO_TRACK1:
        raise ValueError(
            f"el Track 1 resultante supera el maximo de {LARGO_MAXIMO_TRACK1} caracteres"
        )
    return track


def construir_track2(
    pan: str,
    expiracion: str,
    service_code: str,
    discretionary_data: str = "",
) -> str:
    """{PAN}={YYMM}{SERVICE_CODE}{DISCRETIONARY_DATA}

    Sin sentinels fisicos (`;`, `?`) ni LRC. Maximo `LARGO_MAXIMO_TRACK2`
    caracteres (ver el docstring del modulo). Lanza `ValueError` si falta un
    componente obligatorio, si algun componente no cumple su forma, o si el
    resultado excede el maximo.
    """
    pan = _validar_pan(pan)
    expiracion = _validar_expiracion(expiracion)
    service_code = _validar_service_code(service_code)
    discretionary_data = _validar_discretionary_track2(discretionary_data)

    track = f"{pan}{SEPARADOR_TRACK2}{expiracion}{service_code}{discretionary_data}"
    if len(track) > LARGO_MAXIMO_TRACK2:
        raise ValueError(
            f"el Track 2 resultante supera el maximo de {LARGO_MAXIMO_TRACK2} caracteres"
        )
    return track

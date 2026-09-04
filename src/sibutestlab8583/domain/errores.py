"""Errores controlados del proyecto.

Los adaptadores traducen aqui los errores de sus librerias para que el
orquestador y el dominio no tengan que conocer `pyiso8583` ni `asyncio`.

Las condiciones de red **no** son errores aqui: el transporte las devuelve como
resultado —`TiempoAgotado` y `FalloDeConexion` en `modelos.py`—, porque para una
herramienta de pruebas son observaciones que hay que registrar. Por eso no existe
ninguna excepcion de transporte en este modulo.
"""

from __future__ import annotations


class ErrorDelSimulador(Exception):
    """Raiz de todos los errores propios. Permite capturarlos como familia."""


class ErrorDeCodec(ErrorDelSimulador):
    """Fallo al convertir entre el dominio y los bytes ISO 8583."""


class ErrorDeCodificacion(ErrorDeCodec):
    """El mensaje del dominio no pudo convertirse a bytes con el perfil dado."""


class ErrorDeDecodificacion(ErrorDeCodec):
    """Los bytes recibidos no pudieron interpretarse con el perfil dado."""


class ErrorDeFraming(ErrorDelSimulador):
    """El enmarcado o desenmarcado del stream fallo.

    Cubre un payload de largo invalido, un prefijo incompleto y un stream que
    se corta antes de completar el mensaje anunciado.
    """


class ErrorDeCamposManuales(ErrorDelSimulador, ValueError):
    """Un campo manual no procede para el MTI que se esta armando.

    Es `ValueError` ademas de `ErrorDelSimulador` para que la capa web lo trate
    igual que cualquier otro error de entrada (400, sin traza), sin necesitar un
    manejador nuevo.
    """


class CampoNoPermitido(ErrorDeCamposManuales):
    """El campo no esta declarado como editable para este MTI."""


class CampoProtegido(ErrorDeCamposManuales):
    """El campo es derivado o automatico: no puede fijarse manualmente."""


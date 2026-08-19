"""Errores controlados del proyecto.

Los adaptadores traducen aqui los errores de sus librerias para que el
orquestador y el dominio no tengan que conocer `pyiso8583` ni `asyncio`.

Un tiempo de espera agotado **no** es un error: es un resultado esperado del
transporte y se modela como `TiempoAgotado` en `modelos.py`, porque RN-2 exige
contarlo aparte de un rechazo.
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


class ErrorDeTransporte(ErrorDelSimulador):
    """Fallo de red que no es un tiempo de espera agotado."""


class ErrorDeConexion(ErrorDeTransporte):
    """No se pudo establecer la conexion con el destino."""

"""Construccion del mensaje 0100 de compra.

Funcion pura: recibe los datos y devuelve el mensaje. El STAN y el momento se
inyectan en lugar de generarse aqui, para que las pruebas sean deterministas y
para que esta funcion no dependa del reloj.

Solo arma compras. No hay aqui nada para reversos, retiros ni otros MTI.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from .modelos import MTI_COMPRA, DatosCompra, MensajeIso, TarjetaPrueba

#: Un monto ISO viaja en unidades minimas, sin separador decimal, en 12 digitos.
LARGO_CAMPO_MONTO = 12
DECIMALES_POR_DEFECTO = 2

#: Captura manual del numero de tarjeta. Valor del perfil generico de
#: demostracion, no atribuible a ninguna marca.
MODO_CAPTURA_DEMOSTRACION = "011"


def formatear_monto(monto: Decimal, *, decimales: int = DECIMALES_POR_DEFECTO) -> str:
    """Convierte un monto a las unidades minimas que exige el campo 4."""
    if monto < 0:
        raise ValueError(f"el monto no puede ser negativo: {monto}")
    unidades = int((monto * (10**decimales)).to_integral_value())
    texto = str(unidades)
    if len(texto) > LARGO_CAMPO_MONTO:
        raise ValueError(f"el monto excede el campo 4: {monto}")
    return texto.rjust(LARGO_CAMPO_MONTO, "0")


def armar_compra(
    datos: DatosCompra,
    tarjeta: TarjetaPrueba,
    *,
    stan: str,
    momento: datetime,
    codigo_proceso: str,
) -> MensajeIso:
    """Arma el 0100 con los campos que el perfil generico exige.

    No valida: de eso se encarga RN-4 inmediatamente despues, y separar ambas
    cosas permite armar un mensaje incompleto a proposito para probar la regla.
    """
    return MensajeIso(
        mti=MTI_COMPRA,
        campos={
            "2": tarjeta.pan,
            "3": codigo_proceso,
            "4": formatear_monto(datos.monto),
            "7": momento.strftime("%m%d%H%M%S"),
            "11": stan,
            "12": momento.strftime("%H%M%S"),
            "13": momento.strftime("%m%d"),
            "14": tarjeta.expiracion,
            "22": MODO_CAPTURA_DEMOSTRACION,
            "41": datos.terminal,
            "49": datos.moneda,
        },
    )

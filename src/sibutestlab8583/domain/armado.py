"""Construccion del mensaje 0100 de compra.

Funcion pura: recibe los datos y devuelve el mensaje. El STAN y el momento se
inyectan en lugar de generarse aqui, para que las pruebas sean deterministas y
para que esta funcion no dependa del reloj.

Solo arma compras. No hay aqui nada para reversos, retiros ni otros MTI.

CONSTRUCTOR GOBERNADO POR EL PERFIL
====================================
`datos.campos_manuales` es la unica puerta para que el usuario fije un valor
distinto del default en un campo que el perfil declare editable para el 0100
(ver `PoliticaCamposMti` en `profiles/generico.py`). El armado se hace en
capas, cada una pudiendo pisar a la anterior, y la ultima —los campos
estructurales— gana siempre, sin excepcion, aunque la validacion previa
tuviera un defecto: es la defensa en profundidad de que ningun campo derivado
o automatico pueda terminar siendo el que el usuario escribio.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Mapping

from .errores import CampoNoPermitido, CampoProtegido
from .modelos import MTI_COMPRA, DatosCompra, MensajeIso, TarjetaPrueba

#: Un monto ISO viaja en unidades minimas, sin separador decimal, en 12 digitos.
LARGO_CAMPO_MONTO = 12
DECIMALES_POR_DEFECTO = 2


def formatear_monto(monto: Decimal, *, decimales: int = DECIMALES_POR_DEFECTO) -> str:
    """Convierte un monto a las unidades minimas que exige el campo 4."""
    if monto < 0:
        raise ValueError(f"el monto no puede ser negativo: {monto}")
    unidades = int((monto * (10**decimales)).to_integral_value())
    texto = str(unidades)
    if len(texto) > LARGO_CAMPO_MONTO:
        raise ValueError(f"el monto excede el campo 4: {monto}")
    return texto.rjust(LARGO_CAMPO_MONTO, "0")


def validar_campos_manuales(campos_manuales: Mapping[str, str], perfil, mti: str) -> None:
    """Revienta si algun campo manual no procede para este MTI segun el perfil.

    Se llama dos veces por diseno: una vez en la capa web, para devolver un
    error de entrada legible antes de tocar el orquestador; otra vez aqui,
    dentro de `armar_compra`, como defensa en profundidad — no se confia en
    que quien llame ya haya validado, ni en que el HTML solo ofrezca los
    campos permitidos.
    """
    politica = perfil.politica(mti)
    for numero in campos_manuales:
        origen = politica.origen(numero)
        if origen in ("derivado", "automatico"):
            raise CampoProtegido(
                f"el campo {numero} es {origen} para el MTI {mti}: no puede fijarse manualmente"
            )
        if origen == "no_permitido":
            raise CampoNoPermitido(f"el campo {numero} no es editable para el MTI {mti}")


def armar_compra(
    datos: DatosCompra,
    tarjeta: TarjetaPrueba,
    *,
    stan: str,
    momento: datetime,
    perfil,
) -> MensajeIso:
    """Arma el 0100 en cuatro capas, cada una pudiendo pisar a la anterior:

    1. los defaults que el perfil declara para los campos editables del 0100;
    2. lo que el usuario haya fijado en `datos.campos_manuales`, ya validado
       contra la politica del perfil;
    3. los campos estructurales —derivados de la tarjeta y automaticos del
       sistema—, que SIEMPRE ganan, sin excepcion.

    No valida RN-4: de eso se encarga esa regla inmediatamente despues, y
    separar ambas cosas permite armar un mensaje incompleto a proposito para
    probarla.
    """
    validar_campos_manuales(datos.campos_manuales, perfil, MTI_COMPRA)
    politica = perfil.politica(MTI_COMPRA)

    campos = dict(politica.valores_por_defecto)
    campos.update(datos.campos_manuales)
    campos.update(
        {
            "2": tarjeta.pan,
            "4": formatear_monto(datos.monto),
            "7": momento.strftime("%m%d%H%M%S"),
            "11": stan,
            "12": momento.strftime("%H%M%S"),
            "13": momento.strftime("%m%d"),
            "14": tarjeta.expiracion,
        }
    )
    return MensajeIso(mti=MTI_COMPRA, campos=campos)

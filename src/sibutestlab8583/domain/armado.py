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

from .campos_iso import MetadatoCampo
from .errores import CampoConFormaInvalida, CampoNoPermitido, CampoProtegido
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


def valores_efectivos_editables(
    campos_manuales: Mapping[str, str], perfil, mti: str
) -> dict[str, str]:
    """Defaults del perfil + overrides del usuario, solo para campos editables.

    Es exactamente lo que un escenario debe congelar al guardarse: las dos
    primeras capas de `armar_compra` (perfil, despues usuario), sin la tercera
    -la estructural nunca se congela, se regenera en cada ejecucion-. Si
    manana el perfil cambia un default, un escenario ya guardado no debe
    cambiar de comportamiento en silencio: por eso se persiste el valor
    EFECTIVO de hoy, no una referencia a "el default de turno".

    Reutiliza `validar_campos_manuales` para no aceptar de entrada nada que
    `armar_compra` fuera a rechazar despues.
    """
    validar_campos_manuales(campos_manuales, perfil, mti)
    politica = perfil.politica(mti)
    efectivos = dict(politica.valores_por_defecto)
    efectivos.update(campos_manuales)
    return efectivos


def validar_forma_de_opcionales(
    campos_manuales: Mapping[str, str], perfil, mti: str, metadatos: Mapping[str, MetadatoCampo]
) -> None:
    """Revienta con un mensaje especifico si un campo OPCIONAL agregado no
    tiene la forma que su metadata declara (tipo, longitud).

    Deliberadamente **no** se aplica a los editables preexistentes del 0100
    (3/22/37/41/49): esos ya tenian su propio contrato -sin esta validacion de
    forma- antes de este modulo existir, y endurecerlo ahora podria rechazar
    en la entrada un valor que la aplicacion ya aceptaba. Los opcionales son
    nuevos en esta iteracion: no hay comportamiento previo que romper, y sin
    esta validacion un valor con la longitud incorrecta llegaria al codec como
    un `ErrorDeCodificacion` generico en vez de un mensaje que nombre el campo.
    """
    politica = perfil.politica(mti)
    for numero, valor in campos_manuales.items():
        if politica.origen(numero) != "opcional" or not valor:
            continue
        metadato = metadatos.get(numero)
        if metadato is None:
            continue
        mensaje = metadato.validar_forma(valor)
        if mensaje is not None:
            raise CampoConFormaInvalida(mensaje)


def incompatibilidades_escenario(
    campos: Mapping[str, str], perfil, mti: str
) -> tuple[str, ...]:
    """Todo campo guardado que la politica actual ya no trata como editable.

    A diferencia de `validar_campos_manuales` -que revienta ante el primer
    campo fuera de lugar-, esto junta TODOS los problemas de una vez: un
    escenario incompatible se explica completo, no se descubre de a uno. Sirve
    para bloquear la carga/reejecucion de un escenario en vez de reinterpretar
    en silencio un campo que cambio de categoria (por ejemplo, si un editable
    pasara a ser automatico).
    """
    politica = perfil.politica(mti)
    problemas: list[str] = []
    for numero in sorted(campos, key=int):
        origen = politica.origen(numero)
        if origen not in ("editable", "opcional"):
            problemas.append(
                f"el campo {numero} ya no es editable ni opcional en el perfil actual (es {origen})"
            )
    return tuple(problemas)


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

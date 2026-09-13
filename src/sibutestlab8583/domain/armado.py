"""Construccion de mensajes ISO 8583: compra/autorizacion (0100), echo (0800)
y compra financiera (0200, B4).

Funciones puras: reciben los datos y devuelven el mensaje. El STAN y el
momento se inyectan en lugar de generarse aqui, para que las pruebas sean
deterministas y para que estas funciones no dependan del reloj.

CONSTRUCTOR GOBERNADO POR EL PERFIL
====================================
`campos_manuales` es la unica puerta para que el usuario fije un valor
distinto del default en un campo que el perfil declare editable para el MTI
(ver `PoliticaCamposMti` en `profiles/generico.py`). El armado se hace en
capas, cada una pudiendo pisar a la anterior, y la ultima —los campos
estructurales— gana siempre, sin excepcion, aunque la validacion previa
tuviera un defecto: es la defensa en profundidad de que ningun campo derivado
o automatico pueda terminar siendo el que el usuario escribio.

COMPOSICION, NO DUPLICACION (B2, 2026-09-12; ampliado B4, 2026-09-13)
====================================
`_componer_campos_base` es lo genuinamente comun entre operaciones -las
capas 1 y 2 (defaults del perfil + overrides del usuario), validadas contra
la politica del MTI-. Cada operacion (`armar_compra`, `armar_echo`,
`armar_compra_financiera`) le agrega SOLO su propia capa 3 estructural.

B4 confirmo que la capa 3 de compra (0100) y compra financiera (0200) es
IDENTICA -ambas derivan DE2/DE4/DE7/DE11-13/DE14 de tarjeta+monto+stan+
momento, porque ambas mueven fondos con una tarjeta elegida-, asi que esa
capa se extrajo a `_campos_estructurales_transaccion_con_tarjeta` en vez de
duplicarse una tercera vez; echo (sin tarjeta ni monto, solo DE7/DE11) sigue
sin compartirla porque genuinamente deriva de datos distintos. Ninguna de
las tres funciones `armar_*` es una funcion generica con banderas tipo
`armar(tipo, ...)`: ver `docs/roadmap/SIBU_3.md`, seccion de Fase B, para por
que se eligio esta forma y no `ClaveOperacion` ni un "mega builder".
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Mapping

from .campos_iso import MetadatoCampo
from .errores import CampoConFormaInvalida, CampoNoPermitido, CampoProtegido
from .modelos import (
    MTI_COMPRA,
    MTI_COMPRA_FINANCIERA,
    MTI_ECHO,
    DatosCompra,
    DatosCompraFinanciera,
    DatosEcho,
    MensajeIso,
    TarjetaPrueba,
)

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


def _componer_campos_base(
    campos_manuales: Mapping[str, str], perfil, mti: str
) -> dict[str, str]:
    """Capas 1+2: defaults del perfil, pisados por lo que el usuario haya
    fijado -ya validado contra la politica del MTI-. Comun a CUALQUIER
    operacion ISO 8583; la capa 3 (estructural) la agrega cada operacion
    segun lo que sepa derivar (ver docstring del modulo).
    """
    validar_campos_manuales(campos_manuales, perfil, mti)
    politica = perfil.politica(mti)
    campos = dict(politica.valores_por_defecto)
    campos.update(campos_manuales)
    return campos


def _campos_estructurales_transaccion_con_tarjeta(
    tarjeta: TarjetaPrueba, monto: Decimal, *, stan: str, momento: datetime
) -> dict[str, str]:
    """Capa 3 -estructural- comun a CUALQUIER operacion que mueva fondos con
    una tarjeta elegida del catalogo: compra/autorizacion (0100) y compra
    financiera (0200, B4) derivan EXACTAMENTE los mismos siete campos de los
    mismos cuatro datos (tarjeta, monto, stan, momento) -no es una
    coincidencia de redaccion, es el mismo concepto de dominio bajo dos MTI
    distintos-. Lo que SI difiere entre ambas operaciones es unicamente el
    MTI con el que se envuelve el resultado: eso lo decide cada `armar_*`,
    nunca esta funcion.

    Extraida en B4 recien cuando 0200 confirmo la duplicacion real -B2 ya
    habia mostrado con echo que compartir de mas (una funcion con banderas)
    es peor que un pequeno duplicado; esto es lo opuesto: un duplicado real,
    verificado, que ya no se justifica mantener dos veces-.
    """
    return {
        "2": tarjeta.pan,
        "4": formatear_monto(monto),
        "7": momento.strftime("%m%d%H%M%S"),
        "11": stan,
        "12": momento.strftime("%H%M%S"),
        "13": momento.strftime("%m%d"),
        "14": tarjeta.expiracion,
    }


def armar_compra(
    datos: DatosCompra,
    tarjeta: TarjetaPrueba,
    *,
    stan: str,
    momento: datetime,
    perfil,
) -> MensajeIso:
    """Arma el 0100 en tres capas, cada una pudiendo pisar a la anterior:

    1+2. `_componer_campos_base`: defaults del perfil, pisados por
    `datos.campos_manuales`.
    3. los campos estructurales —derivados de la tarjeta y automaticos del
       sistema—, que SIEMPRE ganan, sin excepcion.

    No valida RN-4: de eso se encarga esa regla inmediatamente despues, y
    separar ambas cosas permite armar un mensaje incompleto a proposito para
    probarla.
    """
    campos = _componer_campos_base(datos.campos_manuales, perfil, MTI_COMPRA)
    campos.update(
        _campos_estructurales_transaccion_con_tarjeta(
            tarjeta, datos.monto, stan=stan, momento=momento
        )
    )
    return MensajeIso(mti=MTI_COMPRA, campos=campos)


def armar_compra_financiera(
    datos: DatosCompraFinanciera,
    tarjeta: TarjetaPrueba,
    *,
    stan: str,
    momento: datetime,
    perfil,
) -> MensajeIso:
    """Arma el 0200 (compra financiera, B4) con el mismo patron de tres capas
    que `armar_compra` -capa 3 compartida vía
    `_campos_estructurales_transaccion_con_tarjeta`, capas 1+2 y el MTI final
    son lo unico propio de esta operacion-.

    No valida RN-4: igual que `armar_compra`/`armar_echo`, esa regla corre
    inmediatamente despues.
    """
    campos = _componer_campos_base(datos.campos_manuales, perfil, MTI_COMPRA_FINANCIERA)
    campos.update(
        _campos_estructurales_transaccion_con_tarjeta(
            tarjeta, datos.monto, stan=stan, momento=momento
        )
    )
    return MensajeIso(mti=MTI_COMPRA_FINANCIERA, campos=campos)


def armar_echo(
    datos: DatosEcho,
    *,
    stan: str,
    momento: datetime,
    perfil,
) -> MensajeIso:
    """Arma el 0800 (Network Management/Echo) en tres capas -mismo principio
    que `armar_compra`, sin tarjeta ni monto porque un echo no los tiene-:

    1+2. `_componer_campos_base`: defaults del perfil (DE70) pisados por
    `datos.campos_manuales`.
    3. los campos estructurales -DE7/DE11, automaticos del sistema-, que
       SIEMPRE ganan.

    No valida RN-4: igual que `armar_compra`, esa regla corre inmediatamente
    despues.
    """
    campos = _componer_campos_base(datos.campos_manuales, perfil, MTI_ECHO)
    campos.update(
        {
            "7": momento.strftime("%m%d%H%M%S"),
            "11": stan,
        }
    )
    return MensajeIso(mti=MTI_ECHO, campos=campos)

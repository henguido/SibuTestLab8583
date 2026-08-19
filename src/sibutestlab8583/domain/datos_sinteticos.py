"""Generacion de numeros de tarjeta sinteticos en tiempo de ejecucion.

Politica del repositorio y su justificacion
==========================================

1. **Ningun PAN completo, real o sintetico, aparece como literal en archivos
   versionados.** Un literal con largo de tarjeta es indistinguible de uno real
   para un escaner de secretos, para una auditoria y para quien lea el
   repositorio por primera vez. Que sea inventado lo sabe quien lo escribio, no
   quien lo encuentra.
2. **Los PAN sinteticos se generan en ejecucion**, aqui, a partir de un sufijo
   corto. En Git nunca queda la secuencia completa.
3. **Los datos sinteticos son exclusivamente para la demostracion y el host
   simulado.** No representan ni sustituyen a una tarjeta de pago utilizable.
4. **Las tarjetas de QA reales provienen del ambiente autorizado de la
   institucion** y se almacenan unicamente de forma local, en el archivo SQLite
   que no se versiona.
5. **Nunca se atribuye un PAN sintetico a Visa, a Mastercard ni a ningun rango
   oficialmente reservado**, y no se afirma que el prefijo elegido este libre:
   los rangos de identificador emisor tienen asignaciones nacionales y no es una
   propiedad que este proyecto pueda garantizar.

La propiedad obligatoria es la primera. Como refuerzo adicional, los numeros
generados aqui se construyen para que **no superen la verificacion de Luhn**, de
modo que ningun sistema que valide el digito verificador los acepte como tarjeta.
Eso es comprobable y no depende de suposiciones sobre rangos de emisor.
"""

from __future__ import annotations

LONGITUD_PAN_POR_DEFECTO = 16
DIGITO_RELLENO = "9"
LONGITUD_MINIMA = 12
LONGITUD_MAXIMA = 19


def es_luhn_valido(numero: str) -> bool:
    """Indica si ``numero`` supera la verificacion de Luhn."""
    if not numero.isdigit():
        return False
    total = 0
    for posicion, caracter in enumerate(reversed(numero)):
        digito = int(caracter)
        if posicion % 2 == 1:
            digito *= 2
            if digito > 9:
                digito -= 9
        total += digito
    return total % 10 == 0


def pan_sintetico(
    sufijo: str,
    *,
    longitud: int = LONGITUD_PAN_POR_DEFECTO,
    relleno: str = DIGITO_RELLENO,
) -> str:
    """Construye un numero sintetico de ``longitud`` digitos terminado en ``sufijo``.

    El resultado **nunca supera la verificacion de Luhn**: si el relleno uniforme
    produjera por casualidad un numero valido, se ajusta un digito del relleno
    hasta que deje de serlo. El sufijo se respeta siempre, para que la
    representacion enmascarada siga siendo reconocible en las pruebas.

    Es determinista: el mismo sufijo produce siempre el mismo numero.
    """
    if not sufijo.isdigit():
        raise ValueError(f"el sufijo debe ser numerico: {sufijo!r}")
    if not LONGITUD_MINIMA <= longitud <= LONGITUD_MAXIMA:
        raise ValueError(f"longitud fuera de rango: {longitud}")
    if len(sufijo) >= longitud:
        raise ValueError("el sufijo no puede ocupar el numero completo")
    if len(relleno) != 1 or not relleno.isdigit():
        raise ValueError(f"el relleno debe ser un unico digito: {relleno!r}")

    numero = relleno * (longitud - len(sufijo)) + sufijo
    if not es_luhn_valido(numero):
        return numero

    # Cambiar un digito del relleno rompe el digito verificador sin tocar el
    # sufijo. Siempre existe al menos un candidato invalido.
    for candidato in "0123456789":
        propuesta = candidato + numero[1:]
        if not es_luhn_valido(propuesta):
            return propuesta
    raise AssertionError("no se pudo construir un numero invalido segun Luhn")


def monto_iso(unidades_minimas: str, *, longitud: int = 12) -> str:
    """Formatea un monto para el campo 4, rellenando con ceros a la izquierda.

    Existe para que las pruebas no necesiten escribir un literal de doce digitos.
    """
    if not unidades_minimas.isdigit():
        raise ValueError(f"el monto debe ser numerico: {unidades_minimas!r}")
    return unidades_minimas.rjust(longitud, "0")

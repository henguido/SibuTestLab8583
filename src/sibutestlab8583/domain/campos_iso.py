"""Metadata universal de un campo ISO 8583, para que la UI la interprete.

Esta es la pieza que faltaba junto a las otras dos que ya existian:

- ``especificacion`` (``profiles/generico.py::ESPECIFICACION_GENERICA``) es lo
  que consume ``pyiso8583`` tal cual (``data_enc``/``len_enc``/``max_len``):
  codificacion binaria, no producto.
- ``PoliticaCamposMti`` es quien puede fijar cada campo (derivado/automatico/
  editable/opcional/no_permitido): gobierno, no descripcion.
- ``MetadatoCampo`` (este modulo) es como se describe un campo a un humano y
  como validar la FORMA de lo que escribe -tipo, longitud, ayuda-, para que
  agregar un campo nuevo al catalogo de opcionales no obligue a escribir HTML
  ni Python especifico para ese numero en ninguna pantalla.

Puro: sin red, sin base de datos, sin pyiso8583. No decide reglas de negocio
(eso es domain/validacion.py); solo describe la forma esperada de un valor.
"""

from __future__ import annotations

from dataclasses import dataclass

#: Solo digitos.
TIPO_NUMERICO = "numerico"
#: Letras, digitos y algunos simbolos comunes (nombre de comercio, referencia).
TIPO_ALFANUMERICO = "alfanumerico"


@dataclass(frozen=True)
class MetadatoCampo:
    """Descripcion de un campo para la UI y para su validacion de forma.

    ``longitud_fija`` distingue un campo de largo exacto (``_fijo`` en
    ``profiles/generico.py``) de uno LLVAR de largo maximo variable (``_llvar``):
    el primero exige exactamente ``longitud_maxima`` caracteres si se informa;
    el segundo admite hasta esa cantidad.
    """

    numero: str
    nombre_corto: str
    descripcion: str
    tipo: str
    longitud_fija: bool
    longitud_maxima: int
    sensible: bool
    ayuda: str = ""

    def validar_forma(self, valor: str) -> str | None:
        """Mensaje de error especifico, o `None` si el valor tiene forma valida.

        No valida obligatoriedad -un valor vacio no es asunto de este metodo,
        eso lo decide quien orquesta la validacion segun si el campo es
        requerido en este envio-, solo la forma de lo que SI se informo.
        """
        if self.tipo == TIPO_NUMERICO and not valor.isdigit():
            return f"DE{self.numero} ({self.nombre_corto}) debe contener solo dígitos."
        if self.longitud_fija and len(valor) != self.longitud_maxima:
            return (
                f"DE{self.numero} ({self.nombre_corto}) debe contener exactamente "
                f"{self.longitud_maxima} caracteres."
            )
        if not self.longitud_fija and len(valor) > self.longitud_maxima:
            return (
                f"DE{self.numero} ({self.nombre_corto}) admite hasta "
                f"{self.longitud_maxima} caracteres."
            )
        return None

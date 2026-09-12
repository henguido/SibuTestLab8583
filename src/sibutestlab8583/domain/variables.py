"""Variables dinamicas en campos manuales del 0100 (Fase A, entrega minima).

DECISION DE DISENO (aprobada antes de implementar, ver BITACORA):

Una variable dinamica NO es un mecanismo nuevo de armado del mensaje: es una
fuente de valor adicional para exactamente el mismo lugar donde hoy entra un
literal (`DatosCompra.campos_manuales`). Se resuelve ANTES de `armar_compra`
-nunca dentro de ese modulo, que sigue sin saber que las variables existen-,
en el orquestador y en la vista previa, en el mismo punto donde ya se conoce
el STAN y el momento reales de esa ejecucion.

Alcance de esta primera entrega (deliberadamente pequeno, ver PROYECTO.md):
solo cinco variables built-in, sin namespace, sin variables de usuario, sin
`{{previous.*}}` (reservado para un futuro motor de secuencias, todavia sin
diseno de implementacion). Nada de esto evalua codigo Python: la resolucion
es una tabla de busqueda cerrada (`_VARIABLES_BUILTIN`), nunca `eval`/`exec`,
nunca acceso a filesystem ni a variables de entorno.

Gramatica exacta: `{{` + espacios opcionales + identificador en minusculas
+ espacios opcionales + `}}`, y nada mas -sin anidamiento, sin aritmetica,
sin filtros, sin mezclar con texto literal en el mismo campo-. La gramatica
decide esto de forma EXPLICITA, no por omision: un valor que contenga
`{{`/`}}` en alguna parte pero no calce la forma completa (`ABC{{stan}}`,
`{{stan}}XYZ`, `{{stan}` sin cerrar, `{{}}` vacio) es un ERROR
(`ExpresionMalformada`), nunca un literal silencioso ni una interpolacion
parcial: en un campo que viaja a un mensaje de pago, adivinar la intencion
de un valor a medio escribir es peor que rechazarlo. Un valor que no
contiene NINGUNA llave doble sí se trata como literal sin tocarlo (ver
`resolver_valor`) -asi que un ataque tipo `${HOME}` o `{% ... %}`, que no usa
la gramatica `{{...}}` en absoluto, ni siquiera entra a resolucion-.

LIMITE DE ALCANCE VERIFICADO (auditoria previa a la integracion): las
variables solo se resuelven en los dos puntos que las invocan explicitamente
-`application/orquestador.py::ejecutar_compra` y
`application/vista_previa.py::ServicioVistaPrevia.construir`-. Dos
consecuencias, ambas deliberadas para esta primera entrega:

1. Un CAMPO EDITABLE (3/22/37/41/49 en el perfil generico) admite una
   expresion sin problema, porque la capa web NO valida forma sobre los
   editables preexistentes (`domain/armado.py::validar_forma_de_opcionales`
   lo excluye a proposito). Un CAMPO OPCIONAL (18/25/32/42/43) SI pasa por
   esa validacion de forma en la capa web, sobre el valor SIN resolver, antes
   de llegar aqui: hoy una expresion en un opcional se rechaza con
   `CampoConFormaInvalida` en vez de resolverse. Extender variables a
   opcionales queda para un incremento posterior, no para esta entrega.
2. `application/escenarios.py::valores_efectivos_editables` CONGELA la
   expresion tal cual (`"{{stan}}"`), nunca un valor ya resuelto: un
   escenario guardado con una variable la reevalua en cada reejecucion, no
   queda fijado al primer STAN que tuvo. Verificado con
   `test_valores_efectivos_editables_congela_la_expresion_sin_resolverla` en
   `tests/test_variables.py`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Mapping

from .armado import formatear_monto
from .errores import ExpresionMalformada, VariableDesconocida

_PATRON_EXPRESION = re.compile(r"^\{\{\s*([a-z][a-z0-9_]*)\s*\}\}$")


@dataclass(frozen=True)
class ContextoResolucion:
    """Todo lo que una variable built-in puede necesitar leer. Cerrado a
    proposito: agregar una variable nueva exige agregar un campo aqui y su
    resolutor en `_VARIABLES_BUILTIN`, nunca un acceso generico "leer
    cualquier atributo".
    """

    monto: Decimal
    stan: str
    momento: datetime


#: Variables cuyo valor depende del STAN o del momento de ESTA ejecucion
#: concreta: en una vista previa (que usa un STAN/momento marcador, ver
#: `application/vista_previa.py`) el valor mostrado NO es el que se
#: transmitira de verdad. `amount` no esta aqui: el monto no cambia entre
#: previsualizar y ejecutar.
VARIABLES_NO_REPRODUCIBLES = frozenset(
    {"stan", "transmission_datetime", "local_time", "local_date"}
)

_VARIABLES_BUILTIN = {
    "amount": lambda ctx: formatear_monto(ctx.monto),
    "stan": lambda ctx: ctx.stan,
    "transmission_datetime": lambda ctx: ctx.momento.strftime("%m%d%H%M%S"),
    "local_time": lambda ctx: ctx.momento.strftime("%H%M%S"),
    "local_date": lambda ctx: ctx.momento.strftime("%m%d"),
}


def es_expresion(valor: str) -> bool:
    """True si `valor` -el campo COMPLETO, no un fragmento- es una variable."""
    return bool(_PATRON_EXPRESION.match(valor))


def resolver_valor(valor: str, contexto: ContextoResolucion) -> str:
    """Si `valor` es una expresion `{{...}}`, devuelve el valor resuelto.

    Un literal (incluido uno que por casualidad contenga las llaves sin
    calzar la forma completa) se devuelve tal cual, sin tocarlo -mismo
    criterio que hoy aplica cualquier valor de `campos_manuales`-.
    """
    if "{{" not in valor and "}}" not in valor:
        return valor
    coincidencia = _PATRON_EXPRESION.match(valor)
    if coincidencia is None:
        raise ExpresionMalformada(
            f"la expresión {valor!r} no tiene una forma válida de variable"
        )
    nombre = coincidencia.group(1)
    resolutor = _VARIABLES_BUILTIN.get(nombre)
    if resolutor is None:
        raise VariableDesconocida(f"la variable {nombre!r} no existe")
    return resolutor(contexto)


def resolver_campos_manuales(
    campos_manuales: Mapping[str, str], contexto: ContextoResolucion
) -> tuple[dict[str, str], frozenset[str]]:
    """Devuelve `(campos_resueltos, numeros_no_reproducibles)`.

    `campos_resueltos` tiene la MISMA forma que `campos_manuales` -un literal
    entra y sale identico-, con toda expresion sustituida por su valor.
    `numeros_no_reproducibles` es el subconjunto de campos cuyo valor
    resuelto depende de `VARIABLES_NO_REPRODUCIBLES`: la vista previa lo usa
    para no presentar ese valor como definitivo (ver
    `application/vista_previa.py::CampoVistaPrevia.es_valor_definitivo`).
    """
    resueltos: dict[str, str] = {}
    no_reproducibles: set[str] = set()
    for numero, valor in campos_manuales.items():
        if es_expresion(valor):
            nombre = _PATRON_EXPRESION.match(valor).group(1)  # type: ignore[union-attr]
            if nombre in VARIABLES_NO_REPRODUCIBLES:
                no_reproducibles.add(numero)
        resueltos[numero] = resolver_valor(valor, contexto)
    return resueltos, frozenset(no_reproducibles)

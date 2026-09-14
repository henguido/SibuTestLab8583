"""Referencias entre pasos de una secuencia (Fase C2): `{{step.<id>...}}`.

EXTIENDE LA GRAMATICA DE FASE A, NO LA DUPLICA
================================================
Misma convencion de `domain/variables.py`: `{{` + expresion + `}}`, todo el
campo o nada -sin mezclar con texto literal, sin anidamiento-, y un valor
que contiene `{{`/`}}` pero no calza ninguna forma reconocida es un ERROR
explicito, nunca un literal silencioso ni una interpolacion parcial.

Vive en `application/`, no en `domain/variables.py`: resolver una referencia
de paso necesita leer una `Ejecucion` ya persistida (via un puerto) y
reinterpretar su mensaje (`application.serializacion.interpretar`), ambos
conceptos de la capa de aplicacion -el dominio no puede depender de ellos
sin invertir la direccion de dependencia del proyecto (mismo motivo que
`application/armado_reverso.py` vive aqui y no en `domain/armado.py`, B7).

Por eso esta gramatica es un SEGUNDO RECONOCEDOR, no una extension del
regex de `domain/variables.py::_PATRON_EXPRESION`: las dos conviven porque
resuelven en DOS MOMENTOS distintos del flujo, nunca en el mismo campo a la
vez (un campo es una expresion o la otra, jamas ambas). `EjecutorDeSecuencia`
resuelve las referencias de paso ANTES de tocar el orquestador, dejando un
valor YA LITERAL; el orquestador (armar_compra/armar_compra_financiera via
domain/variables.py) sigue resolviendo `{{stan}}`/`{{amount}}`/etc. exactamente
como siempre, sin saber que "step.*" existe.

SINTAXIS (decidida para C2, no litigada por gusto)
====================================================
    {{step.<paso_id>.request.<deNN>}}    campo tal como se ENVIO en ese paso
    {{step.<paso_id>.response.<deNN>}}   campo tal como VOLVIO en la respuesta
    {{step.<paso_id>.execution_id}}      metadata interna de Sibu (el id de
                                          fila de `ejecuciones`), NUNCA un
                                          valor ISO -namespace separado a
                                          proposito (punto 6 del checkpoint)-

`paso_id` es el identificador ESTABLE de un paso (`PasoSecuencia.paso_id`,
C2), nunca su `orden`: si la secuencia se reordena en el futuro, la
referencia sigue apuntando al paso correcto. `request`/`response` son
namespaces obligatorios y EXCLUYENTES -nunca ambiguo de donde sale un
valor (punto 7)-. `deNN` es el numero de campo ISO en minusculas
(`de38`, `de37`, ...), nunca un nombre de negocio.

SEGURIDAD
=========
Ningun campo sensible (`domain.modelos.CAMPOS_SENSIBLES` o
`perfil.es_sensible()`) puede referenciarse NUNCA, este presente o no en el
mensaje: se revienta ANTES de intentar leerlo (`CampoDeEjecucionSensible`).
Nunca se usa una lista nueva de campos prohibidos: la misma autoridad de
sensibilidad ya consolidada en B3/B6/B7.
"""

from __future__ import annotations

import re

from ..domain.errores import (
    CampoDeEjecucionNoDisponible,
    CampoDeEjecucionSensible,
    ExpresionDePasoMalformada,
    MetadataDeEjecucionDesconocida,
    PasoDeSecuenciaNoEjecutado,
)
from ..domain.modelos import Expectativas, ExpectativaCampo
from ..domain.puertos import RepositorioEjecuciones
from .contexto_secuencia import ContextoSecuencia
from .serializacion import interpretar

#: Claves de la especificacion que no son campos ISO reales (cabecera,
#: tipo de mensaje, bitmaps): nunca referenciables aunque "existan" en el
#: diccionario de especificacion.
_CLAVES_NO_REFERENCIABLES = frozenset({"h", "t", "p", "1"})

_PATRON_CAMPO = re.compile(
    r"^\{\{\s*step\.([a-z][a-z0-9_]*)\.(request|response)\.de([0-9]+)\s*\}\}$"
)
_PATRON_METADATA = re.compile(r"^\{\{\s*step\.([a-z][a-z0-9_]*)\.execution_id\s*\}\}$")
#: Heuristica para distinguir "no es nuestra" de "parece nuestra pero mal
#: escrita" -mismo criterio que `domain.variables.resolver_valor` aplica
#: para `{{`/`}}` sueltos: no se adivina la intencion de algo a medio
#: escribir, se rechaza explicitamente.
_PARECE_REFERENCIA_DE_PASO = re.compile(r"\{\{\s*step\.")


def es_referencia_de_paso(valor: str) -> bool:
    """True si `valor` -el campo COMPLETO- es una referencia de paso valida."""
    return bool(_PATRON_CAMPO.match(valor) or _PATRON_METADATA.match(valor))


def paso_id_referenciado(valor: str) -> str | None:
    """El `paso_id` que una referencia de paso VALIDA menciona, o `None` si
    `valor` no es una. Existe para que `ServicioSecuencias` pueda validar,
    al GUARDAR la definicion (nunca en ejecucion), que la referencia
    apunte a un paso que existe y es estrictamente ANTERIOR -ver punto 10
    del checkpoint C2-, sin necesitar resolver el valor de verdad todavia.
    """
    coincidencia = _PATRON_CAMPO.match(valor) or _PATRON_METADATA.match(valor)
    return coincidencia.group(1) if coincidencia else None


def parece_referencia_de_paso_malformada(valor: str) -> bool:
    """True si `valor` menciona `{{step.` pero no calza ninguna forma
    reconocida -nunca se trata como literal ni se interpola a medias."""
    return bool(_PARECE_REFERENCIA_DE_PASO.search(valor)) and not es_referencia_de_paso(valor)


async def resolver_referencia_de_paso(
    valor: str,
    contexto: ContextoSecuencia,
    repositorio_ejecuciones: RepositorioEjecuciones,
    perfil,
) -> str:
    """Resuelve una referencia `{{step...}}` ya confirmada como valida
    (`es_referencia_de_paso(valor)` es `True`). Revienta con un error de
    dominio claro y especifico -nunca `KeyError`, nunca cadena vacia- para
    cada precondicion que falle (punto 18 del checkpoint).
    """
    coincidencia_metadata = _PATRON_METADATA.match(valor)
    if coincidencia_metadata:
        paso_id = coincidencia_metadata.group(1)
        ejecucion_id = contexto.ejecucion_id_de_paso_id(paso_id)
        if ejecucion_id is None:
            raise PasoDeSecuenciaNoEjecutado(
                f"el paso {paso_id!r} no produjo ninguna ejecución en esta corrida"
            )
        return str(ejecucion_id)

    coincidencia = _PATRON_CAMPO.match(valor)
    assert coincidencia is not None  # garantizado por es_referencia_de_paso()
    paso_id, namespace, numero = coincidencia.group(1), coincidencia.group(2), coincidencia.group(3)

    # La sensibilidad se comprueba PRIMERO y siempre -aunque el campo ni
    # siquiera este declarado en la especificacion de este perfil-: es un
    # piso universal de dominio (domain.modelos.CAMPOS_SENSIBLES), nunca
    # condicionado a que un perfil concreto lo reconozca.
    if perfil.es_sensible(numero):
        raise CampoDeEjecucionSensible(
            f"el campo DE{numero} es sensible: no puede referenciarse entre pasos"
        )
    if numero in _CLAVES_NO_REFERENCIABLES or numero not in perfil.especificacion:
        raise MetadataDeEjecucionDesconocida(f"el campo DE{numero} no existe en el perfil activo")

    ejecucion_id = contexto.ejecucion_id_de_paso_id(paso_id)
    if ejecucion_id is None:
        raise PasoDeSecuenciaNoEjecutado(
            f"el paso {paso_id!r} no produjo ninguna ejecución en esta corrida"
        )
    ejecucion = await repositorio_ejecuciones.obtener(ejecucion_id)
    if ejecucion is None:
        raise PasoDeSecuenciaNoEjecutado(
            f"la ejecución del paso {paso_id!r} ya no existe"
        )

    if namespace == "request":
        mensaje = interpretar(ejecucion.solicitud_json, ejecucion.solicitud_enmascarada)
    else:
        mensaje = interpretar(ejecucion.respuesta_json, ejecucion.respuesta_enmascarada)

    valor_campo = mensaje.valor(numero)
    if valor_campo is None:
        raise CampoDeEjecucionNoDisponible(
            f"el paso {paso_id!r} no tiene DE{numero} en su {namespace}"
        )
    return valor_campo


async def resolver_expectativas_de_paso(
    expectativas: Expectativas | None,
    contexto: ContextoSecuencia,
    repositorio_ejecuciones: RepositorioEjecuciones,
    perfil,
) -> tuple[Expectativas | None, tuple[tuple[str, str, str], ...]]:
    """Expectativas dinamicas (C3, 2026-09-14, punto 12 del checkpoint): un
    VALOR ESPERADO puede depender de la respuesta de un paso anterior -
    `{{step.purchase.response.de38}}` como `ExpectativaCampo.valor`-, usando
    el MISMO motor de arriba, nunca un lenguaje nuevo. Solo aplica a
    `PasoSecuencia.expectativas` (paso DERIVADO): un paso independiente
    sigue tomando sus expectativas del ESCENARIO, que es reusable fuera de
    cualquier secuencia y por eso nunca resuelve `{{step...}}` (ver
    `domain.modelos.PasoSecuencia`, docstring de `expectativas`).

    Se llama DESPUES de que el paso de origen ya tiene su respuesta
    persistida, pero ANTES de evaluar la respuesta de ESTE paso -simetrico a
    `EjecutorDeSecuencia._resolver_referencias_de_paso`, que resuelve
    `campos_manuales` ANTES de enviar, nunca en el mismo momento.

    Devuelve la `Expectativas` con cada valor dinamico YA resuelto a un
    literal -la definicion de la secuencia sigue guardando la EXPRESION,
    nunca el valor resuelto, misma filosofia que Fase A/C2- mas una tupla
    `(numero, expresion, valor_resuelto)` por cada campo que si era dinamico,
    para que quien llama pueda dejar constancia de auditoria (punto 14:
    expresion Y valor efectivo, nunca solo uno de los dos).

    Puede lanzar las mismas excepciones que `resolver_referencia_de_paso`
    (incluida `CampoDeEjecucionSensible`: DE2/DE35/DE45 tampoco pueden
    referenciarse aqui, ni siquiera solo para comparar) y
    `ExpresionDePasoMalformada` si algun valor "parece" una referencia de
    paso pero no calza ninguna forma reconocida.
    """
    if expectativas is None or not expectativas.campos:
        return expectativas, ()

    campos_resueltos: dict[str, ExpectativaCampo] = {}
    resoluciones: list[tuple[str, str, str]] = []
    for numero, campo in expectativas.campos.items():
        valor = campo.valor
        if valor is not None and es_referencia_de_paso(valor):
            valor_resuelto = await resolver_referencia_de_paso(
                valor, contexto, repositorio_ejecuciones, perfil
            )
            campos_resueltos[numero] = ExpectativaCampo(tipo=campo.tipo, valor=valor_resuelto)
            resoluciones.append((numero, valor, valor_resuelto))
        elif valor is not None and parece_referencia_de_paso_malformada(valor):
            raise ExpresionDePasoMalformada(
                f"la expectativa del campo {numero} tiene una referencia de paso con forma "
                f"invalida: {valor!r}"
            )
        else:
            campos_resueltos[numero] = campo

    if not resoluciones:
        return expectativas, ()
    return Expectativas(estado=expectativas.estado, campos=campos_resueltos), tuple(resoluciones)

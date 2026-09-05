"""Expected vs actual: si una ejecucion cumplio la expectativa de su escenario.

Funcion **pura**: solo tipos de dominio (`Expectativas`, `EstadoEjecucion`,
`MensajeInterpretado`), sin codec, sin web, sin persistencia. Mismo espiritu
que `domain/validacion.py` -no depende de como se armo ni de como se va a
mostrar, solo compara lo que ya se resolvio.

No reemplaza RN-1/RN-3: las reutiliza. `EstadoEjecucion` ya es el resultado de
aplicarlas (catalogo configurado + correlacion); una expectativa de `estado`
compara contra ESE resultado, nunca contra un codigo fijo. Una expectativa de
campo, en cambio, es deliberadamente literal: compara el valor concreto que
llego, sin pasar por ningun catalogo. Las dos pueden coexistir y discrepar
entre si -eso no es un error, es exactamente lo que permite distinguir
"la transaccion fue aprobada" de "vino con el codigo exacto que yo esperaba".
"""

from __future__ import annotations

from typing import Mapping

from .modelos import (
    CAMPOS_SENSIBLES,
    DiscrepanciaExpectativa,
    EstadoEjecucion,
    EstadoEvaluacion,
    ExpectativaCampo,
    Expectativas,
    MensajeInterpretado,
    ResultadoEvaluacion,
)

#: Version del formato de expectativas/evaluacion en `expected_json` y
#: `evaluacion_json`. Independiente de `VERSION_CAMPOS_ESCENARIO` (que
#: versiona `campos_json`, una plantilla de entrada) y de
#: `application.serializacion.VERSION_FORMATO` (que versiona un mensaje ISO ya
#: armado): son tres formatos distintos, con ciclos de evolucion propios.
VERSION_EXPECTATIVAS = 1

#: Tipos de expectativa de campo soportados en este bloque. Deliberadamente
#: solo estos tres -nada de regex, rangos, "contains" ni comparadores
#: numericos: eso queda fuera de alcance hasta que un bloque futuro lo pida.
TIPOS_EXPECTATIVA_CAMPO = frozenset({"igual", "presente", "ausente"})


def campos_permitidos_expectativa(perfil, mti: str) -> frozenset[str]:
    """Que campos de una respuesta se pueden usar en una expectativa.

    La fuente de verdad es `perfil.especificacion`: es la unica abstraccion
    real que ya existe para "que campos permite este perfil" -el proyecto no
    modela un conjunto de campos opcionales por MTI aparte de los
    obligatorios, y restringir a `obligatorios()` dejaria fuera cualquier
    campo opcional legitimo que un switch real pudiera devolver-. Se excluyen
    siempre los campos sensibles, sin excepcion, y nada si el perfil no
    soporta el MTI.
    """
    if not perfil.soporta(mti):
        return frozenset()
    return frozenset(n for n in perfil.especificacion if n.isdigit()) - CAMPOS_SENSIBLES


def validar_expectativas(expectativas: Expectativas, perfil, mti_respuesta: str) -> None:
    """Revienta si `expectativas` referencia un campo no permitido o un tipo
    desconocido. Defensa en profundidad: se llama tanto al guardar un
    escenario como, de nuevo, dentro de la evaluacion misma.
    """
    permitidos = campos_permitidos_expectativa(perfil, mti_respuesta)
    for numero, expectativa in expectativas.campos.items():
        if numero not in permitidos:
            raise ValueError(
                f"el campo {numero} no esta permitido en una expectativa para el MTI "
                f"{mti_respuesta}"
            )
        if expectativa.tipo not in TIPOS_EXPECTATIVA_CAMPO:
            raise ValueError(f"tipo de expectativa desconocido: {expectativa.tipo!r}")
        if expectativa.tipo == "igual" and expectativa.valor is None:
            raise ValueError(f"el campo {numero} es 'igual' pero no trae valor")


def incompatibilidades_expectativas(expectativas: Expectativas, perfil, mti_respuesta: str) -> tuple[str, ...]:
    """Todo campo esperado que la politica/especificacion actual ya no permite.

    Mismo principio que `domain.armado.incompatibilidades_escenario`: junta
    todos los problemas de una vez, para bloquear la carga/reejecucion con el
    motivo explicado en vez de reinterpretar en silencio.
    """
    permitidos = campos_permitidos_expectativa(perfil, mti_respuesta)
    problemas = []
    for numero in sorted(expectativas.campos, key=int):
        if numero not in permitidos:
            problemas.append(
                f"el campo {numero} ya no esta permitido en una expectativa para el perfil actual"
            )
    return tuple(problemas)


def evaluar_expectativas(
    expectativas: Expectativas | None,
    estado_real: EstadoEjecucion,
    respuesta: MensajeInterpretado | None,
) -> ResultadoEvaluacion | None:
    """Compara una ejecucion contra la expectativa de su escenario.

    Devuelve `None` -no un `ResultadoEvaluacion` "aprobado"- cuando no hay
    expectativas: la ausencia de expectativa nunca es un PASS implicito.

    Si `respuesta` es `None` (timeout, error de conexion o transmision, o no
    enviada), toda expectativa de campo `presente`/`igual` falla porque no hay
    nada que encontrar, y `ausente` pasa porque, en efecto, no vino. La
    expectativa de `estado` se compara igual que siempre: un escenario que
    espera `timeout` y obtiene `timeout` pasa, sin ningun caso especial.

    No depende de que `respuesta` este enmascarada o no -es agnostico a esa
    decision-: quien llama (`Orquestador._registrar`) elige pasar la version
    ya enmascarada por prudencia, pero esta funcion solo mira los numeros de
    campo que la propia `expectativas` declara, nunca "todos los campos que
    lleguen", asi que un campo sensible no declarado en la expectativa jamas
    se toca ni se serializa.
    """
    if expectativas is None:
        return None

    discrepancias: list[DiscrepanciaExpectativa] = []

    if expectativas.estado is not None and expectativas.estado != estado_real:
        discrepancias.append(
            DiscrepanciaExpectativa(
                criterio="estado",
                campo=None,
                tipo=None,
                esperado=expectativas.estado.value,
                recibido=estado_real.value,
            )
        )

    campos_respuesta: Mapping[str, object] = respuesta.campos if respuesta is not None else {}
    for numero in sorted(expectativas.campos, key=int):
        expectativa = expectativas.campos[numero]
        campo = campos_respuesta.get(numero)
        valor_recibido = campo.valor if campo is not None else None

        if expectativa.tipo == "presente":
            if campo is None:
                discrepancias.append(
                    DiscrepanciaExpectativa("campo", numero, "presente", None, None)
                )
        elif expectativa.tipo == "ausente":
            if campo is not None:
                discrepancias.append(
                    DiscrepanciaExpectativa("campo", numero, "ausente", None, valor_recibido)
                )
        elif expectativa.tipo == "igual":
            if valor_recibido != expectativa.valor:
                discrepancias.append(
                    DiscrepanciaExpectativa(
                        "campo", numero, "igual", expectativa.valor, valor_recibido
                    )
                )

    estado_evaluacion = EstadoEvaluacion.FAIL if discrepancias else EstadoEvaluacion.PASS
    return ResultadoEvaluacion(estado=estado_evaluacion, discrepancias=tuple(discrepancias))


def expectativas_a_dict(expectativas: Expectativas) -> dict:
    """`Expectativas` -> forma JSON-friendly. Formato de `expected_json`."""
    return {
        "version": VERSION_EXPECTATIVAS,
        "estado": expectativas.estado.value if expectativas.estado else None,
        "campos": {
            numero: {"tipo": e.tipo, "valor": e.valor}
            for numero, e in expectativas.campos.items()
        },
    }


def expectativas_desde_dict(datos: Mapping) -> Expectativas:
    """Inverso de `expectativas_a_dict`. No valida version: eso es
    responsabilidad de quien la lea de una fuente que pueda tener un formato
    mas nuevo (no aplica todavia, con `VERSION_EXPECTATIVAS` unico en 1).
    """
    estado_bruto = datos.get("estado")
    campos_brutos = datos.get("campos") or {}
    return Expectativas(
        estado=EstadoEjecucion(estado_bruto) if estado_bruto else None,
        campos={
            numero: ExpectativaCampo(tipo=c["tipo"], valor=c.get("valor"))
            for numero, c in campos_brutos.items()
        },
    )


def discrepancia_a_dict(discrepancia: DiscrepanciaExpectativa) -> dict:
    return {
        "criterio": discrepancia.criterio,
        "campo": discrepancia.campo,
        "tipo": discrepancia.tipo,
        "esperado": discrepancia.esperado,
        "recibido": discrepancia.recibido,
    }


def evaluacion_a_dict(expectativas: Expectativas, resultado: ResultadoEvaluacion) -> dict:
    """El snapshot completo para `evaluacion_json`: expectativa ORIGINAL +
    resultado + discrepancias. Nunca una referencia al escenario -esto es lo
    que una ejecucion historica conserva para siempre, aunque el escenario se
    edite despues-.
    """
    return {
        "version": VERSION_EXPECTATIVAS,
        "resultado": resultado.estado.value,
        "expectativas": expectativas_a_dict(expectativas),
        "discrepancias": [discrepancia_a_dict(d) for d in resultado.discrepancias],
    }

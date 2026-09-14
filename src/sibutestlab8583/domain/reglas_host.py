"""Reglas declarativas del Host Simulado (Fase D1, 2026-09-14).

OBJETIVO: reemplazar el comportamiento HOY mayormente fijo de `HostSimulado`
(`adapters/host_simulado/servidor.py::_construir_respuesta`, un `if/elif`
hardcodeado por MTI mas un umbral sintetico de rechazo) por un conjunto de
`ReglaHost` ordenadas por prioridad, evaluadas en orden hasta la primera
coincidencia -sin pesos, sin "mas especifica gana", determinista-.

LAS REGLAS SON DATOS, NUNCA CODIGO
===================================
Prohibido explicitamente (investigado, no una lista de cortesia): `eval`,
`exec`, cualquier interprete embebido, expresiones booleanas arbitrarias,
acceso a filesystem/environment. Una `ReglaHost` es un dataclass inmutable;
evaluarla es comparar strings/`Decimal`, nunca ejecutar texto. El unico
lenguaje "dinamico" permitido es un conjunto CERRADO de generadores
(`GeneradorValor`), nunca una expresion de template general.

MISMO VOCABULARIO QUE `Expectativas`, NO UNO NUEVO
====================================================
`OperadorCondicion` reutiliza literalmente `igual`/`presente`/`ausente` de
`ExpectativaCampo` (`domain.modelos`) y agrega SOLO `distinto`/`mayor_que`/
`menor_que` -los unicos operadores nuevos que D1 necesita (punto 4 del
checkpoint: "No regex todavia salvo necesidad demostrable"-. No existe
`OR`/agrupacion/`NOT` complejo: `ReglaHost.condiciones` es una lista, y TODAS
deben cumplirse (AND implicito, punto 5).

SEGURIDAD (investigado explicitamente antes de escribir esto)
================================================================
Ni una condicion ni un campo de respuesta pueden referenciar un campo
sensible (`perfil.es_sensible()`, misma autoridad que ya usa
`resolver_referencia_de_paso`/`campos_permitidos_expectativa` -C2/B6-, nunca
una lista nueva). Se rechaza al VALIDAR la regla (`validar_regla`), nunca en
tiempo de evaluacion silenciosamente.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Sequence

#: Pseudo-campo que representa el MTI del mensaje -nunca un numero de campo
#: ISO real, nunca pasa por `perfil.especificacion`/`perfil.es_sensible()`
#: (el MTI no es un dato de negocio ni puede ser sensible).
CAMPO_MTI = "mti"

#: Limite razonable de latencia inducida (punto 12 del checkpoint: "Agregar
#: limites razonables. No permitir delay negativo."). 10 segundos ya excede
#: el `tiempo_limite` tipico usado en pruebas/demostraciones de este
#: laboratorio (2-3s); un valor mayor no aporta nada a un E2E real y si
#: arriesga que una prueba se sienta colgada. No es un limite de ninguna
#: red real, es una decision de laboratorio, documentada como tal.
DELAY_MS_MAXIMO = 10_000


class OperadorCondicion(str, Enum):
    """Mismo vocabulario que `ExpectativaCampo.tipo` -`domain.modelos`- mas
    `distinto`/`mayor_que`/`menor_que`, los unicos operadores nuevos que D1
    necesita."""

    IGUAL = "igual"
    DISTINTO = "distinto"
    MAYOR_QUE = "mayor_que"
    MENOR_QUE = "menor_que"
    PRESENTE = "presente"
    AUSENTE = "ausente"


#: Operadores que SI necesitan `valor` (el resto -presente/ausente- lo
#: rechaza).
_OPERADORES_CON_VALOR = frozenset(
    {OperadorCondicion.IGUAL, OperadorCondicion.DISTINTO,
     OperadorCondicion.MAYOR_QUE, OperadorCondicion.MENOR_QUE}
)
_OPERADORES_NUMERICOS = frozenset({OperadorCondicion.MAYOR_QUE, OperadorCondicion.MENOR_QUE})


@dataclass(frozen=True)
class CondicionRegla:
    """Una condicion sobre UN campo del mensaje recibido -`campo` es un
    numero de campo ISO (`"4"`, `"39"`) o el pseudo-campo `CAMPO_MTI`.

    `valor` es obligatorio para todo operador salvo `presente`/`ausente`
    -donde no hay nada que comparar, solo si el campo aparecio en el
    mensaje-, mismo criterio que `ExpectativaCampo`.
    """

    campo: str
    operador: str
    valor: str | None = None

    def __post_init__(self) -> None:
        if self.operador not in {o.value for o in OperadorCondicion}:
            raise ValueError(f"operador desconocido {self.operador!r}")
        necesita_valor = self.operador in {o.value for o in _OPERADORES_CON_VALOR}
        if necesita_valor and self.valor is None:
            raise ValueError(f"el operador {self.operador!r} necesita un valor")
        if not necesita_valor and self.valor is not None:
            raise ValueError(f"el operador {self.operador!r} no admite un valor")


class TipoComportamiento(str, Enum):
    """Que hace el host DESPUES de decidir la respuesta -o en vez de
    responder, para `TIMEOUT`/`DISCONNECT`- (puntos 12-14 del checkpoint).

    `TIMEOUT` y `DISCONNECT` son DELIBERADAMENTE distintos (punto 14): el
    primero reutiliza el mecanismo YA EXISTENTE de `responder=False`
    -mantiene el manejador vivo esperando el apagado del host, para que un
    cliente real experimente RN-2 (timeout, sin cierre visible del socket)-;
    el segundo cierra el socket DE INMEDIATO sin escribir nada -un cliente
    ve la conexion cerrarse, no un timeout-. Confundirlos produciria el
    error tecnico incorrecto del lado cliente (`TiempoAgotado` vs
    `FalloDeTransmision`/conexion cerrada).
    """

    NORMAL = "normal"
    DELAY = "delay"
    TIMEOUT = "timeout"
    DISCONNECT = "disconnect"


@dataclass(frozen=True)
class ComportamientoRegla:
    """`tipo=NORMAL`/`DELAY` responden (con o sin latencia); `TIMEOUT`/
    `DISCONNECT` nunca responden -ver `TipoComportamiento`."""

    tipo: str = TipoComportamiento.NORMAL.value
    delay_ms: int = 0

    def __post_init__(self) -> None:
        if self.tipo not in {t.value for t in TipoComportamiento}:
            raise ValueError(f"comportamiento desconocido {self.tipo!r}")
        if self.delay_ms < 0:
            raise ValueError("delay_ms no puede ser negativo")
        if self.delay_ms > DELAY_MS_MAXIMO:
            raise ValueError(f"delay_ms no puede superar {DELAY_MS_MAXIMO}")
        if self.tipo == TipoComportamiento.DELAY.value and self.delay_ms <= 0:
            raise ValueError("un comportamiento DELAY necesita delay_ms mayor que 0")
        if self.tipo != TipoComportamiento.DELAY.value and self.delay_ms != 0:
            raise ValueError("delay_ms solo aplica al comportamiento DELAY")


class GeneradorValor(str, Enum):
    """Conjunto CERRADO de valores dinamicos permitidos en una respuesta
    (punto 11 del checkpoint) -nunca un lenguaje de templates general, solo
    estos tres, cada uno resuelto por una funcion Python fija en
    `application.host_simulado_reglas` (o quien evalue la regla), jamas por
    `eval`/interpolacion de texto arbitraria.

    Se distinguen de un literal por el prefijo `@` (`PREFIJO_GENERADOR`):
    `"00"` es un literal, `"@stan_request"` es una referencia a este enum.
    No es un lenguaje de templates -sigue siendo una comparacion contra un
    conjunto cerrado de nombres, nunca una expresion-.
    """

    STAN_REQUEST = "stan_request"
    DATETIME_NOW = "datetime_now"
    AUTORIZACION_DESDE_STAN = "authorization_from_stan"


PREFIJO_GENERADOR = "@"


def es_generador(valor: str) -> bool:
    """True si `valor` referencia un `GeneradorValor` conocido -nunca True
    para un literal que simplemente empiece con `@` sin corresponder a
    ninguno: eso es un error de definicion, ver `validar_regla`."""
    return valor.startswith(PREFIJO_GENERADOR)


def generador_referenciado(valor: str) -> str | None:
    """El nombre del generador que `valor` referencia, o `None` si no
    referencia ninguno (incluye el caso de un prefijo mal escrito -no
    corresponde a ningun `GeneradorValor`, `validar_regla` lo rechaza-)."""
    if not es_generador(valor):
        return None
    nombre = valor[len(PREFIJO_GENERADOR):]
    return nombre if nombre in {g.value for g in GeneradorValor} else None


@dataclass(frozen=True)
class RespuestaRegla:
    """Que declara la regla ganadora sobre la respuesta -el host sigue
    siendo responsable de la base correlacionada (STAN, terminal, etc. via
    `domain.validacion.campos_de_correlacion`, sin cambios); esta clase solo
    declara las DIFERENCIAS, nunca reconstruye los 20 campos de correlacion
    (punto 9 del checkpoint).

    `de39` es obligatorio -toda regla decide un codigo de respuesta-.
    `campos_adicionales` es opcional: cada valor es un literal, O una
    referencia a un `GeneradorValor` (ver `es_generador`).
    """

    de39: str
    campos_adicionales: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "campos_adicionales", MappingProxyType(dict(self.campos_adicionales)))
        if not self.de39:
            raise ValueError("una respuesta de regla necesita un DE39")


@dataclass(frozen=True)
class ReglaHost:
    """Una regla declarativa completa -datos, nunca codigo (ver docstring
    del modulo). `regla_id` es opcional: lo asigna la persistencia
    (`application.reglas_host`), igual criterio que `escenario_id`/
    `secuencia_id` en el resto del proyecto.

    `prioridad`: MENOR se evalua PRIMERO (punto 6 del checkpoint). Debe ser
    `>= 0` -una decision de simplicidad, no una regla de negocio real: nunca
    hay ambiguedad de "prioridad negativa significa qué".

    `condiciones`: TODAS deben cumplirse (AND implicito, sin OR/grupos/NOT
    complejo, punto 5). Una regla sin condiciones NUNCA es valida -seria
    equivalente a "coincide siempre", indistinguible de un default oculto;
    quien quiera un default explicito debe declararlo como tal (ver
    `application.reglas_host`, done en integracion con `HostSimulado`).
    """

    nombre: str
    prioridad: int
    activa: bool
    condiciones: tuple[CondicionRegla, ...]
    respuesta: RespuestaRegla
    comportamiento: ComportamientoRegla = ComportamientoRegla()
    regla_id: str | None = None

    def __post_init__(self) -> None:
        if not self.nombre.strip():
            raise ValueError("una regla necesita un nombre")
        if self.prioridad < 0:
            raise ValueError("la prioridad no puede ser negativa")
        if not self.condiciones:
            raise ValueError("una regla necesita al menos una condicion")
        object.__setattr__(self, "condiciones", tuple(self.condiciones))


def _valor_del_mensaje(campo: str, campos_mensaje: Mapping[str, str], mti: str) -> str | None:
    if campo == CAMPO_MTI:
        return mti
    valor = campos_mensaje.get(campo)
    return valor if valor not in (None, "") else None


def _condicion_coincide(condicion: CondicionRegla, campos_mensaje: Mapping[str, str], mti: str) -> bool:
    valor_mensaje = _valor_del_mensaje(condicion.campo, campos_mensaje, mti)

    if condicion.operador == OperadorCondicion.PRESENTE.value:
        return valor_mensaje is not None
    if condicion.operador == OperadorCondicion.AUSENTE.value:
        return valor_mensaje is None

    if valor_mensaje is None:
        # Ningun operador con valor puede coincidir contra un campo ausente
        # -nunca se interpreta "ausente" como "0" ni como cadena vacia.
        return False

    if condicion.operador == OperadorCondicion.IGUAL.value:
        return valor_mensaje == condicion.valor
    if condicion.operador == OperadorCondicion.DISTINTO.value:
        return valor_mensaje != condicion.valor

    # mayor_que/menor_que: comparacion NUMERICA explicita -nunca lexicografica
    # (un DE4 formateado como string de digitos compararia mal por longitud/
    # ceros a la izquierda). Si cualquiera de los dos lados no es un numero
    # valido, la condicion simplemente NO coincide -nunca una excepcion sin
    # controlar, nunca una coincidencia falsa.
    try:
        izquierda = Decimal(valor_mensaje)
        derecha = Decimal(condicion.valor)
    except InvalidOperation:
        return False
    if condicion.operador == OperadorCondicion.MAYOR_QUE.value:
        return izquierda > derecha
    return izquierda < derecha  # MENOR_QUE, unico operador restante


def regla_coincide(regla: ReglaHost, campos_mensaje: Mapping[str, str], mti: str) -> bool:
    """`True` si TODAS las condiciones de `regla` se cumplen contra un
    mensaje -AND implicito, sin cortocircuito especial mas alla del natural
    de `all()`."""
    return all(_condicion_coincide(c, campos_mensaje, mti) for c in regla.condiciones)


def evaluar_reglas(
    reglas: Sequence[ReglaHost], campos_mensaje: Mapping[str, str], mti: str
) -> ReglaHost | None:
    """La PRIMERA regla activa, en orden de prioridad ascendente (menor
    primero, punto 6), cuyas condiciones coincidan TODAS. `None` si ninguna
    coincide -el llamador decide el comportamiento default (punto 7), esta
    funcion nunca inventa uno."""
    for regla in sorted((r for r in reglas if r.activa), key=lambda r: r.prioridad):
        if regla_coincide(regla, campos_mensaje, mti):
            return regla
    return None


def validar_regla(regla: ReglaHost, perfil) -> None:
    """Valida una regla contra el perfil activo ANTES de guardarla o de
    servir trafico con ella (puntos 22-23 del checkpoint):

    - ningun campo de condicion o de respuesta puede ser sensible
      (`perfil.es_sensible()`, misma autoridad que C2/B6 -nunca una lista
      nueva-), verificado SIEMPRE primero, sin importar si el perfil declara
      el campo;
    - todo campo (salvo el pseudo-campo `CAMPO_MTI`) debe existir en
      `perfil.especificacion`;
    - `respuesta.de39` debe respetar la longitud declarada para el campo 39
      en el perfil, si el perfil la declara.

    Nunca revela el VALOR de un campo en el mensaje de error -solo el
    numero/nombre y el motivo (punto 35 del checkpoint): un nombre de campo
    y un tipo esperado son diagnostico suficiente."""
    for condicion in regla.condiciones:
        _validar_campo_regla(condicion.campo, perfil, contexto="condicion")
    for campo in regla.respuesta.campos_adicionales:
        _validar_campo_regla(campo, perfil, contexto="respuesta")
    if "39" in perfil.especificacion:
        longitud_de39 = perfil.especificacion["39"].get("max_len")
        if longitud_de39 is not None and len(regla.respuesta.de39) != longitud_de39:
            raise ValueError(
                f"regla {regla.nombre!r}: DE39 debe tener {longitud_de39} caracteres"
            )
    for valor in regla.respuesta.campos_adicionales.values():
        if es_generador(valor) and generador_referenciado(valor) is None:
            raise ValueError(
                f"regla {regla.nombre!r}: {valor!r} no es un generador conocido"
            )


def _validar_campo_regla(campo: str, perfil, *, contexto: str) -> None:
    if campo == CAMPO_MTI:
        return
    if perfil.es_sensible(campo):
        raise ValueError(
            f"el campo DE{campo} es sensible: no puede usarse en la {contexto} de una regla"
        )
    if campo not in perfil.especificacion:
        raise ValueError(f"el campo DE{campo} no existe en el perfil activo")


@dataclass(frozen=True)
class EventoReglaHost:
    """Evidencia, del lado del HOST, de que una regla (o ninguna) goberno
    una respuesta real (punto 21 del checkpoint). Deliberadamente sin
    ninguna referencia a `Ejecucion` (tabla del cliente) -conectar ambos
    lados queda para cuando haya evidencia real de que hace falta (punto 21
    lo autoriza explicitamente)-, y NUNCA guarda el valor de un campo del
    mensaje que causo la coincidencia: solo que regla goberno, con que
    prioridad, y que respondio (punto 35: nunca datos sensibles en un
    mensaje de auditoria).

    `regla_id`/`regla_nombre`/`prioridad` son `None` cuando NINGUNA regla
    coincidio -el comportamiento default tambien es evidencia (punto 7).
    """

    mti_solicitud: str
    comportamiento: str
    regla_id: str | None = None
    regla_nombre: str | None = None
    prioridad: int | None = None
    de39_respuesta: str | None = None
    delay_ms: int = 0
    evento_id: int | None = None
    creado_en: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

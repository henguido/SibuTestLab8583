"""Representacion persistible de un mensaje ISO, y su lectura segura.

POR QUE EXISTE ESTE MODULO
==========================
Una ejecucion guarda el mensaje que se armo y el que llego. Hasta ahora se
guardaba en un solo formato de texto, ``MTI=0100 | 2=**** | 3=000000``, unido
por `` | `` y **sin escape**. Ese formato se lee deduciendo la estructura a
partir de la forma del texto, y por eso es fragil: un valor que contenga el
separador se parte, y el parser inventa un campo que nunca existio.

Aqui se resuelve escribiendo tambien una representacion **estructurada** en JSON,
donde la frontera de cada valor la declara el formato en lugar de deducirse.

Las dos representaciones conviven a proposito:

- ``a_texto()`` produce la de siempre. Se conserva por compatibilidad con las
  filas ya escritas y porque es legible de un vistazo.
- ``a_json()`` produce la fiel. Es la que se lee cuando existe.

LIMITE CONOCIDO Y DELIBERADO
============================
El JSON de la **respuesta** puede llevar ``crudo`` por campo, porque
`MensajeInterpretado` lo trae y `enmascarado()` tambien lo enmascara. El de la
**solicitud** no: `Codec.codificar` devuelve bytes y descarta el documento
codificado de pyiso8583, asi que un ``crudo`` por campo de la solicitud **no
existe** en el flujo actual. No se inventa. Recuperarlo exige cambiar el codec y
eso pertenece a otra iteracion.

CAPA
====
Vive en `application` porque lo necesitan dos piezas de esa capa: el orquestador
al persistir y las consultas al leer. En `adapters` obligaria a la capa de
lectura a depender de un adaptador; en `domain` obligaria al dominio a conocer
un formato de almacenamiento. Todas sus funciones son **puras**: sin red, sin
base de datos, sin reloj.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Any, Mapping

from ..domain.modelos import CAMPOS_SENSIBLES, MensajeInterpretado, MensajeIso

#: Version de la ESTRUCTURA del JSON, no del mensaje ISO ni del perfil. Permite
#: que un lector futuro distinga formatos leyendo una declaracion en vez de
#: deducirlos por su forma, que es exactamente el defecto del formato de texto.
VERSION_FORMATO = 1

#: Separador del formato de texto heredado. Se conserva para poder LEER lo ya
#: escrito; no se usa para nada nuevo.
SEPARADOR_HEREDADO = " | "
CLAVE_MTI_HEREDADA = "MTI"

ORIGEN_JSON = "json"
ORIGEN_TEXTO = "texto"
ORIGEN_AUSENTE = "ausente"

AVISO_HEREDADO = (
    "Representacion anterior a la persistencia estructurada. El separador no se"
    " escapaba, asi que no se puede demostrar que un valor no haya quedado"
    " partido: se muestra lo que se pudo leer, no una reconstruccion fiel."
)


class ErrorDeEnmascarado(AssertionError):
    """Un campo con datos de tarjeta llego sin enmascarar a la persistencia.

    Es `AssertionError` a proposito: no es una condicion que el usuario pueda
    provocar ni corregir, es un defecto de programacion que debe romper la
    prueba en lugar de escribir un PAN completo en la base.
    """


@dataclass(frozen=True)
class CampoSerializado:
    """Un campo tal como quedo guardado. `crudo` solo existe en la respuesta."""

    numero: str
    valor: str
    crudo: str | None = None


@dataclass(frozen=True)
class MensajeSerializado:
    """Lo que se pudo recuperar de una representacion persistida.

    `fiel` distingue dos cosas que no deben confundirse:

    - **True** solo cuando se leyo un JSON de una version conocida. Ahi la
      frontera de cada valor la declaro el formato.
    - **False** siempre que provenga del formato de texto heredado, incluso si
      parece haberse leido bien. La razon es que `41=A` es indistinguible de un
      `41=A | B` truncado: no se puede *demostrar* fidelidad, y este proyecto no
      afirma lo que no puede demostrar.
    """

    mti: str = ""
    perfil: str = ""
    campos: tuple[CampoSerializado, ...] = ()
    origen: str = ORIGEN_AUSENTE
    fiel: bool = False
    avisos: tuple[str, ...] = ()

    @property
    def disponible(self) -> bool:
        """Hubo algo que leer. No implica que sea fiel."""
        return self.origen != ORIGEN_AUSENTE

    def valor(self, numero: str) -> str | None:
        for campo in self.campos:
            if campo.numero == numero:
                return campo.valor
        return None


# ------------------------------------------------------------- escritura ------


def _verificar_enmascarado(numero: str, *valores: str | None) -> None:
    """Ultima barrera antes de escribir: un campo sensible no puede ir en claro.

    Existe por si un cambio futuro olvida llamar a `enmascarado()`. Un PAN
    completo en `ejecuciones` violaria la politica de `CLAUDE.md`, que lo
    restringe a `tarjetas_prueba`.
    """
    if numero not in CAMPOS_SENSIBLES:
        return
    for valor in valores:
        if valor and valor.isdigit():
            raise ErrorDeEnmascarado(
                f"el campo {numero} llego sin enmascarar a la persistencia"
            )


def a_texto(mensaje: MensajeIso) -> str:
    """Formato de texto heredado. Se mantiene por compatibilidad y legibilidad.

    Recibe siempre la version enmascarada del mensaje.
    """
    partes = [f"{CLAVE_MTI_HEREDADA}={mensaje.mti}"]
    for numero in sorted(mensaje.campos, key=int):
        valor = mensaje.campos[numero]
        _verificar_enmascarado(numero, valor)
        partes.append(f"{numero}={valor}")
    return SEPARADOR_HEREDADO.join(partes)


def a_json_solicitud(mensaje: MensajeIso, perfil: str) -> str:
    """JSON de la solicitud. Sin `crudo`: no existe en el flujo actual."""
    campos: dict[str, dict[str, str]] = {}
    for numero in sorted(mensaje.campos, key=int):
        valor = mensaje.campos[numero]
        _verificar_enmascarado(numero, valor)
        campos[numero] = {"valor": valor}
    return _volcar(mensaje.mti, perfil, campos)


def a_json_respuesta(mensaje: MensajeInterpretado, perfil: str) -> str:
    """JSON de la respuesta, con `crudo` por campo cuando el codec lo trajo."""
    campos: dict[str, dict[str, str]] = {}
    for numero in sorted(mensaje.campos, key=int):
        campo = mensaje.campos[numero]
        _verificar_enmascarado(numero, campo.valor, campo.crudo)
        entrada = {"valor": campo.valor}
        if campo.crudo:
            entrada["crudo"] = campo.crudo
        campos[numero] = entrada
    return _volcar(mensaje.mti, perfil, campos)


def _volcar(mti: str, perfil: str, campos: Mapping[str, Mapping[str, str]]) -> str:
    # `ensure_ascii=False` para que el JSON guarde el texto tal cual y no
    # secuencias de escape; la columna es TEXT y SQLite almacena UTF-8.
    return json.dumps(
        {"version": VERSION_FORMATO, "mti": mti, "perfil": perfil, "campos": campos},
        ensure_ascii=False,
        separators=(",", ":"),
    )


# --------------------------------------------------------------- lectura ------


def desde_json(texto: str | None) -> MensajeSerializado:
    """Lee la representacion estructurada. Nunca lanza."""
    if not texto:
        return MensajeSerializado()

    try:
        datos = json.loads(texto)
    except (ValueError, TypeError):
        return MensajeSerializado(
            origen=ORIGEN_JSON, avisos=("La representacion estructurada no es JSON legible.",)
        )

    if not isinstance(datos, dict):
        return MensajeSerializado(
            origen=ORIGEN_JSON,
            avisos=("La representacion estructurada no es un objeto JSON.",),
        )

    version = datos.get("version")
    if version != VERSION_FORMATO:
        # No se intenta leer una estructura que este codigo no conoce: hacerlo
        # seria inventar significado. Se declara y se deja indisponible.
        return MensajeSerializado(
            origen=ORIGEN_JSON,
            avisos=(
                f"La representacion declara el formato {version!r} y este programa"
                f" solo interpreta el {VERSION_FORMATO}.",
            ),
        )

    campos, avisos = _leer_campos(datos.get("campos"))
    return MensajeSerializado(
        mti=_cadena(datos.get("mti")),
        perfil=_cadena(datos.get("perfil")),
        campos=campos,
        origen=ORIGEN_JSON,
        fiel=True,
        avisos=avisos,
    )


def _leer_campos(crudos: Any) -> tuple[tuple[CampoSerializado, ...], tuple[str, ...]]:
    if crudos is None:
        return (), ("La representacion no trae campos.",)
    if not isinstance(crudos, dict):
        return (), ("La lista de campos no tiene la forma esperada.",)

    campos: list[CampoSerializado] = []
    avisos: list[str] = []
    for numero, entrada in crudos.items():
        if not isinstance(numero, str) or not numero.isdigit():
            avisos.append(f"Se ignoro una clave de campo no numerica: {numero!r}.")
            continue
        if not isinstance(entrada, dict) or "valor" not in entrada:
            avisos.append(f"El campo {numero} no trae un valor legible.")
            continue
        campos.append(
            CampoSerializado(
                numero=numero,
                valor=_cadena(entrada.get("valor")),
                crudo=_cadena(entrada["crudo"]) if "crudo" in entrada else None,
            )
        )
    campos.sort(key=lambda c: int(c.numero))
    return tuple(campos), tuple(avisos)


def desde_texto_heredado(texto: str | None) -> MensajeSerializado:
    """Lee el formato de texto anterior con tolerancia. Nunca lanza.

    **No intenta resolver la ambiguedad del formato**: un valor que contuviera el
    separador ya se escribio partido y esa informacion no esta. Lo que se hace es
    leer lo legible y marcar el resultado como no demostrablemente fiel.
    """
    if not texto:
        return MensajeSerializado()

    mti = ""
    campos: list[CampoSerializado] = []
    avisos: list[str] = [AVISO_HEREDADO]
    vistos: set[str] = set()

    for segmento in texto.split(SEPARADOR_HEREDADO):
        clave, separador, valor = segmento.partition("=")
        clave = clave.strip()
        if not separador:
            avisos.append(f"Segmento sin clave, no interpretable: {_recortar(segmento)}")
            continue
        if clave == CLAVE_MTI_HEREDADA:
            mti = valor
        elif clave.isdigit():
            if clave in vistos:
                avisos.append(f"El campo {clave} aparece mas de una vez.")
                continue
            vistos.add(clave)
            campos.append(CampoSerializado(numero=clave, valor=valor))
        else:
            avisos.append(f"Clave no reconocida, no interpretable: {_recortar(clave)}")

    campos.sort(key=lambda c: int(c.numero))
    return MensajeSerializado(
        mti=mti,
        perfil="",
        campos=tuple(campos),
        origen=ORIGEN_TEXTO,
        fiel=False,
        avisos=tuple(avisos),
    )


def interpretar(json_texto: str | None, texto_heredado: str | None) -> MensajeSerializado:
    """Lee una representacion persistida dando prioridad a la estructurada.

    Orden: JSON valido primero; si no hay o no se pudo leer, el texto heredado;
    si tampoco, un resultado indisponible. Nunca lanza, para que una fila
    antigua o corrupta no produzca un error del servidor.
    """
    del_json = desde_json(json_texto)
    if del_json.fiel:
        return del_json

    del_texto = desde_texto_heredado(texto_heredado)
    if del_texto.disponible:
        # El aviso del JSON fallido se arrastra: es informacion util para
        # diagnosticar, y taparlo seria ocultar que hubo un intento roto.
        return replace(del_texto, avisos=del_json.avisos + del_texto.avisos)

    return del_json if del_json.disponible else del_texto


def _cadena(valor: Any) -> str:
    return valor if isinstance(valor, str) else ""


def _recortar(texto: str, maximo: int = 40) -> str:
    limpio = texto.strip()
    return limpio if len(limpio) <= maximo else limpio[:maximo] + "..."

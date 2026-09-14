"""Perfil generico de demostracion.

ATENCION - ORIGEN DE ESTOS CAMPOS
=================================
Los campos y su formato son una DECISION TECNICA DE ESTE PROYECTO para tener un
mensaje de compra tecnicamente utilizable en la demostracion academica.

NO son la especificacion de Visa, de Mastercard ni de ninguna otra marca, y no
deben presentarse como tales. PROYECTO.md fija el alcance y las reglas de negocio
pero no define campos ISO; ante esa ausencia se eligio el conjunto minimo descrito
abajo. Los perfiles de marca solo se implementaran cuando existan en el proyecto
los documentos autorizados que definan esos formatos.

Un PerfilDeMarca define formato, codificacion y campos obligatorios por MTI. NO
define que codigo cuenta como aprobado: eso es CatalogoDeRespuestas, un eje
independiente.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from ..domain.campos_iso import TIPO_ALFANUMERICO, TIPO_NUMERICO, MetadatoCampo
from ..domain.modelos import (
    CAMPOS_SENSIBLES,
    MTI_COMPRA,
    MTI_COMPRA_FINANCIERA,
    MTI_ECHO,
    MTI_RESPUESTA_COMPRA,
    MTI_RESPUESTA_COMPRA_FINANCIERA,
    MTI_AVISO_REVERSO,
    MTI_RESPUESTA_AVISO_REVERSO,
    MTI_RESPUESTA_ECHO,
    MTI_RESPUESTA_REVERSO_FINANCIERO,
    MTI_REVERSO_FINANCIERO,
)

NOMBRE_PERFIL_GENERICO = "generico"


@dataclass(frozen=True)
class PoliticaCamposMti:
    """Gobierno de un MTI: quien puede fijar cada campo, y con que valor por defecto.

    Tres categorias, mutuamente excluyentes, que cubren todo campo relevante
    para el MTI:

    - ``derivados``: vienen de otro dato del dominio (la tarjeta elegida), nunca
      de texto libre. DE2 y DE14 en la compra.
    - ``automaticos``: los genera el sistema en el momento de armar el mensaje
      (reloj, secuencia de STAN). DE7, DE11, DE12, DE13 en la compra.
    - ``editables``: el usuario puede fijarlos, y viajan SIEMPRE en el mensaje:
      ``valores_por_defecto`` trae un valor razonable para los que no traiga el
      usuario; un campo editable sin entrada en ese mapa simplemente no tiene
      default y debe informarse.
    - ``opcionales``: el usuario TAMBIEN puede fijarlos, pero -a diferencia de
      un editable- no viajan a menos que el usuario los agregue de forma
      explicita: no tienen (ni pueden tener) un valor por defecto, asi que si
      no aparecen en ``campos_manuales`` simplemente no forman parte del
      mensaje armado. Es la categoria que sostiene "+ Agregar campo": el
      catalogo de candidatos a ofrecer es exactamente esta lista menos los que
      el usuario ya agrego.

    Un numero que no aparece en ninguna de las cuatro listas no es parte de
    este MTI segun este perfil: intentar fijarlo manualmente se rechaza igual
    que un intento de fijar uno derivado o automatico, aunque el motivo se
    distingue (ver `domain/armado.py`).
    """

    derivados: frozenset[str] = frozenset()
    automaticos: frozenset[str] = frozenset()
    editables: frozenset[str] = frozenset()
    opcionales: frozenset[str] = frozenset()
    valores_por_defecto: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "valores_por_defecto", MappingProxyType(dict(self.valores_por_defecto))
        )
        categorias = (self.derivados, self.automaticos, self.editables, self.opcionales)
        solapa: set[str] = set()
        for i, categoria_a in enumerate(categorias):
            for categoria_b in categorias[i + 1 :]:
                solapa |= categoria_a & categoria_b
        if solapa:
            raise ValueError(
                f"un campo no puede pertenecer a más de una categoría: {sorted(solapa)}"
            )
        fuera_de_editables = set(self.valores_por_defecto) - self.editables
        if fuera_de_editables:
            raise ValueError(
                "valores_por_defecto solo aplica a campos editables, no a "
                f"{sorted(fuera_de_editables)}"
            )

    def origen(self, numero: str) -> str:
        """``"derivado"``, ``"automatico"``, ``"editable"``, ``"opcional"`` o
        ``"no_permitido"``."""
        if numero in self.derivados:
            return "derivado"
        if numero in self.automaticos:
            return "automatico"
        if numero in self.editables:
            return "editable"
        if numero in self.opcionales:
            return "opcional"
        return "no_permitido"


@dataclass(frozen=True)
class PerfilDeMarca:
    """Formato ISO, campos obligatorios y politica de edicion por MTI.

    ``especificacion`` es lo que se le entrega a pyiso8583 tal cual; el codec la
    recibe como parametro y por eso nunca necesita saber a que marca corresponde.
    """

    nombre: str
    especificacion: Mapping[str, Mapping[str, Any]]
    obligatorios_por_mti: Mapping[str, frozenset[str]]
    politica_por_mti: Mapping[str, PoliticaCamposMti] = field(default_factory=dict)
    #: Campos que ESTE perfil declara sensibles, ademas del piso universal de
    #: dominio (`domain.modelos.CAMPOS_SENSIBLES`: DE2/35/45, sensibles por
    #: definicion del estandar, no por decision de marca). B3 (2026-09-13,
    #: ARCH-001/SEC-001): pensado para el dia en que un perfil real declare
    #: un campo propietario que tambien transporte datos de tarjeta -sin
    #: necesitar ampliar el significado del piso universal para eso-. Hoy
    #: vacio para el perfil generico: sus unicos campos de tarjeta (2) ya
    #: estan cubiertos por el piso.
    campos_sensibles: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        object.__setattr__(self, "especificacion", MappingProxyType(dict(self.especificacion)))
        object.__setattr__(
            self, "obligatorios_por_mti", MappingProxyType(dict(self.obligatorios_por_mti))
        )
        object.__setattr__(self, "politica_por_mti", MappingProxyType(dict(self.politica_por_mti)))

    def soporta(self, mti: str) -> bool:
        return mti in self.obligatorios_por_mti

    def obligatorios(self, mti: str) -> frozenset[str]:
        """Campos exigidos para ese MTI. Alimenta RN-4, antes de codificar."""
        if mti not in self.obligatorios_por_mti:
            raise ValueError(f"el perfil {self.nombre!r} no soporta el MTI {mti!r}")
        return self.obligatorios_por_mti[mti]

    def politica(self, mti: str) -> PoliticaCamposMti:
        """Gobierno de campos manuales para ese MTI. Alimenta el constructor libre."""
        if mti not in self.politica_por_mti:
            raise ValueError(f"el perfil {self.nombre!r} no declara politica para el MTI {mti!r}")
        return self.politica_por_mti[mti]

    def es_sensible(self, numero: str) -> bool:
        """Autoridad declarativa de sensibilidad para quien SI tiene un
        perfil real en mano (a diferencia de `MensajeIso.enmascarado()`, que
        no lo recibe): el piso universal de dominio, unido a lo que este
        perfil declare como propio. Nunca al reves -este perfil no puede
        "des-declarar" un campo del piso universal-.
        """
        return numero in CAMPOS_SENSIBLES or numero in self.campos_sensibles


def _fijo(largo: int, descripcion: str) -> dict[str, Any]:
    return {
        "data_enc": "ascii",
        "len_enc": "ascii",
        "len_type": 0,
        "max_len": largo,
        "desc": descripcion,
    }


def _llvar(maximo: int, descripcion: str) -> dict[str, Any]:
    return {
        "data_enc": "ascii",
        "len_enc": "ascii",
        "len_type": 2,
        "max_len": maximo,
        "desc": descripcion,
    }


# Especificacion en ASCII, con bitmap tambien en ASCII para que el mensaje sea
# legible en el isoscopio durante la demostracion. Solo incluye campos que el
# recorrido de compra 0100/0110 usa.
ESPECIFICACION_GENERICA: dict[str, dict[str, Any]] = {
    "h": _fijo(0, "Sin cabecera"),
    "t": _fijo(4, "Tipo de mensaje (MTI)"),
    "p": _fijo(16, "Bitmap primario"),
    #: Bitmap secundario: pyiso8583 lo exige declarado en la especificacion
    #: en cuanto un mensaje usa algun campo 65-128 (aqui, DE70 para 0800/0810,
    #: B2) - el propio bit 1 del bitmap primario senala su presencia.
    "1": _fijo(16, "Bitmap secundario"),
    "2": _llvar(19, "Número de tarjeta (PAN)"),
    "3": _fijo(6, "Código de proceso"),
    "4": _fijo(12, "Monto de la transacción"),
    "7": _fijo(10, "Fecha y hora de transmisión (MMDDhhmmss)"),
    "11": _fijo(6, "Número de trazabilidad (STAN)"),
    "12": _fijo(6, "Hora local (hhmmss)"),
    "13": _fijo(4, "Fecha local (MMDD)"),
    "14": _fijo(4, "Fecha de vencimiento (AAMM)"),
    "18": _fijo(4, "Tipo de comercio (Merchant Type / MCC)"),
    "22": _fijo(3, "Modo de captura en el punto de venta"),
    "25": _fijo(2, "Código de condición del punto de servicio (POS)"),
    "32": _llvar(11, "Identificador de la institución adquirente"),
    "37": _fijo(12, "Número de referencia de recuperación"),
    "38": _fijo(6, "Código de autorización"),
    "39": _fijo(2, "Código de respuesta"),
    "41": _fijo(8, "Identificador del terminal"),
    "42": _fijo(15, "Identificador del comercio (Card Acceptor ID)"),
    "43": _fijo(40, "Nombre y ubicación del comercio (Card Acceptor Name/Location)"),
    "49": _fijo(3, "Código de moneda (ISO 4217 numérico)"),
    #: DE70, agregado para el 0800/0810 (Network Management/Echo, B2). El
    #: numero y la longitud (3 digitos) son del estandar ISO 8583 general
    #: -no de ninguna marca-; el VALOR que este perfil usa para identificar
    #: un echo (`VALOR_LABORATORIO_ECHO`, mas abajo) es una convencion propia
    #: de laboratorio, documentada como tal, no una especificacion oficial.
    "70": _fijo(3, "Código de información de gestión de red"),
}

#: Metadata de sensibilidad (ARCH-001/SEC-001, resuelto parcialmente en B2):
#: que campos transporta este perfil que nunca deben persistirse ni mostrarse
#: en claro. Separado de `METADATOS_CAMPOS_0100` a proposito -ese diccionario
#: es "metadata de UI para campos editables"; este es un eje ortogonal que
#: tambien cubre derivados (DE2 nunca se ofrece para editar a mano, pero SI
#: es sensible)-. Es la fuente DECLARATIVA: `test_perfil_generico.py::
#: test_todo_campo_declarado_sensible_tiene_autoridad_en_camposensibles`
#: falla si algun dia se agrega aqui un campo que `domain.modelos.
#: CAMPOS_SENSIBLES` no incluya -asi una futura ampliacion (Fase B2+, otro
#: perfil, otro MTI con un campo de tarjeta bajo otro numero) no puede
#: declarar sensibilidad aqui sin que la reja de enmascarado la aplique de
#: verdad-.
#:
#: NO es todavia una migracion completa: `MensajeIso.enmascarado()` y el
#: resto de los 6+ consumidores de `CAMPOS_SENSIBLES` (codec.py,
#: expectativas.py, validacion.py, serializacion.py, presentacion.py) siguen
#: leyendo la constante global de `domain/modelos.py`, no este diccionario -
#: threading un `perfil` a traves de esas firmas es un cambio mayor,
#: documentado como deuda explicita para B3 en docs/roadmap/SIBU_3.md-. Lo
#: que SI cambia hoy: la constante global deja de ser la unica fuente de
#: verdad no verificada; ahora tiene una prueba que la contrasta contra una
#: declaracion explicita por campo.
METADATOS_SENSIBLES: dict[str, MetadatoCampo] = {
    "2": MetadatoCampo(
        "2", "PAN", "Número de tarjeta (PAN)", TIPO_NUMERICO, False, 19, True,
    ),
}

#: Metadata de UI/validacion de forma para los campos que este perfil conoce
#: para el 0100 -obligatorios, editables y opcionales-. Automaticos/derivados
#: no necesitan entrada aqui: la UI nunca ofrece escribirlos a mano.
#:
#: Los cinco opcionales (18/25/32/42/43) son un conjunto ISO 8583:1987 generico
#: y de uso comun -no una especificacion de marca-, elegido para tener un
#: primer catalogo razonable de "+ Agregar campo"; ampliarlo mas adelante es
#: solo agregar una entrada aqui y en `ESPECIFICACION_GENERICA`, nunca tocar
#: una plantilla.
METADATOS_CAMPOS_0100: dict[str, MetadatoCampo] = {
    "3": MetadatoCampo("3", "Processing Code", "Código de proceso", TIPO_NUMERICO, True, 6, False),
    "18": MetadatoCampo(
        "18", "Merchant Type", "Tipo de comercio (Merchant Type / MCC)",
        TIPO_NUMERICO, True, 4, False,
        ayuda="Código de categoría de comercio de 4 dígitos (MCC), p. ej. 5411.",
    ),
    "22": MetadatoCampo(
        "22", "POS Entry Mode", "Modo de captura en el punto de venta",
        TIPO_NUMERICO, True, 3, False,
    ),
    "25": MetadatoCampo(
        "25", "POS Condition Code", "Código de condición del punto de servicio (POS)",
        TIPO_NUMERICO, True, 2, False,
    ),
    "32": MetadatoCampo(
        "32", "Acquiring Institution ID", "Identificador de la institución adquirente",
        TIPO_NUMERICO, False, 11, False,
    ),
    "37": MetadatoCampo(
        "37", "Retrieval Reference Number", "Número de referencia de recuperación",
        TIPO_ALFANUMERICO, True, 12, False,
    ),
    "41": MetadatoCampo(
        "41", "Card Acceptor Terminal ID", "Identificador del terminal",
        TIPO_ALFANUMERICO, True, 8, False,
    ),
    "42": MetadatoCampo(
        "42", "Card Acceptor ID", "Identificador del comercio (Card Acceptor ID)",
        TIPO_ALFANUMERICO, True, 15, False,
    ),
    "43": MetadatoCampo(
        "43", "Card Acceptor Name/Location",
        "Nombre y ubicación del comercio (Card Acceptor Name/Location)",
        TIPO_ALFANUMERICO, True, 40, False,
    ),
    "49": MetadatoCampo(
        "49", "Transaction Currency Code", "Código de moneda (ISO 4217 numérico)",
        TIPO_NUMERICO, True, 3, False,
    ),
}

#: Metadata de UI/validacion de forma para el 0800 (Network Management/Echo,
#: B2). Un unico campo editable: DE70. Deliberadamente NO copia
#: METADATOS_CAMPOS_0100 -esta operacion no tiene tarjeta, monto, comercio ni
#: terminal, y agregar esos campos aqui seria inventar informacion que el
#: echo no usa.
METADATOS_CAMPOS_0800: dict[str, MetadatoCampo] = {
    "70": MetadatoCampo(
        "70", "Network Management Information Code",
        "Código de información de gestión de red",
        TIPO_NUMERICO, True, 3, False,
        ayuda=(
            "Identifica el tipo de operación de gestión de red. El valor por "
            "defecto es una convención de laboratorio de este perfil genérico "
            "(no una especificación oficial de ninguna red) para un echo test."
        ),
    ),
}

# Obligatorios de la solicitud de compra: lo minimo para que el mensaje describa
# una compra concreta (que tarjeta, cuanto, en que moneda, en que terminal, con
# que trazabilidad).
OBLIGATORIOS_0100 = frozenset({"2", "3", "4", "7", "11", "14", "22", "41", "49"})

# Obligatorios de la respuesta: el codigo de respuesta mas los campos que deben
# volver iguales para poder correlacionar y comprobar la respuesta (RN-3).
OBLIGATORIOS_0110 = frozenset({"3", "4", "7", "11", "39", "41"})

#: Codigo de proceso que identifica una compra en este perfil generico.
CODIGO_PROCESO_COMPRA = "000000"

#: Captura manual del numero de tarjeta. Ver domain/armado.py: valor del perfil
#: generico de demostracion, no atribuible a ninguna marca.
MODO_CAPTURA_DEMOSTRACION = "011"

#: Terminal de demostracion. Un unico valor fijo alcanza para el alcance actual;
#: administrar varios terminales queda fuera de esta iteracion.
TERMINAL_DEMOSTRACION = "TERM0001"

#: Politica de campos de la compra (0100). DE2 y DE14 vienen siempre de la
#: tarjeta elegida (nunca de texto libre); DE7/11/12/13 los genera el sistema al
#: armar el mensaje. El resto de lo que este perfil declara para el 0100 es
#: editable, con un default razonable para no obligar a informarlo.
#:
#: DE38 (codigo de autorizacion) NO esta en editables, a proposito: es un campo
#: que el AUTORIZADOR agrega en su respuesta cuando aprueba —lo hace
#: `HostSimulado._construir_respuesta` en adapters/host_simulado/servidor.py,
#: usando el STAN como valor—, no algo que el emisor declare en la solicitud.
#: Habilitarlo en el 0100 seria incorrecto de dominio, no solo innecesario.
_POLITICA_COMPRA = PoliticaCamposMti(
    derivados=frozenset({"2", "14"}),
    automaticos=frozenset({"7", "11", "12", "13"}),
    editables=frozenset({"3", "22", "37", "41", "49"}),
    opcionales=frozenset({"18", "25", "32", "42", "43"}),
    valores_por_defecto={
        "3": CODIGO_PROCESO_COMPRA,
        "22": MODO_CAPTURA_DEMOSTRACION,
        "41": TERMINAL_DEMOSTRACION,
        "49": "188",
    },
)

#: Valor de laboratorio que este perfil usa en DE70 para identificar un echo
#: test -NO una especificacion oficial de ISO 8583 ni de ninguna red real:
#: distintas implementaciones documentan distintos valores para "echo" en
#: gestion de red, y este proyecto no tiene autoridad para declarar uno como
#: el correcto. Se elige un valor propio, claramente marcado como tal, igual
#: criterio que ya aplica `CODIGO_PROCESO_COMPRA`/`MODO_CAPTURA_DEMOSTRACION`.
VALOR_LABORATORIO_ECHO = "301"

# Obligatorios del echo: los dos campos que todo intercambio 0800/0810 de
# este laboratorio necesita para poder correlacionarse (RN-3), mas DE70 -que
# identifica que tipo de operacion de red es esta-. Sin tarjeta, sin monto,
# sin campos de comercio: ninguno de esos conceptos aplica a un echo.
OBLIGATORIOS_0800 = frozenset({"7", "11", "70"})

# Obligatorios de la respuesta: DE39 se incluye a proposito -ver docstring de
# _POLITICA_ECHO- para que el echo reutilice RN-1/RN-3 sin ningun camino
# especial en domain/validacion.py; el host siempre responde "00" (exito),
# nunca un codigo de rechazo, en esta primera entrega de echo.
OBLIGATORIOS_0810 = frozenset({"7", "11", "39", "70"})

#: Politica de campos del echo (0800). Sin derivados (no hay tarjeta), DE7/11
#: automaticos (igual que en compra: reloj y secuencia de STAN), DE70
#: editable con un default de laboratorio -para que una persona pueda
#: sobreescribirlo explicitamente (o usar una variable dinamica de Fase A
#: sobre el, demostrando que el mecanismo es generico), sin que eso sea
#: obligatorio-.
_POLITICA_ECHO = PoliticaCamposMti(
    automaticos=frozenset({"7", "11"}),
    editables=frozenset({"70"}),
    valores_por_defecto={"70": VALOR_LABORATORIO_ECHO},
)

# ------------------------------------------ Compra financiera (0200/0210, B4) --
#
# Dentro de este laboratorio: 0100 es una AUTORIZACION (verifica/reserva, no
# mueve fondos por si sola); 0200 es una TRANSACCION FINANCIERA (mueve fondos
# en el mismo mensaje). Es la distincion de dominio que ISO 8583 documenta en
# general para "Authorization"/"Financial" -no una regla de Visa, Mastercard
# ni de ninguna otra marca especifica-.
#
# Campo por campo, auditado contra `ESPECIFICACION_GENERICA` (no copiado de
# 0100 sin revisar): una compra financiera describe exactamente el mismo
# concepto de "que tarjeta, cuanto, en que moneda, en que terminal, con que
# trazabilidad" que una compra -por eso el conjunto resultante coincide con
# el de 0100-, pero se declara aqui como su PROPIA politica: si algun dia
# difieren (por ejemplo, un campo propio de liquidacion que 0100 nunca
# necesito), esta politica cambia sola, sin arrastrar a la otra.
CODIGO_PROCESO_COMPRA_FINANCIERA = "000000"

# Obligatorios de la solicitud financiera: mismo razonamiento que OBLIGATORIOS_0100.
OBLIGATORIOS_0200 = frozenset({"2", "3", "4", "7", "11", "14", "22", "41", "49"})

# Obligatorios de la respuesta: el codigo de respuesta mas los campos que deben
# volver iguales para poder correlacionar (RN-3) -mismo razonamiento que OBLIGATORIOS_0110-.
OBLIGATORIOS_0210 = frozenset({"3", "4", "7", "11", "39", "41"})

#: Politica de campos de la compra financiera (0200). Misma forma que
#: `_POLITICA_COMPRA` -DE2/DE14 derivados de la tarjeta, DE7/11/12/13
#: automaticos-, porque la capa estructural de ambas operaciones es
#: literalmente la misma funcion (`domain.armado.
#: _campos_estructurales_transaccion_con_tarjeta`). DE38 tampoco es editable
#: aqui, por el mismo motivo que en 0100: lo agrega el autorizador al
#: aprobar, nunca lo declara el emisor en la solicitud.
_POLITICA_COMPRA_FINANCIERA = PoliticaCamposMti(
    derivados=frozenset({"2", "14"}),
    automaticos=frozenset({"7", "11", "12", "13"}),
    editables=frozenset({"3", "22", "37", "41", "49"}),
    opcionales=frozenset({"18", "25", "32", "42", "43"}),
    valores_por_defecto={
        "3": CODIGO_PROCESO_COMPRA_FINANCIERA,
        "22": MODO_CAPTURA_DEMOSTRACION,
        "41": TERMINAL_DEMOSTRACION,
        "49": "188",
    },
)

#: Metadata de UI/validacion de forma para el 0200: identica a la de 0100
#: porque el conjunto de campos editables/opcionales lo es (ver auditoria mas
#: arriba) -reexportada bajo su propio nombre, no una nueva copia de
#: cuarenta lineas, para que un manana en que difieran no obligue a decidir
#: cual de las dos copias quedo desactualizada.
METADATOS_CAMPOS_0200 = METADATOS_CAMPOS_0100

# --------------------------------------- Reverso financiero (0400/0410, B7) --
#
# Un reverso deshace una 0200 ya aprobada. Ningun campo de este MTI es
# editable ni opcional -a proposito, B7 punto 5: un reverso no es un
# constructor libre-. Cada campo es "nuevo intercambio" (DE3/DE7/DE11:
# generados en el momento del reverso, nunca copiados del original) o
# "referenciado del original" (DE4/DE41/DE49/DE37: copiados del snapshot
# seguro de la ejecucion origen, `application.referencia_ejecucion.
# ReferenciaEjecucion`, B6). El builder (`application/armado_reverso.py`)
# construye estos campos directamente -no hay `campos_manuales` que
# componer, asi que este MTI no reutiliza `domain.armado._componer_campos_base`-.
#
# DE90 (Original Data Elements) -investigado en B6 y revisado de nuevo aqui
# con la composicion exacta en mano- NO se implementa: los primeros 31
# caracteres (MTI+STAN+fecha/hora+adquirente del original) se podrian derivar
# de `ReferenciaEjecucion` sin inventar nada, pero los ultimos 11 (ID de
# institucion RECEPTORA/forwarding) no tienen ninguna fuente en este perfil
# -`ESPECIFICACION_GENERICA` ni siquiera declara ese campo (DE33, Forwarding
# Institution ID) para ningun MTI-. Rellenarlos con cualquier valor
# fabricaria un dato que este laboratorio no tiene: exactamente lo que B7
# punto 7 prohibe ("no aceptar DE90 como texto libre"). La correlacion
# origen<->reverso se apoya en cambio en DE37 (RRN, cuando el original lo
# tuvo) a nivel de protocolo, y en `Ejecucion.ejecucion_origen_id` (B6) a
# nivel de aplicacion.
CODIGO_PROCESO_REVERSO_FINANCIERO = "000000"

# Obligatorios de la solicitud: DE37 (RRN) queda fuera a proposito -el
# original puede no haberlo tenido (no es obligatorio en 0200, ver
# OBLIGATORIOS_0200 mas arriba)-, asi que un reverso sin RRN sigue siendo un
# 0400 valido segun este perfil.
OBLIGATORIOS_0400 = frozenset({"3", "4", "7", "11", "41", "49"})

# Obligatorios de la respuesta: mismo criterio que OBLIGATORIOS_0210.
OBLIGATORIOS_0410 = frozenset({"3", "4", "7", "11", "39", "41"})

#: Politica de campos del reverso financiero (0400, B7). Sin editables ni
#: opcionales -un reverso no es un constructor libre-. DE4/DE41/DE49 son
#: "derivados" en el mismo sentido que DE2/DE14 lo son en compra: vienen de
#: otro dato del dominio (aqui, `ReferenciaEjecucion` en vez de
#: `TarjetaPrueba`), nunca de texto libre. DE37 tambien es derivado -el
#: builder simplemente no lo incluye cuando el original no lo tuvo-. DE3/
#: DE7/DE11 son automaticos: datos NUEVOS de este intercambio, no del
#: original.
_POLITICA_REVERSO_FINANCIERO = PoliticaCamposMti(
    derivados=frozenset({"4", "37", "41", "49"}),
    automaticos=frozenset({"3", "7", "11"}),
)

# ------------------------------------------- Aviso de reverso (0420/0430, B8) --
#
# Un aviso de reverso NOTIFICA que una 0200 ya aprobada se revirtio -no lo
# SOLICITA, a diferencia del 0400 (ver `domain/modelos.py::MTI_AVISO_REVERSO`
# para la diferencia funcional completa, investigada con Agente A-. Esa
# diferencia es de CONTRATO de mensaje (solicitud-que-puede-fallar vs
# aviso-que-debe-aceptarse), no de que campos porta: campo por campo, este
# laboratorio no tiene ninguna fuente que distinga los campos de un 0420 de
# los de un 0400 (mismo perfil generico, mismo `ReferenciaEjecucion` como
# origen de datos) -por eso la composicion de campos es identica a la del
# 0400 (ver `application/armado_operacion_derivada.py`), pero la POLITICA se
# declara aqui de cero, sin importar ni heredar `_POLITICA_REVERSO_FINANCIERO`
# (B8, punto 7): son dos MTI distintos, y que hoy compartan forma no significa
# que compartan definicion -maniana uno podria declarar un campo que el otro
# no admite, y una referencia cruzada lo ocultaria-.
#
# DE90 -mismo analisis y misma decision que 0400/0410 (ver
# `application/armado_operacion_derivada.py`): NO implementado, sin fuente
# para DE33.
CODIGO_PROCESO_AVISO_REVERSO = "000000"

# Obligatorios de la solicitud: mismo conjunto que OBLIGATORIOS_0400 -DE37
# fuera por la misma razon (el original puede no haberlo tenido)-, declarado
# de cero como constante propia (no una referencia a OBLIGATORIOS_0400).
OBLIGATORIOS_0420 = frozenset({"3", "4", "7", "11", "41", "49"})

# Obligatorios de la respuesta: mismo criterio que OBLIGATORIOS_0410.
OBLIGATORIOS_0430 = frozenset({"3", "4", "7", "11", "39", "41"})

#: Politica de campos del aviso de reverso (0420, B8). Misma forma que
#: `_POLITICA_REVERSO_FINANCIERO`, declarada aparte a proposito (ver
#: comentario de seccion arriba).
_POLITICA_AVISO_REVERSO = PoliticaCamposMti(
    derivados=frozenset({"4", "37", "41", "49"}),
    automaticos=frozenset({"3", "7", "11"}),
)

PERFIL_GENERICO = PerfilDeMarca(
    nombre=NOMBRE_PERFIL_GENERICO,
    especificacion=ESPECIFICACION_GENERICA,
    obligatorios_por_mti={
        MTI_COMPRA: OBLIGATORIOS_0100,
        MTI_RESPUESTA_COMPRA: OBLIGATORIOS_0110,
        MTI_ECHO: OBLIGATORIOS_0800,
        MTI_RESPUESTA_ECHO: OBLIGATORIOS_0810,
        MTI_COMPRA_FINANCIERA: OBLIGATORIOS_0200,
        MTI_RESPUESTA_COMPRA_FINANCIERA: OBLIGATORIOS_0210,
        MTI_REVERSO_FINANCIERO: OBLIGATORIOS_0400,
        MTI_RESPUESTA_REVERSO_FINANCIERO: OBLIGATORIOS_0410,
        MTI_AVISO_REVERSO: OBLIGATORIOS_0420,
        MTI_RESPUESTA_AVISO_REVERSO: OBLIGATORIOS_0430,
    },
    politica_por_mti={
        MTI_COMPRA: _POLITICA_COMPRA,
        MTI_ECHO: _POLITICA_ECHO,
        MTI_COMPRA_FINANCIERA: _POLITICA_COMPRA_FINANCIERA,
        MTI_REVERSO_FINANCIERO: _POLITICA_REVERSO_FINANCIERO,
        MTI_AVISO_REVERSO: _POLITICA_AVISO_REVERSO,
    },
)


def perfil_activo() -> PerfilDeMarca:
    """Perfil en uso. Hoy solo existe el generico."""
    return PERFIL_GENERICO

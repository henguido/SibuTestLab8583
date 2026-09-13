"""Registro declarativo de operaciones ISO 8583 con tarjeta (B5).

Existe para eliminar la duplicacion real que B4 dejo entre `/` (Autorizacion,
0100) y `/financiera` (Compra financiera, 0200): dos rutas, dos renderizadores
(`_formulario`/`_formulario_financiera`) y dos plantillas (`compra.html`/
`financiera.html`) que compartian ~90% de su contenido, con solo un puñado de
diferencias reales (MTI, textos, endpoint de ejecucion). Ese ~90% ahora es
un unico renderizador (`_formulario_operacion` en `web/app.py`) y una unica
plantilla (`editor_transaccion.html`); lo que SI difiere entre Autorizacion y
Compra financiera vive aqui, en un `OperacionIso` por operacion.

LO QUE ESTE REGISTRO **NO** ES (deliberado, B5 punto 10):
No declara obligatorios, opcionales, sensibilidad ni longitudes de campo -eso
sigue siendo exclusivo de `PerfilDeMarca`/`PoliticaCamposMti` en
`domain`/`profiles`-. Si algun dia un campo de aqui empezara a parecerse a
eso, seria la señal de que se esta duplicando la politica, no centralizando
metadata de presentacion/despacho.

Echo (0800) deliberadamente NO esta en este registro: no tiene tarjeta ni
monto, y forzarlo aqui solo para "unificar" habria sido homogeneizar dos
operaciones genuinamente distintas (ver `docs/roadmap/SIBU_3.md`, principio
de B5: "unificar lo comun, no homogeneizar cosas diferentes"). Echo conserva
su propio renderizador/plantilla (`_formulario_echo`/`echo.html`).

`clave` es siempre uno de los `OPERACION_*` de `domain.modelos` -la MISMA
fuente de verdad que ya usa `Escenario.operacion`-, nunca un identificador
paralelo: agregar una tercera operacion con tarjeta a este registro es
agregar una entrada aqui, no inventar un segundo esquema de claves.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.modelos import (
    MTI_COMPRA,
    MTI_COMPRA_FINANCIERA,
    MTI_RESPUESTA_COMPRA,
    MTI_RESPUESTA_COMPRA_FINANCIERA,
    DatosCompra,
    DatosCompraFinanciera,
    OPERACION_COMPRA,
    OPERACION_COMPRA_FINANCIERA,
)


@dataclass(frozen=True)
class OperacionIso:
    """Metadata de presentacion y despacho de una operacion con tarjeta.

    `datos_cls` y `metodo_orquestador` son despacho -que tipo construir y que
    metodo de `Orquestador` invocar-, no politica: el propio `Orquestador`
    sigue siendo quien arma el mensaje (`domain.armado.armar_*`) y valida
    RN-1..RN-4; este registro solo sabe a quien preguntarle.
    """

    #: Identidad funcional (domain.modelos.OPERACION_*). Fuente de verdad de
    #: la intencion, separada del MTI a proposito -ver domain.modelos,
    #: docstring de OPERACION_POR_MTI-.
    clave: str
    #: Rotulo humano para navegacion/listados (ej. "Autorización").
    nombre: str
    #: MTI de la solicitud y de la respuesta esperada.
    mti: str
    mti_respuesta: str
    #: Ruta que renderiza el editor (GET) y acepta el POST de "solo
    #: re-renderizar" -cambiar conexion, actualizar preview, agregar/quitar
    #: opcional-, nunca ejecuta la operacion.
    ruta: str
    #: Ruta que SI ejecuta la operacion de verdad.
    ruta_ejecutar: str
    #: `seccion` que ya consume `contexto_de_resultado`/`ruta_activa` -un
    #: concepto de navegacion/resaltado preexistente a B5, deliberadamente
    #: NO fusionado con `clave`: son ejes distintos (uno es intencion de
    #: dominio, el otro es que pantalla esta activa).
    seccion: str
    #: Textos propios de esta operacion para el encabezado y el constructor.
    titulo_pagina: str
    descripcion_pagina: str
    titulo_constructor: str
    verbo_ejecutar: str
    #: Tipo de `DatosX` que arma esta operacion (`domain.modelos.DatosCompra`
    #: o similar) -el editor lo instancia para pedir una vista previa.
    datos_cls: type
    #: Nombre del metodo en `Orquestador` que ejecuta esta operacion
    #: (`getattr(orquestador, metodo_orquestador)`), mismo patron de
    #: despacho por nombre que `application.ejecutor_escenarios.
    #: _ADAPTADORES_POR_MTI` ya establecio para reejecutar un escenario.
    metodo_orquestador: str
    #: Nombre del atributo en `Composicion` que expone el servicio de vista
    #: previa de esta operacion (`composicion.vista_previa`,
    #: `composicion.vista_previa_compra_financiera`, ...).
    atributo_vista_previa: str
    #: Metadata de campos (UI/validacion de forma) de esta operacion, tal
    #: como ya la expone `Composicion` (`metadatos_de_campos_0100`, etc.).
    atributo_metadatos_campos: str


OPERACION_AUTORIZACION = OperacionIso(
    clave=OPERACION_COMPRA,
    nombre="Autorización",
    mti=MTI_COMPRA,
    mti_respuesta=MTI_RESPUESTA_COMPRA,
    ruta="/",
    ruta_ejecutar="/compra",
    seccion="compra",
    titulo_pagina="Nueva transacción",
    descripcion_pagina=(
        "Construye un mensaje 0100, lo transmite por TCP a la conexión elegida e "
        "interpreta la respuesta 0110. Cada intento queda registrado en el historial, "
        "incluidos los que no obtienen respuesta."
    ),
    titulo_constructor="Construir transacción · 0100",
    verbo_ejecutar="Ejecutar transacción",
    datos_cls=DatosCompra,
    metodo_orquestador="ejecutar_compra",
    atributo_vista_previa="vista_previa",
    atributo_metadatos_campos="metadatos_de_campos_0100",
)

OPERACION_FINANCIERA = OperacionIso(
    clave=OPERACION_COMPRA_FINANCIERA,
    nombre="Compra financiera",
    mti=MTI_COMPRA_FINANCIERA,
    mti_respuesta=MTI_RESPUESTA_COMPRA_FINANCIERA,
    ruta="/financiera",
    ruta_ejecutar="/financiera/ejecutar",
    seccion="financiera",
    titulo_pagina="Compra financiera",
    descripcion_pagina=(
        "Construye un mensaje 0200 (transacción financiera: mueve fondos en el mismo "
        "mensaje, a diferencia de la autorización 0100), lo transmite por TCP a la "
        "conexión elegida e interpreta la respuesta 0210. Cada intento queda "
        "registrado en el historial, igual que una autorización."
    ),
    titulo_constructor="Construir transacción · 0200",
    verbo_ejecutar="Ejecutar compra financiera",
    datos_cls=DatosCompraFinanciera,
    metodo_orquestador="ejecutar_compra_financiera",
    atributo_vista_previa="vista_previa_compra_financiera",
    atributo_metadatos_campos="metadatos_de_campos_0200",
)

#: Las operaciones con tarjeta que hoy comparten el editor comun. Agregar una
#: tercera (con tarjeta) es agregar una entrada aqui -ver
#: `tests/test_extensibilidad_operaciones.py`, que demuestra precisamente
#: esto sin implementar un cuarto MTI real.
OPERACIONES_CON_TARJETA: tuple[OperacionIso, ...] = (
    OPERACION_AUTORIZACION,
    OPERACION_FINANCIERA,
)

OPERACIONES_POR_CLAVE: dict[str, OperacionIso] = {op.clave: op for op in OPERACIONES_CON_TARJETA}
OPERACIONES_POR_MTI: dict[str, OperacionIso] = {op.mti: op for op in OPERACIONES_CON_TARJETA}


def operacion_por_clave(clave: str) -> OperacionIso | None:
    return OPERACIONES_POR_CLAVE.get(clave)


def operacion_por_mti(mti: str) -> OperacionIso | None:
    return OPERACIONES_POR_MTI.get(mti)

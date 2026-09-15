"""Interfaz web: FastAPI con plantillas Jinja renderizadas en el servidor.

Capa deliberadamente delgada. **No** importa `aiosqlite`, `pyiso8583` ni
`asyncio`, no abre sockets, no arma mensajes ISO y no implementa ninguna de las
cuatro reglas: delega el recorrido en el orquestador que provee la composicion.

Tampoco levanta el host simulado. La arquitectura lo mantiene como proceso
aparte y la demostracion usa dos terminales: `sibu-host-demo` y `uvicorn`.

Las rutas viven en un `APIRouter` de modulo, no dentro de la fabrica: no
necesitan capturar nada del ambito de `crear_app`, y asi cada una se lee y se
prueba por separado.

La unica pieza estatica es la hoja de estilos propia y un script minimo de UX,
montados en `/estatico`. El script nunca decide una regla de negocio: el
servidor valida todo lo que llega, exista o no JavaScript en el cliente.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path
from typing import Callable, Mapping
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..application import exportacion_corridas
from ..application.conexiones import (
    ConexionNoEncontrada,
    DatosEdicionConexion,
    DatosNuevaConexion,
)
from ..application.comparacion_corridas import (
    CorridaNoEncontrada,
    CorridasDeSuitesDistintas,
    ItemsHistoricosDuplicados,
)
from ..application.corredor_suites import (
    CorridaOrigenNoEncontrada,
    SinItemsReintentables,
    SuiteNoEjecutable,
)
from ..application.ejecutor_escenarios import EscenarioNoEjecutable
from ..application.ejecutor_secuencia import SecuenciaNoEjecutable
from ..application.escenarios import (
    DatosEdicionEscenario,
    DatosNuevoEscenario,
    EscenarioNoEncontrado,
)
from ..application.orquestador import TarjetaDesconocida
from ..application.reglas_host import DatosNuevaRegla, ReglaHostNoEncontrada
from ..application.secuencias import DatosNuevaSecuencia, DatosPaso
from ..application.suites import DatosEdicionSuite, DatosNuevaSuite, SuiteNoEncontrada
from ..application.vista_previa import TarjetaNoDisponibleParaVistaPrevia
from ..application.tarjetas import (
    DatosEdicionTarjeta,
    DatosNuevaTarjeta,
    TarjetaNoEncontrada,
)
from ..composicion import Composicion, Configuracion
from ..domain.armado import validar_forma_de_opcionales
from ..domain.elegibilidad_reverso import puede_generar_operacion_derivada
from ..domain.errores import (
    EjecucionOrigenNoElegible,
    EjecucionOrigenNoEncontrada,
    ErrorDeCamposManuales,
    ErrorDelSimulador,
)
from ..domain.expectativas import (
    campos_permitidos_expectativa,
    expectativas_desde_dict,
    validar_expectativas,
)
from ..domain.modelos import (
    MTI_AVISO_REVERSO,
    MTI_COMPRA,
    MTI_COMPRA_FINANCIERA,
    MTI_ECHO,
    MTI_RESPUESTA_COMPRA,
    MTI_RESPUESTA_COMPRA_FINANCIERA,
    MTI_RESPUESTA_ECHO,
    ORIGEN_PASO_DERIVADO,
    ORIGEN_PASO_INDEPENDIENTE,
    OPERACION_COMPRA_FINANCIERA,
    OPERACION_ECHO,
    OPERACION_POR_MTI,
    DatosAvisoReverso,
    DatosCompra,
    DatosCompraFinanciera,
    DatosEcho,
    DatosReversoFinanciero,
    DestinoTcp,
    EstadoEjecucion,
    ExpectativaCampo,
    Expectativas,
    MensajeIso,
)
from ..domain.reglas_host import (
    ComportamientoRegla,
    CondicionRegla,
    TipoComportamiento,
)
from . import presentacion
from .operaciones import (
    OPERACIONES_CON_TARJETA,
    OPERACION_AUTORIZACION,
    OPERACION_FINANCIERA,
    OperacionIso,
    operacion_por_mti,
)

RAIZ_WEB = Path(__file__).parent
PLANTILLAS = Jinja2Templates(directory=str(RAIZ_WEB / "plantillas"))
DIRECTORIO_ESTATICO = RAIZ_WEB / "estatico"
RUTA_ESTATICA = "/estatico"

# La navegacion es la misma en todas las pantallas: se declara una vez como
# global de Jinja en lugar de repetirla en el contexto de cada endpoint. La
# pantalla activa si es propia de cada ruta y viaja en su contexto (`seccion`).
PLANTILLAS.env.globals["secciones"] = presentacion.SECCIONES
PLANTILLAS.env.globals["grupos_nav"] = presentacion.GRUPOS_NAV
PLANTILLAS.env.globals["ruta_activa"] = presentacion.ruta_activa
PLANTILLAS.env.globals["etiqueta_operacion"] = presentacion.etiqueta_operacion
PLANTILLAS.env.globals["OPERACION_ECHO"] = OPERACION_ECHO
PLANTILLAS.env.globals["ruta_pantalla_por_operacion"] = presentacion.RUTA_PANTALLA_POR_OPERACION
PLANTILLAS.env.globals["operacion_por_mti"] = OPERACION_POR_MTI

enrutador = APIRouter()

_composicion: Composicion | None = None


def obtener_composicion() -> Composicion:
    """Dependencia unica de infraestructura. Las pruebas la sustituyen."""
    global _composicion
    if _composicion is None:
        _composicion = Composicion(Configuracion.desde_entorno())
    return _composicion


@enrutador.get("/", response_class=HTMLResponse)
async def pantalla_compra(
    request: Request,
    # Query, no Form: son enlaces sueltos (historial, escenarios), no el envio
    # de un formulario. Cambiar de conexion sin perder lo escrito usa un
    # mecanismo aparte -ver `_cambiar_conexion_operacion`, POST- precisamente
    # para que los valores del constructor no viajen en la URL.
    conexion_id: str | None = Query(None),
    escenario_id: str | None = Query(None),
    # Presente cuando se llega desde "Editar y volver a ejecutar" o "Guardar
    # como escenario" del resultado de una ejecucion pasada (`/historial/{id}`
    # y `resultado.html` enlazan aqui). Se ignora si la navegacion ya trae
    # `escenario_id` (cargar un escenario sigue siendo la fuente de verdad
    # para ese caso).
    ejecucion_id: str | None = Query(None),
    composicion: Composicion = Depends(obtener_composicion),
):
    return await _pantalla_operacion(
        request, composicion, OPERACION_AUTORIZACION,
        conexion_id=conexion_id, escenario_id=escenario_id, ejecucion_id=ejecucion_id,
    )


@enrutador.post("/", response_class=HTMLResponse)
async def cambiar_conexion(
    request: Request,
    composicion: Composicion = Depends(obtener_composicion),
):
    """Cambia la conexion elegida en el constructor SIN perder lo que ya
    estaba escrito -tarjeta, monto, campos editables, expectativas, nombre
    del escenario- y SIN ejecutar ninguna transaccion ni guardar ningun
    escenario. Ver `_cambiar_conexion_operacion` (comun a cualquier
    operacion con tarjeta, B5) para el detalle del mecanismo POST/"+ Agregar
    campo"/"Quitar".
    """
    return await _cambiar_conexion_operacion(request, composicion, OPERACION_AUTORIZACION)


@enrutador.post("/compra", response_class=HTMLResponse)
async def ejecutar_compra(
    request: Request,
    # Los campos admiten cadena vacia a proposito: si se declararan obligatorios,
    # FastAPI responderia su propio 422 en JSON y el usuario veria un error crudo
    # en vez del formulario con la explicacion.
    card_id: str = Form(""),
    monto: str = Form(""),
    conexion_id: str = Form(""),
    # Presente solo cuando el constructor se cargo desde un escenario: viaja
    # oculto en el mismo formulario para que "Ejecutar transacción" deje
    # trazabilidad en el historial sin que el usuario tenga que hacer nada
    # aparte. Nunca se usa para resolver card_id/conexion_id/campos -esos
    # siguen viniendo del formulario, validados exactamente igual que siempre-.
    escenario_id: str = Form(""),
    composicion: Composicion = Depends(obtener_composicion),
):
    return await _ejecutar_operacion(
        request, composicion, OPERACION_AUTORIZACION,
        card_id=card_id, monto=monto, conexion_id=conexion_id, escenario_id=escenario_id,
    )


# ----------------------------------------------------------------- Echo (B2/B3) --
#
# Segunda operacion real sobre el nucleo generico (Orquestador._ejecutar, B1):
# Network Management/Echo (0800/0810). Deliberadamente una pantalla propia, no
# una pestana dentro de "Nueva transaccion": esta operacion no tiene tarjeta,
# monto, comercio ni campos opcionales -entrelazarla con `compra.html`/
# `_formulario` (que administra tarjeta/monto/campos opcionales, ajenos a
# echo) hubiera significado condicionar buena parte de esa logica por
# operacion, exactamente el tipo de acoplamiento que se queria evitar.
#
# B3 cierra la integracion con escenarios/expectativas que B2 dejaba pendiente
# (`_formulario_echo` ahora admite `escenario_id` igual que `_formulario`, y
# las expectativas se leen/evaluan con el mismo motor generico, solo que
# contra `MTI_RESPUESTA_ECHO`): Compra y Echo comparten el mismo ciclo crear
# -> guardar escenario -> editar/reutilizar -> expected vs actual -> suite,
# sin que `application/escenarios.py` dependa de Compra.


@enrutador.get("/echo", response_class=HTMLResponse)
async def pantalla_echo(
    request: Request,
    conexion_id: str | None = Query(None),
    escenario_id: str | None = Query(None),
    # Igual que en `pantalla_compra` (B4, punto 25): "Editar y volver a
    # ejecutar"/"Guardar como escenario" desde un resultado de echo ahora
    # reconstruyen esta pantalla, no solo la de compra.
    ejecucion_id: str | None = Query(None),
    composicion: Composicion = Depends(obtener_composicion),
):
    try:
        enviado, conexion_id_resuelta, error_carga = await _resolver_reutilizacion_de_ejecucion(
            composicion, ejecucion_id, escenario_id
        )
    except _EjecucionNoReutilizable:
        return await _formulario_echo(
            request, composicion,
            error="La ejecución que se quiere reutilizar no existe o ya no está disponible.",
            estado_http=404,
        )
    if conexion_id_resuelta is not None:
        conexion_id = conexion_id_resuelta
    return await _formulario_echo(
        request, composicion, conexion_id=conexion_id, escenario_id=escenario_id,
        enviado=enviado, error=error_carga,
    )


@enrutador.post("/echo", response_class=HTMLResponse)
async def cambiar_conexion_echo(
    request: Request,
    composicion: Composicion = Depends(obtener_composicion),
):
    """Cambia la conexion o actualiza la vista previa sin ejecutar nada -mismo
    mecanismo que `cambiar_conexion` para compra."""
    formulario_bruto = await request.form()
    ir_a_conexion = (formulario_bruto.get("ir_a_conexion", "") or "").strip() or None
    escenario_id = (formulario_bruto.get("escenario_id", "") or "").strip() or None
    enviado = _leer_enviado_echo(formulario_bruto, composicion.perfil)
    return await _formulario_echo(
        request, composicion, conexion_id=ir_a_conexion, escenario_id=escenario_id, enviado=enviado,
    )


@enrutador.post("/echo/ejecutar", response_class=HTMLResponse)
async def ejecutar_echo(
    request: Request,
    conexion_id: str = Form(""),
    de70: str = Form(""),
    # Mismo mecanismo de trazabilidad que `escenario_id` en `/compra`: viaja
    # oculto en el formulario solo cuando la pantalla se cargo desde un
    # escenario guardado.
    escenario_id: str = Form(""),
    composicion: Composicion = Depends(obtener_composicion),
):
    formulario_bruto = await request.form()
    campos_manuales = {"70": de70.strip()} if de70.strip() else {}

    try:
        expectativas = _leer_expectativas(formulario_bruto, composicion.perfil, mti_respuesta=MTI_RESPUESTA_ECHO)
    except ValueError as error:
        return await _formulario_echo(
            request, composicion, conexion_id=conexion_id or None, escenario_id=escenario_id or None,
            de70=de70, error=str(error), estado_http=400,
        )

    conexion = await composicion.administracion_conexiones.obtener_activa(conexion_id)
    if conexion is None:
        return await _formulario_echo(
            request, composicion, conexion_id=conexion_id or None, escenario_id=escenario_id or None,
            de70=de70, error="Seleccione una conexión activa, o verifique que siga disponible.",
            estado_http=400,
        )
    destino = DestinoTcp(host=conexion.host, puerto=conexion.puerto)

    # El escenario asociado (si lo hay) se resuelve aqui, no antes -mismo
    # criterio que `ejecutar_compra`-: si ya no existe, la ejecucion sigue
    # adelante sin trazabilidad en vez de fallar por una referencia vieja.
    id_escenario_asociado: str | None = None
    nombre_escenario_asociado: str | None = None
    if escenario_id:
        escenario_asociado = await composicion.administracion_escenarios.obtener(escenario_id)
        if escenario_asociado is not None:
            if not escenario_asociado.activo:
                return await _formulario_echo(
                    request, composicion, conexion_id=conexion_id or None, escenario_id=escenario_id,
                    de70=de70,
                    error="Este escenario está inactivo. Reactívelo para poder ejecutarlo, "
                    "o guarde una copia.",
                    estado_http=400,
                )
            id_escenario_asociado = escenario_asociado.escenario_id
            nombre_escenario_asociado = escenario_asociado.nombre

    try:
        orquestador = await composicion.orquestador(destino, tiempo_limite=conexion.timeout)
        resultado = await orquestador.ejecutar_network_echo(
            DatosEcho(campos_manuales=campos_manuales),
            escenario_id=id_escenario_asociado,
            escenario_nombre=nombre_escenario_asociado,
            expectativas=expectativas,
        )
    except ErrorDelSimulador as error:
        return await _formulario_echo(
            request, composicion, conexion_id=conexion_id or None, escenario_id=escenario_id or None,
            de70=de70, aviso=presentacion.aviso_de_error(error),
        )

    return PLANTILLAS.TemplateResponse(
        request=request,
        name="resultado.html",
        context=presentacion.contexto_de_resultado(
            resultado, destino, composicion.descripciones_de_campos,
            bitmap_solicitud=composicion.bitmap_hex(resultado.solicitud),
            bitmap_respuesta=(
                composicion.bitmap_hex(resultado.respuesta.como_mensaje())
                if resultado.respuesta else None
            ),
            raw_solicitud=composicion.raw_hex_seguro(resultado.solicitud),
            raw_respuesta=(
                composicion.raw_hex_seguro(resultado.respuesta.como_mensaje())
                if resultado.respuesta else None
            ),
            seccion="echo",
        ),
    )


async def _formulario_echo(
    request: Request,
    composicion: Composicion,
    *,
    conexion_id: str | None = None,
    escenario_id: str | None = None,
    de70: str = "",
    enviado: dict | None = None,
    error: str | None = None,
    aviso=None,
    estado_http: int = 200,
):
    """Renderiza la pantalla de echo, opcionalmente con un aviso o un error.

    Mismo principio de "nunca sustituir en silencio" que `_formulario`: si se
    pidio una conexion especifica y no esta entre las activas, se deja sin
    resolver -el boton de ejecutar queda deshabilitado con una nota-, en vez
    de elegir otra por su cuenta. B3: ahora tambien admite cargar un
    escenario guardado (sin tarjeta ni monto, esta operacion nunca los usa) y
    definir/mostrar expectativas -mismo motor generico que compra, sin ningun
    evaluador especial para echo-.
    """
    conexiones = await composicion.administracion_conexiones.listar_activas()
    enviado = enviado or {}

    escenario_actual = None
    diagnostico = None
    if escenario_id:
        escenario_actual = await composicion.administracion_escenarios.obtener(escenario_id)
        if escenario_actual is not None:
            diagnostico = await composicion.administracion_escenarios.diagnosticar(
                escenario_actual
            )

    if enviado:
        de70_valor = enviado.get("de70", de70)
        conexion_id_solicitada = (
            conexion_id if conexion_id is not None else enviado.get("conexion_id")
        )
        nombre_escenario = enviado.get(
            "nombre_escenario", escenario_actual.nombre if escenario_actual else ""
        )
        expectativas_actuales = enviado.get(
            "expectativas", escenario_actual.expectativas if escenario_actual else None
        )
    elif escenario_actual is not None:
        de70_valor = de70 or escenario_actual.campos_manuales.get("70", "")
        conexion_id_solicitada = (
            conexion_id if conexion_id is not None else escenario_actual.conexion_id
        )
        nombre_escenario = escenario_actual.nombre
        expectativas_actuales = escenario_actual.expectativas
    else:
        de70_valor = de70
        conexion_id_solicitada = conexion_id
        nombre_escenario = ""
        expectativas_actuales = None

    conexion_no_disponible = False
    if conexion_id_solicitada:
        conexion_actual = next(
            (c for c in conexiones if c.conexion_id == conexion_id_solicitada), None
        )
        if conexion_actual is None:
            conexion_no_disponible = True
    else:
        conexion_actual = conexiones[0] if conexiones else None

    bloqueo_escenario = None
    if escenario_actual is not None:
        bloqueo_escenario = {
            "inactivo": not escenario_actual.activo,
            "conexion_no_disponible": conexion_no_disponible,
            "incompatibilidades": diagnostico.incompatibilidades if diagnostico else (),
        }

    puede_ejecutar = conexion_actual is not None and not (
        bloqueo_escenario
        and (bloqueo_escenario["inactivo"] or bloqueo_escenario["incompatibilidades"])
    )

    politica_echo = composicion.perfil.politica(MTI_ECHO)
    de70_default = politica_echo.valores_por_defecto.get("70", "")

    campos_manuales = {"70": de70_valor.strip()} if de70_valor.strip() else {}
    vista_previa = None
    vista_previa_no_disponible = None
    try:
        vista_previa = await composicion.vista_previa_echo.construir(
            DatosEcho(campos_manuales=campos_manuales)
        )
    except ErrorDeCamposManuales as error_campos:
        vista_previa_no_disponible = str(error_campos)

    campos_esperados = expectativas_actuales.campos if expectativas_actuales else {}
    estado_esperado_actual = (
        expectativas_actuales.estado.value
        if expectativas_actuales and expectativas_actuales.estado
        else ""
    )

    return PLANTILLAS.TemplateResponse(
        request=request,
        name="echo.html",
        context={
            "seccion": "echo",
            "conexiones": conexiones,
            "conexion_actual": conexion_actual,
            "de70": de70_valor,
            "de70_default": de70_default,
            "filas_constructor": presentacion.filas_constructor(
                composicion.perfil, MTI_ECHO, composicion.descripciones_de_campos,
            ),
            "error": error,
            "aviso": aviso,
            "escenario_actual": escenario_actual,
            "nombre_escenario": nombre_escenario,
            "bloqueo_escenario": bloqueo_escenario,
            "puede_ejecutar": puede_ejecutar,
            "mti_echo": MTI_ECHO,
            "estados_ejecucion": list(EstadoEjecucion),
            "avisos": presentacion.AVISOS,
            "estado_esperado_actual": estado_esperado_actual,
            "filas_expectativas": presentacion.filas_expectativas(
                composicion.perfil, MTI_RESPUESTA_ECHO, composicion.descripciones_de_campos,
                campos_esperados,
            ),
            "vista_previa": presentacion.contexto_de_vista_previa(
                vista_previa, composicion.descripciones_de_campos
            ) if vista_previa else None,
            "vista_previa_no_disponible": vista_previa_no_disponible,
        },
        status_code=estado_http,
    )


# ------------------------------------------------- Compra financiera (B4) --
#
# Tercera operacion real, y la que motivo B5: `/` y `/financiera` compartian
# ~90% del mismo formulario (tarjeta, monto, conexion, preview, expectativas,
# guardar escenario), con solo el MTI/textos/rutas de ejecucion realmente
# distintos. B5 extrae eso a un unico renderizador (`_pantalla_operacion`/
# `_cambiar_conexion_operacion`/`_ejecutar_operacion`, mas abajo) parametrizado
# por `OperacionIso` (web/operaciones.py) y una unica plantilla
# (`editor_transaccion.html`) -las rutas siguen existiendo, cada una solo le
# pasa SU `OperacionIso` al renderizador comun. Agregar una tercera operacion
# con tarjeta es agregar una entrada a `OPERACIONES_CON_TARJETA`, no copiar
# esta seccion.


@enrutador.get("/financiera", response_class=HTMLResponse)
async def pantalla_compra_financiera(
    request: Request,
    conexion_id: str | None = Query(None),
    escenario_id: str | None = Query(None),
    # Igual que en `pantalla_compra`/`pantalla_echo` (B4, punto 25).
    ejecucion_id: str | None = Query(None),
    composicion: Composicion = Depends(obtener_composicion),
):
    return await _pantalla_operacion(
        request, composicion, OPERACION_FINANCIERA,
        conexion_id=conexion_id, escenario_id=escenario_id, ejecucion_id=ejecucion_id,
    )


@enrutador.post("/financiera", response_class=HTMLResponse)
async def cambiar_conexion_financiera(
    request: Request,
    composicion: Composicion = Depends(obtener_composicion),
):
    """Cambia la conexion o actualiza la vista previa sin ejecutar nada -mismo
    mecanismo que `cambiar_conexion` para compra (`_cambiar_conexion_operacion`)."""
    return await _cambiar_conexion_operacion(request, composicion, OPERACION_FINANCIERA)


@enrutador.post("/financiera/ejecutar", response_class=HTMLResponse)
async def ejecutar_compra_financiera(
    request: Request,
    card_id: str = Form(""),
    monto: str = Form(""),
    conexion_id: str = Form(""),
    escenario_id: str = Form(""),
    composicion: Composicion = Depends(obtener_composicion),
):
    return await _ejecutar_operacion(
        request, composicion, OPERACION_FINANCIERA,
        card_id=card_id, monto=monto, conexion_id=conexion_id, escenario_id=escenario_id,
    )


async def _pantalla_operacion(
    request: Request,
    composicion: Composicion,
    operacion: OperacionIso,
    *,
    conexion_id: str | None,
    escenario_id: str | None,
    ejecucion_id: str | None,
):
    """GET comun a cualquier operacion con tarjeta (B5): resuelve
    `?ejecucion_id=` (reutilizar una ejecucion pasada) igual que ya hacia
    cada pantalla por separado, y delega el render en `_formulario_operacion`.
    """
    try:
        enviado, conexion_id_resuelta, error_carga = await _resolver_reutilizacion_de_ejecucion(
            composicion, ejecucion_id, escenario_id
        )
    except _EjecucionNoReutilizable:
        return await _formulario_operacion(
            request, composicion, operacion,
            error="La ejecución que se quiere reutilizar no existe o ya no está disponible.",
            estado_http=404,
        )
    if conexion_id_resuelta is not None:
        conexion_id = conexion_id_resuelta

    return await _formulario_operacion(
        request, composicion, operacion,
        conexion_id=conexion_id, escenario_id=escenario_id, enviado=enviado, error=error_carga,
    )


async def _cambiar_conexion_operacion(request: Request, composicion: Composicion, operacion: OperacionIso):
    """POST comun a cualquier operacion con tarjeta (B5): cambia la conexion,
    actualiza la vista previa, o agrega/quita un campo opcional -todo sin
    ejecutar la operacion ni guardar ningun escenario. Es el destino de
    `formaction="{{ operacion.ruta }}"` en `editor_transaccion.html`.

    POST y no GET a proposito -mismo motivo documentado originalmente para
    compra-: por diseño un envio POST no queda en la URL ni en el historial
    del navegador, y los frameworks de servidor no registran el cuerpo de la
    peticion en el log de acceso -solo metodo y ruta-.
    """
    formulario_bruto = await request.form()
    enviado = _leer_enviado(
        formulario_bruto, composicion.perfil, mti=operacion.mti, mti_respuesta=operacion.mti_respuesta
    )
    ir_a_conexion = (formulario_bruto.get("ir_a_conexion", "") or "").strip() or None
    escenario_id = (formulario_bruto.get("escenario_id", "") or "").strip() or None

    # "+ Agregar campo"/"Quitar" tambien resuelven por este mismo POST -mismo
    # criterio que "Cambiar conexion": todo el formulario viaja en el cuerpo,
    # se reconstruye la pantalla con el estado actualizado, y no se ejecuta
    # ninguna transaccion. Solo tocan que filas se MUESTRAN; el perfil sigue
    # siendo quien decide que numeros son validos -ver `_leer_opcionales_activos`-.
    politica = composicion.perfil.politica(operacion.mti)
    opcionales_activos = set(enviado["opcionales_activos"])
    # `candidato_opcional` (el <select>) viaja siempre que se somete el
    # formulario, pulse el usuario el boton que pulse: por eso el disparador
    # real es la presencia del propio boton "agregar_opcional" -solo aporta
    # su name=value cuando ES el que se pulso-, nunca el valor del select por
    # si solo.
    if "agregar_opcional" in formulario_bruto:
        candidato = (formulario_bruto.get("candidato_opcional", "") or "").strip()
        if candidato in politica.opcionales:
            opcionales_activos.add(candidato)
    quitar = (formulario_bruto.get("quitar_opcional", "") or "").strip()
    if quitar:
        opcionales_activos.discard(quitar)
        enviado["campos_manuales"].pop(quitar, None)
    enviado["opcionales_activos"] = frozenset(opcionales_activos)

    return await _formulario_operacion(
        request, composicion, operacion,
        conexion_id=ir_a_conexion, escenario_id=escenario_id, enviado=enviado,
    )


async def _ejecutar_operacion(
    request: Request,
    composicion: Composicion,
    operacion: OperacionIso,
    *,
    card_id: str,
    monto: str,
    conexion_id: str,
    escenario_id: str,
):
    """POST que SI ejecuta una operacion con tarjeta (B5): mismo recorrido
    para Autorizacion y Compra financiera -leer el formulario, interpretar,
    resolver el escenario asociado si lo hay, delegar en el metodo de
    `Orquestador` que `operacion.metodo_orquestador` nombra-. El orquestador
    sigue siendo quien arma el mensaje y aplica RN-1..RN-4; esta funcion solo
    orquesta la peticion HTTP.
    """
    formulario_bruto = await request.form()
    enviado = _leer_enviado(
        formulario_bruto, composicion.perfil, mti=operacion.mti, mti_respuesta=operacion.mti_respuesta
    )
    campos_manuales = enviado["campos_manuales"]
    expectativas = enviado["expectativas"]

    try:
        datos, destino, tiempo_limite = await _interpretar_formulario_operacion(
            composicion, operacion, card_id, monto, conexion_id, campos_manuales
        )
        expectativas = _leer_expectativas(formulario_bruto, composicion.perfil, operacion.mti_respuesta)
        if expectativas is not None:
            validar_expectativas(expectativas, composicion.perfil, operacion.mti_respuesta)
    except ValueError as error:
        return await _formulario_operacion(
            request, composicion, operacion, escenario_id=escenario_id or None,
            error=str(error), enviado=enviado, estado_http=400,
        )

    # El escenario asociado (si lo hay) se resuelve aqui, no antes: si ya no
    # existe, la ejecucion sigue adelante sin trazabilidad en vez de fallar
    # por una referencia que quedo vieja. Si esta inactivo, "no se reejecuta"
    # tambien aplica cuando la ejecucion pasa por el constructor, no solo en
    # la reejecucion directa.
    id_escenario_asociado: str | None = None
    nombre_escenario_asociado: str | None = None
    if escenario_id:
        escenario_asociado = await composicion.administracion_escenarios.obtener(escenario_id)
        if escenario_asociado is not None:
            if not escenario_asociado.activo:
                return await _formulario_operacion(
                    request, composicion, operacion, escenario_id=escenario_id,
                    error="Este escenario está inactivo. Reactívelo para poder ejecutarlo, "
                    "o guarde una copia.",
                    enviado=enviado, estado_http=400,
                )
            id_escenario_asociado = escenario_asociado.escenario_id
            nombre_escenario_asociado = escenario_asociado.nombre

    # --- el recorrido lo hace el orquestador, no esta capa ---
    try:
        orquestador = await composicion.orquestador(destino, tiempo_limite=tiempo_limite)
        metodo = getattr(orquestador, operacion.metodo_orquestador)
        resultado = await metodo(
            datos, escenario_id=id_escenario_asociado, escenario_nombre=nombre_escenario_asociado,
            expectativas=expectativas,
        )
    except TarjetaDesconocida:
        return await _formulario_operacion(
            request, composicion, operacion, escenario_id=escenario_id or None,
            error=f"No existe la tarjeta {card_id!r} en el catálogo, o está inactiva.",
            enviado=enviado, estado_http=400,
        )
    except ErrorDelSimulador as error:
        # Fallo de infraestructura: no es un rechazo del autorizador y no debe
        # presentarse como tal. Tampoco se muestra la excepcion.
        return await _formulario_operacion(
            request, composicion, operacion, escenario_id=escenario_id or None,
            aviso=presentacion.aviso_de_error(error), enviado=enviado,
        )

    return PLANTILLAS.TemplateResponse(
        request=request,
        name="resultado.html",
        context=presentacion.contexto_de_resultado(
            resultado, destino, composicion.descripciones_de_campos,
            bitmap_solicitud=composicion.bitmap_hex(resultado.solicitud),
            bitmap_respuesta=(
                composicion.bitmap_hex(resultado.respuesta.como_mensaje())
                if resultado.respuesta else None
            ),
            raw_solicitud=composicion.raw_hex_seguro(resultado.solicitud),
            raw_respuesta=(
                composicion.raw_hex_seguro(resultado.respuesta.como_mensaje())
                if resultado.respuesta else None
            ),
            seccion=operacion.seccion,
        ),
    )


async def _formulario_operacion(
    request: Request,
    composicion: Composicion,
    operacion: OperacionIso,
    *,
    conexion_id: str | None = None,
    escenario_id: str | None = None,
    error: str | None = None,
    aviso=None,
    enviado: dict | None = None,
    estado_http: int = 200,
):
    """Renderiza el editor de una operacion con tarjeta (B5): unico
    renderizador para Autorizacion (0100) y Compra financiera (0200) -antes
    de B5, `_formulario`/`_formulario_financiera` eran casi el mismo cuerpo
    con el MTI/plantilla cambiados a mano.

    Ni la conexion ni el escenario cargado viven en una sesion ni en una
    cookie: llegan por query string en el GET normal (`?conexion_id=`,
    `?escenario_id=`), o por el propio `enviado` cuando se re-renderiza tras
    un error de un POST.

    REGLA DE NO SUSTITUCION SILENCIOSA: si se pidio una tarjeta o una conexion
    especificas (por query, por `enviado`, o por venir de un escenario) y esa
    tarjeta/conexion no esta entre las activas, NO se reemplaza por la primera
    disponible -eso cambiaria la intencion sin que nadie lo haya pedido-. Se
    deja sin resolver y se bloquea el boton de ejecucion hasta que alguien
    elija otra a mano. Solo cuando NO se pidio ninguna en particular se
    preselecciona la primera activa, igual que siempre.
    """
    conexiones = await composicion.administracion_conexiones.listar_activas()
    tarjetas = await composicion.consultas.tarjetas()
    enviado = enviado or {}

    escenario_actual = None
    diagnostico = None
    if escenario_id:
        escenario_actual = await composicion.administracion_escenarios.obtener(escenario_id)
        if escenario_actual is not None:
            diagnostico = await composicion.administracion_escenarios.diagnosticar(
                escenario_actual
            )

    politica = composicion.perfil.politica(operacion.mti)

    if enviado:
        card_id = enviado.get("card_id", "")
        monto = enviado.get("monto", "")
        campos_manuales_enviados = enviado.get("campos_manuales", {})
        opcionales_activos = enviado.get("opcionales_activos") or frozenset(
            n for n in campos_manuales_enviados if politica.origen(n) == "opcional"
        )
        conexion_id_solicitada = (
            conexion_id if conexion_id is not None else enviado.get("conexion_id")
        )
        nombre_escenario = enviado.get(
            "nombre_escenario", escenario_actual.nombre if escenario_actual else ""
        )
        expectativas_actuales = enviado.get(
            "expectativas", escenario_actual.expectativas if escenario_actual else None
        )
    elif escenario_actual is not None:
        card_id = escenario_actual.card_id
        monto = str(escenario_actual.monto)
        campos_manuales_enviados = dict(escenario_actual.campos_manuales)
        opcionales_activos = frozenset(
            n for n in campos_manuales_enviados if politica.origen(n) == "opcional"
        )
        conexion_id_solicitada = (
            conexion_id if conexion_id is not None else escenario_actual.conexion_id
        )
        nombre_escenario = escenario_actual.nombre
        expectativas_actuales = escenario_actual.expectativas
    else:
        card_id = ""
        monto = ""
        campos_manuales_enviados = {}
        opcionales_activos = frozenset()
        conexion_id_solicitada = conexion_id
        nombre_escenario = ""
        expectativas_actuales = None

    # --- conexion: nunca se sustituye en silencio una pedida explicitamente ---
    conexion_no_disponible = False
    if conexion_id_solicitada:
        conexion_actual = next(
            (c for c in conexiones if c.conexion_id == conexion_id_solicitada), None
        )
        if conexion_actual is None:
            conexion_no_disponible = True
    else:
        conexion_actual = conexiones[0] if conexiones else None

    # --- tarjeta: mismo principio; el radio simplemente no queda marcado ---
    tarjeta_no_disponible = bool(card_id) and not any(t.card_id == card_id for t in tarjetas)

    bloqueo_escenario = None
    if escenario_actual is not None:
        bloqueo_escenario = {
            "inactivo": not escenario_actual.activo,
            "tarjeta_no_disponible": tarjeta_no_disponible,
            "conexion_no_disponible": conexion_no_disponible,
            "incompatibilidades": diagnostico.incompatibilidades if diagnostico else (),
        }

    puede_ejecutar = (
        conexion_actual is not None
        and not tarjeta_no_disponible
        and not (
            bloqueo_escenario
            and (bloqueo_escenario["inactivo"] or bloqueo_escenario["incompatibilidades"])
        )
    )

    campos_esperados = expectativas_actuales.campos if expectativas_actuales else {}
    estado_esperado_actual = (
        expectativas_actuales.estado.value
        if expectativas_actuales and expectativas_actuales.estado
        else ""
    )

    vista_previa, vista_previa_no_disponible = await _construir_vista_previa(
        composicion, card_id, monto, campos_manuales_enviados,
        servicio_vista_previa=getattr(composicion, operacion.atributo_vista_previa),
        fabrica_datos=operacion.datos_cls,
    )

    return PLANTILLAS.TemplateResponse(
        request=request,
        name="editor_transaccion.html",
        context={
            "operacion": operacion,
            "seccion": operacion.seccion,
            "tarjetas": tarjetas,
            "conexiones": conexiones,
            "conexion_actual": conexion_actual,
            "conexion_id": (
                conexion_actual.conexion_id if conexion_actual else (conexion_id_solicitada or "")
            ),
            "monto": monto,
            "card_id": card_id,
            "filas_constructor": presentacion.filas_constructor(
                composicion.perfil, operacion.mti, composicion.descripciones_de_campos,
                opcionales_activos,
            ),
            "campos_opcionales_disponibles": presentacion.campos_opcionales_disponibles(
                composicion.perfil, operacion.mti, composicion.descripciones_de_campos,
                opcionales_activos,
            ),
            "opcionales_activos_csv": ",".join(sorted(opcionales_activos, key=int)),
            "campos_manuales": campos_manuales_enviados,
            "error": error,
            "aviso": aviso,
            "escenario_actual": escenario_actual,
            "nombre_escenario": nombre_escenario,
            "bloqueo_escenario": bloqueo_escenario,
            "puede_ejecutar": puede_ejecutar,
            "estados_ejecucion": list(EstadoEjecucion),
            "avisos": presentacion.AVISOS,
            "estado_esperado_actual": estado_esperado_actual,
            "filas_expectativas": presentacion.filas_expectativas(
                composicion.perfil, operacion.mti_respuesta, composicion.descripciones_de_campos,
                campos_esperados,
            ),
            "vista_previa": presentacion.contexto_de_vista_previa(
                vista_previa, composicion.descripciones_de_campos
            ) if vista_previa else None,
            "vista_previa_no_disponible": vista_previa_no_disponible,
        },
        status_code=estado_http,
    )


async def _interpretar_formulario_operacion(
    composicion: Composicion,
    operacion: OperacionIso,
    card_id: str,
    monto: str,
    conexion_id: str,
    campos_manuales: dict[str, str],
):
    """Convierte el formulario en objetos del dominio para cualquier
    operacion con tarjeta (B5). Lanza `ValueError` util. Mismas reglas de
    entrada para Autorizacion y Compra financiera -ambas exigen tarjeta y
    monto-; lo unico que cambia por operacion es el tipo de `DatosX` que se
    construye (`operacion.datos_cls`) y la metadata de forma que valida los
    opcionales (`operacion.atributo_metadatos_campos`).
    """
    if not card_id.strip():
        raise ValueError("Seleccione una tarjeta de prueba.")
    validar_forma_de_opcionales(
        campos_manuales, composicion.perfil, operacion.mti,
        getattr(composicion, operacion.atributo_metadatos_campos),
    )
    datos = operacion.datos_cls(
        card_id=card_id.strip(),
        monto=presentacion.validar_monto(monto),
        campos_manuales=campos_manuales,
    )

    conexion = await composicion.administracion_conexiones.obtener_activa(conexion_id)
    if conexion is None:
        raise ValueError("Seleccione una conexión activa, o verifique que siga disponible.")

    destino = DestinoTcp(host=conexion.host, puerto=conexion.puerto)
    return datos, destino, conexion.timeout


@enrutador.get("/historial", response_class=HTMLResponse)
async def historial(
    request: Request,
    pagina: int = Query(1, ge=1),
    desde: str = Query(""),
    hasta: str = Query(""),
    estado: str = Query(""),
    evaluacion: str = Query(""),
    card_id: str = Query(""),
    destino: str = Query(""),
    stan: str = Query(""),
    composicion: Composicion = Depends(obtener_composicion),
):
    filtro_bruto = {
        "desde": desde, "hasta": hasta, "estado": estado, "evaluacion": evaluacion,
        "card_id": card_id, "destino": destino, "stan": stan,
    }
    try:
        filtro = presentacion.leer_filtro_historial(**filtro_bruto)
    except ValueError as error:
        return PLANTILLAS.TemplateResponse(
            request=request,
            name="historial.html",
            context={
                "seccion": "historial",
                "pagina_resultado": None,
                "filtro_valores": filtro_bruto,
                "estados_ejecucion": list(EstadoEjecucion),
                "avisos": presentacion.AVISOS,
                "error": str(error),
            },
            status_code=400,
        )

    pagina_resultado = await composicion.consultas.historial(filtro, pagina=pagina)
    # La paginacion preserva los filtros en la URL -no una sesion ni una
    # cookie-: cada enlace "Anterior"/"Siguiente" repite exactamente los
    # mismos parametros que ya trae esta peticion.
    query_filtros = urlencode({clave: valor for clave, valor in filtro_bruto.items() if valor})
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="historial.html",
        context={
            "seccion": "historial",
            "pagina_resultado": pagina_resultado,
            "filtro_valores": filtro_bruto,
            "hay_filtros": not filtro.vacio(),
            "estados_ejecucion": list(EstadoEjecucion),
            "avisos": presentacion.AVISOS,
            "query_filtros": query_filtros,
        },
    )


@enrutador.get("/historial/{id_ejecucion}", response_class=HTMLResponse)
async def detalle_ejecucion(
    request: Request,
    id_ejecucion: str,
    composicion: Composicion = Depends(obtener_composicion),
):
    """Detalle de una ejecucion ya registrada.

    El identificador se recibe como cadena **a proposito**, igual que los campos
    del formulario: declarado como `int`, FastAPI responderia su propio 422 en
    JSON ante `/historial/abc` y el usuario veria un error crudo en vez de una
    pagina del producto. Convertirlo aqui deja los dos casos —no numerico y no
    existente— en la misma respuesta 404 con HTML propio.
    """
    try:
        numero = int(id_ejecucion)
    except ValueError:
        return _no_encontrado(request)

    detalle = await composicion.consultas.detalle_ejecucion(numero)
    if detalle is None:
        return _no_encontrado(request)

    mensaje_solicitud = _reconstruir_mensaje_persistido(
        detalle.ejecucion.mti_solicitud, detalle.solicitud
    )
    mensaje_respuesta = _reconstruir_mensaje_persistido(
        detalle.ejecucion.mti_respuesta, detalle.respuesta
    )
    # B6: modelo de operacion derivada (indicador + navegacion). B7 conecta
    # el indicador a una accion real: "Crear reverso" (ver rutas debajo).
    derivadas = await composicion.consultas.derivadas_de(numero)
    elegible_para_derivada = puede_generar_operacion_derivada(detalle.ejecucion)
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="detalle.html",
        context=presentacion.contexto_de_detalle(
            detalle, composicion.descripciones_de_campos,
            bitmap_solicitud=composicion.bitmap_hex(mensaje_solicitud) if mensaje_solicitud else None,
            bitmap_respuesta=composicion.bitmap_hex(mensaje_respuesta) if mensaje_respuesta else None,
            raw_solicitud=composicion.raw_hex_seguro(mensaje_solicitud) if mensaje_solicitud else None,
            raw_respuesta=composicion.raw_hex_seguro(mensaje_respuesta) if mensaje_respuesta else None,
            derivadas=derivadas,
            elegible_para_derivada=elegible_para_derivada,
        ),
    )


@enrutador.get("/historial/{id_ejecucion}/reverso", response_class=HTMLResponse)
async def reverso_preview(
    request: Request,
    id_ejecucion: str,
    composicion: Composicion = Depends(obtener_composicion),
):
    """Vista previa del reverso financiero (0400, B7): la persona ve QUÉ se
    va a enviar antes de ejecutar -nunca se ejecuta directamente desde el
    detalle historico (B7, punto 3)-.

    La elegibilidad se revalida aqui (via `ServicioVistaPreviaReversoFinanciero`
    -> `referencia_origen_elegible`, B6/B7): un id inexistente o no elegible
    nunca llega a construir un mensaje, sin importar si alguien llega a esta
    URL sin haber pasado por el boton "Crear reverso" del detalle.
    """
    try:
        numero = int(id_ejecucion)
    except ValueError:
        return _no_encontrado(request)

    try:
        vista = await composicion.vista_previa_reverso_financiero.construir(numero)
    except EjecucionOrigenNoEncontrada:
        return _no_encontrado(request)
    except EjecucionOrigenNoElegible:
        return _no_encontrado(
            request,
            titulo="Esta ejecución no admite un reverso",
            detalle=(
                "Solo una compra financiera (0200) aprobada puede originar un reverso "
                "en este laboratorio."
            ),
        )

    # Ya se sabe que `numero` es elegible (la linea de arriba no revento):
    # `detalle_ejecucion` aqui es solo para mostrar los datos ORIGINALES en
    # el panel "Derivado de" (B7, punto 4) -RRN incluido, "segun disponibilidad"-,
    # nunca para decidir nada de negocio otra vez.
    detalle_origen = await composicion.consultas.detalle_ejecucion(numero)
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="reverso_preview.html",
        context={
            "seccion": "historial",
            "ejecucion_origen_id": numero,
            "ejecucion_origen": detalle_origen.ejecucion,
            "rrn_original": detalle_origen.solicitud.valor("37"),
            "codigo_autorizacion_original": detalle_origen.respuesta.valor("38"),
            **presentacion.contexto_de_vista_previa(vista, composicion.descripciones_de_campos),
        },
    )


@enrutador.post("/historial/{id_ejecucion}/reverso/ejecutar", response_class=HTMLResponse)
async def reverso_ejecutar(
    request: Request,
    id_ejecucion: str,
    composicion: Composicion = Depends(obtener_composicion),
):
    """POST que SI ejecuta el reverso financiero (0400, B7).

    El destino de transporte es el MISMO host/puerto al que fue la 0200
    original (`Ejecucion.destino_host`/`destino_puerto`, ya persistidos):
    un reverso viaja adonde viajó la transacción que reversa, nunca a una
    conexión que la persona elija en este formulario -no hay ningún campo
    de conexión en esta pantalla, a propósito (B7, punto 5).

    La elegibilidad del origen se revalida DE NUEVO dentro del orquestador
    (`Orquestador.ejecutar_reverso_financiero` -> `referencia_origen_elegible`):
    esta ruta no confía en que la vista previa ya la haya comprobado, para
    que un POST directo (sin pasar por el preview) no pueda saltarse la
    regla (B7, puntos 15/16).
    """
    try:
        numero = int(id_ejecucion)
    except ValueError:
        return _no_encontrado(request)

    detalle_origen = await composicion.consultas.detalle_ejecucion(numero)
    if detalle_origen is None or not detalle_origen.ejecucion.destino_host:
        return _no_encontrado(request)

    destino = DestinoTcp(
        host=detalle_origen.ejecucion.destino_host,
        puerto=detalle_origen.ejecucion.destino_puerto,
    )

    try:
        orquestador = await composicion.orquestador(destino)
        resultado = await orquestador.ejecutar_reverso_financiero(
            DatosReversoFinanciero(ejecucion_origen_id=numero)
        )
    except (EjecucionOrigenNoEncontrada, EjecucionOrigenNoElegible):
        return _no_encontrado(
            request,
            titulo="Esta ejecución no admite un reverso",
            detalle=(
                "Solo una compra financiera (0200) aprobada puede originar un reverso "
                "en este laboratorio."
            ),
        )
    except ErrorDelSimulador as error:
        # Fallo de infraestructura: no es un rechazo del autorizador y no
        # debe presentarse como tal, ni mostrar la excepcion.
        return PLANTILLAS.TemplateResponse(
            request=request,
            name="no_encontrado.html",
            context={
                "seccion": "historial",
                "titulo": "No se pudo ejecutar el reverso",
                "detalle": presentacion.aviso_de_error(error).detalle,
                "ruta_vuelta": f"/historial/{numero}",
                "texto_vuelta": "Volver a la ejecución original",
            },
            status_code=502,
        )

    contexto_resultado = presentacion.contexto_de_resultado(
        resultado, destino, composicion.descripciones_de_campos,
        bitmap_solicitud=composicion.bitmap_hex(resultado.solicitud),
        bitmap_respuesta=(
            composicion.bitmap_hex(resultado.respuesta.como_mensaje())
            if resultado.respuesta else None
        ),
        raw_solicitud=composicion.raw_hex_seguro(resultado.solicitud),
        raw_respuesta=(
            composicion.raw_hex_seguro(resultado.respuesta.como_mensaje())
            if resultado.respuesta else None
        ),
        seccion="reverso",
    )
    # `seccion="reverso"` no es una pantalla de constructor -no hay "/reverso"-,
    # asi que "reutilizar esta transaccion" ya queda oculto (`rutas_por_seccion`
    # en resultado.html no reconoce "reverso"); el unico ajuste que hace falta
    # es "volver" hacia la ejecucion ORIGEN, no hacia una pantalla de nueva
    # transaccion (B7, punto 17).
    contexto_resultado["url_volver"] = f"/historial/{numero}"
    return PLANTILLAS.TemplateResponse(
        request=request, name="resultado.html", context=contexto_resultado,
    )


@enrutador.get("/historial/{id_ejecucion}/aviso-reverso", response_class=HTMLResponse)
async def aviso_reverso_preview(
    request: Request,
    id_ejecucion: str,
    composicion: Composicion = Depends(obtener_composicion),
):
    """Vista previa del aviso de reverso (0420, B8): mismo principio que
    `reverso_preview` -la persona ve QUE se va a enviar antes de ejecutar,
    nunca se ejecuta directamente desde el detalle historico-.

    La elegibilidad se revalida aqui (via `ServicioVistaPreviaAvisoReverso`
    -> `referencia_origen_elegible`, misma regla que el reverso financiero,
    investigada y confirmada sin cambios para B8).
    """
    try:
        numero = int(id_ejecucion)
    except ValueError:
        return _no_encontrado(request)

    try:
        vista = await composicion.vista_previa_aviso_reverso.construir(numero)
    except EjecucionOrigenNoEncontrada:
        return _no_encontrado(request)
    except EjecucionOrigenNoElegible:
        return _no_encontrado(
            request,
            titulo="Esta ejecución no admite un aviso de reverso",
            detalle=(
                "Solo una compra financiera (0200) aprobada puede originar un aviso de "
                "reverso en este laboratorio."
            ),
        )

    detalle_origen = await composicion.consultas.detalle_ejecucion(numero)
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="aviso_reverso_preview.html",
        context={
            "seccion": "historial",
            "ejecucion_origen_id": numero,
            "ejecucion_origen": detalle_origen.ejecucion,
            "rrn_original": detalle_origen.solicitud.valor("37"),
            "codigo_autorizacion_original": detalle_origen.respuesta.valor("38"),
            **presentacion.contexto_de_vista_previa(vista, composicion.descripciones_de_campos),
        },
    )


@enrutador.post("/historial/{id_ejecucion}/aviso-reverso/ejecutar", response_class=HTMLResponse)
async def aviso_reverso_ejecutar(
    request: Request,
    id_ejecucion: str,
    composicion: Composicion = Depends(obtener_composicion),
):
    """POST que SI ejecuta el aviso de reverso (0420, B8).

    Mismo criterio que `reverso_ejecutar`: transmite al mismo destino que
    recibio la 0200 original, y revalida la elegibilidad del origen DENTRO
    del orquestador (`Orquestador.ejecutar_aviso_reverso` ->
    `referencia_origen_elegible`), para que un POST directo no pueda
    saltarse la regla.
    """
    try:
        numero = int(id_ejecucion)
    except ValueError:
        return _no_encontrado(request)

    detalle_origen = await composicion.consultas.detalle_ejecucion(numero)
    if detalle_origen is None or not detalle_origen.ejecucion.destino_host:
        return _no_encontrado(request)

    destino = DestinoTcp(
        host=detalle_origen.ejecucion.destino_host,
        puerto=detalle_origen.ejecucion.destino_puerto,
    )

    try:
        orquestador = await composicion.orquestador(destino)
        resultado = await orquestador.ejecutar_aviso_reverso(
            DatosAvisoReverso(ejecucion_origen_id=numero)
        )
    except (EjecucionOrigenNoEncontrada, EjecucionOrigenNoElegible):
        return _no_encontrado(
            request,
            titulo="Esta ejecución no admite un aviso de reverso",
            detalle=(
                "Solo una compra financiera (0200) aprobada puede originar un aviso de "
                "reverso en este laboratorio."
            ),
        )
    except ErrorDelSimulador as error:
        return PLANTILLAS.TemplateResponse(
            request=request,
            name="no_encontrado.html",
            context={
                "seccion": "historial",
                "titulo": "No se pudo ejecutar el aviso de reverso",
                "detalle": presentacion.aviso_de_error(error).detalle,
                "ruta_vuelta": f"/historial/{numero}",
                "texto_vuelta": "Volver a la ejecución original",
            },
            status_code=502,
        )

    contexto_resultado = presentacion.contexto_de_resultado(
        resultado, destino, composicion.descripciones_de_campos,
        bitmap_solicitud=composicion.bitmap_hex(resultado.solicitud),
        bitmap_respuesta=(
            composicion.bitmap_hex(resultado.respuesta.como_mensaje())
            if resultado.respuesta else None
        ),
        raw_solicitud=composicion.raw_hex_seguro(resultado.solicitud),
        raw_respuesta=(
            composicion.raw_hex_seguro(resultado.respuesta.como_mensaje())
            if resultado.respuesta else None
        ),
        seccion="aviso_reverso",
    )
    contexto_resultado["url_volver"] = f"/historial/{numero}"
    return PLANTILLAS.TemplateResponse(
        request=request, name="resultado.html", context=contexto_resultado,
    )


def _reconstruir_mensaje_persistido(mti: str | None, serializado) -> MensajeIso | None:
    """Reconstruye un `MensajeIso` a partir de un `MensajeSerializado`
    historico, SOLO cuando es demostrable -ver `MensajeSerializado.fiel`-, o
    `None` en cualquier otro caso (sin MTI, sin representacion, o formato de
    texto heredado que no puede demostrar que ningun valor haya quedado
    partido por el separador sin escape).

    Es la base compartida para bitmap y RAW/HEX historicos: ambos son
    exactamente la misma reconstruccion, solo cambia que hacen con ella.
    """
    if mti is None or not serializado.disponible or not serializado.fiel:
        return None
    return MensajeIso(mti=mti, campos={c.numero: c.valor for c in serializado.campos})


@enrutador.get("/configuracion", response_class=HTMLResponse)
async def configuracion(
    request: Request, composicion: Composicion = Depends(obtener_composicion)
):
    return PLANTILLAS.TemplateResponse(
        request=request, name="configuracion.html", context={"seccion": "configuracion"}
    )


@enrutador.get("/configuracion/tarjetas", response_class=HTMLResponse)
async def config_tarjetas(
    request: Request, composicion: Composicion = Depends(obtener_composicion)
):
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="config_tarjetas.html",
        context={
            "seccion": "configuracion",
            "tarjetas": await composicion.administracion_tarjetas.listar(),
        },
    )


@enrutador.get("/configuracion/tarjetas/nueva", response_class=HTMLResponse)
async def config_tarjeta_nueva(
    request: Request, composicion: Composicion = Depends(obtener_composicion)
):
    return _formulario_tarjeta(request, modo="nueva")


@enrutador.post("/configuracion/tarjetas", response_class=HTMLResponse)
async def config_tarjeta_crear(
    request: Request,
    # Cadena vacia a proposito: declarar los campos obligatorios haria que
    # FastAPI respondiera su propio 422 en JSON ante un formulario vacio, en
    # vez de la pantalla propia con el error explicado.
    card_id: str = Form(""),
    descripcion: str = Form(""),
    pan: str = Form(""),
    expiracion: str = Form(""),
    confirma_qa: str = Form(""),
    composicion: Composicion = Depends(obtener_composicion),
):
    try:
        await composicion.administracion_tarjetas.crear(
            DatosNuevaTarjeta(
                card_id=card_id,
                descripcion=descripcion,
                pan=pan,
                expiracion=expiracion,
                confirma_qa=bool(confirma_qa),
            )
        )
    except ValueError as error:
        # El PAN nunca vuelve al formulario: ni el recibido ni ningun otro.
        return _formulario_tarjeta(
            request,
            modo="nueva",
            error=str(error),
            card_id=card_id,
            descripcion=descripcion,
            expiracion=expiracion,
            confirma_qa=bool(confirma_qa),
            estado_http=400,
        )
    return RedirectResponse("/configuracion/tarjetas", status_code=303)


@enrutador.get("/configuracion/tarjetas/{card_id}/editar", response_class=HTMLResponse)
async def config_tarjeta_editar_formulario(
    request: Request,
    card_id: str,
    composicion: Composicion = Depends(obtener_composicion),
):
    tarjeta = await composicion.administracion_tarjetas.obtener(card_id)
    if tarjeta is None:
        return _tarjeta_no_encontrada(request)
    return _formulario_tarjeta(
        request,
        modo="editar",
        card_id=tarjeta.card_id,
        descripcion=tarjeta.descripcion,
        expiracion=tarjeta.expiracion,
        pan_enmascarado=tarjeta.pan_enmascarado,
    )


@enrutador.post("/configuracion/tarjetas/{card_id}", response_class=HTMLResponse)
async def config_tarjeta_actualizar(
    request: Request,
    card_id: str,
    descripcion: str = Form(""),
    expiracion: str = Form(""),
    pan_nuevo: str = Form(""),
    confirma_qa: str = Form(""),
    composicion: Composicion = Depends(obtener_composicion),
):
    try:
        await composicion.administracion_tarjetas.actualizar(
            card_id,
            DatosEdicionTarjeta(
                descripcion=descripcion,
                expiracion=expiracion,
                pan_nuevo=pan_nuevo,
                confirma_qa=bool(confirma_qa),
            ),
        )
    except TarjetaNoEncontrada:
        return _tarjeta_no_encontrada(request)
    except ValueError as error:
        actual = await composicion.administracion_tarjetas.obtener(card_id)
        return _formulario_tarjeta(
            request,
            modo="editar",
            error=str(error),
            card_id=card_id,
            descripcion=descripcion,
            expiracion=expiracion,
            pan_enmascarado=actual.pan_enmascarado if actual else "",
            confirma_qa=bool(confirma_qa),
            estado_http=400,
        )
    return RedirectResponse("/configuracion/tarjetas", status_code=303)


@enrutador.post("/configuracion/tarjetas/{card_id}/estado", response_class=HTMLResponse)
async def config_tarjeta_estado(
    request: Request,
    card_id: str,
    activa: str = Form(""),
    composicion: Composicion = Depends(obtener_composicion),
):
    try:
        activa_bool = presentacion.validar_activa(activa)
    except ValueError as error:
        return await _config_tarjetas_con_error(request, composicion, str(error))

    try:
        await composicion.administracion_tarjetas.cambiar_estado(card_id, activa=activa_bool)
    except TarjetaNoEncontrada:
        return _tarjeta_no_encontrada(request)
    return RedirectResponse("/configuracion/tarjetas", status_code=303)


async def _config_tarjetas_con_error(request: Request, composicion: Composicion, error: str):
    """El listado de tarjetas, con un banner de error. 400: entrada rechazada."""
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="config_tarjetas.html",
        context={
            "seccion": "configuracion",
            "tarjetas": await composicion.administracion_tarjetas.listar(),
            "error": error,
        },
        status_code=400,
    )


def _formulario_tarjeta(
    request: Request,
    *,
    modo: str,
    card_id: str = "",
    descripcion: str = "",
    expiracion: str = "",
    pan_enmascarado: str = "",
    confirma_qa: bool = False,
    error: str | None = None,
    estado_http: int = 200,
):
    """Renderiza el formulario de tarjeta, comun a crear y editar.

    Nunca recibe ni reenvia el PAN: ni el que se acaba de escribir ni ninguno
    guardado. `pan_enmascarado` es lo unico que puede mostrarse de un numero
    ya existente.
    """
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="config_tarjeta_form.html",
        context={
            "seccion": "configuracion",
            "modo": modo,
            "card_id": card_id,
            "descripcion": descripcion,
            "expiracion": expiracion,
            "pan_enmascarado": pan_enmascarado,
            "confirma_qa": confirma_qa,
            "error": error,
        },
        status_code=estado_http,
    )


def _tarjeta_no_encontrada(request: Request):
    """404 con HTML del producto para un `card_id` que no existe."""
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="no_encontrado.html",
        context={
            "seccion": "configuracion",
            "titulo": "Tarjeta no encontrada",
            "detalle": "La tarjeta solicitada no existe o ya no está disponible.",
            "ruta_vuelta": "/configuracion/tarjetas",
            "texto_vuelta": "Volver a tarjetas",
        },
        status_code=404,
    )


# ------------------------------------------------------------- conexiones ----


@enrutador.get("/configuracion/conexiones", response_class=HTMLResponse)
async def config_conexiones(
    request: Request, composicion: Composicion = Depends(obtener_composicion)
):
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="config_conexiones.html",
        context={
            "seccion": "configuracion",
            "conexiones": await composicion.administracion_conexiones.listar(),
        },
    )


@enrutador.get("/configuracion/conexiones/nueva", response_class=HTMLResponse)
async def config_conexion_nueva(
    request: Request, composicion: Composicion = Depends(obtener_composicion)
):
    return _formulario_conexion(request, modo="nueva")


@enrutador.post("/configuracion/conexiones", response_class=HTMLResponse)
async def config_conexion_crear(
    request: Request,
    conexion_id: str = Form(""),
    nombre: str = Form(""),
    host: str = Form(""),
    puerto: str = Form(""),
    timeout: str = Form(""),
    composicion: Composicion = Depends(obtener_composicion),
):
    try:
        await composicion.administracion_conexiones.crear(
            DatosNuevaConexion(
                conexion_id=conexion_id, nombre=nombre, host=host, puerto=puerto, timeout=timeout
            )
        )
    except ValueError as error:
        return _formulario_conexion(
            request,
            modo="nueva",
            error=str(error),
            conexion_id=conexion_id,
            nombre=nombre,
            host=host,
            puerto=puerto,
            timeout=timeout,
            estado_http=400,
        )
    return RedirectResponse("/configuracion/conexiones", status_code=303)


@enrutador.get("/configuracion/conexiones/{conexion_id}/editar", response_class=HTMLResponse)
async def config_conexion_editar_formulario(
    request: Request,
    conexion_id: str,
    composicion: Composicion = Depends(obtener_composicion),
):
    conexion = await composicion.administracion_conexiones.obtener(conexion_id)
    if conexion is None:
        return _conexion_no_encontrada(request)
    return _formulario_conexion(
        request,
        modo="editar",
        conexion_id=conexion.conexion_id,
        nombre=conexion.nombre,
        host=conexion.host,
        puerto=str(conexion.puerto),
        timeout=_texto_timeout(conexion.timeout),
    )


@enrutador.post("/configuracion/conexiones/{conexion_id}", response_class=HTMLResponse)
async def config_conexion_actualizar(
    request: Request,
    conexion_id: str,
    nombre: str = Form(""),
    host: str = Form(""),
    puerto: str = Form(""),
    timeout: str = Form(""),
    composicion: Composicion = Depends(obtener_composicion),
):
    try:
        await composicion.administracion_conexiones.actualizar(
            conexion_id,
            DatosEdicionConexion(nombre=nombre, host=host, puerto=puerto, timeout=timeout),
        )
    except ConexionNoEncontrada:
        return _conexion_no_encontrada(request)
    except ValueError as error:
        return _formulario_conexion(
            request,
            modo="editar",
            error=str(error),
            conexion_id=conexion_id,
            nombre=nombre,
            host=host,
            puerto=puerto,
            timeout=timeout,
            estado_http=400,
        )
    return RedirectResponse("/configuracion/conexiones", status_code=303)


@enrutador.post("/configuracion/conexiones/{conexion_id}/estado", response_class=HTMLResponse)
async def config_conexion_estado(
    request: Request,
    conexion_id: str,
    activa: str = Form(""),
    composicion: Composicion = Depends(obtener_composicion),
):
    try:
        activa_bool = presentacion.validar_activa(activa)
    except ValueError as error:
        return await _config_conexiones_con_error(request, composicion, str(error))

    try:
        await composicion.administracion_conexiones.cambiar_estado(
            conexion_id, activa=activa_bool
        )
    except ConexionNoEncontrada:
        return _conexion_no_encontrada(request)
    return RedirectResponse("/configuracion/conexiones", status_code=303)


@enrutador.post("/configuracion/conexiones/{conexion_id}/probar", response_class=HTMLResponse)
async def config_conexion_probar(
    request: Request,
    conexion_id: str,
    composicion: Composicion = Depends(obtener_composicion),
):
    """Comprobacion TCP puntual, ajena al recorrido de compra.

    No envia un mensaje ISO, no pasa por el orquestador y no persiste una
    `Ejecucion`: solo abre y cierra un socket. El resultado no se guarda -se
    calcula al momento y se muestra una unica vez, en esta misma respuesta-,
    asi que nunca puede presentarse como una verdad desactualizada.
    """
    try:
        disponible = await composicion.administracion_conexiones.probar(conexion_id)
    except ConexionNoEncontrada:
        return _conexion_no_encontrada(request)
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="config_conexiones.html",
        context={
            "seccion": "configuracion",
            "conexiones": await composicion.administracion_conexiones.listar(),
            "resultado_prueba": {"conexion_id": conexion_id, "disponible": disponible},
        },
    )


async def _config_conexiones_con_error(request: Request, composicion: Composicion, error: str):
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="config_conexiones.html",
        context={
            "seccion": "configuracion",
            "conexiones": await composicion.administracion_conexiones.listar(),
            "error": error,
        },
        status_code=400,
    )


def _texto_timeout(timeout: float) -> str:
    """Representa un timeout sin ceros de mas: `10.0` -> `"10"`, `7.5` -> `"7.5"`."""
    return f"{timeout:g}"


def _formulario_conexion(
    request: Request,
    *,
    modo: str,
    conexion_id: str = "",
    nombre: str = "",
    host: str = "",
    puerto: str = "",
    timeout: str = "",
    error: str | None = None,
    estado_http: int = 200,
):
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="config_conexion_form.html",
        context={
            "seccion": "configuracion",
            "modo": modo,
            "conexion_id": conexion_id,
            "nombre": nombre,
            "host": host,
            "puerto": puerto,
            "timeout": timeout,
            "error": error,
        },
        status_code=estado_http,
    )


def _conexion_no_encontrada(request: Request):
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="no_encontrado.html",
        context={
            "seccion": "configuracion",
            "titulo": "Conexión no encontrada",
            "detalle": "La conexión solicitada no existe o ya no está disponible.",
            "ruta_vuelta": "/configuracion/conexiones",
            "texto_vuelta": "Volver a conexiones",
        },
        status_code=404,
    )


# ------------------------------------------------------------- escenarios ----
#
# No hay un segundo constructor aqui: "Nuevo escenario" y "Editar" reutilizan
# Nueva transaccion (`/` con `?escenario_id=...` para cargar, y los botones
# "Guardar como escenario"/"Guardar cambios"/"Guardar como copia" del mismo
# formulario). Esta seccion solo administra metadatos y ciclo de vida: listar,
# buscar, activar/desactivar, duplicar y reejecutar sin pasar por el
# constructor.


@enrutador.get("/escenarios", response_class=HTMLResponse)
async def escenarios_lista(
    request: Request,
    buscar: str = Query(""),
    composicion: Composicion = Depends(obtener_composicion),
):
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="escenarios.html",
        context={
            "seccion": "escenarios",
            "escenarios": await composicion.administracion_escenarios.listar(buscar=buscar),
            "buscar": buscar,
        },
    )


@enrutador.post("/escenarios", response_class=HTMLResponse)
async def escenario_crear(
    request: Request,
    nombre: str = Form(""),
    card_id: str = Form(""),
    monto: str = Form(""),
    conexion_id: str = Form(""),
    mti: str = Form(MTI_COMPRA),
    composicion: Composicion = Depends(obtener_composicion),
):
    """Crea un escenario. Es el destino de "Guardar como escenario" y de
    "Guardar como copia" -ambas son la misma operacion: crear uno nuevo a
    partir del estado actual del constructor (compra o echo, segun cual haya
    enviado el formulario)-. `mti` decide la operacion: echo.html envia
    `MTI_ECHO` en un campo oculto, compra.html no envia nada y por eso el
    valor por defecto sigue siendo compra -sin romper el formulario existente-.
    """
    if mti == MTI_ECHO:
        formulario_bruto = await request.form()
        enviado = _leer_enviado_echo(formulario_bruto, composicion.perfil)
        try:
            expectativas = _leer_expectativas(
                formulario_bruto, composicion.perfil, mti_respuesta=MTI_RESPUESTA_ECHO
            )
            creado = await composicion.administracion_escenarios.crear(
                DatosNuevoEscenario(
                    nombre=nombre,
                    mti=MTI_ECHO,
                    conexion_id=conexion_id,
                    campos_manuales=enviado["campos_manuales"],
                    expectativas=expectativas,
                )
            )
        except ValueError as error:
            return await _formulario_echo(
                request, composicion, conexion_id=conexion_id or None,
                de70=enviado["de70"], error=str(error), estado_http=400,
            )
        return RedirectResponse(f"/echo?escenario_id={creado.escenario_id}", status_code=303)

    # Operaciones "con tarjeta" (comparten forma con compra: card_id + monto +
    # campos editables/opcionales, via `_leer_enviado` parametrizado). B5:
    # `operacion_por_mti` consulta el registro declarativo unico
    # (`web.operaciones.OPERACIONES_CON_TARJETA`), nunca un
    # `if mti == ... elif mti == ...` que crezca por operacion.
    operacion = operacion_por_mti(mti)
    if operacion is None:
        raise ValueError(f"operación no soportada para guardar un escenario: {mti!r}")

    formulario_bruto = await request.form()
    enviado = _leer_enviado(
        formulario_bruto, composicion.perfil, mti=mti, mti_respuesta=operacion.mti_respuesta
    )
    campos_manuales = enviado["campos_manuales"]
    try:
        monto_decimal = presentacion.validar_monto(monto)
        expectativas = _leer_expectativas(formulario_bruto, composicion.perfil, operacion.mti_respuesta)
        creado = await composicion.administracion_escenarios.crear(
            DatosNuevoEscenario(
                nombre=nombre,
                mti=mti,
                card_id=card_id.strip(),
                conexion_id=conexion_id,
                monto=monto_decimal,
                campos_manuales=campos_manuales,
                expectativas=expectativas,
            )
        )
    except ValueError as error:
        return await _formulario_operacion(
            request, composicion, operacion, error=str(error), enviado=enviado, estado_http=400
        )
    return RedirectResponse(f"{operacion.ruta}?escenario_id={creado.escenario_id}", status_code=303)


@enrutador.post("/escenarios/{escenario_id}", response_class=HTMLResponse)
async def escenario_actualizar(
    request: Request,
    escenario_id: str,
    nombre: str = Form(""),
    card_id: str = Form(""),
    monto: str = Form(""),
    conexion_id: str = Form(""),
    composicion: Composicion = Depends(obtener_composicion),
):
    """"Guardar cambios": vuelve a congelar los valores efectivos de hoy, no
    parcha lo que ya estaba guardado -mismo criterio que crear-. Editar nunca
    cambia la operacion (`DatosEdicionEscenario` no tiene `mti`): se consulta
    el escenario existente solo para saber si es de echo (sin tarjeta/monto)
    o de compra, y leer/validar el formulario en consecuencia.
    """
    existente = await composicion.administracion_escenarios.obtener(escenario_id)
    if existente is None:
        return _escenario_no_encontrado(request)

    if existente.mti == MTI_ECHO:
        formulario_bruto = await request.form()
        enviado = _leer_enviado_echo(formulario_bruto, composicion.perfil)
        try:
            expectativas = _leer_expectativas(
                formulario_bruto, composicion.perfil, mti_respuesta=MTI_RESPUESTA_ECHO
            )
            await composicion.administracion_escenarios.actualizar(
                escenario_id,
                DatosEdicionEscenario(
                    nombre=nombre,
                    conexion_id=conexion_id,
                    campos_manuales=enviado["campos_manuales"],
                    expectativas=expectativas,
                ),
            )
        except EscenarioNoEncontrado:
            return _escenario_no_encontrado(request)
        except ValueError as error:
            return await _formulario_echo(
                request, composicion, escenario_id=escenario_id, conexion_id=conexion_id or None,
                de70=enviado["de70"], error=str(error), estado_http=400,
            )
        return RedirectResponse(f"/echo?escenario_id={escenario_id}", status_code=303)

    # Mismo criterio que `escenario_crear` (B5): el registro declarativo
    # unico (`operacion_por_mti`) para las operaciones "con tarjeta".
    operacion = operacion_por_mti(existente.mti)
    if operacion is None:
        raise ValueError(f"operación no soportada para actualizar un escenario: {existente.mti!r}")

    formulario_bruto = await request.form()
    enviado = _leer_enviado(
        formulario_bruto, composicion.perfil, mti=existente.mti, mti_respuesta=operacion.mti_respuesta
    )
    campos_manuales = enviado["campos_manuales"]
    try:
        monto_decimal = presentacion.validar_monto(monto)
        expectativas = _leer_expectativas(formulario_bruto, composicion.perfil, operacion.mti_respuesta)
        await composicion.administracion_escenarios.actualizar(
            escenario_id,
            DatosEdicionEscenario(
                nombre=nombre,
                card_id=card_id.strip(),
                conexion_id=conexion_id,
                monto=monto_decimal,
                campos_manuales=campos_manuales,
                expectativas=expectativas,
            ),
        )
    except EscenarioNoEncontrado:
        return _escenario_no_encontrado(request)
    except ValueError as error:
        return await _formulario_operacion(
            request, composicion, operacion, escenario_id=escenario_id,
            error=str(error), enviado=enviado, estado_http=400,
        )
    return RedirectResponse(f"{operacion.ruta}?escenario_id={escenario_id}", status_code=303)


@enrutador.post("/escenarios/{escenario_id}/estado", response_class=HTMLResponse)
async def escenario_estado(
    request: Request,
    escenario_id: str,
    activo: str = Form(""),
    composicion: Composicion = Depends(obtener_composicion),
):
    try:
        activo_bool = presentacion.validar_activa(activo)
    except ValueError as error:
        return await _escenarios_con_error(request, composicion, str(error))

    try:
        await composicion.administracion_escenarios.cambiar_estado(escenario_id, activo=activo_bool)
    except EscenarioNoEncontrado:
        return _escenario_no_encontrado(request)
    return RedirectResponse("/escenarios", status_code=303)


def _config_pantalla_de_operacion(mti: str) -> tuple[str, Callable, str]:
    """(ruta_pantalla, renderizador, etiqueta_seccion) para el MTI de un
    escenario -unica fuente de "a que pantalla se carga/redirige/renderiza el
    resultado de esta operacion" (B4 punto 25; B5: las operaciones con
    tarjeta ahora vienen del registro declarativo unico,
    `web.operaciones.OPERACIONES_CON_TARJETA`, en vez de una tabla propia-.
    La consultan `escenario_duplicar`, `escenario_ejecutar` y
    `_reconstruir_desde_ejecucion`, ninguno la duplica ni la reemplaza por un
    `if mti == ... elif ...` propio.

    Se define como funcion (no un dict de modulo) porque el renderizador de
    echo (`_formulario_echo`) se define mas abajo en este archivo: al momento
    en que esta funcion se LLAMA (nunca al definirse), el modulo ya esta
    completamente cargado.
    """
    operacion = operacion_por_mti(mti)
    if operacion is not None:
        renderizador = functools.partial(_formulario_operacion, operacion=operacion)
        return operacion.ruta, renderizador, operacion.seccion
    if mti == MTI_ECHO:
        return "/echo", _formulario_echo, "echo"
    raise ValueError(f"operación no soportada para esta pantalla: {mti!r}")


@enrutador.post("/escenarios/{escenario_id}/duplicar", response_class=HTMLResponse)
async def escenario_duplicar(
    request: Request,
    escenario_id: str,
    composicion: Composicion = Depends(obtener_composicion),
):
    """Copia atomica del lado del servidor: la copia se abre en el constructor
    para ajustarla, no hace falta pasar por el listado primero.
    """
    try:
        copia = await composicion.administracion_escenarios.duplicar(escenario_id)
    except EscenarioNoEncontrado:
        return _escenario_no_encontrado(request)
    ruta_pantalla, _renderizador, _seccion = _config_pantalla_de_operacion(copia.mti)
    return RedirectResponse(f"{ruta_pantalla}?escenario_id={copia.escenario_id}", status_code=303)


@enrutador.post("/escenarios/{escenario_id}/ejecutar", response_class=HTMLResponse)
async def escenario_ejecutar(
    request: Request,
    escenario_id: str,
    composicion: Composicion = Depends(obtener_composicion),
):
    """Reejecuta un escenario sin pasar por el constructor.

    Si algo lo bloquea -escenario inactivo, tarjeta o conexion no disponible,
    incompatibilidad con el perfil actual- no se ejecuta nada: se muestra el
    constructor cargado con ese escenario, con el motivo explicado. Es el
    mismo diagnostico que "cargar" ya calcula (`_formulario`/`_formulario_echo`
    segun la operacion), reutilizado aqui en vez de duplicado.
    """
    escenario_previo = await composicion.administracion_escenarios.obtener(escenario_id)
    if escenario_previo is None:
        return _escenario_no_encontrado(request)
    _ruta_pantalla, renderizador_pantalla, seccion = _config_pantalla_de_operacion(escenario_previo.mti)

    async def _recargar(*, error: str | None = None, aviso=None, estado_http: int = 200):
        return await renderizador_pantalla(
            request, composicion, escenario_id=escenario_id,
            error=error, aviso=aviso, estado_http=estado_http,
        )

    try:
        resultado = await composicion.ejecutor_escenarios.ejecutar(escenario_id)
    except EscenarioNoEncontrado:
        return _escenario_no_encontrado(request)
    except EscenarioNoEjecutable:
        return await _recargar(estado_http=400)
    except TarjetaDesconocida:
        return await _recargar(
            error=f"No existe la tarjeta {escenario_previo.card_id!r} en el catálogo, o está inactiva.",
            estado_http=400,
        )
    except ErrorDelSimulador as error:
        return await _recargar(aviso=presentacion.aviso_de_error(error))

    # El destino que se muestra aqui es el SOLICITADO -de la conexion elegida-,
    # no el persistido: mismo criterio que ya distingue el resultado inmediato
    # del detalle historico (ver presentacion.resumen).
    escenario = await composicion.administracion_escenarios.obtener(escenario_id)
    conexion = await composicion.administracion_conexiones.obtener_activa(escenario.conexion_id)
    destino = DestinoTcp(host=conexion.host, puerto=conexion.puerto)
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="resultado.html",
        context=presentacion.contexto_de_resultado(
            resultado, destino, composicion.descripciones_de_campos,
            bitmap_solicitud=composicion.bitmap_hex(resultado.solicitud),
            bitmap_respuesta=(
                composicion.bitmap_hex(resultado.respuesta.como_mensaje())
                if resultado.respuesta else None
            ),
            raw_solicitud=composicion.raw_hex_seguro(resultado.solicitud),
            raw_respuesta=(
                composicion.raw_hex_seguro(resultado.respuesta.como_mensaje())
                if resultado.respuesta else None
            ),
            seccion=seccion,
        ),
    )


async def _escenarios_con_error(request: Request, composicion: Composicion, error: str):
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="escenarios.html",
        context={
            "seccion": "escenarios",
            "escenarios": await composicion.administracion_escenarios.listar(),
            "buscar": "",
            "error": error,
        },
        status_code=400,
    )


def _escenario_no_encontrado(request: Request):
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="no_encontrado.html",
        context={
            "seccion": "escenarios",
            "titulo": "Escenario no encontrado",
            "detalle": "El escenario solicitado no existe o ya no está disponible.",
            "ruta_vuelta": "/escenarios",
            "texto_vuelta": "Volver a escenarios",
        },
        status_code=404,
    )


# ============================================================== SUITES =====
#
# Bloque 4: agrupaciones reutilizables de escenarios, con ejecucion secuencial
# y agregado PASS/FAIL/ERROR/INCOMPLETA/SIN_EXPECTATIVAS. `suite_ejecutar`
# delega enteramente en `composicion.corredor_suites`, que a su vez reutiliza
# `EjecutorDeEscenarios` -la misma capacidad que ya usa "Ejecutar" en la
# pantalla de escenarios-: no hay una segunda implementacion de RN-1..RN-4 ni
# de Expected vs Actual en esta seccion.


@enrutador.get("/suites", response_class=HTMLResponse)
async def suites_lista(
    request: Request,
    buscar: str = Query(""),
    composicion: Composicion = Depends(obtener_composicion),
):
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="suites.html",
        context={
            "seccion": "suites",
            "suites": await composicion.administracion_suites.listar(buscar=buscar),
            "buscar": buscar,
        },
    )


@enrutador.get("/suites/nueva", response_class=HTMLResponse)
async def suite_nueva_formulario(
    request: Request, composicion: Composicion = Depends(obtener_composicion)
):
    return await _formulario_suite(request, composicion)


@enrutador.get("/suites/{suite_id}/editar", response_class=HTMLResponse)
async def suite_editar_formulario(
    request: Request, suite_id: str, composicion: Composicion = Depends(obtener_composicion)
):
    suite = await composicion.administracion_suites.obtener(suite_id)
    if suite is None:
        return _suite_no_encontrada(request)
    return await _formulario_suite(request, composicion, suite=suite)


@enrutador.post("/suites", response_class=HTMLResponse)
async def suite_crear(
    request: Request,
    nombre: str = Form(""),
    descripcion: str = Form(""),
    composicion: Composicion = Depends(obtener_composicion),
):
    """Crea una suite. `suite_id` es autogenerado y opaco -el QA solo escribe
    nombre y descripcion, igual criterio que ya aplica `escenario_id`.
    """
    formulario_bruto = await request.form()
    catalogo = await composicion.administracion_escenarios.listar()
    try:
        escenarios = _leer_escenarios_de_suite(formulario_bruto, catalogo)
        creada = await composicion.administracion_suites.crear(
            DatosNuevaSuite(nombre=nombre, descripcion=descripcion, escenarios=escenarios)
        )
    except ValueError as error:
        return await _formulario_suite(
            request, composicion, error=str(error),
            enviado={"nombre": nombre, "descripcion": descripcion},
            formulario_bruto=formulario_bruto, estado_http=400,
        )
    return RedirectResponse(f"/suites/{creada.suite_id}/editar", status_code=303)


@enrutador.post("/suites/{suite_id}", response_class=HTMLResponse)
async def suite_actualizar(
    request: Request,
    suite_id: str,
    nombre: str = Form(""),
    descripcion: str = Form(""),
    composicion: Composicion = Depends(obtener_composicion),
):
    """"Guardar cambios": reemplaza entera la membresia -no la fusiona con la
    anterior-, mismo criterio que ya aplica `escenario_actualizar`.
    """
    formulario_bruto = await request.form()
    catalogo = await composicion.administracion_escenarios.listar()
    try:
        escenarios = _leer_escenarios_de_suite(formulario_bruto, catalogo)
        await composicion.administracion_suites.actualizar(
            suite_id,
            DatosEdicionSuite(nombre=nombre, descripcion=descripcion, escenarios=escenarios),
        )
    except SuiteNoEncontrada:
        return _suite_no_encontrada(request)
    except ValueError as error:
        return await _formulario_suite(
            request, composicion, suite_id=suite_id, error=str(error),
            enviado={"nombre": nombre, "descripcion": descripcion},
            formulario_bruto=formulario_bruto, estado_http=400,
        )
    return RedirectResponse(f"/suites/{suite_id}/editar", status_code=303)


@enrutador.post("/suites/{suite_id}/estado", response_class=HTMLResponse)
async def suite_estado(
    request: Request,
    suite_id: str,
    activa: str = Form(""),
    composicion: Composicion = Depends(obtener_composicion),
):
    try:
        activa_bool = presentacion.validar_activa(activa)
    except ValueError as error:
        return await _suites_con_error(request, composicion, str(error))
    try:
        await composicion.administracion_suites.cambiar_estado(suite_id, activa=activa_bool)
    except SuiteNoEncontrada:
        return _suite_no_encontrada(request)
    return RedirectResponse("/suites", status_code=303)


@enrutador.post("/suites/{suite_id}/duplicar", response_class=HTMLResponse)
async def suite_duplicar(
    request: Request, suite_id: str, composicion: Composicion = Depends(obtener_composicion)
):
    try:
        copia = await composicion.administracion_suites.duplicar(suite_id)
    except SuiteNoEncontrada:
        return _suite_no_encontrada(request)
    return RedirectResponse(f"/suites/{copia.suite_id}/editar", status_code=303)


@enrutador.post("/suites/{suite_id}/ejecutar", response_class=HTMLResponse)
async def suite_ejecutar(
    request: Request, suite_id: str, composicion: Composicion = Depends(obtener_composicion)
):
    """Corre la suite completa, secuencialmente, en esta misma peticion -sin
    progreso en vivo: limitacion consciente de este bloque, ver diseno-.
    """
    try:
        corrida = await composicion.corredor_suites.ejecutar(suite_id)
    except SuiteNoEjecutable as error:
        return await _suites_con_error(request, composicion, str(error))
    return RedirectResponse(f"/suites/corridas/{corrida.corrida_id}", status_code=303)


@enrutador.get("/suites/corridas", response_class=HTMLResponse)
async def corridas_lista(
    request: Request, composicion: Composicion = Depends(obtener_composicion)
):
    corridas = await composicion.corridas_suite.listar()
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="corridas.html",
        context={
            "seccion": "suites",
            "filas": [presentacion.fila_de_corrida(c) for c in corridas],
        },
    )


@enrutador.get("/suites/corridas/{corrida_id}", response_class=HTMLResponse)
async def corrida_detalle(
    request: Request, corrida_id: str, composicion: Composicion = Depends(obtener_composicion)
):
    """`corrida_id` llega como `str`, no `int`: mismo motivo que
    `detalle_ejecucion` -controlar el formato del 404 en vez del 422 de
    FastAPI para un identificador que no es numerico.
    """
    try:
        numero = int(corrida_id)
    except ValueError:
        return _corrida_no_encontrada(request)

    corrida = await composicion.corridas_suite.obtener(numero)
    if corrida is None:
        return _corrida_no_encontrada(request)

    items = await composicion.corridas_suite.obtener_items(numero)
    fila_corrida = presentacion.fila_de_corrida(corrida)
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="corrida_detalle.html",
        context={
            "seccion": "suites",
            "corrida": fila_corrida,
            "filas_items": presentacion.filas_de_corrida(items, composicion.descripciones_de_campos),
            "aviso_resultado": presentacion.AVISOS_RESULTADO_GLOBAL_SUITE.get(
                fila_corrida.resultado_global
            ),
            # Ninguna corrida FINALIZADA con 0 items en FAIL/ERROR tiene algo
            # que reintentar -el boton se oculta en vez de mostrarse
            # deshabilitado sin explicacion (ver `SinItemsReintentables`,
            # que ademas revalida esto mismo del lado del servidor).
            "puede_reintentar": (corrida.cantidad_fail + corrida.cantidad_error) > 0,
        },
    )


# ==================================== SECUENCIAS (Fase C1) ==================== #
#
# SECUENCIA != SUITE: pasos DEPENDIENTES, no escenarios independientes (ver
# docstring de `domain.modelos`, seccion "Fase C1"). C1 solo soporta la
# primera forma real: paso 1 = compra financiera (financial_purchase,
# escenario elegido), paso 2 = reverso de ese paso (financial_reversal,
# automatico -el usuario nunca elige la operacion de un paso derivado, la
# decide `domain.elegibilidad_reverso`).


def _secuencia_no_encontrada(request: Request):
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="no_encontrado.html",
        context={
            "seccion": "secuencias",
            "titulo": "Secuencia no encontrada",
            "detalle": "La secuencia solicitada no existe o ya no está disponible.",
            "ruta_vuelta": "/secuencias",
            "texto_vuelta": "Volver a secuencias",
        },
        status_code=404,
    )


def _corrida_secuencia_no_encontrada(request: Request):
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="no_encontrado.html",
        context={
            "seccion": "secuencias",
            "titulo": "Corrida no encontrada",
            "detalle": "La corrida de secuencia solicitada no existe o ya no está disponible.",
            "ruta_vuelta": "/secuencias/corridas",
            "texto_vuelta": "Volver a corridas de secuencia",
        },
        status_code=404,
    )


async def _formulario_secuencia_nueva(
    request: Request,
    composicion: Composicion,
    *,
    error: str | None = None,
    enviado: Mapping | None = None,
    estado_http: int = 200,
):
    enviado = enviado or {}
    # Solo compra financiera puede ser el paso 1 -es la unica operacion
    # con tarjeta cuya ejecucion aprobada `domain.elegibilidad_reverso`
    # reconoce como origen valido de un reverso (B6/B7); ofrecer otros MTI
    # aqui fingiria una capacidad que C1 no soporta (punto 20/21).
    candidatos = [
        e for e in await composicion.administracion_escenarios.listar()
        if e.mti == MTI_COMPRA_FINANCIERA
    ]
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="secuencia_nueva.html",
        context={
            "seccion": "secuencias",
            "error": error,
            "nombre": enviado.get("nombre", ""),
            "descripcion": enviado.get("descripcion", ""),
            "escenario_id_elegido": enviado.get("escenario_id", ""),
            "escenarios_candidatos": candidatos,
        },
        status_code=estado_http,
    )


#: D1: numero maximo de filas de condicion/campo-de-respuesta que el
#: formulario ofrece -primera version enfocada (punto 26 del checkpoint),
#: sin "+Agregar campo" incremental: una fila vacia simplemente se ignora.
_MAX_CONDICIONES_FORMULARIO = 4
_MAX_CAMPOS_RESPUESTA_FORMULARIO = 4


def _leer_condiciones_regla(formulario) -> tuple[CondicionRegla, ...]:
    condiciones = []
    for i in range(1, _MAX_CONDICIONES_FORMULARIO + 1):
        campo = (formulario.get(f"condicion_campo_{i}") or "").strip()
        operador = (formulario.get(f"condicion_operador_{i}") or "").strip()
        if not campo or not operador:
            continue
        valor = (formulario.get(f"condicion_valor_{i}") or "").strip()
        condiciones.append(CondicionRegla(campo=campo, operador=operador, valor=valor or None))
    return tuple(condiciones)


def _leer_campos_respuesta(formulario) -> dict[str, str]:
    campos: dict[str, str] = {}
    for i in range(1, _MAX_CAMPOS_RESPUESTA_FORMULARIO + 1):
        campo = (formulario.get(f"respuesta_campo_{i}") or "").strip()
        valor = (formulario.get(f"respuesta_valor_{i}") or "").strip()
        if campo and valor:
            campos[campo] = valor
    return campos


def _leer_datos_regla(formulario) -> DatosNuevaRegla:
    tipo_comportamiento = (formulario.get("comportamiento_tipo") or TipoComportamiento.NORMAL.value).strip()
    delay_bruto = (formulario.get("comportamiento_delay_ms") or "0").strip()
    try:
        delay_ms = int(delay_bruto) if delay_bruto else 0
    except ValueError:
        raise ValueError("El retardo (delay_ms) debe ser un número entero.")
    try:
        prioridad = int((formulario.get("prioridad") or "0").strip())
    except ValueError:
        raise ValueError("La prioridad debe ser un número entero.")
    # D2: vacio = ilimitada (mismo criterio ya usado por delay_ms: cadena
    # vacia -> valor sentinel, nunca un error de forma).
    max_aplicaciones_bruto = (formulario.get("max_aplicaciones") or "").strip()
    try:
        max_aplicaciones = int(max_aplicaciones_bruto) if max_aplicaciones_bruto else None
    except ValueError:
        raise ValueError("El número máximo de aplicaciones debe ser un número entero.")
    return DatosNuevaRegla(
        nombre=(formulario.get("nombre") or "").strip(),
        prioridad=prioridad,
        activa=formulario.get("activa") == "on",
        condiciones=_leer_condiciones_regla(formulario),
        de39=(formulario.get("de39") or "").strip(),
        campos_adicionales=_leer_campos_respuesta(formulario),
        comportamiento=ComportamientoRegla(tipo=tipo_comportamiento, delay_ms=delay_ms),
        max_aplicaciones=max_aplicaciones,
    )


def _regla_host_no_encontrada(request: Request) -> HTMLResponse:
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="no_encontrado.html",
        context={
            "seccion": "reglas_host",
            "titulo": "Regla no encontrada",
            "detalle": "La regla solicitada no existe o ya no está disponible.",
            "ruta_vuelta": "/reglas-host",
            "texto_vuelta": "Volver a Reglas del Host",
        },
        status_code=404,
    )


async def _formulario_regla_host(
    request: Request, composicion: Composicion, *,
    regla_id: str | None = None, error: str | None = None,
    valores: Mapping[str, str] | None = None, estado_http: int = 200,
) -> HTMLResponse:
    regla_existente = await composicion.administracion_reglas_host.obtener(regla_id) if regla_id else None
    if regla_id and regla_existente is None:
        return _regla_host_no_encontrada(request)
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="regla_host_form.html",
        context={
            "seccion": "reglas_host",
            "regla_id": regla_id,
            "regla": regla_existente,
            "valores": valores or {},
            "error": error,
            "campos_disponibles": presentacion.campos_disponibles_para_reglas(
                composicion.perfil, composicion.descripciones_de_campos
            ),
            "operadores": ["igual", "distinto", "mayor_que", "menor_que", "presente", "ausente"],
            "comportamientos": [t.value for t in TipoComportamiento],
            "rango_condiciones": range(1, _MAX_CONDICIONES_FORMULARIO + 1),
            "rango_campos_respuesta": range(1, _MAX_CAMPOS_RESPUESTA_FORMULARIO + 1),
        },
        status_code=estado_http,
    )


@enrutador.get("/reglas-host", response_class=HTMLResponse)
async def reglas_host_lista(request: Request, composicion: Composicion = Depends(obtener_composicion)):
    servicio = composicion.administracion_reglas_host
    reglas = await servicio.listar()
    filas = [
        presentacion.fila_de_regla_host(r, await servicio.obtener_estado(r.regla_id))
        for r in reglas
    ]
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="reglas_host.html",
        context={
            "seccion": "reglas_host",
            "filas": filas,
        },
    )


@enrutador.get("/reglas-host/nueva", response_class=HTMLResponse)
async def regla_host_nueva(request: Request, composicion: Composicion = Depends(obtener_composicion)):
    return await _formulario_regla_host(request, composicion)


@enrutador.post("/reglas-host/nueva", response_class=HTMLResponse)
async def regla_host_crear(request: Request, composicion: Composicion = Depends(obtener_composicion)):
    formulario = await request.form()
    try:
        datos = _leer_datos_regla(formulario)
        await composicion.administracion_reglas_host.crear(datos)
    except ValueError as error:
        return await _formulario_regla_host(
            request, composicion, error=str(error), valores=formulario, estado_http=400
        )
    return RedirectResponse("/reglas-host", status_code=303)


@enrutador.get("/reglas-host/{regla_id}/editar", response_class=HTMLResponse)
async def regla_host_editar(
    request: Request, regla_id: str, composicion: Composicion = Depends(obtener_composicion)
):
    return await _formulario_regla_host(request, composicion, regla_id=regla_id)


@enrutador.post("/reglas-host/{regla_id}/editar", response_class=HTMLResponse)
async def regla_host_actualizar(
    request: Request, regla_id: str, composicion: Composicion = Depends(obtener_composicion)
):
    formulario = await request.form()
    try:
        datos = _leer_datos_regla(formulario)
        await composicion.administracion_reglas_host.actualizar(regla_id, datos)
    except ReglaHostNoEncontrada:
        return _regla_host_no_encontrada(request)
    except ValueError as error:
        return await _formulario_regla_host(
            request, composicion, regla_id=regla_id, error=str(error),
            valores=formulario, estado_http=400,
        )
    return RedirectResponse("/reglas-host", status_code=303)


@enrutador.post("/reglas-host/{regla_id}/estado", response_class=HTMLResponse)
async def regla_host_estado(
    request: Request, regla_id: str, activa: str = Form(""),
    composicion: Composicion = Depends(obtener_composicion),
):
    try:
        activa_bool = presentacion.validar_activa(activa)
    except ValueError:
        return _regla_host_no_encontrada(request)
    try:
        await composicion.administracion_reglas_host.cambiar_estado(regla_id, activa=activa_bool)
    except ReglaHostNoEncontrada:
        return _regla_host_no_encontrada(request)
    return RedirectResponse("/reglas-host", status_code=303)


@enrutador.post("/reglas-host/{regla_id}/duplicar", response_class=HTMLResponse)
async def regla_host_duplicar(
    request: Request, regla_id: str, composicion: Composicion = Depends(obtener_composicion)
):
    try:
        await composicion.administracion_reglas_host.duplicar(regla_id)
    except ReglaHostNoEncontrada:
        return _regla_host_no_encontrada(request)
    return RedirectResponse("/reglas-host", status_code=303)


@enrutador.post("/reglas-host/{regla_id}/reiniciar-contador", response_class=HTMLResponse)
async def regla_host_reiniciar_contador(
    request: Request, regla_id: str, composicion: Composicion = Depends(obtener_composicion)
):
    """Accion EXPLICITA (D2, punto 20 del checkpoint): pone el contador en
    0 sin tocar la configuracion ni la auditoria historica. Siempre POST,
    nunca GET -mismo criterio que activar/desactivar/duplicar."""
    try:
        await composicion.administracion_reglas_host.reiniciar_contador(regla_id)
    except ReglaHostNoEncontrada:
        return _regla_host_no_encontrada(request)
    return RedirectResponse("/reglas-host", status_code=303)


@enrutador.get("/secuencias", response_class=HTMLResponse)
async def secuencias_lista(
    request: Request, composicion: Composicion = Depends(obtener_composicion)
):
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="secuencias.html",
        context={
            "seccion": "secuencias",
            "secuencias": await composicion.administracion_secuencias.listar(),
        },
    )


@enrutador.get("/secuencias/nueva", response_class=HTMLResponse)
async def secuencia_nueva_formulario(
    request: Request, composicion: Composicion = Depends(obtener_composicion)
):
    return await _formulario_secuencia_nueva(request, composicion)


@enrutador.post("/secuencias", response_class=HTMLResponse)
async def secuencia_crear(
    request: Request,
    nombre: str = Form(""),
    descripcion: str = Form(""),
    escenario_id: str = Form(""),
    composicion: Composicion = Depends(obtener_composicion),
):
    """Crea una secuencia de dos pasos: paso 1 independiente (el escenario
    de compra financiera elegido), paso 2 derivado del paso 1 (reverso,
    automático -sin selector: C1 solo soporta esta forma, ver punto 20).
    """
    try:
        creada = await composicion.administracion_secuencias.crear(
            DatosNuevaSecuencia(
                nombre=nombre,
                descripcion=descripcion,
                pasos=[
                    DatosPaso(origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=escenario_id or None),
                    DatosPaso(origen_tipo=ORIGEN_PASO_DERIVADO, origen_paso_orden=1),
                ],
            )
        )
    except ValueError as error:
        return await _formulario_secuencia_nueva(
            request, composicion, error=str(error),
            enviado={"nombre": nombre, "descripcion": descripcion, "escenario_id": escenario_id},
            estado_http=400,
        )
    return RedirectResponse(f"/secuencias?creada={creada.secuencia_id}", status_code=303)


@enrutador.post("/secuencias/{secuencia_id}/ejecutar", response_class=HTMLResponse)
async def secuencia_ejecutar(
    request: Request, secuencia_id: str, composicion: Composicion = Depends(obtener_composicion)
):
    """Corre la secuencia completa, paso a paso, en esta misma peticion -sin
    progreso en vivo, misma limitacion consciente que `suite_ejecutar`."""
    try:
        corrida = await composicion.ejecutor_secuencia.ejecutar(secuencia_id)
    except SecuenciaNoEjecutable:
        return _secuencia_no_encontrada(request)
    return RedirectResponse(f"/secuencias/corridas/{corrida.corrida_id}", status_code=303)


@enrutador.get("/secuencias/corridas", response_class=HTMLResponse)
async def corridas_secuencia_lista(
    request: Request, composicion: Composicion = Depends(obtener_composicion)
):
    corridas = await composicion.corridas_secuencia.listar()
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="secuencia_corridas.html",
        context={
            "seccion": "corridas_secuencia",
            "filas": [presentacion.fila_de_corrida_secuencia(c) for c in corridas],
        },
    )


@enrutador.get("/secuencias/corridas/{corrida_id}", response_class=HTMLResponse)
async def corrida_secuencia_detalle(
    request: Request, corrida_id: str, composicion: Composicion = Depends(obtener_composicion)
):
    try:
        numero = int(corrida_id)
    except ValueError:
        return _corrida_secuencia_no_encontrada(request)

    corrida = await composicion.corridas_secuencia.obtener(numero)
    if corrida is None:
        return _corrida_secuencia_no_encontrada(request)

    pasos = await composicion.corridas_secuencia.obtener_pasos(numero)
    intentos_por_orden = {
        paso.orden: await composicion.corridas_secuencia.obtener_intentos(numero, paso.orden)
        for paso in pasos
    }
    fila_corrida = presentacion.fila_de_corrida_secuencia(corrida)
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="secuencia_corrida_detalle.html",
        context={
            "seccion": "corridas_secuencia",
            "corrida": fila_corrida,
            "filas_pasos": presentacion.filas_de_corrida_secuencia(
                pasos, composicion.descripciones_de_campos, intentos_por_orden
            ),
            "aviso_resultado": presentacion.AVISOS_RESULTADO_GLOBAL_SUITE.get(
                fila_corrida.resultado_global
            ),
        },
    )


@enrutador.get("/suites/corridas/{corrida_id}/comparar", response_class=HTMLResponse)
async def corrida_comparar(
    request: Request,
    corrida_id: str,
    contra: str = Query(""),
    composicion: Composicion = Depends(obtener_composicion),
):
    """Sin `contra`: selector de corridas de la MISMA suite. Con `contra`:
    la comparacion en si. GET puro -es una consulta de solo lectura, nunca
    escribe nada- por eso el destino elegido viaja en la querystring y no en
    un POST.
    """
    try:
        numero = int(corrida_id)
    except ValueError:
        return _corrida_no_encontrada(request)

    corrida = await composicion.corridas_suite.obtener(numero)
    if corrida is None:
        return _corrida_no_encontrada(request)

    candidatas = [
        c for c in await composicion.corridas_suite.listar_por_suite(corrida.suite_id, limite=100)
        if c.corrida_id != numero
    ]
    contexto = {
        "seccion": "suites",
        "corrida": presentacion.fila_de_corrida(corrida),
        "candidatas": [presentacion.fila_de_corrida(c) for c in candidatas],
        "corrida_b_id": contra,
        "error": None,
        "comparacion": None,
    }

    contra_bruto = (contra or "").strip()
    if not contra_bruto:
        return PLANTILLAS.TemplateResponse(
            request=request, name="corrida_comparar.html", context=contexto
        )

    try:
        numero_b = int(contra_bruto)
    except ValueError:
        contexto["error"] = "El identificador de la corrida a comparar no es válido."
        return PLANTILLAS.TemplateResponse(
            request=request, name="corrida_comparar.html", context=contexto, status_code=400
        )

    try:
        comparacion = await composicion.comparador_corridas.comparar(numero, numero_b)
    except CorridaNoEncontrada:
        contexto["error"] = "La corrida elegida para comparar no existe o ya no está disponible."
        return PLANTILLAS.TemplateResponse(
            request=request, name="corrida_comparar.html", context=contexto, status_code=404
        )
    except CorridasDeSuitesDistintas:
        contexto["error"] = "Solo se pueden comparar corridas de la misma suite."
        return PLANTILLAS.TemplateResponse(
            request=request, name="corrida_comparar.html", context=contexto, status_code=400
        )
    except ItemsHistoricosDuplicados as error:
        # Dato historico inconsistente (nunca deberia ocurrir por los
        # caminos actuales de la aplicacion, ver docstring de la excepcion):
        # se rechaza explicito en vez de elegir un item en silencio.
        # `error.corrida_id`/`error.escenario_id` son identificadores
        # tecnicos, nunca datos de tarjeta.
        contexto["error"] = (
            f"La corrida #{error.corrida_id} tiene más de un ítem histórico con el "
            f"escenario {error.escenario_id!r}: no se puede comparar de forma confiable."
        )
        return PLANTILLAS.TemplateResponse(
            request=request, name="corrida_comparar.html", context=contexto, status_code=409
        )

    contexto.update(presentacion.contexto_de_comparacion(comparacion, composicion.descripciones_de_campos))
    return PLANTILLAS.TemplateResponse(
        request=request, name="corrida_comparar.html", context=contexto
    )


@enrutador.post("/suites/corridas/{corrida_id}/reintentar", response_class=HTMLResponse)
async def corrida_reintentar(
    request: Request, corrida_id: str, composicion: Composicion = Depends(obtener_composicion)
):
    """Crea una corrida NUEVA con los items en FAIL/ERROR de `corrida_id`
    -ver `CorredorDeSuites.reintentar_fallidos`-. Nunca modifica la corrida
    original.
    """
    try:
        numero = int(corrida_id)
    except ValueError:
        return _corrida_no_encontrada(request)

    try:
        nueva = await composicion.corredor_suites.reintentar_fallidos(numero)
    except CorridaOrigenNoEncontrada:
        return _corrida_no_encontrada(request)
    except SinItemsReintentables:
        corrida = await composicion.corridas_suite.obtener(numero)
        if corrida is None:
            return _corrida_no_encontrada(request)
        items = await composicion.corridas_suite.obtener_items(numero)
        fila_corrida = presentacion.fila_de_corrida(corrida)
        return PLANTILLAS.TemplateResponse(
            request=request,
            name="corrida_detalle.html",
            context={
                "seccion": "suites",
                "corrida": fila_corrida,
                "filas_items": presentacion.filas_de_corrida(
                    items, composicion.descripciones_de_campos
                ),
                "aviso_resultado": presentacion.AVISOS_RESULTADO_GLOBAL_SUITE.get(
                    fila_corrida.resultado_global
                ),
                "puede_reintentar": False,
                "error": "Esta corrida no tiene ítems en FAIL o ERROR para reintentar.",
            },
            status_code=400,
        )
    return RedirectResponse(f"/suites/corridas/{nueva.corrida_id}", status_code=303)


@enrutador.get("/suites/corridas/{corrida_id}/exportar.json", response_class=PlainTextResponse)
async def corrida_exportar_json(
    corrida_id: str, composicion: Composicion = Depends(obtener_composicion)
):
    return await _exportar_corrida(composicion, corrida_id, formato="json")


@enrutador.get("/suites/corridas/{corrida_id}/exportar.csv", response_class=PlainTextResponse)
async def corrida_exportar_csv(
    corrida_id: str, composicion: Composicion = Depends(obtener_composicion)
):
    return await _exportar_corrida(composicion, corrida_id, formato="csv")


async def _exportar_corrida(composicion: Composicion, corrida_id: str, *, formato: str):
    """Descarga el reporte de una corrida YA PERSISTIDA -nunca la ejecuta de
    nuevo, y nunca depende de como esten configurados hoy sus escenarios: lee
    unicamente el snapshot ya guardado (`CorridaSuite` + sus
    `ItemCorridaSuite`), exactamente igual que `sibu-run-suite export-run`.
    Es la MISMA funcion de `application/exportacion_corridas.py` -ningun
    calculo propio de esta ruta, solo resolver el identificador, elegir el
    tipo de contenido y devolver la respuesta.
    """
    try:
        numero = int(corrida_id)
    except ValueError:
        return _corrida_no_encontrada_texto()

    corrida = await composicion.corridas_suite.obtener(numero)
    if corrida is None:
        return _corrida_no_encontrada_texto()

    items = await composicion.corridas_suite.obtener_items(numero)
    descripciones = composicion.descripciones_de_campos

    if formato == "csv":
        contenido = exportacion_corridas.reporte_a_csv(corrida, items, descripciones)
        tipo = "text/csv; charset=utf-8"
        nombre_archivo = f"corrida-{numero}.csv"
    else:
        contenido = exportacion_corridas.reporte_a_json(corrida, items)
        tipo = "application/json; charset=utf-8"
        nombre_archivo = f"corrida-{numero}.json"

    return PlainTextResponse(
        contenido,
        media_type=tipo,
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )


def _corrida_no_encontrada_texto() -> PlainTextResponse:
    """404 en texto plano para una exportacion -no HTML: es una descarga, no
    una pantalla-. Mismo mensaje que ya usa la CLI para el mismo caso.
    """
    return PlainTextResponse("La corrida solicitada no existe o ya no está disponible.", status_code=404)


async def _formulario_suite(
    request: Request,
    composicion: Composicion,
    *,
    suite=None,
    suite_id: str | None = None,
    error: str | None = None,
    enviado: dict | None = None,
    formulario_bruto=None,
    estado_http: int = 200,
):
    """`formulario_bruto`, si se pasa, es el POST que se acaba de rechazar: la
    seleccion de escenarios se reconstruye de ahi -conservando exactamente
    los que estaban marcados y el orden que se habia escrito, aunque ese
    orden no fuera valido- en vez de la de `suite` (que puede no existir
    todavia, o estar desactualizada frente a lo que la persona acaba de
    escribir). Sin `formulario_bruto`, el comportamiento es el de siempre:
    la seleccion sale de `suite`.
    """
    enviado = enviado or {}
    nombre = enviado.get("nombre", suite.nombre if suite else "")
    descripcion = enviado.get("descripcion", suite.descripcion if suite else "")
    catalogo = await composicion.administracion_escenarios.listar()
    if formulario_bruto is not None:
        filas_seleccion = presentacion.filas_seleccion_escenarios_desde_formulario(
            catalogo, formulario_bruto
        )
    else:
        escenarios_incluidos = suite.escenarios if suite else ()
        filas_seleccion = presentacion.filas_seleccion_escenarios(catalogo, escenarios_incluidos)
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="suite_form.html",
        context={
            "seccion": "suites",
            "suite_actual": suite,
            "suite_id": suite_id or (suite.suite_id if suite else None),
            "nombre": nombre,
            "descripcion": descripcion,
            "error": error,
            "filas_seleccion": filas_seleccion,
        },
        status_code=estado_http,
    )


def _leer_escenarios_de_suite(formulario_bruto, catalogo) -> tuple[str, ...]:
    """Lee `incluir_{id}`/`orden_{id}` del formulario, solo para los
    `escenario_id` que el CATALOGO REAL declara -mismo principio de
    seguridad que `_leer_expectativas`: un `incluir_{id}` para un escenario
    que no esta en el catalogo real nunca se mira, asi que no hace falta
    rechazarlo explicitamente: no hay forma de que se cuele-.

    El orden debe ser un entero positivo y distinto por cada escenario
    incluido; cualquier otra cosa es un 400 explicado, nunca una
    reinterpretacion silenciosa (por ejemplo, ordenar por el orden en que
    llegaron los campos del formulario).
    """
    seleccionados: list[tuple[int, str]] = []
    for escenario in catalogo:
        if not (formulario_bruto.get(f"incluir_{escenario.escenario_id}") or ""):
            continue
        orden_bruto = (formulario_bruto.get(f"orden_{escenario.escenario_id}", "") or "").strip()
        try:
            orden = int(orden_bruto)
        except ValueError:
            raise ValueError(f"El orden de «{escenario.nombre}» debe ser un número entero.")
        if orden <= 0:
            raise ValueError(f"El orden de «{escenario.nombre}» debe ser mayor que cero.")
        seleccionados.append((orden, escenario.escenario_id))

    ordenes = [orden for orden, _ in seleccionados]
    if len(ordenes) != len(set(ordenes)):
        raise ValueError("Dos escenarios no pueden compartir el mismo número de orden.")

    seleccionados.sort(key=lambda par: par[0])
    return tuple(escenario_id for _, escenario_id in seleccionados)


async def _suites_con_error(request: Request, composicion: Composicion, error: str):
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="suites.html",
        context={
            "seccion": "suites",
            "suites": await composicion.administracion_suites.listar(),
            "buscar": "",
            "error": error,
        },
        status_code=400,
    )


def _suite_no_encontrada(request: Request):
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="no_encontrado.html",
        context={
            "seccion": "suites",
            "titulo": "Suite no encontrada",
            "detalle": "La suite solicitada no existe o ya no está disponible.",
            "ruta_vuelta": "/suites",
            "texto_vuelta": "Volver a suites",
        },
        status_code=404,
    )


def _corrida_no_encontrada(request: Request):
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="no_encontrado.html",
        context={
            "seccion": "suites",
            "titulo": "Corrida no encontrada",
            "detalle": "La corrida solicitada no existe o ya no está disponible.",
            "ruta_vuelta": "/suites/corridas",
            "texto_vuelta": "Volver a corridas",
        },
        status_code=404,
    )


def _no_encontrado(
    request: Request,
    *,
    titulo: str = "Ejecución no encontrada",
    detalle: str = "La ejecución solicitada no existe o ya no está disponible.",
):
    """404 con HTML del producto, nunca el JSON por defecto de FastAPI.

    `titulo`/`detalle` son personalizables (B7): la misma pantalla sirve
    tanto para "no existe" como para "existe, pero no es elegible para
    generar una operación derivada" -dos motivos distintos, misma forma de
    presentarlos, sin inventar una segunda plantilla de error.
    """
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="no_encontrado.html",
        context={
            "seccion": "historial",
            "titulo": titulo,
            "detalle": detalle,
            "ruta_vuelta": "/historial",
            "texto_vuelta": "Volver al historial",
        },
        status_code=404,
    )


def _leer_expectativas(
    formulario_bruto, perfil, mti_respuesta: str = MTI_RESPUESTA_COMPRA
) -> Expectativas | None:
    """Lee `estado_esperado` y `tipo_esperado_{n}`/`valor_esperado_{n}` del
    formulario, igual que `campos_manuales` se lee de `campo_{n}`.

    A diferencia de `campos_manuales` -donde un `campo_2` forzado a mano
    simplemente nunca se mira, porque `armar_compra` reconstruye el 0100
    entero desde cero-, aqui un `tipo_esperado_{n}`/`valor_esperado_{n}` para
    un `n` que `campos_permitidos_expectativa` NO declara (sensible, o
    sencillamente no soportado por el perfil/MTI de respuesta) hace fallar la
    lectura por completo: la UI real jamas emite un control para un numero no
    permitido, asi que su sola presencia en el formulario es evidencia de una
    peticion manipulada, no una eleccion legitima que deba ignorarse en
    silencio ni reinterpretarse como "no se pidio nada". El mensaje de error
    nunca repite el numero de campo ni ningun valor enviado: alguien
    forzando el nombre exacto de un DE sensible ya sabe cual DE probo, pero el
    mensaje no se lo confirma.

    Devuelve `None` solo cuando el formulario, ya sabido limpio, no fijo
    ninguna expectativa -nunca un `Expectativas` vacio-: la ausencia de
    expectativa es un estado propio, no un caso particular de "todo vacio", y
    tampoco debe confundirse con una peticion rechazada.
    """
    permitidos = campos_permitidos_expectativa(perfil, mti_respuesta)
    for clave in formulario_bruto:
        for prefijo in ("tipo_esperado_", "valor_esperado_"):
            if clave.startswith(prefijo) and clave[len(prefijo):] not in permitidos:
                raise ValueError(
                    "El formulario incluye una expectativa para un campo que no "
                    "está permitido."
                )

    estado_bruto = (formulario_bruto.get("estado_esperado", "") or "").strip()
    estado = EstadoEjecucion(estado_bruto) if estado_bruto else None

    campos: dict[str, ExpectativaCampo] = {}
    for numero in permitidos:
        tipo = (formulario_bruto.get(f"tipo_esperado_{numero}", "") or "").strip()
        if not tipo:
            continue
        valor = (formulario_bruto.get(f"valor_esperado_{numero}", "") or "").strip()
        campos[numero] = ExpectativaCampo(tipo=tipo, valor=valor if tipo == "igual" else None)

    if estado is None and not campos:
        return None
    return Expectativas(estado=estado, campos=campos)


def _leer_opcionales_activos(mapping, perfil, mti: str = MTI_COMPRA) -> frozenset[str]:
    """El conjunto de opcionales que la pantalla debe seguir mostrando como
    fila, tras este envio: los que ya venian marcados en el campo oculto
    `opcionales_activos` (CSV), mas cualquiera que ya traiga un valor escrito
    -asi un campo agregado y llenado no desaparece si por algun motivo el
    campo oculto no lo incluyera-. Nunca incluye numeros que el perfil no
    reconozca como opcional: un CSV manipulado a mano no puede reintroducir un
    campo protegido por esta via -`filas_constructor`/`validar_campos_manuales`
    igual lo rechazarian, pero esto evita mostrar una fila que no correspondia-.

    `mti` (B4): que MTI gobierna esta lectura -compra por defecto, para no
    tocar ningun llamador existente-, para que compra financiera (0200)
    reutilice esta misma funcion en vez de una copia.
    """
    politica = perfil.politica(mti)
    desde_csv = {
        numero.strip()
        for numero in (mapping.get("opcionales_activos", "") or "").split(",")
        if numero.strip()
    }
    desde_valores = {
        numero
        for numero in politica.opcionales
        if (mapping.get(f"campo_{numero}", "") or "").strip()
    }
    return frozenset((desde_csv | desde_valores) & politica.opcionales)


def _leer_enviado(
    mapping, perfil, *, mti: str = MTI_COMPRA, mti_respuesta: str = MTI_RESPUESTA_COMPRA
) -> dict:
    """Extrae card_id/monto/conexion_id/campos_manuales/expectativas/nombre de
    un mapping tipo formulario -o de una querystring, que expone la misma
    interfaz de lectura (`.get()`, iterable por clave)-.

    Un solo lugar para lo que antes se repetia casi identico en el POST de
    compra y en los dos POST de escenario: eso es lo que permite que "cambiar
    de conexion" (una navegacion GET que reenvia el mismo `<form>`) conserve
    exactamente lo mismo que ya conservaba un error de validacion -mismo
    criterio de lectura, sin una segunda implementacion que pudiera divergir.

    `mti`/`mti_respuesta` (B4): parametrizados -compra por defecto- para que
    compra financiera (0200/0210) reutilice esta misma lectura: ambas
    operaciones comparten forma (tarjeta, monto, campos editables/opcionales,
    expectativas), asi que duplicar esta funcion solo por el MTI hubiera sido
    exactamente el antipatron que este proyecto evita.
    """
    politica = perfil.politica(mti)
    opcionales_activos = _leer_opcionales_activos(mapping, perfil, mti)
    numeros_a_leer = politica.editables | opcionales_activos
    campos_manuales = {
        numero: valor
        for numero in numeros_a_leer
        if (valor := (mapping.get(f"campo_{numero}", "") or "").strip())
    }
    try:
        expectativas = _leer_expectativas(mapping, perfil, mti_respuesta)
    except ValueError:
        expectativas = None
    return {
        "card_id": (mapping.get("card_id", "") or ""),
        "monto": (mapping.get("monto", "") or ""),
        "conexion_id": (mapping.get("conexion_id", "") or ""),
        "campos_manuales": campos_manuales,
        "opcionales_activos": opcionales_activos,
        "nombre_escenario": (mapping.get("nombre", "") or ""),
        "expectativas": expectativas,
    }


def _leer_enviado_echo(mapping, perfil) -> dict:
    """Version de `_leer_enviado` para Echo: sin tarjeta, monto ni opcionales
    -esta operacion solo tiene DE70-. Mismo criterio de un unico lugar de
    lectura, para que "cambiar de conexion" conserve exactamente lo mismo que
    ya conserva un error de validacion.
    """
    de70 = (mapping.get("de70", "") or "").strip()
    try:
        expectativas = _leer_expectativas(mapping, perfil, mti_respuesta=MTI_RESPUESTA_ECHO)
    except ValueError:
        expectativas = None
    return {
        "conexion_id": (mapping.get("conexion_id", "") or ""),
        "de70": de70,
        "campos_manuales": ({"70": de70} if de70 else {}),
        "nombre_escenario": (mapping.get("nombre", "") or ""),
        "expectativas": expectativas,
    }


def _expectativas_de_ejecucion(ejecucion) -> Expectativas | None:
    """Reconstruye la `Expectativas` que se evaluo en su momento, a partir del
    snapshot persistido -nunca desde un escenario, que puede haber cambiado o
    ya no existir-. `None` si la ejecucion no tenia expectativas o si el JSON
    guardado no se puede interpretar -nunca inventa una expectativa a partir
    de datos que no se pueden leer.
    """
    if not ejecucion.evaluacion_json:
        return None
    try:
        datos = json.loads(ejecucion.evaluacion_json)
        return expectativas_desde_dict(datos["expectativas"])
    except (ValueError, KeyError, TypeError):
        return None


def _enviado_con_tarjeta_desde_ejecucion(
    campos_manuales: dict[str, str], opcionales_activos: frozenset[str],
    ejecucion, expectativas,
) -> dict:
    """Forma de `enviado` para operaciones con tarjeta (compra, compra
    financiera): `_formulario`/`_formulario_financiera` esperan `card_id`/
    `monto` de primera clase."""
    return {
        "card_id": ejecucion.card_id,
        "monto": str(ejecucion.monto),
        "conexion_id": "",
        "campos_manuales": campos_manuales,
        "opcionales_activos": opcionales_activos,
        "nombre_escenario": "",
        "expectativas": expectativas,
    }


def _enviado_echo_desde_ejecucion(
    campos_manuales: dict[str, str], opcionales_activos: frozenset[str],
    ejecucion, expectativas,
) -> dict:
    """Forma de `enviado` para echo: `_formulario_echo` espera `de70`, sin
    `card_id` ni `monto` -esta operacion nunca los tuvo."""
    return {
        "conexion_id": "",
        "de70": campos_manuales.get("70", ""),
        "campos_manuales": campos_manuales,
        "nombre_escenario": "",
        "expectativas": expectativas,
    }


#: MTI -> (requiere verificar que la tarjeta siga disponible, constructor de
#: `enviado`). Unica fuente de "como se traduce una solicitud persistida a lo
#: que la pantalla de esa operacion espera" (B4, punto 25: generalizar
#: `_reconstruir_desde_ejecucion` mas alla de compra, con dispatch/adapter en
#: vez de un `if mti == ... elif ...` que creciera por operacion). Un MTI que
#: no este aqui simplemente no puede reutilizarse desde el historial todavia
#: -`_reconstruir_desde_ejecucion` devuelve `None`, nunca un intento a medias.
#:
#: B5: las entradas "con tarjeta" (compra, compra financiera, y cualquier
#: operacion futura que se agregue a `OPERACIONES_CON_TARJETA`) se derivan
#: del registro declarativo -nunca se listan aqui una por una-; Echo se
#: agrega aparte porque no es una operacion con tarjeta (no vive en ese
#: registro, ver docstring de `web/operaciones.py`).
_RECONSTRUCCION_POR_MTI: dict[str, tuple[bool, Callable]] = {
    **{op.mti: (True, _enviado_con_tarjeta_desde_ejecucion) for op in OPERACIONES_CON_TARJETA},
    MTI_ECHO: (False, _enviado_echo_desde_ejecucion),
}


async def _reconstruir_desde_ejecucion(
    composicion: Composicion, id_ejecucion: int
) -> tuple[dict, str | None, str | None] | None:
    """Recupera la configuracion de una ejecucion pasada para "Editar y volver
    a ejecutar"/"Guardar como escenario" desde el resultado.

    Nunca reconstruye el PAN ni ningun otro dato sensible: `card_id` alcanza
    para que el builder de la operacion derive de nuevo el mensaje con la
    tarjeta real. Los campos editables se recuperan de la SOLICITUD ya
    persistida (enmascarada, pero los campos editables del perfil genérico
    -3, 22, 37, 41, 49, 70- no son sensibles), nunca de la respuesta ni de un
    valor enmascarado que pudiera confundirse con datos reales de tarjeta.
    Las expectativas se reconstruyen del snapshot propio de la ejecucion
    (`evaluacion_json`), nunca de un escenario -que pudo cambiar o ya no
    existir-: por eso ninguna de las dos cosas depende del estado ACTUAL de
    ningun escenario.

    Generalizada en B4 (antes solo reconstruia compra, ver
    `_RECONSTRUCCION_POR_MTI`): la politica de CADA mti decide que campos
    recuperar de la solicitud -nunca hardcodeado a la de compra-, y solo el
    "requiere tarjeta" (compra/financiera si, echo no) distingue si se avisa
    de una tarjeta ya no disponible.

    Devuelve `None` si la ejecucion no existe, o si su MTI todavia no tiene
    una reconstruccion soportada (`_RECONSTRUCCION_POR_MTI`). En caso
    contrario, devuelve `(enviado, conexion_id_resuelta_o_None, error_o_None)`.

    NINGUNA sustitucion silenciosa: si la tarjeta usada ya no esta disponible
    (desactivada o eliminada), o si la conexion usada no se puede identificar
    hoy entre las administradas (o nunca se intento transmitir), se explica
    en `error_o_None` y se deja sin resolver -el constructor ya bloquea
    "Ejecutar transacción" en esos casos (`tarjeta_no_disponible`,
    `conexion_actual is None`), pero antes de esta correccion lo hacia sin
    decir por que: la persona solo veia el boton deshabilitado. Los dos
    problemas pueden coexistir; el mensaje los junta, no se queda solo con
    el primero.
    """
    detalle = await composicion.consultas.detalle_ejecucion(id_ejecucion)
    if detalle is None:
        return None

    ejecucion = detalle.ejecucion
    config = _RECONSTRUCCION_POR_MTI.get(ejecucion.mti_solicitud)
    if config is None:
        return None
    requiere_tarjeta, construir_enviado = config

    politica = composicion.perfil.politica(ejecucion.mti_solicitud)
    campos_manuales = {
        numero: valor
        for numero in (politica.editables | politica.opcionales)
        if (valor := detalle.solicitud.valor(numero)) is not None
    }
    opcionales_activos = frozenset(n for n in campos_manuales if n in politica.opcionales)
    enviado = construir_enviado(
        campos_manuales, opcionales_activos, ejecucion, _expectativas_de_ejecucion(ejecucion)
    )

    problemas: list[str] = []

    # La solicitud persistida con el formato de texto heredado (anterior a la
    # persistencia estructurada) no es demostrablemente fiel -ver el docstring
    # de `MensajeSerializado.fiel`-: un valor podria haber quedado partido por
    # el separador sin que se pueda distinguir. Recuperar campos editables de
    # ahi es la mejor aproximacion posible, pero no debe presentarse como si
    # fuera "la configuracion exacta": se avisa, sin bloquear la ejecucion
    # -la persona decide si revisa y corrige antes de continuar.
    if detalle.solicitud.disponible and not detalle.solicitud.fiel:
        problemas.append(
            "Esta ejecución se registró con un formato anterior: los campos "
            "recuperados son la mejor aproximación posible, pero no puede "
            "garantizarse que sean exactos. Revíselos antes de ejecutar."
        )

    if requiere_tarjeta:
        tarjetas_disponibles = await composicion.consultas.tarjetas()
        if not any(t.card_id == ejecucion.card_id for t in tarjetas_disponibles):
            problemas.append(
                f"La tarjeta {ejecucion.card_id!r} usada en esa ejecución ya no está disponible "
                "(fue desactivada o eliminada del catálogo). Seleccione otra tarjeta para poder "
                "ejecutar."
            )

    conexion_resuelta: str | None = None
    if ejecucion.destino_host is None:
        problemas.append(
            "Esta ejecución no llegó a intentar transmisión por la red, así que no hay una "
            "conexión que recuperar. Seleccione una conexión para poder ejecutar."
        )
    else:
        activas = await composicion.administracion_conexiones.listar_activas()
        candidatas = [
            c for c in activas
            if c.host == ejecucion.destino_host and c.puerto == ejecucion.destino_puerto
        ]
        if len(candidatas) == 1:
            conexion_resuelta = candidatas[0].conexion_id
        else:
            problemas.append(
                "No se pudo determinar automáticamente qué conexión administrada corresponde "
                f"a {ejecucion.destino_host}:{ejecucion.destino_puerto}. Seleccione una "
                "conexión para poder ejecutar."
            )

    error = " ".join(problemas) if problemas else None
    return enviado, conexion_resuelta, error


class _EjecucionNoReutilizable(Exception):
    """`?ejecucion_id=` vino, pero no es un entero, o no hay nada que
    reconstruir con el (no existe, o su MTI no esta en
    `_RECONSTRUCCION_POR_MTI`). El llamador debe mostrar un 404 explicado."""


async def _resolver_reutilizacion_de_ejecucion(
    composicion: Composicion, ejecucion_id: str | None, escenario_id: str | None
) -> tuple[dict | None, str | None, str | None]:
    """`(enviado, conexion_id_resuelta, error)` a partir de `?ejecucion_id=`,
    o `(None, None, None)` si no aplica -no vino, o ya vino `escenario_id`
    (cargar un escenario sigue siendo la fuente de verdad en ese caso)-.

    Comun a las tres pantallas de constructor (B4, punto 25): antes esta
    resolucion vivia solo en `pantalla_compra`; ahora `pantalla_echo` y
    `pantalla_compra_financiera` la llaman igual, sin duplicar el parseo de
    `ejecucion_id` ni el manejo de "no encontrado".
    """
    if not ejecucion_id or escenario_id:
        return None, None, None
    try:
        numero = int(ejecucion_id)
    except ValueError:
        numero = None
    reconstruido = await _reconstruir_desde_ejecucion(composicion, numero) if numero is not None else None
    if reconstruido is None:
        raise _EjecucionNoReutilizable()
    return reconstruido




async def _construir_vista_previa(
    composicion: Composicion,
    card_id: str,
    monto: str,
    campos_manuales: dict[str, str],
    *,
    servicio_vista_previa=None,
    fabrica_datos=DatosCompra,
):
    """Vista previa (Bloque 7) para una pantalla con tarjeta y monto: `None`
    con un motivo explicado en vez de una excepcion, en CUALQUIER estado
    incompleto de la pantalla -sin tarjeta todavia, monto invalido, un campo
    manual con forma incorrecta mientras se escribe-. Es solo lectura: nunca
    reserva STAN, nunca toca la red, nunca persiste nada.

    `servicio_vista_previa`/`fabrica_datos` (B4): parametrizados -compra por
    defecto, para no tocar su unico llamador previo- asi que compra financiera
    (0200) reutiliza esta misma funcion con `composicion.vista_previa_compra_financiera`
    y `DatosCompraFinanciera` en vez de una segunda copia casi identica.
    """
    servicio_vista_previa = servicio_vista_previa or composicion.vista_previa
    if not card_id.strip():
        return None, "Seleccione una tarjeta de prueba para ver la vista previa."
    try:
        monto_valido = presentacion.validar_monto(monto)
    except ValueError:
        return None, "Indique un monto válido para ver la vista previa."
    try:
        vista = await servicio_vista_previa.construir(
            fabrica_datos(card_id=card_id, monto=monto_valido, campos_manuales=campos_manuales)
        )
    except TarjetaNoDisponibleParaVistaPrevia:
        return None, "La tarjeta elegida no está disponible."
    except ErrorDeCamposManuales as error:
        return None, str(error)
    return vista, None


def crear_app(composicion: Composicion | None = None) -> FastAPI:
    """Construye la aplicacion. Con `composicion` explicita, la usa en lugar de la real."""
    app = FastAPI(
        title="SibuTestLab8583",
        description="Simulador de transacciones ISO 8583 - compra 0100/0110",
    )
    if composicion is not None:
        app.dependency_overrides[obtener_composicion] = lambda: composicion
    # La hoja de estilos y el script minimo se sirven como archivos, no
    # embebidos en la plantilla: el navegador los cachea y las plantillas
    # quedan solo con estructura.
    app.mount(
        RUTA_ESTATICA,
        StaticFiles(directory=str(DIRECTORIO_ESTATICO)),
        name="estatico",
    )
    app.include_router(enrutador)
    return app


app = crear_app()

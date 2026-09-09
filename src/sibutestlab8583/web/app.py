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

import json
from pathlib import Path
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..application.conexiones import (
    ConexionNoEncontrada,
    DatosEdicionConexion,
    DatosNuevaConexion,
)
from ..application.corredor_suites import SuiteNoEjecutable
from ..application.ejecutor_escenarios import EscenarioNoEjecutable
from ..application.escenarios import (
    DatosEdicionEscenario,
    DatosNuevoEscenario,
    EscenarioNoEncontrado,
)
from ..application.orquestador import TarjetaDesconocida
from ..application.suites import DatosEdicionSuite, DatosNuevaSuite, SuiteNoEncontrada
from ..application.tarjetas import (
    DatosEdicionTarjeta,
    DatosNuevaTarjeta,
    TarjetaNoEncontrada,
)
from ..composicion import Composicion, Configuracion
from ..domain.errores import ErrorDelSimulador
from ..domain.expectativas import (
    campos_permitidos_expectativa,
    expectativas_desde_dict,
    validar_expectativas,
)
from ..domain.modelos import (
    MTI_COMPRA,
    MTI_RESPUESTA_COMPRA,
    DatosCompra,
    DestinoTcp,
    EstadoEjecucion,
    ExpectativaCampo,
    Expectativas,
)
from . import presentacion

RAIZ_WEB = Path(__file__).parent
PLANTILLAS = Jinja2Templates(directory=str(RAIZ_WEB / "plantillas"))
DIRECTORIO_ESTATICO = RAIZ_WEB / "estatico"
RUTA_ESTATICA = "/estatico"

# La navegacion es la misma en todas las pantallas: se declara una vez como
# global de Jinja en lugar de repetirla en el contexto de cada endpoint. La
# pantalla activa si es propia de cada ruta y viaja en su contexto (`seccion`).
PLANTILLAS.env.globals["secciones"] = presentacion.SECCIONES

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
    # mecanismo aparte -ver `cambiar_conexion`, POST- precisamente para que
    # los valores del constructor no viajen en la URL.
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
    enviado = None
    error_carga = None
    if ejecucion_id and not escenario_id:
        try:
            numero = int(ejecucion_id)
        except ValueError:
            numero = None
        reconstruido = (
            await _reconstruir_desde_ejecucion(composicion, numero) if numero is not None else None
        )
        if reconstruido is None:
            return await _formulario(
                request, composicion,
                error="La ejecución que se quiere reutilizar no existe o ya no está disponible.",
                estado_http=404,
            )
        enviado, conexion_id_resuelta, error_carga = reconstruido
        if conexion_id_resuelta is not None:
            conexion_id = conexion_id_resuelta

    return await _formulario(
        request,
        composicion,
        conexion_id=conexion_id,
        escenario_id=escenario_id,
        enviado=enviado,
        error=error_carga,
    )


@enrutador.post("/", response_class=HTMLResponse)
async def cambiar_conexion(
    request: Request,
    composicion: Composicion = Depends(obtener_composicion),
):
    """Cambia la conexion elegida en el constructor SIN perder lo que ya
    estaba escrito -tarjeta, monto, campos editables, expectativas, nombre
    del escenario- y SIN ejecutar ninguna transaccion ni guardar ningun
    escenario: solo vuelve a renderizar `compra.html` con el estado enviado y
    la conexion nueva. Es el destino del boton "Cambiar" de la barra de
    conexion, que vive dentro del mismo `<form>` del constructor con
    `formaction="/"` (metodo POST, heredado del formulario) y
    `formnovalidate` -asi un `monto` vacio o invalido (campo `required`) no
    bloquea el cambio de conexion, que es justamente el proposito de este
    mecanismo-.

    POST y no GET a proposito: por-diseno un envio POST no queda en la URL
    ni en el historial del navegador, y los frameworks de servidor (incluido
    Uvicorn) no registran el cuerpo de la peticion en el log de acceso -solo
    metodo y ruta-. Antes de este cambio, el mismo mecanismo iba por GET con
    `formmethod="get"`, y el monto/los campos/el nombre del escenario
    quedaban en la querystring, visibles en el historial del navegador y en
    los logs de acceso por defecto del servidor (nunca el PAN: los unicos
    campos que se leen son los editables segun el perfil -3, 22, 37, 41,
    49-, estructuralmente excluidos de ser sensibles). Este endpoint corrige
    esa exposicion sin introducir sesion ni almacenamiento en el navegador:
    el propio POST, mas `_formulario`, alcanzan.

    `ir_a_conexion` es el nombre propio del boton -deliberadamente distinto
    de `conexion_id`, el campo oculto del mismo formulario que lleva el
    valor VIEJO- para que el destino real de la navegacion sea siempre el
    que la persona eligio, nunca el que ya estaba.
    """
    formulario_bruto = await request.form()
    enviado = _leer_enviado(formulario_bruto, composicion.perfil)
    ir_a_conexion = (formulario_bruto.get("ir_a_conexion", "") or "").strip() or None
    escenario_id = (formulario_bruto.get("escenario_id", "") or "").strip() or None

    return await _formulario(
        request,
        composicion,
        conexion_id=ir_a_conexion,
        escenario_id=escenario_id,
        enviado=enviado,
    )


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
    # Los campos manuales, las expectativas y el nombre del escenario se leen
    # del mismo formulario -se hayan guardado o no en ningun escenario-:
    # "Ejecutar transacción" siempre evalua contra lo que esta escrito en la
    # pantalla en ese momento, igual que ya hace con card_id/monto -no contra
    # lo ultimo guardado-. Se calculan antes del try/except para que, si algo
    # falla, el formulario se vuelva a mostrar con lo que la persona escribio,
    # no en blanco.
    formulario_bruto = await request.form()
    enviado = _leer_enviado(formulario_bruto, composicion.perfil)
    campos_manuales = enviado["campos_manuales"]
    expectativas = enviado["expectativas"]

    # --- entrada del usuario: errores controlados, nunca un 500 ---
    try:
        datos, destino, tiempo_limite = await _interpretar_formulario(
            composicion, card_id, monto, conexion_id, campos_manuales
        )
        expectativas = _leer_expectativas(formulario_bruto, composicion.perfil)
        if expectativas is not None:
            validar_expectativas(expectativas, composicion.perfil, MTI_RESPUESTA_COMPRA)
    except ValueError as error:
        return await _formulario(
            request, composicion, escenario_id=escenario_id or None,
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
                return await _formulario(
                    request, composicion, escenario_id=escenario_id,
                    error="Este escenario está inactivo. Reactívelo para poder ejecutarlo, "
                    "o guarde una copia.",
                    enviado=enviado, estado_http=400,
                )
            id_escenario_asociado = escenario_asociado.escenario_id
            nombre_escenario_asociado = escenario_asociado.nombre

    # --- el recorrido lo hace el orquestador, no esta capa ---
    try:
        orquestador = await composicion.orquestador(destino, tiempo_limite=tiempo_limite)
        resultado = await orquestador.ejecutar_compra(
            datos, escenario_id=id_escenario_asociado, escenario_nombre=nombre_escenario_asociado,
            expectativas=expectativas,
        )
    except TarjetaDesconocida:
        return await _formulario(
            request,
            composicion,
            escenario_id=escenario_id or None,
            error=f"No existe la tarjeta {card_id!r} en el catálogo, o está inactiva.",
            enviado=enviado,
            estado_http=400,
        )
    except ErrorDelSimulador as error:
        # Fallo de infraestructura: no es un rechazo del autorizador y no debe
        # presentarse como tal. Tampoco se muestra la excepcion.
        return await _formulario(
            request, composicion, escenario_id=escenario_id or None,
            aviso=presentacion.aviso_de_error(error), enviado=enviado,
        )

    return PLANTILLAS.TemplateResponse(
        request=request,
        name="resultado.html",
        context=presentacion.contexto_de_resultado(
            resultado, destino, composicion.descripciones_de_campos
        ),
    )


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

    return PLANTILLAS.TemplateResponse(
        request=request,
        name="detalle.html",
        context=presentacion.contexto_de_detalle(
            detalle, composicion.descripciones_de_campos
        ),
    )


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
    composicion: Composicion = Depends(obtener_composicion),
):
    """Crea un escenario. Es el destino de "Guardar como escenario" y de
    "Guardar como copia" -ambas son la misma operacion: crear uno nuevo a
    partir del estado actual del constructor-.
    """
    formulario_bruto = await request.form()
    enviado = _leer_enviado(formulario_bruto, composicion.perfil)
    campos_manuales = enviado["campos_manuales"]
    expectativas = enviado["expectativas"]
    try:
        monto_decimal = presentacion.validar_monto(monto)
        expectativas = _leer_expectativas(formulario_bruto, composicion.perfil)
        creado = await composicion.administracion_escenarios.crear(
            DatosNuevoEscenario(
                nombre=nombre,
                card_id=card_id.strip(),
                conexion_id=conexion_id,
                monto=monto_decimal,
                campos_manuales=campos_manuales,
                expectativas=expectativas,
            )
        )
    except ValueError as error:
        return await _formulario(
            request, composicion, error=str(error), enviado=enviado, estado_http=400
        )
    return RedirectResponse(f"/?escenario_id={creado.escenario_id}", status_code=303)


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
    parcha lo que ya estaba guardado -mismo criterio que crear-.
    """
    formulario_bruto = await request.form()
    enviado = _leer_enviado(formulario_bruto, composicion.perfil)
    campos_manuales = enviado["campos_manuales"]
    expectativas = enviado["expectativas"]
    try:
        monto_decimal = presentacion.validar_monto(monto)
        expectativas = _leer_expectativas(formulario_bruto, composicion.perfil)
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
        return await _formulario(
            request, composicion, escenario_id=escenario_id,
            error=str(error), enviado=enviado, estado_http=400,
        )
    return RedirectResponse(f"/?escenario_id={escenario_id}", status_code=303)


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
    return RedirectResponse(f"/?escenario_id={copia.escenario_id}", status_code=303)


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
    mismo diagnostico que "cargar" ya calcula (`_formulario`), reutilizado
    aqui en vez de duplicado.
    """
    try:
        resultado = await composicion.ejecutor_escenarios.ejecutar(escenario_id)
    except EscenarioNoEncontrado:
        return _escenario_no_encontrado(request)
    except EscenarioNoEjecutable:
        return await _formulario(request, composicion, escenario_id=escenario_id, estado_http=400)
    except TarjetaDesconocida:
        escenario = await composicion.administracion_escenarios.obtener(escenario_id)
        return await _formulario(
            request, composicion, escenario_id=escenario_id,
            error=f"No existe la tarjeta {escenario.card_id!r} en el catálogo, o está inactiva.",
            estado_http=400,
        )
    except ErrorDelSimulador as error:
        return await _formulario(
            request, composicion, escenario_id=escenario_id,
            aviso=presentacion.aviso_de_error(error),
        )

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
            resultado, destino, composicion.descripciones_de_campos
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
        },
    )


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


def _no_encontrado(request: Request):
    """404 con HTML del producto, nunca el JSON por defecto de FastAPI."""
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="no_encontrado.html",
        context={
            "seccion": "historial",
            "titulo": "Ejecución no encontrada",
            "detalle": "La ejecución solicitada no existe o ya no está disponible.",
            "ruta_vuelta": "/historial",
            "texto_vuelta": "Volver al historial",
        },
        status_code=404,
    )


def _leer_expectativas(formulario_bruto, perfil) -> Expectativas | None:
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
    permitidos = campos_permitidos_expectativa(perfil, MTI_RESPUESTA_COMPRA)
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


def _leer_enviado(mapping, perfil) -> dict:
    """Extrae card_id/monto/conexion_id/campos_manuales/expectativas/nombre de
    un mapping tipo formulario -o de una querystring, que expone la misma
    interfaz de lectura (`.get()`, iterable por clave)-.

    Un solo lugar para lo que antes se repetia casi identico en el POST de
    compra y en los dos POST de escenario: eso es lo que permite que "cambiar
    de conexion" (una navegacion GET que reenvia el mismo `<form>`) conserve
    exactamente lo mismo que ya conservaba un error de validacion -mismo
    criterio de lectura, sin una segunda implementacion que pudiera divergir.
    """
    editables = perfil.politica(MTI_COMPRA).editables
    campos_manuales = {
        numero: valor
        for numero in editables
        if (valor := (mapping.get(f"campo_{numero}", "") or "").strip())
    }
    try:
        expectativas = _leer_expectativas(mapping, perfil)
    except ValueError:
        expectativas = None
    return {
        "card_id": (mapping.get("card_id", "") or ""),
        "monto": (mapping.get("monto", "") or ""),
        "conexion_id": (mapping.get("conexion_id", "") or ""),
        "campos_manuales": campos_manuales,
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


async def _reconstruir_desde_ejecucion(
    composicion: Composicion, id_ejecucion: int
) -> tuple[dict, str | None, str | None] | None:
    """Recupera la configuracion de una ejecucion pasada para "Editar y volver
    a ejecutar"/"Guardar como escenario" desde el resultado.

    Nunca reconstruye el PAN ni ningun otro dato sensible: `card_id` alcanza
    para que `armar_compra` derive de nuevo el 0100 con la tarjeta real. Los
    campos editables se recuperan de la SOLICITUD ya persistida (enmascarada,
    pero los campos editables del perfil genérico -3, 22, 37, 41, 49- no son
    sensibles), nunca de la respuesta ni de un valor enmascarado que pudiera
    confundirse con datos reales de tarjeta. Las expectativas se reconstruyen
    del snapshot propio de la ejecucion (`evaluacion_json`), nunca de un
    escenario -que pudo cambiar o ya no existir-: por eso ninguna de las dos
    cosas depende del estado ACTUAL de ningun escenario.

    Devuelve `None` si la ejecucion no existe. En caso contrario, devuelve
    `(enviado, conexion_id_resuelta_o_None, error_o_None)`.

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
    editables = composicion.perfil.politica(MTI_COMPRA).editables
    campos_manuales = {
        numero: valor
        for numero in editables
        if (valor := detalle.solicitud.valor(numero)) is not None
    }
    enviado = {
        "card_id": ejecucion.card_id,
        "monto": str(ejecucion.monto),
        "conexion_id": "",
        "campos_manuales": campos_manuales,
        "nombre_escenario": "",
        "expectativas": _expectativas_de_ejecucion(ejecucion),
    }

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


async def _interpretar_formulario(
    composicion: Composicion,
    card_id: str,
    monto: str,
    conexion_id: str,
    campos_manuales: dict[str, str],
) -> tuple[DatosCompra, DestinoTcp, float]:
    """Convierte el formulario en objetos del dominio. Lanza `ValueError` util.

    El formulario nunca trae host, puerto ni timeout: transporta unicamente
    `conexion_id`. El servidor vuelve a buscar host/puerto/timeout en la
    conexion administrada, y solo si esta activa - un `conexion_id` que no
    exista, este desactivado, o haya sido manipulado a mano, se rechaza igual
    que un `card_id` de una tarjeta inactiva.
    """
    if not card_id.strip():
        raise ValueError("Seleccione una tarjeta de prueba.")
    datos = DatosCompra(
        card_id=card_id.strip(),
        monto=presentacion.validar_monto(monto),
        campos_manuales=campos_manuales,
    )

    conexion = await composicion.administracion_conexiones.obtener_activa(conexion_id)
    if conexion is None:
        raise ValueError("Seleccione una conexión activa, o verifique que siga disponible.")

    destino = DestinoTcp(host=conexion.host, puerto=conexion.puerto)
    return datos, destino, conexion.timeout


async def _formulario(
    request: Request,
    composicion: Composicion,
    *,
    conexion_id: str | None = None,
    escenario_id: str | None = None,
    error: str | None = None,
    aviso=None,
    enviado: dict | None = None,
    estado_http: int = 200,
):
    """Renderiza la pantalla de compra, opcionalmente con un aviso o un error.

    Ni la conexion ni el escenario cargado viven en una sesion ni en una
    cookie: llegan por query string en el GET normal (`?conexion_id=`,
    `?escenario_id=`), o por el propio `enviado` cuando se re-renderiza tras
    un error de un POST.

    REGLA DE NO SUSTITUCION SILENCIOSA: si se pidio una tarjeta o una conexion
    especificas (por query, por `enviado`, o por venir de un escenario) y esa
    tarjeta/conexion no esta entre las activas, NO se reemplaza por la primera
    disponible -eso cambiaria la intencion sin que nadie lo haya pedido-. Se
    deja sin resolver y se bloquea "Ejecutar transacción" hasta que alguien
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

    if enviado:
        card_id = enviado.get("card_id", "")
        monto = enviado.get("monto", "")
        campos_manuales_enviados = enviado.get("campos_manuales", {})
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
        conexion_id_solicitada = (
            conexion_id if conexion_id is not None else escenario_actual.conexion_id
        )
        nombre_escenario = escenario_actual.nombre
        expectativas_actuales = escenario_actual.expectativas
    else:
        card_id = ""
        monto = ""
        campos_manuales_enviados = {}
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
            and (
                bloqueo_escenario["inactivo"]
                or bloqueo_escenario["incompatibilidades"]
            )
        )
    )

    campos_esperados = expectativas_actuales.campos if expectativas_actuales else {}
    estado_esperado_actual = (
        expectativas_actuales.estado.value
        if expectativas_actuales and expectativas_actuales.estado
        else ""
    )

    return PLANTILLAS.TemplateResponse(
        request=request,
        name="compra.html",
        context={
            "seccion": "compra",
            "tarjetas": tarjetas,
            "conexiones": conexiones,
            "conexion_actual": conexion_actual,
            "conexion_id": (
                conexion_actual.conexion_id if conexion_actual else (conexion_id_solicitada or "")
            ),
            "monto": monto,
            "card_id": card_id,
            "filas_constructor": presentacion.filas_constructor(
                composicion.perfil, MTI_COMPRA, composicion.descripciones_de_campos
            ),
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
                composicion.perfil, MTI_RESPUESTA_COMPRA, composicion.descripciones_de_campos,
                campos_esperados,
            ),
        },
        status_code=estado_http,
    )


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

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

from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..application.conexiones import (
    ConexionNoEncontrada,
    DatosEdicionConexion,
    DatosNuevaConexion,
)
from ..application.orquestador import TarjetaDesconocida
from ..application.tarjetas import (
    DatosEdicionTarjeta,
    DatosNuevaTarjeta,
    TarjetaNoEncontrada,
)
from ..composicion import Composicion, Configuracion
from ..domain.errores import ErrorDelSimulador
from ..domain.modelos import MTI_COMPRA, DatosCompra, DestinoTcp
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
    # Query, no Form: cambiar de conexion es una navegacion (GET), no un envio
    # de formulario. Sin JavaScript, "Cambiar conexion" es una lista de enlaces
    # a "/?conexion_id=...", y esto es lo que cada uno resuelve.
    conexion_id: str | None = Query(None),
    composicion: Composicion = Depends(obtener_composicion),
):
    return await _formulario(request, composicion, conexion_id=conexion_id)


@enrutador.post("/compra", response_class=HTMLResponse)
async def ejecutar_compra(
    request: Request,
    # Los campos admiten cadena vacia a proposito: si se declararan obligatorios,
    # FastAPI responderia su propio 422 en JSON y el usuario veria un error crudo
    # en vez del formulario con la explicacion.
    card_id: str = Form(""),
    monto: str = Form(""),
    conexion_id: str = Form(""),
    composicion: Composicion = Depends(obtener_composicion),
):
    # Los campos manuales no se declaran uno por uno en la firma: se leen del
    # formulario segun lo que el perfil declare editable para el 0100. Agregar
    # un campo editable nuevo al perfil no obliga a tocar esta ruta.
    #
    # Un campo editable que llega vacio (o que no vino en el formulario) no se
    # incluye: se deja que `armar_compra` aplique el default de la politica.
    # Si se incluyera como cadena vacia, el merge lo sobreescribiria y borraria
    # el default aunque el usuario no haya tocado el campo.
    formulario_bruto = await request.form()
    editables = composicion.perfil.politica(MTI_COMPRA).editables
    campos_manuales = {
        numero: valor
        for numero in editables
        if (valor := (formulario_bruto.get(f"campo_{numero}", "") or "").strip())
    }
    enviado = {
        "card_id": card_id,
        "monto": monto,
        "conexion_id": conexion_id,
        "campos_manuales": campos_manuales,
    }

    # --- entrada del usuario: errores controlados, nunca un 500 ---
    try:
        datos, destino, tiempo_limite = await _interpretar_formulario(
            composicion, card_id, monto, conexion_id, campos_manuales
        )
    except ValueError as error:
        return await _formulario(
            request, composicion, error=str(error), enviado=enviado, estado_http=400
        )

    # --- el recorrido lo hace el orquestador, no esta capa ---
    try:
        orquestador = await composicion.orquestador(destino, tiempo_limite=tiempo_limite)
        resultado = await orquestador.ejecutar_compra(datos)
    except TarjetaDesconocida:
        return await _formulario(
            request,
            composicion,
            error=f"No existe la tarjeta {card_id!r} en el catálogo, o está inactiva.",
            enviado=enviado,
            estado_http=400,
        )
    except ErrorDelSimulador as error:
        # Fallo de infraestructura: no es un rechazo del autorizador y no debe
        # presentarse como tal. Tampoco se muestra la excepcion.
        return await _formulario(
            request, composicion, aviso=presentacion.aviso_de_error(error), enviado=enviado
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
    request: Request, composicion: Composicion = Depends(obtener_composicion)
):
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="historial.html",
        context={
            "seccion": "historial",
            "ejecuciones": await composicion.consultas.ejecuciones_recientes(),
            "avisos": presentacion.AVISOS,
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
    error: str | None = None,
    aviso=None,
    enviado: dict | None = None,
    estado_http: int = 200,
):
    """Renderiza la pantalla de compra, opcionalmente con un aviso o un error.

    La conexion elegida no vive en una sesion ni en una cookie: `conexion_id`
    llega por query string en el GET normal, o por el propio `enviado` cuando
    se re-renderiza tras un error de un POST. Sin ninguno de los dos, se
    preselecciona la primera conexion activa -igual que ya se hace con la
    primera tarjeta-, para que el primer envio nunca falle sin motivo.
    """
    conexiones = await composicion.administracion_conexiones.listar_activas()
    conexion_id = conexion_id if conexion_id is not None else (enviado or {}).get("conexion_id")
    conexion_actual = next((c for c in conexiones if c.conexion_id == conexion_id), None)
    if conexion_actual is None and conexiones:
        conexion_actual = conexiones[0]

    enviado = enviado or {}
    campos_manuales_enviados = enviado.get("campos_manuales", {})
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="compra.html",
        context={
            "seccion": "compra",
            "tarjetas": await composicion.consultas.tarjetas(),
            "conexiones": conexiones,
            "conexion_actual": conexion_actual,
            "conexion_id": conexion_actual.conexion_id if conexion_actual else "",
            "monto": enviado.get("monto", ""),
            "card_id": enviado.get("card_id", ""),
            "filas_constructor": presentacion.filas_constructor(
                composicion.perfil, MTI_COMPRA, composicion.descripciones_de_campos
            ),
            "campos_manuales": campos_manuales_enviados,
            "error": error,
            "aviso": aviso,
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

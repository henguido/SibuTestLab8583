"""Interfaz web: FastAPI con plantillas Jinja renderizadas en el servidor.

Capa deliberadamente delgada. **No** importa `aiosqlite`, `pyiso8583` ni
`asyncio`, no abre sockets, no arma mensajes ISO y no implementa ninguna de las
cuatro reglas: delega el recorrido en el orquestador que provee la composicion.

Tampoco levanta el host simulado. La arquitectura lo mantiene como proceso
aparte y la demostracion usa dos terminales: `sibu-host-demo` y `uvicorn`.

Las rutas viven en un `APIRouter` de modulo, no dentro de la fabrica: no
necesitan capturar nada del ambito de `crear_app`, y asi cada una se lee y se
prueba por separado.

La unica pieza estatica es la hoja de estilos propia, montada en `/estatico`.
No hay framework CSS, ni JavaScript, ni paso de compilacion.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..application.orquestador import TarjetaDesconocida
from ..application.tarjetas import (
    DatosEdicionTarjeta,
    DatosNuevaTarjeta,
    TarjetaNoEncontrada,
)
from ..composicion import Composicion, Configuracion
from ..domain.errores import ErrorDelSimulador
from ..domain.modelos import DatosCompra, DestinoTcp
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
    request: Request, composicion: Composicion = Depends(obtener_composicion)
):
    return await _formulario(request, composicion)


@enrutador.post("/compra", response_class=HTMLResponse)
async def ejecutar_compra(
    request: Request,
    # Los campos admiten cadena vacia a proposito: si se declararan obligatorios,
    # FastAPI responderia su propio 422 en JSON y el usuario veria un error crudo
    # en vez del formulario con la explicacion.
    card_id: str = Form(""),
    monto: str = Form(""),
    host: str = Form(""),
    puerto: str = Form(""),
    composicion: Composicion = Depends(obtener_composicion),
):
    enviado = {"card_id": card_id, "monto": monto, "host": host, "puerto": puerto}

    # --- entrada del usuario: errores controlados, nunca un 500 ---
    try:
        datos, destino = _interpretar_formulario(card_id, monto, host, puerto)
    except ValueError as error:
        return await _formulario(
            request, composicion, error=str(error), enviado=enviado, estado_http=400
        )

    # --- el recorrido lo hace el orquestador, no esta capa ---
    try:
        orquestador = await composicion.orquestador(destino)
        resultado = await orquestador.ejecutar_compra(datos)
    except TarjetaDesconocida:
        return await _formulario(
            request,
            composicion,
            error=f"No existe la tarjeta {card_id!r} en el catálogo.",
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


def _interpretar_formulario(
    card_id: str, monto: str, host: str, puerto: str
) -> tuple[DatosCompra, DestinoTcp]:
    """Convierte el formulario en objetos del dominio. Lanza `ValueError` util."""
    if not card_id.strip():
        raise ValueError("Seleccione una tarjeta de prueba.")
    datos = DatosCompra(card_id=card_id.strip(), monto=presentacion.validar_monto(monto))
    destino = DestinoTcp(
        host=presentacion.validar_host(host), puerto=presentacion.validar_puerto(puerto)
    )
    return datos, destino


async def _formulario(
    request: Request,
    composicion: Composicion,
    *,
    error: str | None = None,
    aviso=None,
    enviado: dict | None = None,
    estado_http: int = 200,
):
    """Renderiza la pantalla de compra, opcionalmente con un aviso o un error."""
    configuracion = composicion.configuracion
    enviado = enviado or {}
    return PLANTILLAS.TemplateResponse(
        request=request,
        name="compra.html",
        context={
            "seccion": "compra",
            "tarjetas": await composicion.consultas.tarjetas(),
            "host": enviado.get("host") or configuracion.host_destino,
            "puerto": enviado.get("puerto") or configuracion.puerto_destino,
            "monto": enviado.get("monto", ""),
            "card_id": enviado.get("card_id", ""),
            "error": error,
            "aviso": aviso,
            "tiempo_limite": configuracion.tiempo_limite,
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
    # La hoja de estilos se sirve como archivo, no embebida en la plantilla:
    # el navegador la cachea y las plantillas quedan solo con estructura.
    app.mount(
        RUTA_ESTATICA,
        StaticFiles(directory=str(DIRECTORIO_ESTATICO)),
        name="estatico",
    )
    app.include_router(enrutador)
    return app


app = crear_app()

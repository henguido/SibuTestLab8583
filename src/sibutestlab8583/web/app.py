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
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..application.orquestador import TarjetaDesconocida
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
        resultado = await composicion.orquestador(destino).ejecutar_compra(datos)
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

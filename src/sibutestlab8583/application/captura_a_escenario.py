"""Servicio de Captura -> Escenario (Fase E2, 2026-09-21).

Convierte un intercambio observado por el Proxy (Fase E1) en un escenario
de QA reutilizable, con REVISION HUMANA obligatoria antes de guardar
-nunca automatico (punto 12 del encargo: "el escenario no debe intentar
reproducir byte-for-byte la transaccion capturada, debe reproducir su
intencion funcional").

Responsabilidades (punto 30): validar la captura, resolver la operacion,
extraer los parametros que el formulario de revision necesita mostrar, y
delegar el guardado real en `ServicioEscenarios.crear` -nunca reimplementa
esa logica, y nunca vive en `web/app.py`.

SEGURIDAD: `MensajeProxyCapturado` (E1) es deliberadamente ciego a los
campos de un mensaje -solo trae MTI/direccion/timestamp. Este servicio
NUNCA infiere un monto, un PAN ni ningun campo de la captura: el monto, la
tarjeta y los campos opcionales los aporta la persona en el formulario de
revision (`PropuestaEscenarioCapturado` solo describe QUE se necesita
pedir, nunca un valor ya "adivinado")."""

from __future__ import annotations

from dataclasses import dataclass

from ..domain.expectativas import campos_permitidos_expectativa
from ..domain.modelos import OPERACION_POR_MTI, MTI_COMPRA, MTI_COMPRA_FINANCIERA, MTI_ECHO
from ..domain.proxy import OrigenCapturaEscenario, derivar_intercambios
from ..domain.puertos import (
    RepositorioDestinos,
    RepositorioMensajesProxy,
    RepositorioOrigenCapturaEscenario,
    RepositorioSesionesProxy,
)
from ..domain.validacion import mti_de_respuesta
from .escenarios import DatosNuevoEscenario, EscenarioAdministrado, ServicioEscenarios

#: MTIs con constructor de Escenario propio HOY
#: (`application.ejecutor_escenarios._ADAPTADORES_POR_MTI`). 0400/0420
#: quedan deliberadamente fuera: dependen de una `ejecucion_origen` concreta
#: de ESTE sistema (`application.referencia_ejecucion.ReferenciaEjecucion`),
#: que una captura externa del Proxy -pudo venir de un switch real- no
#: tiene (punto 14 del encargo: "no permitir convertir una captura aislada
#: de 0400/0420 en escenario independiente").
MTIS_CON_OPERACION_IMPORTABLE = frozenset({MTI_COMPRA, MTI_COMPRA_FINANCIERA, MTI_ECHO})


class InteraccionNoImportable(Exception):
    """El intercambio senalado no puede convertirse en escenario -MTI sin
    operacion soportada, no interpretable, o sin respuesta correlacionada."""


@dataclass(frozen=True)
class PropuestaEscenarioCapturado:
    """Lo que el formulario de revision de E2 necesita para mostrarse.
    Todavia NO es un `Escenario` -es, deliberadamente, el paso intermedio
    que permite revisar antes de guardar (punto 31 del encargo)."""

    session_id: str
    mensaje_id_solicitud: int
    mensaje_id_respuesta: int | None
    mti_solicitud: str
    mti_respuesta: str
    operacion: str
    nombre_sugerido: str
    requiere_tarjeta: bool
    requiere_monto: bool
    campos_opcionales_disponibles: frozenset[str]
    campos_expectativa_disponibles: frozenset[str]
    conexion_sugerida_id: str | None


class ServicioCapturaAEscenario:
    def __init__(
        self,
        sesiones: RepositorioSesionesProxy,
        mensajes: RepositorioMensajesProxy,
        origenes: RepositorioOrigenCapturaEscenario,
        conexiones: RepositorioDestinos,
        escenarios: ServicioEscenarios,
        perfil,
    ) -> None:
        self._sesiones = sesiones
        self._mensajes = mensajes
        self._origenes = origenes
        self._conexiones = conexiones
        self._escenarios = escenarios
        self._perfil = perfil

    async def _intercambio_o_falla(self, session_id: str, mensaje_id_solicitud: int):
        mensajes = await self._mensajes.listar_por_sesion(session_id)
        for intercambio in derivar_intercambios(mensajes):
            if intercambio.solicitud.mensaje_id == mensaje_id_solicitud:
                return intercambio
        raise InteraccionNoImportable(
            f"no existe el mensaje {mensaje_id_solicitud!r} en la sesión {session_id!r}"
        )

    async def proponer(self, session_id: str, mensaje_id_solicitud: int) -> PropuestaEscenarioCapturado:
        """Valida la captura y arma la propuesta -nunca guarda nada."""
        intercambio = await self._intercambio_o_falla(session_id, mensaje_id_solicitud)
        solicitud = intercambio.solicitud
        if not solicitud.interpretable or solicitud.mti is None:
            raise InteraccionNoImportable("el mensaje no es interpretable como ISO 8583")
        if not intercambio.correlacionado or intercambio.respuesta is None:
            raise InteraccionNoImportable("el intercambio no tiene una respuesta correlacionada")
        mti = solicitud.mti
        if mti not in MTIS_CON_OPERACION_IMPORTABLE:
            raise InteraccionNoImportable(
                f"el MTI {mti!r} no tiene un constructor de escenario soportado todavía"
            )

        mti_respuesta = intercambio.respuesta.mti or mti_de_respuesta(mti)
        obligatorios = self._perfil.obligatorios(mti)

        conexion_sugerida_id: str | None = None
        sesion = await self._sesiones.obtener(session_id)
        if sesion is not None:
            for destino in await self._conexiones.listar():
                if destino.host == sesion.upstream_host and destino.puerto == sesion.upstream_puerto:
                    conexion_sugerida_id = destino.destino_id
                    break

        return PropuestaEscenarioCapturado(
            session_id=session_id,
            mensaje_id_solicitud=solicitud.mensaje_id,
            mensaje_id_respuesta=intercambio.respuesta.mensaje_id,
            mti_solicitud=mti,
            mti_respuesta=mti_respuesta,
            operacion=OPERACION_POR_MTI.get(mti, mti),
            nombre_sugerido=f"Captura proxy · sesión {session_id[:8]} · solicitud #{solicitud.mensaje_id}",
            requiere_tarjeta="2" in obligatorios,
            requiere_monto="4" in obligatorios,
            campos_opcionales_disponibles=self._perfil.politica(mti).opcionales,
            campos_expectativa_disponibles=campos_permitidos_expectativa(self._perfil, mti_respuesta),
            conexion_sugerida_id=conexion_sugerida_id,
        )

    async def crear_desde_captura(
        self,
        datos: DatosNuevoEscenario,
        *,
        session_id: str,
        mensaje_id_solicitud: int,
        mensaje_id_respuesta: int | None,
    ) -> EscenarioAdministrado:
        """Guarda el escenario (vía `ServicioEscenarios.crear`, SIN camino
        de ejecución especial) y registra su procedencia por separado."""
        creado = await self._escenarios.crear(datos)
        await self._origenes.registrar(OrigenCapturaEscenario(
            escenario_id=creado.escenario_id,
            session_id=session_id,
            mensaje_id_solicitud=mensaje_id_solicitud,
            mensaje_id_respuesta=mensaje_id_respuesta,
        ))
        return creado

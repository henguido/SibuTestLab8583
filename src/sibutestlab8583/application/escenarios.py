"""Administracion de escenarios: transacciones ISO8583 reutilizables.

ESCENARIO = intencion reutilizable de prueba (que tarjeta, que conexion, que
monto, que campos editables). EJECUCION = una corrida concreta de esa
intencion en un momento determinado. Este modulo administra la primera; la
segunda sigue siendo responsabilidad exclusiva de `application.orquestador`,
que ni siquiera conoce que existen los escenarios: solo recibe un
`DatosCompra` y, opcionalmente, el id/nombre del escenario del que provino
-para trazabilidad en el historial, no para logica-.

Reutiliza `domain.armado.valores_efectivos_editables` para congelar, al
guardar, los valores EFECTIVOS de los campos editables (defaults del perfil +
overrides del usuario), nunca solo lo que el usuario haya tocado: si el
perfil cambia un default despues, un escenario ya guardado no debe cambiar de
comportamiento en silencio. `domain.armado.incompatibilidades_escenario`
revalida esos campos contra la politica ACTUAL en cada carga y reejecucion,
para no reinterpretar en silencio un campo que cambio de categoria.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass, field, replace
from decimal import Decimal
from typing import Mapping, Sequence

from ..domain.armado import incompatibilidades_escenario, valores_efectivos_editables
from ..domain.modelos import MTI_COMPRA, Escenario
from ..domain.puertos import RepositorioDestinos, RepositorioEscenarios, RepositorioTarjetas

#: Prefijo legible del id autogenerado; el sufijo aleatorio lo hace unico sin
#: pedirle al usuario que invente un identificador tecnico. A diferencia de
#: tarjetas y conexiones -catalogos de administracion infrecuente-, un
#: escenario se crea todo el tiempo como parte del flujo diario de un QA: el
#: `nombre` es el unico handle que le importa a la persona; el id es un
#: detalle interno, inmutable, que nunca vuelve a escribirse a mano.
PREFIJO_ESCENARIO_ID = "ESC"


class EscenarioNoEncontrado(Exception):
    """No existe un escenario con el `escenario_id` indicado."""


@dataclass(frozen=True)
class DiagnosticoEscenario:
    """Lo que hace falta saber antes de cargar o reejecutar un escenario.

    Deliberadamente no lanza: cargar un escenario roto debe poder MOSTRARSE
    -con una explicacion clara de que esta mal-, nunca fallar en seco ni
    reinterpretarse en silencio.
    """

    tarjeta_disponible: bool
    conexion_disponible: bool
    incompatibilidades: tuple[str, ...] = ()

    @property
    def bloqueado(self) -> bool:
        return not self.tarjeta_disponible or not self.conexion_disponible or bool(
            self.incompatibilidades
        )


@dataclass(frozen=True)
class EscenarioAdministrado:
    """Lo que la pantalla de escenarios y el constructor necesitan de uno."""

    escenario_id: str
    nombre: str
    perfil: str
    mti: str
    card_id: str
    conexion_id: str
    monto: Decimal
    campos_manuales: Mapping[str, str] = field(default_factory=dict)
    activo: bool = True


@dataclass(frozen=True)
class DatosNuevoEscenario:
    nombre: str
    card_id: str
    conexion_id: str
    monto: Decimal
    campos_manuales: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class DatosEdicionEscenario:
    nombre: str
    card_id: str
    conexion_id: str
    monto: Decimal
    campos_manuales: Mapping[str, str] = field(default_factory=dict)


def _validar_nombre(nombre: str) -> str:
    nombre = (nombre or "").strip()
    if not nombre:
        raise ValueError("Indique un nombre para el escenario.")
    return nombre


def _generar_escenario_id() -> str:
    return f"{PREFIJO_ESCENARIO_ID}-{secrets.token_hex(4)}"


class ServicioEscenarios:
    """Administracion de escenarios: listar, buscar, crear, editar, duplicar, estado."""

    def __init__(
        self,
        repositorio: RepositorioEscenarios,
        tarjetas: RepositorioTarjetas,
        conexiones: RepositorioDestinos,
        perfil,
        mti: str = MTI_COMPRA,
    ) -> None:
        self._escenarios = repositorio
        self._tarjetas = tarjetas
        self._conexiones = conexiones
        self._perfil = perfil
        self._mti = mti

    async def listar(self, *, buscar: str = "") -> Sequence[EscenarioAdministrado]:
        escenarios = [_a_administrado(e) for e in await self._escenarios.listar()]
        if not buscar.strip():
            return escenarios
        objetivo = buscar.strip().lower()
        return [e for e in escenarios if objetivo in e.nombre.lower()]

    async def obtener(self, escenario_id: str) -> EscenarioAdministrado | None:
        escenario = await self._escenarios.obtener(escenario_id)
        return _a_administrado(escenario) if escenario else None

    async def obtener_activo(self, escenario_id: str) -> EscenarioAdministrado | None:
        """Un escenario, solo si existe y esta activo.

        Es lo que usa la reejecucion directa: un escenario desactivado no debe
        poder dispararse con un click, aunque su id se conozca o se fuerce a
        mano -mismo principio ya aplicado a tarjetas y conexiones inactivas-.
        """
        escenario = await self._escenarios.obtener(escenario_id)
        if escenario is None or not escenario.activo:
            return None
        return _a_administrado(escenario)

    async def crear(self, datos: DatosNuevoEscenario) -> EscenarioAdministrado:
        nombre = _validar_nombre(datos.nombre)
        if await self._tarjetas.obtener(datos.card_id) is None:
            raise ValueError(f"No existe la tarjeta {datos.card_id!r}.")
        if await self._conexiones.obtener(datos.conexion_id) is None:
            raise ValueError(f"No existe la conexión {datos.conexion_id!r}.")

        efectivos = valores_efectivos_editables(datos.campos_manuales, self._perfil, self._mti)
        escenario = Escenario(
            escenario_id=_generar_escenario_id(),
            nombre=nombre,
            perfil=self._perfil.nombre,
            mti=self._mti,
            card_id=datos.card_id,
            conexion_id=datos.conexion_id,
            monto=datos.monto,
            campos_manuales=efectivos,
        )
        await self._escenarios.guardar(escenario)
        return _a_administrado(escenario)

    async def actualizar(
        self, escenario_id: str, datos: DatosEdicionEscenario
    ) -> EscenarioAdministrado:
        actual = await self._escenarios.obtener(escenario_id)
        if actual is None:
            raise EscenarioNoEncontrado(escenario_id)

        nombre = _validar_nombre(datos.nombre)
        if await self._tarjetas.obtener(datos.card_id) is None:
            raise ValueError(f"No existe la tarjeta {datos.card_id!r}.")
        if await self._conexiones.obtener(datos.conexion_id) is None:
            raise ValueError(f"No existe la conexión {datos.conexion_id!r}.")

        # "Guardar cambios" vuelve a congelar los valores EFECTIVOS de hoy, no
        # un parche sobre lo guardado antes: mismo criterio que crear().
        efectivos = valores_efectivos_editables(datos.campos_manuales, self._perfil, self._mti)
        actualizado = replace(
            actual,
            nombre=nombre,
            card_id=datos.card_id,
            conexion_id=datos.conexion_id,
            monto=datos.monto,
            campos_manuales=efectivos,
            perfil=self._perfil.nombre,
        )
        await self._escenarios.guardar(actualizado)
        return _a_administrado(actualizado)

    async def duplicar(self, escenario_id: str) -> EscenarioAdministrado:
        actual = await self._escenarios.obtener(escenario_id)
        if actual is None:
            raise EscenarioNoEncontrado(escenario_id)
        copia = replace(
            actual,
            escenario_id=_generar_escenario_id(),
            nombre=f"{actual.nombre} (copia)",
            activo=True,
        )
        await self._escenarios.guardar(copia)
        return _a_administrado(copia)

    async def cambiar_estado(self, escenario_id: str, *, activo: bool) -> EscenarioAdministrado:
        actual = await self._escenarios.obtener(escenario_id)
        if actual is None:
            raise EscenarioNoEncontrado(escenario_id)
        actualizado = replace(actual, activo=activo)
        await self._escenarios.guardar(actualizado)
        return _a_administrado(actualizado)

    async def diagnosticar(self, escenario: EscenarioAdministrado) -> DiagnosticoEscenario:
        """Compatibilidad de un escenario con el estado ACTUAL del sistema.

        No basta con comparar `escenario.perfil == perfil.nombre`: el perfil
        podria conservar el mismo nombre y haber cambiado que campos gobierna
        como editables. Por eso se revalida cada campo guardado contra la
        politica de hoy, no solo el nombre del perfil.
        """
        tarjeta = await self._tarjetas.obtener(escenario.card_id)
        conexion = await self._conexiones.obtener(escenario.conexion_id)

        if escenario.perfil != self._perfil.nombre:
            incompatibilidades = (
                f"el escenario se guardó con el perfil '{escenario.perfil}'; "
                f"el perfil activo es '{self._perfil.nombre}'",
            )
        else:
            incompatibilidades = incompatibilidades_escenario(
                escenario.campos_manuales, self._perfil, escenario.mti
            )

        return DiagnosticoEscenario(
            tarjeta_disponible=tarjeta is not None and tarjeta.activa,
            conexion_disponible=conexion is not None and conexion.activo,
            incompatibilidades=incompatibilidades,
        )


def _a_administrado(escenario: Escenario) -> EscenarioAdministrado:
    return EscenarioAdministrado(
        escenario_id=escenario.escenario_id,
        nombre=escenario.nombre,
        perfil=escenario.perfil,
        mti=escenario.mti,
        card_id=escenario.card_id,
        conexion_id=escenario.conexion_id,
        monto=escenario.monto,
        campos_manuales=escenario.campos_manuales,
        activo=escenario.activo,
    )

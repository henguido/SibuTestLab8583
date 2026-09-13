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

from decimal import Decimal

from ..domain.armado import incompatibilidades_escenario, valores_efectivos_editables
from ..domain.expectativas import incompatibilidades_expectativas, validar_expectativas
from ..domain.modelos import MTI_COMPRA, Escenario, Expectativas, OPERACION_POR_MTI
from ..domain.puertos import RepositorioDestinos, RepositorioEscenarios, RepositorioTarjetas
from ..domain.validacion import mti_de_respuesta

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
    operacion: str
    conexion_id: str
    card_id: str | None = None
    monto: Decimal | None = None
    campos_manuales: Mapping[str, str] = field(default_factory=dict)
    expectativas: Expectativas | None = None
    activo: bool = True


@dataclass(frozen=True)
class DatosNuevoEscenario:
    """`mti` decide la operacion (compra por defecto, para no romper a los
    llamadores existentes que nunca lo pasaban). `card_id`/`monto` son
    opcionales: `ServicioEscenarios.crear` los exige solo si el perfil los
    declara obligatorios para ese MTI (`"2"`/`"4"` en
    `perfil.obligatorios(mti)`) -asi, un echo no necesita informarlos, y un
    intento de compra sin tarjeta sigue rechazandose igual que siempre."""

    nombre: str
    conexion_id: str
    mti: str = MTI_COMPRA
    card_id: str | None = None
    monto: Decimal | None = None
    campos_manuales: Mapping[str, str] = field(default_factory=dict)
    expectativas: Expectativas | None = None


@dataclass(frozen=True)
class DatosEdicionEscenario:
    """Sin `mti`: editar un escenario nunca cambia su operacion -eso seria
    guardar uno distinto, no "editar este"-. `ServicioEscenarios.actualizar`
    sigue usando el `mti`/`operacion` ya guardados en el escenario actual."""

    nombre: str
    conexion_id: str
    card_id: str | None = None
    monto: Decimal | None = None
    campos_manuales: Mapping[str, str] = field(default_factory=dict)
    expectativas: Expectativas | None = None


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
    ) -> None:
        self._escenarios = repositorio
        self._tarjetas = tarjetas
        self._conexiones = conexiones
        self._perfil = perfil

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

    async def _validar_tarjeta_y_monto(
        self, mti: str, card_id: str | None, monto: Decimal | None
    ) -> None:
        """Exige tarjeta/monto solo si el perfil los declara obligatorios
        para este MTI -DE2 (PAN) y DE4 (monto) respectivamente-, nunca por un
        `if mti == MTI_COMPRA` hardcodeado: si mañana otro MTI necesitara
        tarjeta, esta regla ya lo cubriria sin tocar una linea.
        """
        obligatorios = self._perfil.obligatorios(mti)
        if "2" in obligatorios:
            if not card_id or await self._tarjetas.obtener(card_id) is None:
                raise ValueError(f"No existe la tarjeta {card_id!r}.")
        if "4" in obligatorios and monto is None:
            raise ValueError("Indique un monto para este escenario.")

    async def crear(self, datos: DatosNuevoEscenario) -> EscenarioAdministrado:
        nombre = _validar_nombre(datos.nombre)
        mti = datos.mti
        await self._validar_tarjeta_y_monto(mti, datos.card_id, datos.monto)
        if await self._conexiones.obtener(datos.conexion_id) is None:
            raise ValueError(f"No existe la conexión {datos.conexion_id!r}.")
        if datos.expectativas is not None:
            validar_expectativas(datos.expectativas, self._perfil, mti_de_respuesta(mti))

        efectivos = valores_efectivos_editables(datos.campos_manuales, self._perfil, mti)
        escenario = Escenario(
            escenario_id=_generar_escenario_id(),
            nombre=nombre,
            perfil=self._perfil.nombre,
            mti=mti,
            operacion=OPERACION_POR_MTI.get(mti, mti),
            card_id=datos.card_id,
            conexion_id=datos.conexion_id,
            monto=datos.monto,
            campos_manuales=efectivos,
            expectativas=datos.expectativas,
        )
        await self._escenarios.guardar(escenario)
        return _a_administrado(escenario)

    async def actualizar(
        self, escenario_id: str, datos: DatosEdicionEscenario
    ) -> EscenarioAdministrado:
        actual = await self._escenarios.obtener(escenario_id)
        if actual is None:
            raise EscenarioNoEncontrado(escenario_id)

        # La operacion (mti/operacion) de un escenario NUNCA cambia al
        # editarlo -eso seria guardar uno distinto, no "editar este"-: se
        # reutiliza la del escenario ya guardado, nunca un valor nuevo.
        mti = actual.mti
        nombre = _validar_nombre(datos.nombre)
        await self._validar_tarjeta_y_monto(mti, datos.card_id, datos.monto)
        if await self._conexiones.obtener(datos.conexion_id) is None:
            raise ValueError(f"No existe la conexión {datos.conexion_id!r}.")
        if datos.expectativas is not None:
            validar_expectativas(datos.expectativas, self._perfil, mti_de_respuesta(mti))

        # "Guardar cambios" vuelve a congelar los valores EFECTIVOS de hoy, no
        # un parche sobre lo guardado antes: mismo criterio que crear(). Lo
        # mismo aplica a las expectativas: se reemplazan enteras, no se
        # fusionan con las anteriores.
        efectivos = valores_efectivos_editables(datos.campos_manuales, self._perfil, mti)
        actualizado = replace(
            actual,
            nombre=nombre,
            card_id=datos.card_id,
            conexion_id=datos.conexion_id,
            monto=datos.monto,
            campos_manuales=efectivos,
            expectativas=datos.expectativas,
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

        `tarjeta_disponible`/`card_id` son `None` para un escenario que no
        necesita tarjeta (echo): `tarjeta is not None and tarjeta.activa`
        seria `False` con `card_id=None` -bloquearia sin motivo un escenario
        que nunca tuvo tarjeta-, asi que se considera disponible cuando
        simplemente no aplica.
        """
        tarjeta = await self._tarjetas.obtener(escenario.card_id) if escenario.card_id else None
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
            if escenario.expectativas is not None:
                incompatibilidades += incompatibilidades_expectativas(
                    escenario.expectativas, self._perfil, mti_de_respuesta(escenario.mti)
                )

        return DiagnosticoEscenario(
            tarjeta_disponible=(escenario.card_id is None) or (tarjeta is not None and tarjeta.activa),
            conexion_disponible=conexion is not None and conexion.activo,
            incompatibilidades=incompatibilidades,
        )


def _a_administrado(escenario: Escenario) -> EscenarioAdministrado:
    return EscenarioAdministrado(
        escenario_id=escenario.escenario_id,
        nombre=escenario.nombre,
        perfil=escenario.perfil,
        mti=escenario.mti,
        operacion=escenario.operacion,
        card_id=escenario.card_id,
        conexion_id=escenario.conexion_id,
        monto=escenario.monto,
        campos_manuales=escenario.campos_manuales,
        expectativas=escenario.expectativas,
        activo=escenario.activo,
    )

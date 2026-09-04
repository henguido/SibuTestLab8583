"""Administracion del catalogo de conexiones TCP de prueba.

Capa de aplicacion: usa `RepositorioDestinos` por su contrato, no conoce
SQLite. Mismo patron que `application/tarjetas.py` -listar, crear, editar,
activar/desactivar-, pero sin ninguna de sus reglas de PAN: una conexion no
contiene datos de tarjeta.

"Conexion" es el concepto de dominio/UI de este modulo; la tabla y el
repositorio siguen llamandose `destinos` porque son de una fase anterior y
renombrarlos no aporta nada -ver `DestinoGuardado`/`RepositorioDestinos` en
`domain/`-. Aqui, en la capa de aplicacion hacia arriba, todo se llama
conexion.

Desactivar una conexion no borra la fila ni afecta el historial: una ejecucion
guarda `destino_host`/`destino_puerto` como valores propios (ver
`domain/modelos.DestinoGuardado`), no una referencia a esta tabla.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from ..domain.modelos import DestinoGuardado
from ..domain.puertos import RepositorioDestinos, VerificadorDeConexion

LARGO_ID_MINIMO = 1

#: Limite de tiempo por defecto para una conexion nueva, si no se indica otro.
TIMEOUT_POR_DEFECTO = 10.0


class ConexionNoEncontrada(Exception):
    """No existe una conexion con el `conexion_id` indicado."""


@dataclass(frozen=True)
class ConexionAdministrada:
    """Lo que la pantalla de administracion necesita de una conexion."""

    conexion_id: str
    nombre: str
    host: str
    puerto: int
    timeout: float
    activa: bool


@dataclass(frozen=True)
class DatosNuevaConexion:
    conexion_id: str
    nombre: str
    host: str
    puerto: str
    timeout: str = ""


@dataclass(frozen=True)
class DatosEdicionConexion:
    nombre: str
    host: str
    puerto: str
    timeout: str = ""


def _validar_conexion_id(conexion_id: str) -> str:
    conexion_id = (conexion_id or "").strip()
    if not conexion_id:
        raise ValueError("Indique un identificador para la conexión.")
    # Misma familia de caracteres que ya usan los identificadores de tarjetas
    # y la conexion sembrada (LOCAL-DEMO): letras, digitos, guion y guion bajo.
    if not all(c.isalnum() or c in "-_" for c in conexion_id):
        raise ValueError(
            "El identificador solo admite letras, números, guiones y guion bajo."
        )
    return conexion_id


def _validar_nombre(nombre: str) -> str:
    nombre = (nombre or "").strip()
    if not nombre:
        raise ValueError("Indique un nombre para la conexión.")
    return nombre


def _validar_host(host: str) -> str:
    host = (host or "").strip()
    if not host:
        raise ValueError("Indique el host de la conexión.")
    return host


def _validar_puerto(puerto: str) -> int:
    try:
        numero = int((puerto or "").strip())
    except ValueError as error:
        raise ValueError("El puerto debe ser un número entero.") from error
    if not 1 <= numero <= 65535:
        raise ValueError("El puerto debe estar entre 1 y 65535.")
    return numero


def _validar_timeout(timeout: str) -> float:
    texto = (timeout or "").strip()
    if not texto:
        return TIMEOUT_POR_DEFECTO
    try:
        numero = float(texto)
    except ValueError as error:
        raise ValueError("El timeout debe ser un número.") from error
    if numero <= 0:
        raise ValueError("El timeout debe ser mayor que cero.")
    return numero


class ServicioConexiones:
    """Administracion del catalogo de conexiones: listar, crear, editar, estado, probar."""

    def __init__(
        self, repositorio: RepositorioDestinos, verificador: VerificadorDeConexion | None = None
    ) -> None:
        self._destinos = repositorio
        self._verificador = verificador

    async def listar(self) -> Sequence[ConexionAdministrada]:
        return [_a_administrada(d) for d in await self._destinos.listar()]

    async def listar_activas(self) -> Sequence[ConexionAdministrada]:
        """Lo que el constructor de transacciones puede ofrecer como opción."""
        return [_a_administrada(d) for d in await self._destinos.listar() if d.activo]

    async def obtener(self, conexion_id: str) -> ConexionAdministrada | None:
        destino = await self._destinos.obtener(conexion_id)
        return _a_administrada(destino) if destino else None

    async def obtener_activa(self, conexion_id: str) -> ConexionAdministrada | None:
        """Una conexion, solo si existe y esta activa.

        Es la consulta que usa el constructor de transacciones al resolver un
        `conexion_id` recibido del formulario: si la conexion fue desactivada
        entre que se cargo la pantalla y se envio el formulario, o si el
        `conexion_id` fue manipulado, el resultado es el mismo que si no
        existiera - no se confia en que el cliente solo pudo haber ofrecido
        conexiones activas.
        """
        destino = await self._destinos.obtener(conexion_id)
        if destino is None or not destino.activo:
            return None
        return _a_administrada(destino)

    async def crear(self, datos: DatosNuevaConexion) -> ConexionAdministrada:
        conexion_id = _validar_conexion_id(datos.conexion_id)
        if await self._destinos.obtener(conexion_id) is not None:
            raise ValueError(f"Ya existe una conexión con el identificador «{conexion_id}».")
        nombre = _validar_nombre(datos.nombre)
        host = _validar_host(datos.host)
        puerto = _validar_puerto(datos.puerto)
        timeout = _validar_timeout(datos.timeout)

        destino = DestinoGuardado(
            destino_id=conexion_id,
            nombre=nombre,
            host=host,
            puerto=puerto,
            activo=True,
            timeout=timeout,
        )
        await self._destinos.guardar(destino)
        return _a_administrada(destino)

    async def actualizar(
        self, conexion_id: str, datos: DatosEdicionConexion
    ) -> ConexionAdministrada:
        actual = await self._destinos.obtener(conexion_id)
        if actual is None:
            raise ConexionNoEncontrada(conexion_id)

        nombre = _validar_nombre(datos.nombre)
        host = _validar_host(datos.host)
        puerto = _validar_puerto(datos.puerto)
        timeout = _validar_timeout(datos.timeout)

        actualizado = replace(actual, nombre=nombre, host=host, puerto=puerto, timeout=timeout)
        await self._destinos.guardar(actualizado)
        return _a_administrada(actualizado)

    async def cambiar_estado(self, conexion_id: str, *, activa: bool) -> ConexionAdministrada:
        actual = await self._destinos.obtener(conexion_id)
        if actual is None:
            raise ConexionNoEncontrada(conexion_id)
        actualizado = replace(actual, activo=activa)
        await self._destinos.guardar(actualizado)
        return _a_administrada(actualizado)

    async def probar(self, conexion_id: str) -> bool:
        """Comprobacion TCP puntual: no envia ISO, no persiste una ejecucion.

        Se calcula al momento -no se guarda como verdad permanente-, porque el
        resultado puede quedar obsoleto apenas termina la comprobacion.
        """
        actual = await self._destinos.obtener(conexion_id)
        if actual is None:
            raise ConexionNoEncontrada(conexion_id)
        if self._verificador is None:
            raise RuntimeError("este servicio no tiene un verificador de conexion configurado")
        return await self._verificador.probar(actual.host, actual.puerto, actual.timeout)


def _a_administrada(destino: DestinoGuardado) -> ConexionAdministrada:
    return ConexionAdministrada(
        conexion_id=destino.destino_id,
        nombre=destino.nombre,
        host=destino.host,
        puerto=destino.puerto,
        timeout=destino.timeout,
        activa=destino.activo,
    )

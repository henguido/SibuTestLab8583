"""Administracion del catalogo de tarjetas de prueba.

Capa de aplicacion: usa `RepositorioTarjetas` por su contrato, no conoce
SQLite. La web valida la forma del formulario (que venga algo, que no sea un
tipo disparatado) y delega en este servicio la validacion de negocio -largo y
Luhn del PAN, formato del vencimiento, unicidad del identificador- y la
persistencia.

Ningun objeto que este modulo devuelve hacia la web lleva el PAN completo:
`TarjetaAdministrada` solo trae `pan_enmascarado`, igual que `TarjetaListada`
en `consultas.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from ..domain.datos_sinteticos import es_luhn_valido
from ..domain.modelos import TarjetaPrueba
from ..domain.puertos import RepositorioTarjetas

LARGO_PAN_MINIMO = 12
LARGO_PAN_MAXIMO = 19


class TarjetaNoEncontrada(Exception):
    """No existe una tarjeta con el `card_id` indicado."""


@dataclass(frozen=True)
class TarjetaAdministrada:
    """Lo que la pantalla de administracion necesita de una tarjeta."""

    card_id: str
    descripcion: str
    pan_enmascarado: str
    expiracion: str
    sintetica: bool
    activa: bool


@dataclass(frozen=True)
class DatosNuevaTarjeta:
    card_id: str
    descripcion: str
    pan: str
    expiracion: str
    confirma_qa: bool = False


@dataclass(frozen=True)
class DatosEdicionTarjeta:
    descripcion: str
    expiracion: str
    pan_nuevo: str = ""
    confirma_qa: bool = False


def _validar_card_id(card_id: str) -> str:
    card_id = (card_id or "").strip()
    if not card_id:
        raise ValueError("Indique un identificador para la tarjeta.")
    # Misma familia de caracteres que ya usan los identificadores existentes
    # en el proyecto (DEMO-0001, T-002, SIN-VENC): letras, digitos, guion y
    # guion bajo. No es una regla nueva, es la que ya se estaba siguiendo.
    # No se impone un largo maximo: ningun campo ISO lleva el card_id, la
    # columna SQLite es TEXT sin limite, y el proyecto no define ninguna cota
    # para identificadores en ningun otro lugar. Inventar un numero (40, 64,
    # lo que sea) seria una regla de negocio nueva sin respaldo.
    if not all(c.isalnum() or c in "-_" for c in card_id):
        raise ValueError(
            "El identificador solo admite letras, números, guiones y guion bajo."
        )
    return card_id


def _validar_descripcion(descripcion: str) -> str:
    descripcion = (descripcion or "").strip()
    if not descripcion:
        raise ValueError("Indique una descripción para la tarjeta.")
    return descripcion


def _validar_expiracion(expiracion: str) -> str:
    expiracion = (expiracion or "").strip()
    if len(expiracion) != 4 or not expiracion.isdigit():
        raise ValueError("El vencimiento debe tener el formato AAMM: cuatro dígitos.")
    mes = int(expiracion[2:])
    if not 1 <= mes <= 12:
        raise ValueError("El vencimiento debe traer un mes entre 01 y 12.")
    return expiracion


def _validar_pan(pan: str, *, confirma_qa: bool) -> tuple[str, bool]:
    """Devuelve `(pan_limpio, sintetica)`. Nunca repite el PAN en un mensaje."""
    limpio = (pan or "").strip()
    if not limpio.isdigit():
        raise ValueError("El número de tarjeta debe contener solo dígitos.")
    if not LARGO_PAN_MINIMO <= len(limpio) <= LARGO_PAN_MAXIMO:
        raise ValueError(
            f"El número de tarjeta debe tener entre {LARGO_PAN_MINIMO} y "
            f"{LARGO_PAN_MAXIMO} dígitos."
        )
    if es_luhn_valido(limpio):
        if not confirma_qa:
            raise ValueError(
                "Este número supera la validación de tarjeta real. Marque la "
                "confirmación de ambiente de pruebas autorizado antes de guardarlo."
            )
        return limpio, False
    return limpio, True


class ServicioTarjetas:
    """Administracion del catalogo: listar, crear, editar, activar/desactivar."""

    def __init__(self, repositorio: RepositorioTarjetas) -> None:
        self._tarjetas = repositorio

    async def listar(self) -> Sequence[TarjetaAdministrada]:
        return [_a_administrada(t) for t in await self._tarjetas.listar()]

    async def obtener(self, card_id: str) -> TarjetaAdministrada | None:
        tarjeta = await self._tarjetas.obtener(card_id)
        return _a_administrada(tarjeta) if tarjeta else None

    async def crear(self, datos: DatosNuevaTarjeta) -> TarjetaAdministrada:
        card_id = _validar_card_id(datos.card_id)
        if await self._tarjetas.obtener(card_id) is not None:
            raise ValueError(f"Ya existe una tarjeta con el identificador «{card_id}».")
        descripcion = _validar_descripcion(datos.descripcion)
        expiracion = _validar_expiracion(datos.expiracion)
        pan, sintetica = _validar_pan(datos.pan, confirma_qa=datos.confirma_qa)

        tarjeta = TarjetaPrueba(
            card_id=card_id,
            pan=pan,
            expiracion=expiracion,
            descripcion=descripcion,
            sintetica=sintetica,
            activa=True,
        )
        await self._tarjetas.guardar(tarjeta)
        return _a_administrada(tarjeta)

    async def actualizar(self, card_id: str, datos: DatosEdicionTarjeta) -> TarjetaAdministrada:
        actual = await self._tarjetas.obtener(card_id)
        if actual is None:
            raise TarjetaNoEncontrada(card_id)

        descripcion = _validar_descripcion(datos.descripcion)
        expiracion = _validar_expiracion(datos.expiracion)
        if datos.pan_nuevo.strip():
            pan, sintetica = _validar_pan(datos.pan_nuevo, confirma_qa=datos.confirma_qa)
        else:
            pan, sintetica = actual.pan, actual.sintetica

        actualizada = TarjetaPrueba(
            card_id=card_id,
            pan=pan,
            expiracion=expiracion,
            descripcion=descripcion,
            sintetica=sintetica,
            activa=actual.activa,
        )
        await self._tarjetas.guardar(actualizada)
        return _a_administrada(actualizada)

    async def cambiar_estado(self, card_id: str, *, activa: bool) -> TarjetaAdministrada:
        actual = await self._tarjetas.obtener(card_id)
        if actual is None:
            raise TarjetaNoEncontrada(card_id)
        actualizada = replace(actual, activa=activa)
        await self._tarjetas.guardar(actualizada)
        return _a_administrada(actualizada)


def _a_administrada(tarjeta: TarjetaPrueba) -> TarjetaAdministrada:
    return TarjetaAdministrada(
        card_id=tarjeta.card_id,
        descripcion=tarjeta.descripcion,
        pan_enmascarado=tarjeta.pan_enmascarado,
        expiracion=tarjeta.expiracion,
        sintetica=tarjeta.sintetica,
        activa=tarjeta.activa,
    )

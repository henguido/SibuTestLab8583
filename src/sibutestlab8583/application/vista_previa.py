"""Vista previa del mensaje 0100 antes de transmitirlo (Bloque 7).

DECISION ARQUITECTONICA (documentada explicitamente, pedida por el usuario):

DE7/DE11/DE12/DE13 -los campos `automaticos` del perfil- se resuelven con el
reloj y con el generador de STAN en el momento REAL de ejecutar, no antes.
Dos disenos eran posibles para la vista previa:

  A. Representacion ESTRUCTURAL: se arma el mismo mensaje con el mismo
     `armar_compra` de siempre, pero con un STAN/momento MARCADOR -nunca el
     que se usara al enviar-, y la UI etiqueta esos campos como "se generara
     al enviar" en vez de presentarlos como el valor definitivo.
  B. Composicion RESERVADA: pre-generar el STAN real (consumiendo la
     secuencia) y el timestamp real, para que el preview sea exactamente lo
     que se transmite despues.

Se elige **A**. B exige reservar un STAN de la secuencia SQLite antes de que
la persona decida ejecutar -o descartar- la transaccion: si preview y envio
terminan en STANs distintos (usuario abre preview, lo cierra, ejecuta mas
tarde) igual quedaria un STAN "quemado" sin ejecucion asociada, y bajo uso
concurrente (dos pestañas, o un futuro motor de carga) reservar-sin-consumir
introduce una carrera que hoy no existe. A no tiene ningun efecto secundario
-es una funcion de lectura pura sobre datos ya en memoria/DB-, preserva la
garantia de que el STAN transmitido es SIEMPRE el que genera
`GeneradorStanSQLite` en el momento de `ejecutar_compra`, y evita que este
modulo dependa de el.

Por eso `CampoVistaPrevia.es_valor_definitivo` es `False` para los cuatro
automaticos: la UI nunca debe presentar `123456` como "el STAN que se va a
enviar", solo como una forma valida del campo.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Sequence

from ..domain.armado import armar_compra, armar_compra_financiera, armar_echo
from ..domain.errores import ErrorDeCodificacion
from ..domain.modelos import DatosCompra, DatosCompraFinanciera, DatosEcho
from ..domain.puertos import RepositorioTarjetas
from ..domain.variables import ContextoResolucion, resolver_campos_manuales

#: Nunca se transmite: solo sostiene la forma (6 digitos) para poder calcular
#: bitmap/campos. Un valor fijo y reconocible, no un STAN real ni plausible.
STAN_MARCADOR = "000000"


@dataclass(frozen=True)
class CampoVistaPrevia:
    """Una fila de la vista previa: numero, valor (ya enmascarado si aplica),
    de donde sale, y si ese valor es el que de verdad se transmitira.
    """

    numero: str
    valor: str
    origen: str  # "derivado" | "automatico" | "editable" | "opcional"
    es_valor_definitivo: bool


@dataclass(frozen=True)
class VistaPreviaMensaje:
    mti: str
    bitmap: str | None
    campos: Sequence[CampoVistaPrevia]


class TarjetaNoDisponibleParaVistaPrevia(Exception):
    """La tarjeta elegida no existe o esta inactiva: no hay nada que previsualizar."""


def _origen_para_vista_previa(politica, numero: str) -> str:
    """Como `politica.origen()`, pero distingue el unico caso que ese metodo
    no puede: un campo estructural que `armar_compra` fija SIEMPRE por fuera
    de la politica -hoy solo DE4, que viene de `DatosCompra.monto` (ver
    `test_la_politica_de_campos_cubre_todos_los_obligatorios_de_la_compra`)-.
    Sin esto, DE4 se rotularia "no_permitido" en la vista previa, que es
    exactamente lo contrario de lo que significa: no es que este prohibido,
    es que ni siquiera pasa por la politica de campos manuales.
    """
    origen = politica.origen(numero)
    if origen == "no_permitido":
        return "estructural"
    return origen


def _vista_previa_de_mensaje(
    mensaje, perfil, codec, no_reproducibles: frozenset[str]
) -> VistaPreviaMensaje:
    """Comun a cualquier operacion (B2): enmascarar, calcular bitmap, y armar
    las filas de `CampoVistaPrevia` -lo unico que cambia entre compra y echo
    es COMO se llega a `mensaje`, nunca esta parte."""
    mti = mensaje.mti
    # Reasignado a la MISMA variable a proposito -nunca queda una referencia
    # viva al mensaje real bajo otro nombre que un cambio futuro pudiera usar
    # por error-: en cuanto se enmascara, "mensaje" YA ES la version segura
    # para el resto de esta funcion.
    mensaje = mensaje.enmascarado()

    try:
        bitmap = codec.bitmap_hex(mensaje, perfil)
    except ErrorDeCodificacion:
        bitmap = None

    politica = perfil.politica(mti)
    campos = [
        CampoVistaPrevia(
            numero=numero,
            valor=valor,
            origen=_origen_para_vista_previa(politica, numero),
            es_valor_definitivo=(
                politica.origen(numero) != "automatico" and numero not in no_reproducibles
            ),
        )
        for numero, valor in sorted(mensaje.campos.items(), key=lambda par: int(par[0]))
    ]
    return VistaPreviaMensaje(mti=mti, bitmap=bitmap, campos=campos)


class ServicioVistaPreviaTransaccionTarjeta:
    """Vista previa comun a CUALQUIER operacion que mueva fondos con una
    tarjeta elegida del catalogo (B5): parametrizada por el builder
    (`armar_fn`) de esa operacion, nunca por una bandera `tipo`. Antes de B5
    existian `ServicioVistaPrevia` (compra) y `ServicioVistaPreviaCompraFinanciera`
    (compra financiera) con el cuerpo de `construir()` duplicado salvo por
    esa unica linea -que builder llamar-; ahora son wrappers de compatibilidad
    sobre esta clase (ver mas abajo), no una segunda implementacion.
    """

    def __init__(
        self,
        armar_fn,
        repositorio_tarjetas: RepositorioTarjetas,
        codec,
        perfil,
        *,
        reloj: Callable[[], datetime] | None = None,
    ) -> None:
        self._armar = armar_fn
        self._tarjetas = repositorio_tarjetas
        self._codec = codec
        self._perfil = perfil
        self._reloj = reloj or (lambda: datetime.now(timezone.utc))

    async def construir(self, datos) -> VistaPreviaMensaje:
        """Puede lanzar `TarjetaNoDisponibleParaVistaPrevia` o
        `ErrorDeCamposManuales` -mismos motivos por los que la ejecucion real
        rechazaria el envio-: el llamador (la ruta web) ya sabe traducir
        ambos a un mensaje de entrada, y no hace falta duplicar esa traduccion
        aqui.
        """
        tarjeta = await self._tarjetas.obtener(datos.card_id)
        if tarjeta is None or not tarjeta.activa:
            raise TarjetaNoDisponibleParaVistaPrevia(datos.card_id)

        momento = self._reloj()
        # Misma resolucion que hace el orquestador real (ver
        # `application/orquestador.py::ejecutar_compra`), pero con el
        # STAN/momento MARCADOR de esta vista previa: por eso `{{stan}}` y
        # `{{transmission_datetime}}`/`{{local_time}}`/`{{local_date}}` jamas
        # deben presentarse aqui como el valor definitivo (ver mas abajo).
        contexto_variables = ContextoResolucion(monto=datos.monto, stan=STAN_MARCADOR, momento=momento)
        campos_resueltos, no_reproducibles = resolver_campos_manuales(
            datos.campos_manuales, contexto_variables
        )
        datos = dataclasses.replace(datos, campos_manuales=campos_resueltos)

        mensaje = self._armar(
            datos, tarjeta, stan=STAN_MARCADOR, momento=momento, perfil=self._perfil
        )
        return _vista_previa_de_mensaje(mensaje, self._perfil, self._codec, no_reproducibles)


class ServicioVistaPrevia(ServicioVistaPreviaTransaccionTarjeta):
    """Wrapper de compatibilidad: vista previa del 0100 (Autorización).

    Conserva el nombre/firma publicos de antes de B5 -codigo y pruebas
    existentes que lo instancian con `(repositorio_tarjetas, codec, perfil)`
    siguen funcionando sin cambios-, pero delega en
    `ServicioVistaPreviaTransaccionTarjeta` en vez de duplicar `construir()`.
    """

    def __init__(
        self,
        repositorio_tarjetas: RepositorioTarjetas,
        codec,
        perfil,
        *,
        reloj: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(armar_compra, repositorio_tarjetas, codec, perfil, reloj=reloj)


class ServicioVistaPreviaCompraFinanciera(ServicioVistaPreviaTransaccionTarjeta):
    """Wrapper de compatibilidad: vista previa del 0200 (compra financiera,
    B4). Mismo criterio que `ServicioVistaPrevia`."""

    def __init__(
        self,
        repositorio_tarjetas: RepositorioTarjetas,
        codec,
        perfil,
        *,
        reloj: Callable[[], datetime] | None = None,
    ) -> None:
        super().__init__(armar_compra_financiera, repositorio_tarjetas, codec, perfil, reloj=reloj)


class ServicioVistaPreviaEcho:
    """Vista previa del 0800 (Network Management/Echo, B2): mismo principio
    que `ServicioVistaPrevia`, reusando `armar_echo` -nunca una segunda
    implementacion del builder-. Sin tarjeta que buscar: la construccion es
    mas simple que la de compra, no porque se haya recortado nada, sino
    porque un echo genuinamente no tiene ese concepto.
    """

    def __init__(
        self,
        codec,
        perfil,
        *,
        reloj: Callable[[], datetime] | None = None,
    ) -> None:
        self._codec = codec
        self._perfil = perfil
        self._reloj = reloj or (lambda: datetime.now(timezone.utc))

    async def construir(self, datos: DatosEcho) -> VistaPreviaMensaje:
        momento = self._reloj()
        contexto_variables = ContextoResolucion(stan=STAN_MARCADOR, momento=momento)
        campos_resueltos, no_reproducibles = resolver_campos_manuales(
            datos.campos_manuales, contexto_variables
        )
        datos = dataclasses.replace(datos, campos_manuales=campos_resueltos)

        mensaje = armar_echo(datos, stan=STAN_MARCADOR, momento=momento, perfil=self._perfil)
        return _vista_previa_de_mensaje(mensaje, self._perfil, self._codec, no_reproducibles)

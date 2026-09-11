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

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Sequence

from ..domain.armado import armar_compra
from ..domain.errores import ErrorDeCodificacion
from ..domain.modelos import MTI_COMPRA, DatosCompra
from ..domain.puertos import RepositorioTarjetas

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


class ServicioVistaPrevia:
    """Arma la vista previa reusando el mismo `armar_compra` y el mismo codec
    que la ejecucion real -nunca una segunda implementacion del builder-.
    """

    def __init__(
        self,
        repositorio_tarjetas: RepositorioTarjetas,
        codec,
        perfil,
        *,
        reloj: Callable[[], datetime] | None = None,
    ) -> None:
        self._tarjetas = repositorio_tarjetas
        self._codec = codec
        self._perfil = perfil
        self._reloj = reloj or (lambda: datetime.now(timezone.utc))

    async def construir(self, datos: DatosCompra) -> VistaPreviaMensaje:
        """Puede lanzar `TarjetaNoDisponibleParaVistaPrevia` o
        `ErrorDeCamposManuales` -mismos motivos por los que `/compra`
        rechazaria el envio real-: el llamador (la ruta web) ya sabe traducir
        ambos a un mensaje de entrada, y no hace falta duplicar esa traduccion
        aqui.
        """
        tarjeta = await self._tarjetas.obtener(datos.card_id)
        if tarjeta is None or not tarjeta.activa:
            raise TarjetaNoDisponibleParaVistaPrevia(datos.card_id)

        mensaje = armar_compra(
            datos, tarjeta, stan=STAN_MARCADOR, momento=self._reloj(), perfil=self._perfil
        )
        mti = mensaje.mti
        # Reasignado a la MISMA variable a proposito -nunca queda una
        # referencia viva al mensaje real bajo otro nombre que un cambio
        # futuro pudiera usar por error-: en cuanto se enmascara, "mensaje" YA
        # ES la version segura para el resto de esta funcion.
        mensaje = mensaje.enmascarado()

        try:
            bitmap = self._codec.bitmap_hex(mensaje, self._perfil)
        except ErrorDeCodificacion:
            bitmap = None

        politica = self._perfil.politica(MTI_COMPRA)
        campos = [
            CampoVistaPrevia(
                numero=numero,
                valor=valor,
                origen=_origen_para_vista_previa(politica, numero),
                es_valor_definitivo=politica.origen(numero) != "automatico",
            )
            for numero, valor in sorted(mensaje.campos.items(), key=lambda par: int(par[0]))
        ]
        return VistaPreviaMensaje(mti=mti, bitmap=bitmap, campos=campos)

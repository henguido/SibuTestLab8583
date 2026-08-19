"""Piezas compartidas por las pruebas.

Los dobles de prueba viven aqui porque varios archivos los necesitan. El doble
de transporte es el que permite comprobar RN-4 de verdad: no basta con ver que
el resultado sea "no enviada", hay que comprobar que el transporte **nunca fue
invocado**.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, inicializar
from sibutestlab8583.adapters.persistence.sqlite_repos import (
    GeneradorStanSQLite,
    RepositorioEjecucionesSQLite,
    RepositorioTarjetasSQLite,
)
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.application.orquestador import Orquestador
from sibutestlab8583.domain.catalogo import CATALOGO_GENERICO
from sibutestlab8583.domain.modelos import (
    MTI_RESPUESTA_COMPRA,
    DatosCompra,
    DestinoTcp,
    MensajeIso,
    TiempoAgotado,
)
from sibutestlab8583.domain.validacion import CAMPO_CODIGO_RESPUESTA, campos_de_correlacion
from sibutestlab8583.profiles.generico import CODIGO_PROCESO_COMPRA, PERFIL_GENERICO

MOMENTO_FIJO = datetime(2026, 8, 19, 12, 30, 45, tzinfo=timezone.utc)
DESTINO_INERTE = DestinoTcp(host="127.0.0.1", puerto=9)


class TransporteFalso:
    """Doble de transporte: devuelve lo indicado y registra si fue invocado.

    Con `codigo` construye la respuesta **correlacionada con la solicitud que
    recibe**, igual que hace el host real. Antes bastaba una respuesta enlatada,
    pero solo porque el STAN era siempre el mismo: eso era el defecto, no una
    simplificacion legitima. Fabricar la respuesta a partir de lo enviado hace
    que el doble no pueda volver a esconderlo.
    """

    def __init__(
        self,
        respuesta: bytes | TiempoAgotado | None = None,
        *,
        codigo: str | None = None,
    ) -> None:
        self.respuesta = respuesta
        self.codigo = codigo
        self.invocaciones: list[bytes] = []

    @property
    def fue_invocado(self) -> bool:
        return bool(self.invocaciones)

    async def enviar(self, payload, destino, tiempo_limite=None):
        self.invocaciones.append(payload)
        if self.codigo is not None:
            return self._responder_correlacionado(payload)
        if self.respuesta is None:
            raise AssertionError("el transporte fue invocado sin respuesta preparada")
        return self.respuesta

    def _responder_correlacionado(self, payload: bytes) -> bytes:
        codec = CodecIso8583()
        solicitud = codec.decodificar(payload, PERFIL_GENERICO).como_mensaje()
        campos = {
            numero: solicitud.campos[numero]
            for numero in campos_de_correlacion(PERFIL_GENERICO, MTI_RESPUESTA_COMPRA)
            if numero in solicitud.campos
        }
        campos[CAMPO_CODIGO_RESPUESTA] = self.codigo
        return codec.codificar(
            MensajeIso(mti=MTI_RESPUESTA_COMPRA, campos=campos), PERFIL_GENERICO
        )


@pytest.fixture
def codec() -> CodecIso8583:
    return CodecIso8583()


@pytest.fixture
def framing() -> FramingDemostracion:
    return FramingDemostracion()


@pytest.fixture
def perfil():
    return PERFIL_GENERICO


@pytest.fixture
async def base(tmp_path):
    """Base SQLite real, aislada por prueba."""
    return await inicializar(tmp_path / "iteracion.db")


@pytest.fixture
def datos_compra() -> DatosCompra:
    return DatosCompra(card_id=CARD_ID_DEMO, monto=Decimal("150.00"))


def construir_orquestador(base, transporte, *, destino=DESTINO_INERTE, tiempo_limite=None):
    """Orquestador con repositorios reales y el transporte que se le pase."""
    return Orquestador(
        codec=CodecIso8583(),
        perfil=PERFIL_GENERICO,
        catalogo=CATALOGO_GENERICO,
        transporte=transporte,
        repositorio_ejecuciones=RepositorioEjecucionesSQLite(base),
        repositorio_tarjetas=RepositorioTarjetasSQLite(base),
        # Generador real y no un doble: un fake escondería el defecto que esta
        # iteración corrige.
        generador_stan=GeneradorStanSQLite(base),
        destino=destino,
        codigo_proceso=CODIGO_PROCESO_COMPRA,
        tiempo_limite=tiempo_limite,
        reloj=lambda: MOMENTO_FIJO,
    )

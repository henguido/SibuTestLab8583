"""Distincion y persistencia de los desenlaces de comunicacion.

Cubre los dos defectos corregidos en esta iteracion:

- un intento que no llegaba a la red desaparecia del historial;
- un tiempo agotado al **conectar** se presentaba como RN-2, que exige que la
  conexion se haya establecido y la escritura local haya terminado.

El fallo de conexion se fuerza con un nombre irresoluble bajo `.invalid`,
reservado por RFC 2606. Es portable: no depende de como cada sistema operativo
trate una conexion a un puerto cerrado, particularidad que en Windows produce un
tiempo agotado en lugar de un rechazo.
"""

from __future__ import annotations

import sqlite3
from decimal import Decimal

import pytest

from conftest import TransporteFalso, construir_orquestador
from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, PAN_DEMO
from sibutestlab8583.adapters.persistence.sqlite_repos import RepositorioEjecucionesSQLite
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.adapters.transporte.tcp import TransporteTcp
from sibutestlab8583.domain.errores import ErrorDeCodificacion
from sibutestlab8583.domain.modelos import (
    DatosCompra,
    DestinoTcp,
    EstadoEjecucion,
    FalloDeConexion,
    FalloDeTransmision,
    TiempoAgotado,
)
from sibutestlab8583.profiles.generico import PERFIL_GENERICO
from sibutestlab8583.web.presentacion import AVISOS

#: Nombre que ninguna resolucion DNS puede satisfacer (RFC 2606).
DESTINO_IRRESOLUBLE = DestinoTcp(host="no-existe.sibutestlab.invalid", puerto=9)


async def _compra(base, transporte, *, destino=DESTINO_IRRESOLUBLE, tiempo_limite=2.0):
    return await construir_orquestador(
        base, transporte, destino=destino, tiempo_limite=tiempo_limite
    ).ejecutar_compra(DatosCompra(card_id=CARD_ID_DEMO, monto=Decimal("150.00")))


# ------------------------------------------------- error de conexion real ----


async def test_un_destino_irresoluble_da_error_de_conexion(base):
    resultado = await _compra(base, TransporteTcp(FramingDemostracion(), tiempo_limite=2.0))

    assert resultado.estado is EstadoEjecucion.ERROR_CONEXION
    assert resultado.estado is not EstadoEjecucion.TIMEOUT
    assert resultado.estado is not EstadoEjecucion.RECHAZADA
    assert resultado.motivos, "debe explicar por que no se pudo conectar"


async def test_el_intento_fallido_queda_persistido(base):
    """El defecto corregido: antes la excepcion subia y no quedaba rastro."""
    await _compra(base, TransporteTcp(FramingDemostracion(), tiempo_limite=2.0))

    guardadas = await RepositorioEjecucionesSQLite(base).listar()
    assert len(guardadas) == 1, "el intento debe aparecer en el historial"
    ejecucion = guardadas[0]

    assert ejecucion.estado is EstadoEjecucion.ERROR_CONEXION
    assert ejecucion.card_id == CARD_ID_DEMO
    assert ejecucion.monto == Decimal("150.00")
    assert ejecucion.moneda == "188"
    assert ejecucion.stan and len(ejecucion.stan) == 6
    assert ejecucion.mti_solicitud == "0100"
    assert ejecucion.destino_host == DESTINO_IRRESOLUBLE.host
    assert ejecucion.destino_puerto == DESTINO_IRRESOLUBLE.puerto
    assert ejecucion.solicitud_enmascarada, "la solicitud armada debe quedar registrada"
    assert ejecucion.latencia_ms is not None, "el tiempo del intento es informacion util"


async def test_un_error_de_conexion_no_tiene_respuesta_ni_codigo_39(base):
    await _compra(base, TransporteTcp(FramingDemostracion(), tiempo_limite=2.0))
    ejecucion = (await RepositorioEjecucionesSQLite(base).listar())[0]

    assert ejecucion.mti_respuesta is None, "nunca llego una respuesta"
    assert ejecucion.codigo_respuesta is None, "no puede haber campo 39 sin respuesta"
    assert ejecucion.respuesta_enmascarada is None


# ---------------------------------------------------------- timeout real -----


async def test_timeout_real_contra_el_host_que_no_responde(base):
    """RN-2 con su significado exacto: el host acepta la conexion y calla."""
    host = HostSimulado(
        CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), responder=False
    )
    async with host:
        resultado = await _compra(
            base,
            TransporteTcp(FramingDemostracion(), tiempo_limite=0.3),
            destino=DestinoTcp(host=host.host, puerto=host.puerto),
            tiempo_limite=0.3,
        )

    # Aqui SI se puede afirmar que llego: lo observa el propio host simulado,
    # no el cliente. Desde el cliente eso nunca es demostrable.
    assert host.solicitudes_recibidas == 1, "el host simulado contabilizo el 0100"
    assert resultado.estado is EstadoEjecucion.TIMEOUT
    assert resultado.estado is not EstadoEjecucion.ERROR_CONEXION


async def test_el_timeout_queda_persistido_con_destino(base):
    host = HostSimulado(
        CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), responder=False
    )
    async with host:
        await _compra(
            base,
            TransporteTcp(FramingDemostracion(), tiempo_limite=0.3),
            destino=DestinoTcp(host=host.host, puerto=host.puerto),
            tiempo_limite=0.3,
        )

    ejecucion = (await RepositorioEjecucionesSQLite(base).listar())[0]
    assert ejecucion.estado is EstadoEjecucion.TIMEOUT
    assert ejecucion.destino_puerto == host.puerto
    assert ejecucion.codigo_respuesta is None
    assert ejecucion.latencia_ms is not None


async def test_error_de_conexion_y_timeout_son_estados_distintos(base):
    """Los dos casos, sobre la misma base, deben quedar separados."""
    host = HostSimulado(
        CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), responder=False
    )
    async with host:
        await _compra(
            base,
            TransporteTcp(FramingDemostracion(), tiempo_limite=0.3),
            destino=DestinoTcp(host=host.host, puerto=host.puerto),
            tiempo_limite=0.3,
        )
    await _compra(base, TransporteTcp(FramingDemostracion(), tiempo_limite=2.0))

    estados = [e.estado for e in await RepositorioEjecucionesSQLite(base).listar()]
    assert EstadoEjecucion.TIMEOUT in estados
    assert EstadoEjecucion.ERROR_CONEXION in estados
    assert estados.count(EstadoEjecucion.TIMEOUT) == 1
    assert estados.count(EstadoEjecucion.ERROR_CONEXION) == 1


def test_el_transporte_no_confunde_los_dos_resultados():
    """Son tipos distintos, no el mismo valor con una bandera."""
    assert not isinstance(FalloDeConexion("x"), TiempoAgotado)
    assert not isinstance(TiempoAgotado(1.0), FalloDeConexion)


# ------------------------------------------- fallo de codec: NO_ENVIADA ------


class CodecQueNoCodifica:
    """Codifica siempre mal; decodifica como el real."""

    def codificar(self, mensaje, perfil):
        raise ErrorDeCodificacion("el perfil no admite este mensaje")

    def decodificar(self, payload, perfil):
        return CodecIso8583().decodificar(payload, perfil)


async def test_un_fallo_de_codec_queda_como_no_enviada(base):
    """Nunca llego al transporte, asi que es el mismo caso que RN-4."""
    from conftest import MOMENTO_FIJO
    from sibutestlab8583.adapters.persistence.sqlite_repos import (
        GeneradorStanSQLite,
        RepositorioTarjetasSQLite,
    )
    from sibutestlab8583.application.orquestador import Orquestador
    from sibutestlab8583.domain.catalogo import CATALOGO_GENERICO
    from sibutestlab8583.profiles.generico import CODIGO_PROCESO_COMPRA

    transporte = TransporteFalso()
    orquestador = Orquestador(
        codec=CodecQueNoCodifica(),
        perfil=PERFIL_GENERICO,
        catalogo=CATALOGO_GENERICO,
        transporte=transporte,
        repositorio_ejecuciones=RepositorioEjecucionesSQLite(base),
        repositorio_tarjetas=RepositorioTarjetasSQLite(base),
        generador_stan=GeneradorStanSQLite(base),
        destino=DESTINO_IRRESOLUBLE,
        codigo_proceso=CODIGO_PROCESO_COMPRA,
        reloj=lambda: MOMENTO_FIJO,
    )

    resultado = await orquestador.ejecutar_compra(
        DatosCompra(card_id=CARD_ID_DEMO, monto=Decimal("150.00"))
    )

    assert resultado.estado is EstadoEjecucion.NO_ENVIADA
    assert not transporte.fue_invocado, "no debe tocar la red si no pudo codificar"

    ejecucion = (await RepositorioEjecucionesSQLite(base).listar())[0]
    assert ejecucion.estado is EstadoEjecucion.NO_ENVIADA
    assert ejecucion.destino_host is None, "no se envio: no hay destino que registrar"
    assert ejecucion.codigo_respuesta is None
    assert any("perfil" in m for m in resultado.motivos)


# ------------------------------------------------ presentacion e historial ---


def test_avisos_cubre_todos_los_estados():
    """Falla si aparece un estado nuevo sin presentacion asociada.

    Sin esto, agregar un miembro a EstadoEjecucion rompe el historial con un
    KeyError en tiempo de ejecucion en lugar de fallar en la suite.
    """
    faltantes = [e.name for e in EstadoEjecucion if e not in AVISOS]
    assert not faltantes, f"estados sin entrada en AVISOS: {faltantes}"


def test_cada_estado_tiene_titulo_y_tono_propios():
    titulos = {AVISOS[e].titulo for e in EstadoEjecucion}
    assert len(titulos) == len(list(EstadoEjecucion)), "dos estados comparten titulo"
    assert AVISOS[EstadoEjecucion.ERROR_CONEXION].titulo != AVISOS[
        EstadoEjecucion.TIMEOUT
    ].titulo


async def test_el_historial_acepta_los_dos_estados_nuevos(base):
    """El listado debe renderizar sin romperse con ambos estados."""
    import httpx2

    from sibutestlab8583.composicion import Composicion, Configuracion
    from sibutestlab8583.web.app import crear_app

    host = HostSimulado(
        CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), responder=False
    )
    async with host:
        await _compra(
            base,
            TransporteTcp(FramingDemostracion(), tiempo_limite=0.3),
            destino=DestinoTcp(host=host.host, puerto=host.puerto),
            tiempo_limite=0.3,
        )
    await _compra(base, TransporteTcp(FramingDemostracion(), tiempo_limite=2.0))

    composicion = Composicion(Configuracion(ruta_base_datos=base))
    app = crear_app(composicion)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://prueba"
    ) as cliente:
        respuesta = await cliente.get("/historial")

    assert respuesta.status_code == 200
    assert "timeout" in respuesta.text
    assert "error_conexion" in respuesta.text
    assert PAN_DEMO not in respuesta.text
    assert "Traceback" not in respuesta.text


async def test_ningun_caso_expone_el_pan_completo(base):
    """Los tres desenlaces nuevos, comprobados contra la base."""
    host = HostSimulado(
        CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), responder=False
    )
    async with host:
        await _compra(
            base,
            TransporteTcp(FramingDemostracion(), tiempo_limite=0.3),
            destino=DestinoTcp(host=host.host, puerto=host.puerto),
            tiempo_limite=0.3,
        )
    await _compra(base, TransporteTcp(FramingDemostracion(), tiempo_limite=2.0))

    with sqlite3.connect(base) as conexion:
        filas = conexion.execute("SELECT * FROM ejecuciones").fetchall()

    assert len(filas) == 2
    for fila in filas:
        for valor in fila:
            assert PAN_DEMO not in str(valor)

# ------------------------------------- ERROR_TRANSMISION de extremo a extremo -


class TransporteQueFalla:
    """Doble que devuelve el resultado de transporte indicado."""

    def __init__(self, resultado) -> None:
        self.resultado = resultado
        self.invocado = False

    async def enviar(self, payload, destino, tiempo_limite=None):
        self.invocado = True
        return self.resultado


async def test_un_fallo_de_transmision_se_registra_como_error_transmision(base):
    detalle = "la conexion se establecio y el envio se interrumpio: no puede determinarse"
    resultado = await _compra(base, TransporteQueFalla(FalloDeTransmision(detalle)))

    assert resultado.estado is EstadoEjecucion.ERROR_TRANSMISION
    assert resultado.estado is not EstadoEjecucion.ERROR_CONEXION
    assert resultado.estado is not EstadoEjecucion.TIMEOUT
    assert resultado.estado is not EstadoEjecucion.NO_ENVIADA
    assert any(detalle in m for m in resultado.motivos)


async def test_el_fallo_de_transmision_queda_persistido_con_todo(base):
    await _compra(base, TransporteQueFalla(FalloDeTransmision("intercambio interrumpido")))

    ejecucion = (await RepositorioEjecucionesSQLite(base).listar())[0]
    assert ejecucion.estado is EstadoEjecucion.ERROR_TRANSMISION
    assert ejecucion.card_id == CARD_ID_DEMO
    assert ejecucion.monto == Decimal("150.00")
    assert ejecucion.moneda == "188"
    assert len(ejecucion.stan) == 6
    assert ejecucion.mti_solicitud == "0100"
    assert ejecucion.destino_host == DESTINO_IRRESOLUBLE.host
    assert ejecucion.destino_puerto == DESTINO_IRRESOLUBLE.puerto
    assert ejecucion.solicitud_enmascarada
    assert ejecucion.latencia_ms is not None
    # No hubo respuesta ISO utilizable.
    assert ejecucion.mti_respuesta is None
    assert ejecucion.codigo_respuesta is None
    assert ejecucion.respuesta_enmascarada is None


async def test_los_tres_estados_de_comunicacion_conviven_y_no_se_mezclan(base):
    """ERROR_CONEXION, ERROR_TRANSMISION y TIMEOUT, sobre la misma base."""
    await _compra(base, TransporteTcp(FramingDemostracion(), tiempo_limite=2.0))
    await _compra(base, TransporteQueFalla(FalloDeTransmision("interrumpido")))
    host = HostSimulado(
        CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), responder=False
    )
    async with host:
        await _compra(
            base,
            TransporteTcp(FramingDemostracion(), tiempo_limite=0.3),
            destino=DestinoTcp(host=host.host, puerto=host.puerto),
            tiempo_limite=0.3,
        )

    guardadas = await RepositorioEjecucionesSQLite(base).listar()
    estados = [e.estado for e in guardadas]
    for esperado in (
        EstadoEjecucion.ERROR_CONEXION,
        EstadoEjecucion.ERROR_TRANSMISION,
        EstadoEjecucion.TIMEOUT,
    ):
        assert estados.count(esperado) == 1, f"{esperado.name} no quedo registrado una vez"

    # Ninguno de los tres tiene respuesta ISO.
    for ejecucion in guardadas:
        assert ejecucion.mti_respuesta is None
        assert ejecucion.codigo_respuesta is None


async def test_la_web_presenta_los_tres_casos_con_textos_distintos(base):
    import httpx2

    from sibutestlab8583.composicion import Composicion, Configuracion
    from sibutestlab8583.web.app import crear_app

    for transporte in (
        TransporteTcp(FramingDemostracion(), tiempo_limite=2.0),
        TransporteQueFalla(FalloDeTransmision("interrumpido")),
    ):
        await _compra(base, transporte)
    host = HostSimulado(
        CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), responder=False
    )
    async with host:
        await _compra(
            base,
            TransporteTcp(FramingDemostracion(), tiempo_limite=0.3),
            destino=DestinoTcp(host=host.host, puerto=host.puerto),
            tiempo_limite=0.3,
        )

    app = crear_app(Composicion(Configuracion(ruta_base_datos=base)))
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://prueba"
    ) as cliente:
        historial = await cliente.get("/historial")

    assert historial.status_code == 200
    for valor in ("error_conexion", "error_transmision", "timeout"):
        assert valor in historial.text, f"el historial no muestra {valor}"
    assert PAN_DEMO not in historial.text
    assert "Traceback" not in historial.text

    titulos = {
        AVISOS[e].titulo
        for e in (
            EstadoEjecucion.ERROR_CONEXION,
            EstadoEjecucion.ERROR_TRANSMISION,
            EstadoEjecucion.TIMEOUT,
        )
    }
    assert len(titulos) == 3, "los tres casos deben decir cosas distintas"


def test_avisos_coincide_exactamente_con_los_estados():
    assert set(AVISOS) == set(EstadoEjecucion)


def test_ningun_aviso_afirma_que_no_se_envio_en_error_de_transmision():
    """La prohibicion, comprobada sobre el texto que ve el usuario."""
    aviso = AVISOS[EstadoEjecucion.ERROR_TRANSMISION]
    texto = (aviso.titulo + " " + aviso.detalle).lower()
    for prohibido in ("nunca salio", "no se envio", "cero bytes", "nada salio"):
        assert prohibido not in texto, f"el aviso afirma lo indemostrable: {prohibido!r}"
    assert "no puede determinarse" in texto

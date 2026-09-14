"""Seguridad del aviso de reverso (0420/0430, B8).

Adversarial, real (TCP/SQLite/HTTP reales), espejo de
`test_seguridad_reverso_financiero.py`: confirma que el PAN completo nunca
aparece en la pantalla de vista previa del aviso ni en su resultado, que
DE90 sigue sin implementarse (misma decision que 0400, B7 punto 7 -B8 no
reabre esa decision-), y que el aviso persiste usando `card_id`, nunca el
PAN.
"""

from __future__ import annotations

from decimal import Decimal

import httpx2
import pytest

from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, DESTINO_ID_DEMO, PAN_DEMO
from sibutestlab8583.adapters.persistence.sqlite_repos import (
    RepositorioDestinosSQLite,
    RepositorioEjecucionesSQLite,
    RepositorioEscenariosSQLite,
    RepositorioSecuenciasSQLite,
    RepositorioTarjetasSQLite,
)
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.application.conexiones import DatosNuevaConexion
from sibutestlab8583.application.contexto_secuencia import ContextoSecuencia
from sibutestlab8583.application.escenarios import DatosNuevoEscenario, ServicioEscenarios
from sibutestlab8583.application.secuencias import (
    DatosNuevaSecuencia,
    DatosPaso,
    ServicioSecuencias,
)
from sibutestlab8583.application.variables_secuencia import resolver_referencia_de_paso
from sibutestlab8583.composicion import Composicion, Configuracion
from sibutestlab8583.domain.errores import CampoDeEjecucionSensible
from sibutestlab8583.domain.modelos import (
    ORIGEN_PASO_INDEPENDIENTE,
    MTI_COMPRA_FINANCIERA,
)
from sibutestlab8583.profiles.generico import PERFIL_GENERICO
from sibutestlab8583.web.app import crear_app


def _host(**kwargs) -> HostSimulado:
    return HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), **kwargs)


async def test_el_pan_nunca_aparece_en_preview_ni_en_resultado_del_aviso(base):
    composicion = Composicion(
        Configuracion(ruta_base_datos=base, host_destino="127.0.0.1", tiempo_limite=3.0)
    )
    host = _host()
    app = crear_app(composicion)

    async with host:
        await composicion.administracion_conexiones.crear(
            DatosNuevaConexion(
                conexion_id="SEC-B8", nombre="Host simulado de la prueba",
                host=host.host, puerto=str(host.puerto),
            )
        )
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://prueba"
        ) as cliente:
            await cliente.post(
                "/financiera/ejecutar",
                data={"card_id": CARD_ID_DEMO, "monto": "55.00", "conexion_id": "SEC-B8"},
            )
            origen_id = (await composicion.consultas.ejecuciones_recientes())[0].id

            preview = await cliente.get(f"/historial/{origen_id}/aviso-reverso")
            resultado = await cliente.post(f"/historial/{origen_id}/aviso-reverso/ejecutar")

            derivada_id = (await composicion.consultas.derivadas_de(origen_id))[0].id
            detalle_derivada = await cliente.get(f"/historial/{derivada_id}")

    for pagina in (preview, resultado, detalle_derivada):
        assert PAN_DEMO not in pagina.text

    ejecucion_derivada = (await composicion.consultas.ejecuciones_recientes())[0]
    assert ejecucion_derivada.card_id == CARD_ID_DEMO


async def test_de90_nunca_aparece_porque_no_esta_implementado(base):
    """B8 no reabre la decision de B7 sobre DE90 (ver
    application/armado_aviso_reverso.py): sigue sin fuente defendible para
    DE33, asi que ningun campo "90" debe aparecer en la vista previa del
    aviso de reverso."""
    composicion = Composicion(
        Configuracion(ruta_base_datos=base, host_destino="127.0.0.1", tiempo_limite=3.0)
    )
    host = _host()
    app = crear_app(composicion)

    async with host:
        await composicion.administracion_conexiones.crear(
            DatosNuevaConexion(
                conexion_id="SEC-B8-2", nombre="Host simulado de la prueba",
                host=host.host, puerto=str(host.puerto),
            )
        )
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url="http://prueba"
        ) as cliente:
            await cliente.post(
                "/financiera/ejecutar",
                data={"card_id": CARD_ID_DEMO, "monto": "45.00", "conexion_id": "SEC-B8-2"},
            )
            origen_id = (await composicion.consultas.ejecuciones_recientes())[0].id
            preview = await cliente.get(f"/historial/{origen_id}/aviso-reverso")

    assert 'campo-iso">90<' not in preview.text


async def test_referencia_de_paso_a_de35_o_de45_se_rechaza_igual_tras_agregar_0420(base):
    """Regresion (B8): el piso universal de seguridad de C2
    (`perfil.es_sensible` chequeado ANTES que cualquier otra cosa en
    `resolver_referencia_de_paso`) no depende de cuantas operaciones
    derivadas soporte el motor de secuencias -confirma que agregar 0420 no
    abrio ninguna puerta nueva para DE35/DE45."""
    escenarios = ServicioEscenarios(
        RepositorioEscenariosSQLite(base), RepositorioTarjetasSQLite(base),
        RepositorioDestinosSQLite(base), PERFIL_GENERICO,
    )
    paso1 = await escenarios.crear(
        DatosNuevoEscenario(
            nombre="Paso 1", conexion_id=DESTINO_ID_DEMO,
            mti=MTI_COMPRA_FINANCIERA, card_id=CARD_ID_DEMO, monto=Decimal("10.00"),
        )
    )
    secuencias = ServicioSecuencias(RepositorioSecuenciasSQLite(base), RepositorioEscenariosSQLite(base))
    await secuencias.crear(
        DatosNuevaSecuencia(
            nombre="Prueba de seguridad B8",
            pasos=[
                DatosPaso(
                    origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso1.escenario_id,
                    paso_id="purchase",
                ),
            ],
        )
    )

    contexto = ContextoSecuencia()
    contexto.registrar(1, ejecucion_id=999, paso_id="purchase")
    ejecuciones = RepositorioEjecucionesSQLite(base)

    for campo_sensible in ("35", "45"):
        with pytest.raises(CampoDeEjecucionSensible):
            await resolver_referencia_de_paso(
                f"{{{{step.purchase.response.de{campo_sensible}}}}}",
                contexto, ejecuciones, PERFIL_GENERICO,
            )

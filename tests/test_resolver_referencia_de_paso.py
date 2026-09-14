"""`application.variables_secuencia.resolver_referencia_de_paso` (Fase C2).

Real (TCP/codec/SQLite/host simulado reales, sin dobles): construye una
compra financiera real y aprobada, la registra en un `ContextoSecuencia`
bajo un `paso_id` estable, y resuelve referencias reales contra su
snapshot persistido -exactamente el camino que sigue `EjecutorDeSecuencia`
para un paso independiente cuyo escenario referencia a otro paso.

Cubre los adversariales explicitamente pedidos por el checkpoint (punto
22): DE2/DE35/DE45 rechazados, paso inexistente, campo inexistente.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, PAN_DEMO
from sibutestlab8583.adapters.persistence.sqlite_repos import RepositorioEjecucionesSQLite
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.adapters.transporte.tcp import TransporteTcp
from sibutestlab8583.application.contexto_secuencia import ContextoSecuencia
from sibutestlab8583.application.variables_secuencia import resolver_referencia_de_paso
from sibutestlab8583.domain.errores import (
    CampoDeEjecucionNoDisponible,
    CampoDeEjecucionSensible,
    MetadataDeEjecucionDesconocida,
    PasoDeSecuenciaNoEjecutado,
)
from sibutestlab8583.domain.modelos import DatosCompraFinanciera
from sibutestlab8583.profiles.generico import PERFIL_GENERICO

from conftest import construir_orquestador


def _host(**kwargs) -> HostSimulado:
    return HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), **kwargs)


async def _ejecutar_financiera_real(base, *, monto=Decimal("50.00")):
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        from sibutestlab8583.domain.modelos import DestinoTcp

        orquestador = construir_orquestador(
            base, transporte, destino=DestinoTcp(host=host.host, puerto=host.puerto), tiempo_limite=2.0,
        )
        return await orquestador.ejecutar_compra_financiera(
            DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=monto)
        )


async def test_resuelve_un_campo_de_respuesta_real(base):
    resultado = await _ejecutar_financiera_real(base)
    contexto = ContextoSecuencia()
    contexto.registrar(1, resultado.ejecucion.id, paso_id="purchase")
    repo = RepositorioEjecucionesSQLite(base)

    valor = await resolver_referencia_de_paso(
        "{{step.purchase.response.de38}}", contexto, repo, PERFIL_GENERICO
    )
    assert valor == resultado.ejecucion.stan  # DE38 lo copia el host del STAN al aprobar


async def test_resuelve_metadata_execution_id():
    resultado_id = 73
    contexto = ContextoSecuencia()
    contexto.registrar(1, resultado_id, paso_id="purchase")

    # No necesita SQLite: execution_id es metadata interna, no un campo ISO.
    valor = await resolver_referencia_de_paso(
        "{{step.purchase.execution_id}}", contexto, repositorio_ejecuciones=None, perfil=PERFIL_GENERICO
    )
    assert valor == str(resultado_id)


async def test_de2_pan_se_rechaza_siempre(base):
    resultado = await _ejecutar_financiera_real(base)
    contexto = ContextoSecuencia()
    contexto.registrar(1, resultado.ejecucion.id, paso_id="purchase")
    repo = RepositorioEjecucionesSQLite(base)

    with pytest.raises(CampoDeEjecucionSensible):
        await resolver_referencia_de_paso(
            "{{step.purchase.request.de2}}", contexto, repo, PERFIL_GENERICO
        )


async def test_de35_track2_se_rechaza_siempre(base):
    resultado = await _ejecutar_financiera_real(base)
    contexto = ContextoSecuencia()
    contexto.registrar(1, resultado.ejecucion.id, paso_id="purchase")
    repo = RepositorioEjecucionesSQLite(base)

    with pytest.raises(CampoDeEjecucionSensible):
        await resolver_referencia_de_paso(
            "{{step.purchase.request.de35}}", contexto, repo, PERFIL_GENERICO
        )


async def test_de45_track1_se_rechaza_siempre(base):
    resultado = await _ejecutar_financiera_real(base)
    contexto = ContextoSecuencia()
    contexto.registrar(1, resultado.ejecucion.id, paso_id="purchase")
    repo = RepositorioEjecucionesSQLite(base)

    with pytest.raises(CampoDeEjecucionSensible):
        await resolver_referencia_de_paso(
            "{{step.purchase.request.de45}}", contexto, repo, PERFIL_GENERICO
        )


async def test_un_paso_inexistente_revienta_con_error_claro(base):
    contexto = ContextoSecuencia()  # nunca se registro "purchase"
    repo = RepositorioEjecucionesSQLite(base)

    with pytest.raises(PasoDeSecuenciaNoEjecutado):
        await resolver_referencia_de_paso(
            "{{step.purchase.response.de38}}", contexto, repo, PERFIL_GENERICO
        )


async def test_un_campo_inexistente_en_el_perfil_revienta_con_error_claro(base):
    resultado = await _ejecutar_financiera_real(base)
    contexto = ContextoSecuencia()
    contexto.registrar(1, resultado.ejecucion.id, paso_id="purchase")
    repo = RepositorioEjecucionesSQLite(base)

    with pytest.raises(MetadataDeEjecucionDesconocida):
        await resolver_referencia_de_paso(
            "{{step.purchase.response.de99}}", contexto, repo, PERFIL_GENERICO
        )


async def test_un_campo_ausente_en_ese_mensaje_revienta_con_error_claro(base):
    resultado = await _ejecutar_financiera_real(base)
    contexto = ContextoSecuencia()
    contexto.registrar(1, resultado.ejecucion.id, paso_id="purchase")
    repo = RepositorioEjecucionesSQLite(base)

    # DE18 (tipo de comercio) es un campo OPCIONAL de 0200: valido segun el
    # perfil, pero esta compra no lo agrego -no debe resolver a "" en silencio-.
    with pytest.raises(CampoDeEjecucionNoDisponible):
        await resolver_referencia_de_paso(
            "{{step.purchase.request.de18}}", contexto, repo, PERFIL_GENERICO
        )


async def test_el_pan_completo_nunca_aparece_al_resolver_de37(base):
    """Adversarial: aunque DE37 (RRN) no es sensible, confirma que resolverlo
    nunca expone el PAN por accidente (el campo simplemente no lo contiene)."""
    resultado = await _ejecutar_financiera_real(base)
    contexto = ContextoSecuencia()
    contexto.registrar(1, resultado.ejecucion.id, paso_id="purchase")
    repo = RepositorioEjecucionesSQLite(base)

    try:
        valor = await resolver_referencia_de_paso(
            "{{step.purchase.request.de37}}", contexto, repo, PERFIL_GENERICO
        )
    except CampoDeEjecucionNoDisponible:
        valor = ""  # DE37 no es obligatorio en 0200; puede no estar
    assert PAN_DEMO not in valor

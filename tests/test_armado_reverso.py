"""`application.armado_reverso.armar_reverso_financiero` (B7).

Pruebas puras: sin red, sin base de datos. `ReferenciaEjecucion` se
construye a mano aqui -no hace falta una ejecucion real para probar el
builder en aislamiento; el camino real end-to-end (`ReferenciaEjecucion`
construida de verdad desde una 0200 real) se prueba en
`test_orquestador_reverso_financiero.py`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from sibutestlab8583.application.armado_reverso import armar_reverso_financiero
from sibutestlab8583.application.referencia_ejecucion import ReferenciaEjecucion
from sibutestlab8583.domain.armado import formatear_monto
from sibutestlab8583.domain.errores import ReferenciaOrigenIncompleta
from sibutestlab8583.domain.modelos import MTI_REVERSO_FINANCIERO

MOMENTO = datetime(2026, 9, 13, 12, 0, 0, tzinfo=timezone.utc)


def _referencia(**overrides) -> ReferenciaEjecucion:
    base = dict(
        ejecucion_id=100,
        mti_solicitud="0200",
        mti_respuesta="0210",
        stan="000050",
        monto=Decimal("75.00"),
        moneda="188",
        card_id="DEMO-0001",
        codigo_respuesta="00",
        destino_host="127.0.0.1",
        destino_puerto=9999,
        creada_en=MOMENTO,
        terminal="TERM0001",
        rrn="RRN00000A012",
        campos_respuesta={"38": "000050"},
    )
    base.update(overrides)
    return ReferenciaEjecucion(**base)


def test_arma_un_0400_con_los_campos_esperados():
    mensaje = armar_reverso_financiero(_referencia(), stan_nuevo="000099", momento_nuevo=MOMENTO)
    assert mensaje.mti == MTI_REVERSO_FINANCIERO
    assert mensaje.campos["3"] == "000000"
    assert mensaje.campos["4"] == formatear_monto(Decimal("75.00"))
    assert mensaje.campos["11"] == "000099"
    assert mensaje.campos["41"] == "TERM0001"
    assert mensaje.campos["49"] == "188"
    assert mensaje.campos["37"] == "RRN00000A012"
    assert mensaje.campos["7"] == MOMENTO.strftime("%m%d%H%M%S")


def test_el_stan_del_reverso_nunca_es_el_stan_original():
    referencia = _referencia(stan="000050")
    mensaje = armar_reverso_financiero(referencia, stan_nuevo="000099", momento_nuevo=MOMENTO)
    assert mensaje.campos["11"] != referencia.stan
    assert mensaje.campos["11"] == "000099"


def test_sin_rrn_original_el_reverso_no_incluye_de37():
    referencia = _referencia(rrn=None)
    mensaje = armar_reverso_financiero(referencia, stan_nuevo="000099", momento_nuevo=MOMENTO)
    assert "37" not in mensaje.campos


def test_sin_monto_revienta_con_referencia_incompleta():
    with pytest.raises(ReferenciaOrigenIncompleta):
        armar_reverso_financiero(
            _referencia(monto=None), stan_nuevo="000099", momento_nuevo=MOMENTO
        )


def test_sin_moneda_revienta_con_referencia_incompleta():
    with pytest.raises(ReferenciaOrigenIncompleta):
        armar_reverso_financiero(
            _referencia(moneda=None), stan_nuevo="000099", momento_nuevo=MOMENTO
        )


def test_sin_terminal_revienta_con_referencia_incompleta():
    with pytest.raises(ReferenciaOrigenIncompleta):
        armar_reverso_financiero(
            _referencia(terminal=None), stan_nuevo="000099", momento_nuevo=MOMENTO
        )


def test_no_hay_ningun_campo_de_texto_libre_posible():
    """`armar_reverso_financiero` no recibe `campos_manuales`: su firma no
    admite ningun valor arbitrario de quien llame -a diferencia de
    `armar_compra`/`armar_compra_financiera`."""
    import inspect

    firma = inspect.signature(armar_reverso_financiero)
    assert set(firma.parameters) == {"referencia_original", "stan_nuevo", "momento_nuevo"}

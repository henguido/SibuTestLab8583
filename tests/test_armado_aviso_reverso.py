"""`application.armado_aviso_reverso.armar_aviso_reverso` (B8).

Pruebas puras: sin red, sin base de datos. Espejo de
`test_armado_reverso.py` -misma composicion de campos, medida y confirmada
identica en `application/armado_operacion_derivada.py`-, salvo el MTI y el
codigo de proceso propios de 0420.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from sibutestlab8583.application.armado_aviso_reverso import armar_aviso_reverso
from sibutestlab8583.application.referencia_ejecucion import ReferenciaEjecucion
from sibutestlab8583.domain.armado import formatear_monto
from sibutestlab8583.domain.errores import ReferenciaOrigenIncompleta
from sibutestlab8583.domain.modelos import MTI_AVISO_REVERSO

MOMENTO = datetime(2026, 9, 14, 12, 0, 0, tzinfo=timezone.utc)


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


def test_arma_un_0420_con_los_campos_esperados():
    mensaje = armar_aviso_reverso(_referencia(), stan_nuevo="000099", momento_nuevo=MOMENTO)
    assert mensaje.mti == MTI_AVISO_REVERSO
    assert mensaje.campos["3"] == "000000"
    assert mensaje.campos["4"] == formatear_monto(Decimal("75.00"))
    assert mensaje.campos["11"] == "000099"
    assert mensaje.campos["41"] == "TERM0001"
    assert mensaje.campos["49"] == "188"
    assert mensaje.campos["37"] == "RRN00000A012"
    assert mensaje.campos["7"] == MOMENTO.strftime("%m%d%H%M%S")


def test_el_stan_del_aviso_nunca_es_el_stan_original():
    referencia = _referencia(stan="000050")
    mensaje = armar_aviso_reverso(referencia, stan_nuevo="000099", momento_nuevo=MOMENTO)
    assert mensaje.campos["11"] != referencia.stan
    assert mensaje.campos["11"] == "000099"


def test_sin_rrn_original_el_aviso_no_incluye_de37():
    referencia = _referencia(rrn=None)
    mensaje = armar_aviso_reverso(referencia, stan_nuevo="000099", momento_nuevo=MOMENTO)
    assert "37" not in mensaje.campos


def test_sin_monto_revienta_con_referencia_incompleta():
    with pytest.raises(ReferenciaOrigenIncompleta):
        armar_aviso_reverso(_referencia(monto=None), stan_nuevo="000099", momento_nuevo=MOMENTO)


def test_sin_moneda_revienta_con_referencia_incompleta():
    with pytest.raises(ReferenciaOrigenIncompleta):
        armar_aviso_reverso(_referencia(moneda=None), stan_nuevo="000099", momento_nuevo=MOMENTO)


def test_sin_terminal_revienta_con_referencia_incompleta():
    with pytest.raises(ReferenciaOrigenIncompleta):
        armar_aviso_reverso(_referencia(terminal=None), stan_nuevo="000099", momento_nuevo=MOMENTO)


def test_no_hay_ningun_campo_de_texto_libre_posible():
    """`armar_aviso_reverso` no recibe `campos_manuales`, mismo criterio que
    `armar_reverso_financiero`."""
    import inspect

    firma = inspect.signature(armar_aviso_reverso)
    assert set(firma.parameters) == {"referencia_original", "stan_nuevo", "momento_nuevo"}


def test_un_mismo_origen_produce_0400_y_0420_con_stan_distinto():
    """El aviso de reverso y el reverso financiero son operaciones DERIVADAS
    distintas (B8): comparten origen pero cada una recibe su propio STAN, y
    ninguna reutiliza el STAN de la otra."""
    from sibutestlab8583.application.armado_reverso import armar_reverso_financiero

    referencia = _referencia()
    reverso = armar_reverso_financiero(referencia, stan_nuevo="000098", momento_nuevo=MOMENTO)
    aviso = armar_aviso_reverso(referencia, stan_nuevo="000099", momento_nuevo=MOMENTO)

    assert reverso.mti != aviso.mti
    assert reverso.campos["11"] != aviso.campos["11"]

"""Variables dinamicas en campos manuales (Fase A, entrega minima).

Cubre: reconocimiento/rechazo de la gramatica `{{...}}`, resolucion de los
cinco built-ins, errores controlados (expresion malformada, variable
desconocida), integracion end-to-end (el valor resuelto por el orquestador
real coincide con el STAN real del mensaje transmitido) y el efecto en la
vista previa (`es_valor_definitivo` debe ser falso para variables no
reproducibles y verdadero para `{{amount}}`).
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO
from sibutestlab8583.application.vista_previa import ServicioVistaPrevia
from sibutestlab8583.domain.armado import formatear_monto
from sibutestlab8583.domain.datos_sinteticos import pan_sintetico
from sibutestlab8583.domain.errores import ExpresionMalformada, VariableDesconocida
from sibutestlab8583.domain.modelos import DatosCompra, TarjetaPrueba
from sibutestlab8583.domain.variables import (
    VARIABLES_NO_REPRODUCIBLES,
    ContextoResolucion,
    es_expresion,
    resolver_campos_manuales,
    resolver_valor,
)
from sibutestlab8583.profiles.generico import PERFIL_GENERICO

from conftest import TransporteFalso, construir_orquestador

MOMENTO = datetime(2026, 9, 11, 14, 30, 45, tzinfo=timezone.utc)


def _contexto(**kwargs) -> ContextoResolucion:
    base = dict(monto=Decimal("150.00"), stan="000123", momento=MOMENTO)
    base.update(kwargs)
    return ContextoResolucion(**base)


class TestEsExpresion:
    def test_reconoce_una_variable_valida(self):
        assert es_expresion("{{stan}}") is True

    def test_reconoce_con_espacios_internos(self):
        assert es_expresion("{{ stan }}") is True

    def test_rechaza_un_literal_plano(self):
        assert es_expresion("000123") is False

    def test_rechaza_texto_con_llaves_que_no_calzan(self):
        assert es_expresion("prefijo {{stan}}") is False
        assert es_expresion("{{stan}} sufijo") is False
        assert es_expresion("{{no valido}}") is False
        assert es_expresion("{{}}") is False

    def test_rechaza_nombre_con_mayusculas(self):
        assert es_expresion("{{STAN}}") is False


class TestResolverValor:
    def test_amount_usa_el_formato_de_de4(self):
        # Comparado contra el mismo formateador que usa DE4, no contra un
        # literal: un literal de 12 digitos dispararia el guardian de PAN
        # (`test_datos_sinteticos.py`), que no distingue "digitos de un monto
        # formateado" de "posible numero de tarjeta".
        monto = Decimal("10.00")
        assert resolver_valor("{{amount}}", _contexto(monto=monto)) == formatear_monto(monto)

    def test_stan_devuelve_el_stan_del_contexto(self):
        assert resolver_valor("{{stan}}", _contexto(stan="000456")) == "000456"

    def test_transmission_datetime_usa_mmddhhmmss(self):
        assert resolver_valor("{{transmission_datetime}}", _contexto()) == "0911143045"

    def test_local_time_usa_hhmmss(self):
        assert resolver_valor("{{local_time}}", _contexto()) == "143045"

    def test_local_date_usa_mmdd(self):
        assert resolver_valor("{{local_date}}", _contexto()) == "0911"

    def test_un_literal_se_devuelve_tal_cual(self):
        assert resolver_valor("5411", _contexto()) == "5411"

    def test_expresion_malformada_revienta(self):
        with pytest.raises(ExpresionMalformada):
            resolver_valor("{{stan} }", _contexto())

    def test_variable_desconocida_revienta(self):
        with pytest.raises(VariableDesconocida):
            resolver_valor("{{rrn}}", _contexto())


class TestResolverCamposManuales:
    def test_deja_literales_intactos(self):
        resueltos, no_reproducibles = resolver_campos_manuales(
            {"18": "5411"}, _contexto()
        )
        assert resueltos == {"18": "5411"}
        assert no_reproducibles == frozenset()

    def test_marca_como_no_reproducible_solo_las_variables_de_esa_lista(self):
        resueltos, no_reproducibles = resolver_campos_manuales(
            {"3": "{{stan}}", "49": "840"}, _contexto(stan="000789")
        )
        assert resueltos == {"3": "000789", "49": "840"}
        assert no_reproducibles == frozenset({"3"})

    def test_amount_no_se_marca_como_no_reproducible(self):
        _, no_reproducibles = resolver_campos_manuales(
            {"43": "{{amount}}"}, _contexto()
        )
        assert no_reproducibles == frozenset()

    def test_variables_no_reproducibles_no_incluye_amount(self):
        assert "amount" not in VARIABLES_NO_REPRODUCIBLES


class _RepositorioTarjetasFalso:
    def __init__(self, tarjetas):
        self._tarjetas = tarjetas

    async def obtener(self, card_id):
        return self._tarjetas.get(card_id)


async def test_vista_previa_marca_stan_dinamico_como_no_definitivo():
    codec = CodecIso8583()
    tarjetas = {"X": TarjetaPrueba(card_id="X", pan=pan_sintetico("6666"), expiracion="3012")}
    servicio = ServicioVistaPrevia(_RepositorioTarjetasFalso(tarjetas), codec, PERFIL_GENERICO)

    vista = await servicio.construir(
        DatosCompra(card_id="X", monto=Decimal("10.00"), campos_manuales={"3": "{{stan}}"})
    )

    por_numero = {c.numero: c for c in vista.campos}
    assert por_numero["3"].es_valor_definitivo is False


async def test_vista_previa_marca_amount_como_definitivo():
    codec = CodecIso8583()
    tarjetas = {"X": TarjetaPrueba(card_id="X", pan=pan_sintetico("6666"), expiracion="3012")}
    servicio = ServicioVistaPrevia(_RepositorioTarjetasFalso(tarjetas), codec, PERFIL_GENERICO)

    vista = await servicio.construir(
        DatosCompra(card_id="X", monto=Decimal("10.00"), campos_manuales={"49": "840"})
    )

    por_numero = {c.numero: c for c in vista.campos}
    assert por_numero["49"].es_valor_definitivo is True


async def test_orquestador_resuelve_stan_dinamico_igual_al_stan_real(base):
    """El valor que `{{stan}}` produce en un campo manual debe coincidir,
    campo a campo, con el STAN real (DE11) del mismo mensaje transmitido -no
    con un marcador ni con un valor adivinado por separado."""
    transporte = TransporteFalso(codigo="00")
    orquestador = construir_orquestador(base, transporte)

    resultado = await orquestador.ejecutar_compra(
        DatosCompra(
            card_id=CARD_ID_DEMO,
            monto=Decimal("10.00"),
            campos_manuales={"3": "{{stan}}"},
        ),
    )

    assert resultado.solicitud.campos["3"] == resultado.solicitud.campos["11"]

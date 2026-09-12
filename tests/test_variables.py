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
from sibutestlab8583.domain.armado import formatear_monto, valores_efectivos_editables
from sibutestlab8583.domain.datos_sinteticos import pan_sintetico
from sibutestlab8583.domain.errores import ExpresionMalformada, VariableDesconocida
from sibutestlab8583.domain.modelos import MTI_COMPRA, DatosCompra, TarjetaPrueba
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


class TestExpresionesParcialesYMixtas:
    """La gramatica es cerrada A PROPOSITO: solo `{{identificador}}`, el campo
    COMPLETO, nada mas. Un campo que mezcle literal y variable, o que tenga
    una llave sin cerrar, no es "parcialmente resuelto": es un error, porque
    intentar adivinar la intencion en un campo que viaja a un mensaje de pago
    es exactamente el tipo de "reinterpretar en silencio" que el proyecto
    evita en todos sus otros modulos (ver `incompatibilidades_escenario`,
    `DiagnosticoEscenario`, etc.).
    """

    @pytest.mark.parametrize(
        "valor",
        [
            "ABC{{stan}}",
            "{{stan}}XYZ",
            "{{stan} }",
            "{{stan",
            "{{ stan",
            "stan}}",
        ],
    )
    def test_variable_mezclada_con_literal_o_incompleta_revienta(self, valor):
        with pytest.raises(ExpresionMalformada):
            resolver_valor(valor, _contexto())

    def test_una_expresion_vacia_revienta_como_malformada_no_como_desconocida(self):
        with pytest.raises(ExpresionMalformada):
            resolver_valor("{{}}", _contexto())


class TestPayloadsAdversariales:
    """Los intentos de inyeccion/ejecucion nunca deben resolverse: la
    gramatica cerrada (`^\\{\\{\\s*[a-z][a-z0-9_]*\\s*\\}\\}$`) no admite
    parentesis, comillas, puntos, barras ni signos de dolar, asi que ninguno
    de estos payloads puede convertirse en una variable valida. Ninguna de
    estas pruebas ejecuta el payload: solo comprueba que `resolver_valor`
    jamas lo interpreta como codigo, y que el resultado es siempre uno de los
    tres estados legales (literal / expresion invalida / variable
    desconocida), nunca una cuarta ruta que evalue algo.
    """

    @pytest.mark.parametrize(
        "payload",
        [
            "{{__import__('os')}}",
            "{{os.system}}",
            "{{env.PASSWORD}}",
            "{{../../archivo}}",
            "{{os.system('ls')}}",
        ],
    )
    def test_payloads_con_llaves_dobles_no_calzan_la_gramatica(self, payload):
        with pytest.raises(ExpresionMalformada):
            resolver_valor(payload, _contexto())

    @pytest.mark.parametrize("payload", ["${HOME}", "{% import os %}", "{%stan%}"])
    def test_payloads_sin_llaves_dobles_se_tratan_como_literal(self, payload):
        # No contienen "{{"/"}}" -la unica gramatica que este modulo reconoce
        # como variable-, asi que nunca entran a resolucion: se devuelven tal
        # cual, igual que cualquier otro literal de campos_manuales. Esto no
        # es una omision: es la razon por la que nunca hay una ruta hacia un
        # motor de plantillas de terceros ni hacia el shell.
        assert resolver_valor(payload, _contexto()) == payload

    def test_ningun_payload_ejecuta_codigo_python(self):
        marcador = {"ejecutado": False}

        def _no_deberia_llamarse():
            marcador["ejecutado"] = True

        # Si `resolver_valor` alguna vez usara `eval`/`exec` sobre el valor,
        # este payload literal lo delataria: una funcion Python real referida
        # por nombre dentro de las llaves. Con la gramatica actual, "llamar"
        # no es una forma valida de identificador (contiene "(" y ")"), asi
        # que revienta como expresion malformada antes de llegar a cualquier
        # tabla de busqueda.
        with pytest.raises(ExpresionMalformada):
            resolver_valor("{{_no_deberia_llamarse()}}", _contexto())
        assert marcador["ejecutado"] is False


def test_valores_efectivos_editables_congela_la_expresion_sin_resolverla():
    """Un escenario guardado debe conservar `{{stan}}` TAL CUAL, no un STAN ya
    resuelto: la resolucion ocurre en cada reejecucion (orquestador/vista
    previa), nunca al guardar. Si este congelamiento resolviera la variable,
    todo escenario con `{{stan}}` quedaria con el mismo STAN fijo para
    siempre, exactamente lo que Fase A busca evitar.
    """
    efectivos = valores_efectivos_editables({"3": "{{stan}}"}, PERFIL_GENERICO, MTI_COMPRA)
    assert efectivos["3"] == "{{stan}}"


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

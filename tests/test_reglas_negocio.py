"""Las cuatro reglas de negocio de PROYECTO.md seccion 4.

Cada prueba falla si la regla se rompe. Se prueban contra el orquestador real y
los repositorios reales; solo el transporte es un doble, porque el objetivo es
la regla y no la red. La red se prueba en `test_integracion_end_to_end.py`.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from conftest import MOMENTO_FIJO, TransporteFalso, construir_orquestador
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO
from sibutestlab8583.adapters.persistence.sqlite_repos import (
    RepositorioEjecucionesSQLite,
    RepositorioTarjetasSQLite,
)
from sibutestlab8583.domain.armado import armar_compra
from sibutestlab8583.domain.catalogo import (
    CatalogoDeRespuestas,
    CodigoRespuesta,
    CATALOGO_GENERICO,
)
from sibutestlab8583.domain.modelos import (
    MTI_RESPUESTA_COMPRA,
    DatosCompra,
    EstadoEjecucion,
    MensajeIso,
    TarjetaPrueba,
    TiempoAgotado,
)
from sibutestlab8583.domain.validacion import (
    CAMPO_CODIGO_RESPUESTA,
    campos_de_correlacion,
    evaluar_respuesta,
    validar_envio,
)
from sibutestlab8583.profiles.generico import (
    CODIGO_PROCESO_COMPRA,
    OBLIGATORIOS_0100,
    PERFIL_GENERICO,
)
from sibutestlab8583.domain.datos_sinteticos import pan_sintetico

CODEC = CodecIso8583()


def _solicitud_valida() -> MensajeIso:
    return armar_compra(
        DatosCompra(card_id=CARD_ID_DEMO, monto=Decimal("150.00")),
        TarjetaPrueba(card_id=CARD_ID_DEMO, pan=pan_sintetico("6666"), expiracion="3012"),
        stan="000001",
        momento=MOMENTO_FIJO,
        codigo_proceso=CODIGO_PROCESO_COMPRA,
    )


def _respuesta_correlacionada(solicitud: MensajeIso, codigo: str = "00") -> MensajeIso:
    campos = {
        numero: solicitud.campos[numero]
        for numero in campos_de_correlacion(PERFIL_GENERICO, MTI_RESPUESTA_COMPRA)
        if numero in solicitud.campos
    }
    campos[CAMPO_CODIGO_RESPUESTA] = codigo
    return MensajeIso(mti=MTI_RESPUESTA_COMPRA, campos=campos)


# ---------------------------------------------------------------- RN-1 -------


def test_rn1_el_catalogo_decide_la_aprobacion():
    solicitud = _solicitud_valida()
    estado, _ = evaluar_respuesta(
        solicitud, _respuesta_correlacionada(solicitud, "00"), CATALOGO_GENERICO, PERFIL_GENERICO
    )
    assert estado is EstadoEjecucion.APROBADA


@pytest.mark.parametrize("codigo", ["05", "14", "51", "54", "94"])
def test_rn1_los_demas_codigos_del_catalogo_son_rechazos(codigo):
    solicitud = _solicitud_valida()
    estado, motivos = evaluar_respuesta(
        solicitud,
        _respuesta_correlacionada(solicitud, codigo),
        CATALOGO_GENERICO,
        PERFIL_GENERICO,
    )
    assert estado is EstadoEjecucion.RECHAZADA
    assert motivos


def test_rn1_la_logica_consulta_el_catalogo_y_no_compara_contra_00():
    """Con un catalogo donde 00 NO aprueba y 51 SI, el resultado debe invertirse.

    Si la aprobacion estuviera escrita como `codigo == "00"`, esta prueba
    fallaria. Es la comprobacion de que RN-1 depende de la configuracion.
    """
    catalogo_invertido = CatalogoDeRespuestas.desde(
        "invertido",
        [
            CodigoRespuesta("00", "No aprobada en este catalogo", aprobado=False),
            CodigoRespuesta("51", "Aprobada en este catalogo", aprobado=True),
        ],
    )
    solicitud = _solicitud_valida()

    estado_00, _ = evaluar_respuesta(
        solicitud, _respuesta_correlacionada(solicitud, "00"), catalogo_invertido, PERFIL_GENERICO
    )
    estado_51, _ = evaluar_respuesta(
        solicitud, _respuesta_correlacionada(solicitud, "51"), catalogo_invertido, PERFIL_GENERICO
    )

    assert estado_00 is EstadoEjecucion.RECHAZADA
    assert estado_51 is EstadoEjecucion.APROBADA


# ---------------------------------------------------------------- RN-2 -------


async def test_rn2_sin_respuesta_el_resultado_es_timeout(base, datos_compra):
    """El limite se inyecta: la prueba no espera diez segundos reales."""
    transporte = TransporteFalso(TiempoAgotado(limite_segundos=0.01))
    resultado = await construir_orquestador(base, transporte, tiempo_limite=0.01).ejecutar_compra(
        datos_compra
    )

    assert resultado.estado is EstadoEjecucion.TIMEOUT
    assert resultado.respuesta is None, "no debe evaluarse una respuesta inexistente"
    assert transporte.fue_invocado


async def test_rn2_el_timeout_se_persiste_y_se_cuenta_aparte_del_rechazo(base, datos_compra):
    orquestador_timeout = construir_orquestador(
        base, TransporteFalso(TiempoAgotado(limite_segundos=0.01))
    )
    await orquestador_timeout.ejecutar_compra(datos_compra)
    await construir_orquestador(base, TransporteFalso(codigo="05")).ejecutar_compra(datos_compra)

    guardadas = await RepositorioEjecucionesSQLite(base).listar()
    estados = [e.estado for e in guardadas]
    assert EstadoEjecucion.TIMEOUT in estados
    assert EstadoEjecucion.RECHAZADA in estados
    assert estados.count(EstadoEjecucion.TIMEOUT) == 1
    assert estados.count(EstadoEjecucion.RECHAZADA) == 1


async def test_rn2_el_limite_por_defecto_de_la_demostracion_es_diez_segundos():
    from sibutestlab8583.adapters.transporte.tcp import TIEMPO_LIMITE_POR_DEFECTO, TransporteTcp
    from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion

    assert TIEMPO_LIMITE_POR_DEFECTO == 10.0
    assert TransporteTcp(FramingDemostracion()).tiempo_limite == 10.0


# ---------------------------------------------------------------- RN-3 -------


def test_rn3_una_respuesta_correlacionada_es_valida():
    solicitud = _solicitud_valida()
    estado, motivos = evaluar_respuesta(
        solicitud, _respuesta_correlacionada(solicitud), CATALOGO_GENERICO, PERFIL_GENERICO
    )
    assert estado is EstadoEjecucion.APROBADA
    assert motivos == ()


@pytest.mark.parametrize(
    "campo", sorted(campos_de_correlacion(PERFIL_GENERICO, MTI_RESPUESTA_COMPRA), key=int)
)
def test_rn3_alterar_cualquier_campo_de_correlacion_invalida_la_respuesta(campo):
    """Aunque el campo 39 diga aprobado. Es la defensa contra el falso positivo."""
    solicitud = _solicitud_valida()
    respuesta = _respuesta_correlacionada(solicitud, "00")
    original = respuesta.campos[campo]
    # Se altera el primer caracter conservando el largo: garantiza que el valor
    # cambie sin escribir literales largos en el codigo.
    distinto = ("8" if original[0] != "8" else "7") + original[1:]
    alterada = MensajeIso(mti=respuesta.mti, campos={**dict(respuesta.campos), campo: distinto})

    estado, motivos = evaluar_respuesta(solicitud, alterada, CATALOGO_GENERICO, PERFIL_GENERICO)

    assert estado is EstadoEjecucion.INVALIDA, f"el campo {campo} alterado debio invalidar"
    assert estado is not EstadoEjecucion.APROBADA
    assert any(campo in m for m in motivos)


def test_rn3_una_respuesta_con_mti_inesperado_es_invalida():
    solicitud = _solicitud_valida()
    respuesta = _respuesta_correlacionada(solicitud)
    otra = MensajeIso(mti="0210", campos=dict(respuesta.campos))
    estado, motivos = evaluar_respuesta(solicitud, otra, CATALOGO_GENERICO, PERFIL_GENERICO)
    assert estado is EstadoEjecucion.INVALIDA
    assert any("MTI" in m for m in motivos)


def test_rn3_una_respuesta_sin_campos_obligatorios_es_invalida():
    solicitud = _solicitud_valida()
    incompleta = MensajeIso(mti=MTI_RESPUESTA_COMPRA, campos={CAMPO_CODIGO_RESPUESTA: "00"})
    estado, _ = evaluar_respuesta(solicitud, incompleta, CATALOGO_GENERICO, PERFIL_GENERICO)
    assert estado is EstadoEjecucion.INVALIDA


# ---------------------------------------------------------------- RN-4 -------


@pytest.mark.parametrize("campo", sorted(OBLIGATORIOS_0100, key=int))
def test_rn4_falta_un_campo_obligatorio_y_no_se_valida(campo):
    solicitud = _solicitud_valida()
    incompleta = MensajeIso(
        mti=solicitud.mti, campos={n: v for n, v in solicitud.campos.items() if n != campo}
    )
    resultado = validar_envio(incompleta, PERFIL_GENERICO)
    assert not resultado
    assert campo in resultado.faltantes


async def test_rn4_un_mensaje_incompleto_nunca_llega_al_transporte(base, datos_compra):
    """La comprobacion que importa: el doble de transporte no debe ser invocado."""
    transporte = TransporteFalso()
    orquestador = construir_orquestador(base, transporte)

    # Una tarjeta sin fecha de vencimiento deja el 0100 sin el campo 14.
    await RepositorioTarjetasSQLite(base).guardar(
        TarjetaPrueba(card_id="SIN-VENC", pan=pan_sintetico("1111"), expiracion="")
    )

    resultado = await orquestador.ejecutar_compra(replace(datos_compra, card_id="SIN-VENC"))

    assert resultado.estado is EstadoEjecucion.NO_ENVIADA
    assert not transporte.fue_invocado, "el transporte fue invocado con un mensaje incompleto"
    assert any("14" in m for m in resultado.motivos)


async def test_rn4_la_ejecucion_no_enviada_queda_persistida(base, datos_compra):
    await RepositorioTarjetasSQLite(base).guardar(
        TarjetaPrueba(card_id="SIN-VENC-2", pan=pan_sintetico("2222"), expiracion="")
    )
    await construir_orquestador(base, TransporteFalso()).ejecutar_compra(
        replace(datos_compra, card_id="SIN-VENC-2")
    )

    guardadas = await RepositorioEjecucionesSQLite(base).listar()
    assert guardadas[0].estado is EstadoEjecucion.NO_ENVIADA
    assert guardadas[0].destino_host is None, "no se envio: no hay destino que registrar"

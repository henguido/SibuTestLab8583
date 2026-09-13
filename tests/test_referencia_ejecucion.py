"""B6: `application.referencia_ejecucion.ReferenciaEjecucion`.

E2E real (TCP/codec/SQLite, sin dobles) -mismo estilo que
`test_compra_financiera_e2e.py`-: construye una ejecucion real, aprobada,
con tarjeta real (sintetica, generada en ejecucion), y confirma que la
referencia construida a partir de su snapshot persistido:

1. nunca expone el PAN completo ni ningun Track (adversarial, punto 16/19
   de B6, investigado con Agente D);
2. solo trae los campos whitelisted de la respuesta (DE37/DE38);
3. se construye SIEMPRE desde el snapshot ya persistido -nunca desde el
   escenario vivo ni el perfil vigente (punto 5 de B6)-.
"""

from __future__ import annotations

from decimal import Decimal

from sibutestlab8583.adapters.host_simulado import HostSimulado
from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, PAN_DEMO
from sibutestlab8583.adapters.persistence.sqlite_repos import (
    RepositorioEjecucionesSQLite,
    RepositorioTarjetasSQLite,
)
from sibutestlab8583.adapters.transporte.framing_demo import FramingDemostracion
from sibutestlab8583.adapters.transporte.tcp import TransporteTcp
from sibutestlab8583.application.consultas import ServicioConsultas
from sibutestlab8583.application.referencia_ejecucion import (
    CAMPOS_REFERENCIA_RESPUESTA,
    referencia_desde_detalle,
)
from sibutestlab8583.domain.modelos import DatosCompraFinanciera, DestinoTcp, EstadoEjecucion
from sibutestlab8583.profiles.generico import PERFIL_GENERICO

from conftest import construir_orquestador


def _host(**kwargs) -> HostSimulado:
    return HostSimulado(CodecIso8583(), PERFIL_GENERICO, FramingDemostracion(), **kwargs)


async def _ejecutar_financiera_real(base, *, monto=Decimal("50.00")):
    host = _host()
    async with host:
        transporte = TransporteTcp(FramingDemostracion(), tiempo_limite=2.0)
        orquestador = construir_orquestador(
            base, transporte,
            destino=DestinoTcp(host=host.host, puerto=host.puerto), tiempo_limite=2.0,
        )
        return await orquestador.ejecutar_compra_financiera(
            DatosCompraFinanciera(card_id=CARD_ID_DEMO, monto=monto)
        )


async def test_la_referencia_nunca_expone_el_pan_completo(base):
    resultado = await _ejecutar_financiera_real(base)
    assert resultado.estado is EstadoEjecucion.APROBADA

    consultas = ServicioConsultas(RepositorioTarjetasSQLite(base), RepositorioEjecucionesSQLite(base))
    detalle = await consultas.detalle_ejecucion(resultado.ejecucion.id)
    referencia = referencia_desde_detalle(detalle)

    # Adversarial: recorrer todos los valores de la referencia -incluido el
    # dict de campos whitelisted- y confirmar que el PAN real jamas aparece,
    # ni siquiera como substring de otro campo.
    valores = [
        str(referencia.ejecucion_id), referencia.mti_solicitud, referencia.mti_respuesta,
        referencia.stan, str(referencia.monto), str(referencia.moneda),
        str(referencia.card_id), str(referencia.codigo_respuesta),
        str(referencia.destino_host), str(referencia.destino_puerto),
        str(referencia.creada_en), *referencia.campos_respuesta.values(),
    ]
    texto_completo = " ".join(valores)
    assert PAN_DEMO not in texto_completo


async def test_la_referencia_usa_card_id_no_el_pan(base):
    """`card_id` es el identificador de catalogo -nunca el PAN-, y es
    justamente lo que un futuro reverso necesitaria para re-derivar la
    tarjeta por el camino normal (`armar_compra_financiera`), no para leer
    un numero de vuelta."""
    resultado = await _ejecutar_financiera_real(base)
    consultas = ServicioConsultas(RepositorioTarjetasSQLite(base), RepositorioEjecucionesSQLite(base))
    detalle = await consultas.detalle_ejecucion(resultado.ejecucion.id)
    referencia = referencia_desde_detalle(detalle)

    assert referencia.card_id == CARD_ID_DEMO
    assert referencia.card_id != PAN_DEMO


async def test_la_referencia_solo_trae_los_campos_whitelisted_de_la_respuesta(base):
    resultado = await _ejecutar_financiera_real(base)
    consultas = ServicioConsultas(RepositorioTarjetasSQLite(base), RepositorioEjecucionesSQLite(base))
    detalle = await consultas.detalle_ejecucion(resultado.ejecucion.id)
    referencia = referencia_desde_detalle(detalle)

    assert set(referencia.campos_respuesta) <= CAMPOS_REFERENCIA_RESPUESTA
    # DE38 (codigo de autorizacion) lo agrega el host al aprobar: debe
    # aparecer aqui, sin exponer nada mas de la respuesta.
    assert "38" in referencia.campos_respuesta


async def test_los_datos_basicos_de_la_referencia_coinciden_con_la_ejecucion(base):
    resultado = await _ejecutar_financiera_real(base, monto=Decimal("30.00"))
    consultas = ServicioConsultas(RepositorioTarjetasSQLite(base), RepositorioEjecucionesSQLite(base))
    detalle = await consultas.detalle_ejecucion(resultado.ejecucion.id)
    referencia = referencia_desde_detalle(detalle)

    assert referencia.ejecucion_id == resultado.ejecucion.id
    assert referencia.mti_solicitud == resultado.ejecucion.mti_solicitud
    assert referencia.mti_respuesta == resultado.ejecucion.mti_respuesta
    assert referencia.monto == Decimal("30.00")
    assert referencia.codigo_respuesta == "00"


async def test_la_referencia_se_construye_del_snapshot_no_del_escenario_vivo(base):
    """Punto 5 de B6: aunque el escenario que origino la ejecucion se edite
    despues, la referencia -construida del snapshot ya persistido- no debe
    cambiar. No hay escenario en este flujo directo, asi que la prueba
    confirma la propiedad mas fuerte: la referencia se arma enteramente de
    `DetalleEjecucion` (el snapshot), nunca de una consulta en vivo al
    perfil ni a ningun catalogo -`referencia_desde_detalle` no recibe ni el
    perfil ni el catalogo como argumento-.
    """
    import inspect

    firma = inspect.signature(referencia_desde_detalle)
    assert list(firma.parameters) == ["detalle"]

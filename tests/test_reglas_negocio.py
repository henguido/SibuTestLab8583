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
from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, PAN_DEMO
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
    MTI_COMPRA,
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
    ESPECIFICACION_GENERICA,
    OBLIGATORIOS_0100,
    OBLIGATORIOS_0110,
    PERFIL_GENERICO,
    PerfilDeMarca,
)
from sibutestlab8583.domain.datos_sinteticos import monto_iso, pan_sintetico

CODEC = CodecIso8583()


def _solicitud_valida() -> MensajeIso:
    return armar_compra(
        DatosCompra(card_id=CARD_ID_DEMO, monto=Decimal("150.00")),
        TarjetaPrueba(card_id=CARD_ID_DEMO, pan=pan_sintetico("6666"), expiracion="3012"),
        stan="000001",
        momento=MOMENTO_FIJO,
        perfil=PERFIL_GENERICO,
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

    # Mejora posterior: el motivo persistido de cada una es distinto y
    # corresponde a su propia causa -nunca el mismo texto para TIMEOUT y
    # RECHAZADA, que son desenlaces distintos con causas distintas.
    por_estado = {e.estado: e.motivo_detalle for e in guardadas}
    assert por_estado[EstadoEjecucion.TIMEOUT] is not None
    assert "0.01" in por_estado[EstadoEjecucion.TIMEOUT] or "s" in por_estado[EstadoEjecucion.TIMEOUT]
    assert por_estado[EstadoEjecucion.RECHAZADA] is not None
    assert por_estado[EstadoEjecucion.TIMEOUT] != por_estado[EstadoEjecucion.RECHAZADA]


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


def test_campos_de_correlacion_excluye_siempre_los_campos_sensibles():
    """`campos_de_correlacion` nunca debe incluir DE2/DE35, aunque un perfil
    futuro los declarara obligatorios en la respuesta -mismo criterio que ya
    aplica `campos_permitidos_expectativa` en `domain/expectativas.py`-.

    Motivo: `_discrepancias_de_correlacion` arma el texto del motivo
    interpolando el valor tal cual (`f"...se envió {esperado!r} y volvió
    {recibido!r}"`) y ese texto se persiste sin pasar por `.enmascarado()`
    -ver `application/orquestador.py::_registrar`-. Si el campo de
    correlacion fuera sensible, el PAN o el track completo quedarian en
    `motivo_detalle`, en el historial y en pantalla. No se prueba insertando
    un perfil real con esta falla -el perfil generico vigente no la tiene-,
    sino con un perfil de prueba construido a mano que sí la tendria si la
    exclusion no existiera.
    """
    perfil_con_de2_obligatorio = PerfilDeMarca(
        nombre="perfil-de-prueba-solo-para-este-test",
        especificacion=ESPECIFICACION_GENERICA,
        obligatorios_por_mti={
            MTI_COMPRA: OBLIGATORIOS_0100,
            MTI_RESPUESTA_COMPRA: OBLIGATORIOS_0110 | {"2", "35"},
        },
    )
    correlacion = campos_de_correlacion(perfil_con_de2_obligatorio, MTI_RESPUESTA_COMPRA)
    assert "2" not in correlacion
    assert "35" not in correlacion


async def test_rn3_invalida_persiste_un_motivo_distinto_del_de_timeout_o_rechazo(
    base, datos_compra
):
    """Diagnostico historico: INVALIDA (RN-3, correlacion rota) debe quedar
    con su propio motivo persistido -distinto del de TIMEOUT/RECHAZADA/
    ERROR_CONEXION-, para que el historial pueda diferenciar realmente los
    cuatro tipos de fallo, no solo por el `estado` sino tambien por la causa.
    """

    class TransporteRespuestaNoCorrelacionada:
        """Devuelve una respuesta 0110 real, pero con el STAN (campo 11)
        cambiado -misma tecnica que ya usa
        `test_rn3_alterar_cualquier_campo_de_correlacion_invalida_la_respuesta`,
        aqui contra el orquestador completo en vez de la funcion pura."""

        async def enviar(self, payload, destino, tiempo_limite=None):
            solicitud = CODEC.decodificar(payload, PERFIL_GENERICO).como_mensaje()
            respuesta = _respuesta_correlacionada(solicitud, "00")
            alterada = MensajeIso(
                mti=respuesta.mti,
                campos={**dict(respuesta.campos), "11": "999999"},
            )
            return CODEC.codificar(alterada, PERFIL_GENERICO)

    orquestador = construir_orquestador(base, TransporteRespuestaNoCorrelacionada())
    resultado = await orquestador.ejecutar_compra(datos_compra)

    assert resultado.estado is EstadoEjecucion.INVALIDA
    guardada = (await RepositorioEjecucionesSQLite(base).listar())[0]
    assert guardada.motivo_detalle is not None
    assert "11" in guardada.motivo_detalle
    assert "no corresponde a la solicitud" in guardada.motivo_detalle


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
    # Mejora posterior: la causa concreta tambien queda persistida (antes solo
    # se mostraba en la pantalla de resultado inmediato, nunca se guardaba).
    assert guardadas[0].motivo_detalle is not None
    assert "14" in guardadas[0].motivo_detalle
    assert "Traceback" not in guardadas[0].motivo_detalle


async def test_motivo_detalle_de_un_error_de_codec_es_texto_propio_no_de_la_libreria(
    base, datos_compra
):
    """Un campo manual que no cabe en el ancho fijo que exige el perfil hace
    fallar la codificacion (pyiso8583.EncodeError).

    `CodecIso8583.codificar` NO debe persistir `str(error)`/`error.msg` -el
    texto libre que redacta pyiso8583-: eso es un contrato de una dependencia
    externa que este proyecto no controla ni puede auditar hacia adelante
    (una version futura podria describir el fallo citando el propio valor
    del campo). El motivo persistido debe ser texto REDACTADO POR ESTE
    PROYECTO, usando solo `error.field` (el numero de campo, un dato
    estructural) -nunca el mensaje de la libreria, sea cual sea su forma en
    la version instalada.
    """
    orquestador = construir_orquestador(base, TransporteFalso())
    # DE37 (numero de referencia de recuperacion) exige 12 caracteres exactos
    # en el perfil generico; 3 es deliberadamente invalido.
    resultado = await orquestador.ejecutar_compra(
        replace(datos_compra, campos_manuales={"37": "ABC"})
    )

    assert resultado.estado is EstadoEjecucion.NO_ENVIADA
    guardada = (await RepositorioEjecucionesSQLite(base).listar())[0]
    assert guardada.motivo_detalle is not None
    assert guardada.motivo_detalle == (
        "no se pudo codificar el campo 37 para el MTI 0100 con el perfil 'generico'"
    ), "debe ser EXACTAMENTE el texto propio, no el de pyiso8583"
    assert "ABC" not in guardada.motivo_detalle, "el valor rechazado no debe quedar en el motivo"
    assert "Traceback" not in guardada.motivo_detalle
    # Ninguna palabra de la redaccion de la libreria para este caso concreto
    # (verificado leyendo su fuente instalada: "Field data is N bytes,
    # expecting M") debe sobrevivir al mensaje persistido.
    assert "expecting" not in guardada.motivo_detalle
    assert "bytes" not in guardada.motivo_detalle


async def test_motivo_detalle_de_un_fallo_de_conexion_es_el_texto_de_socket_no_una_traza(
    base, datos_compra
):
    """`FalloDeConexion.detalle` (host/puerto y el error de red) es lo que
    debe quedar persistido para ERROR_CONEXION -nunca una excepcion cruda de
    asyncio, que el transporte real ya convierte en este resultado antes de
    que llegue al orquestador (ver `domain.puertos.Transporte`)."""

    class TransporteQueRechaza:
        async def enviar(self, payload, destino, tiempo_limite=None):
            from sibutestlab8583.domain.modelos import FalloDeConexion

            return FalloDeConexion(
                f"no se pudo establecer la conexión con {destino}: conexión rechazada"
            )

    orquestador = construir_orquestador(base, TransporteQueRechaza())
    resultado = await orquestador.ejecutar_compra(datos_compra)

    assert resultado.estado is EstadoEjecucion.ERROR_CONEXION
    guardada = (await RepositorioEjecucionesSQLite(base).listar())[0]
    assert guardada.motivo_detalle == (
        f"no se pudo establecer la conexión con {orquestador._destino}: conexión rechazada"
    )
    assert "Traceback" not in guardada.motivo_detalle
    assert "Exception" not in guardada.motivo_detalle


async def test_una_aprobada_no_persiste_ningun_motivo(base, datos_compra):
    """APROBADA no tiene nada que explicar: `motivo_detalle` debe quedar
    `None`, nunca una cadena vacia -distincion ya establecida en
    `presentacion.motivo_de` y en el esquema-.
    """
    orquestador = construir_orquestador(base, TransporteFalso(codigo="00"))
    resultado = await orquestador.ejecutar_compra(datos_compra)

    assert resultado.estado is EstadoEjecucion.APROBADA
    guardada = (await RepositorioEjecucionesSQLite(base).listar())[0]
    assert guardada.motivo_detalle is None


# --------------------------------------------------- CodecIso8583.bitmap_hex --
#
# Bloque 6 (Isoscopio 2.0): el bitmap solo depende de que campos estan
# presentes, nunca de sus valores -por eso es seguro calcularlo sobre un
# mensaje ya enmascarado, y por eso dos mensajes con los mismos campos activos
# pero valores distintos dan el mismo bitmap-.


def test_bitmap_hex_es_estable_entre_dos_mensajes_con_los_mismos_campos():
    solicitud_a = _solicitud_valida().enmascarado()
    solicitud_b = replace(solicitud_a, campos={**solicitud_a.campos, "37": "REF-DISTINTA"})
    assert "37" not in solicitud_a.campos  # confirma que agregar 37 cambia el conjunto de campos
    bitmap_sin_37 = CODEC.bitmap_hex(solicitud_a, PERFIL_GENERICO)
    bitmap_con_37 = CODEC.bitmap_hex(solicitud_b, PERFIL_GENERICO)
    assert bitmap_sin_37 != bitmap_con_37, "un campo activo distinto debe cambiar el bitmap"
    # Pero el MISMO conjunto de campos, con OTRO valor, da el MISMO bitmap.
    solicitud_c = replace(solicitud_a, campos={**solicitud_a.campos, "4": monto_iso("99999")})
    assert CODEC.bitmap_hex(solicitud_c, PERFIL_GENERICO) == bitmap_sin_37


def test_bitmap_hex_es_mayuscula_hexadecimal():
    bitmap = CODEC.bitmap_hex(_solicitud_valida().enmascarado(), PERFIL_GENERICO)
    assert bitmap == bitmap.upper()
    assert all(c in "0123456789ABCDEF" for c in bitmap)


def test_bitmap_hex_de_un_campo_que_el_perfil_no_conoce_da_error_controlado():
    """Simula el drift que `web.app._bitmap_de_persistido` debe blindar: un
    mensaje historico con un campo que el perfil VIGENTE ya no declara.
    """
    from sibutestlab8583.domain.errores import ErrorDeCodificacion

    mensaje = MensajeIso(mti=MTI_COMPRA, campos={"63": "dato-que-ya-no-existe"})
    with pytest.raises(ErrorDeCodificacion):
        CODEC.bitmap_hex(mensaje, PERFIL_GENERICO)


# ----------------------------------------- CodecIso8583.raw_hex_seguro (B10) --
#
# Estrategia de sanitizacion de este proyecto: `raw_hex_seguro` NUNCA recibe
# el mensaje real -solo se llama sobre la version ya `enmascarado()`-, asi
# que el HEX resultante nunca puede contener un PAN/Track completo: no se
# redacta un dump que los tuviera, se construye uno que nunca los tuvo.


def test_raw_hex_seguro_devuelve_hex_y_longitud_coherentes():
    solicitud = _solicitud_valida().enmascarado()
    hexadecimal, longitud = CODEC.raw_hex_seguro(solicitud, PERFIL_GENERICO)
    assert hexadecimal == hexadecimal.upper()
    assert all(c in "0123456789ABCDEF" for c in hexadecimal)
    assert len(hexadecimal) == longitud * 2  # dos caracteres hex por byte


async def test_raw_hex_seguro_de_un_mensaje_enmascarado_nunca_contiene_el_pan_real(base, datos_compra):
    """Prueba de seguridad de punta a punta: ejecuta una compra REAL (con el
    PAN real de `CARD_ID_DEMO` seedeado en la base), toma `resultado.solicitud`
    -que el orquestador ya devuelve enmascarado, ver `Orquestador._registrar`-,
    calcula su RAW/HEX, lo decodifica de vuelta a texto, y confirma que el PAN
    real no aparece por ningun lado, mientras que la version enmascarada si.
    """
    resultado = await construir_orquestador(base, TransporteFalso(codigo="00")).ejecutar_compra(
        datos_compra
    )
    hexadecimal, _ = CODEC.raw_hex_seguro(resultado.solicitud, PERFIL_GENERICO)
    decodificado = bytes.fromhex(hexadecimal).decode("ascii", errors="replace")
    assert PAN_DEMO not in decodificado
    assert "************6666" in decodificado


def test_bitmap_hex_es_seguro_por_construccion_ante_un_mensaje_sin_enmascarar():
    """No basta con que cada llamador RECUERDE enmascarar antes de llamar:
    `bitmap_hex`/`raw_hex_seguro` deben rechazar por si mismos un mensaje con
    el PAN todavia en claro, sin importar quien llama ni si se equivoco.
    """
    from sibutestlab8583.adapters.iso8583.codec import MensajeSinEnmascararError

    solicitud_real = _solicitud_valida()  # PAN real, sin `.enmascarado()`
    with pytest.raises(MensajeSinEnmascararError):
        CODEC.bitmap_hex(solicitud_real, PERFIL_GENERICO)


def test_raw_hex_seguro_es_seguro_por_construccion_ante_un_mensaje_sin_enmascarar():
    from sibutestlab8583.adapters.iso8583.codec import MensajeSinEnmascararError

    solicitud_real = _solicitud_valida()
    with pytest.raises(MensajeSinEnmascararError):
        CODEC.raw_hex_seguro(solicitud_real, PERFIL_GENERICO)


def test_raw_hex_seguro_de_un_campo_que_el_perfil_no_conoce_da_error_controlado():
    from sibutestlab8583.domain.errores import ErrorDeCodificacion

    mensaje = MensajeIso(mti=MTI_COMPRA, campos={"63": "dato-que-ya-no-existe"})
    with pytest.raises(ErrorDeCodificacion):
        CODEC.raw_hex_seguro(mensaje, PERFIL_GENERICO)

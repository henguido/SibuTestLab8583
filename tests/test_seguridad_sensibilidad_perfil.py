"""B3: ARCH-001/SEC-001 -sensibilidad con una autoridad declarativa clara.

`CAMPOS_SENSIBLES` (domain/modelos.py) es el PISO UNIVERSAL: protege DE2
(PAN)/DE35 (Track 2)/DE45 (Track 1) para cualquier perfil, incluso los
metodos que no reciben un perfil (`MensajeIso.enmascarado()`). Un perfil
puede declarar sensibilidad ADICIONAL propia (`PerfilDeMarca.campos_sensibles`
/`es_sensible()`), consultada por los tres guardias que SI reciben un perfil
real: `domain.expectativas.campos_permitidos_expectativa`,
`domain.validacion.campos_de_correlacion`,
`adapters.iso8583.codec._verificar_enmascarado_para_inspeccion` (via
`bitmap_hex`/`raw_hex_seguro`).

Cubre especificamente el pedido de B3: que DE35/DE45 sigan protegidos aunque
hoy no se transmitan en ningun mensaje real (no estan en
`ESPECIFICACION_GENERICA`), y que `raw_hex_seguro`/`bitmap_hex` sigan seguros
por construccion despues de la migracion.
"""

from __future__ import annotations

from sibutestlab8583.adapters.iso8583.codec import CodecIso8583, MensajeSinEnmascararError
from sibutestlab8583.domain.datos_sinteticos import monto_iso, pan_sintetico
from sibutestlab8583.domain.modelos import CAMPOS_SENSIBLES, MensajeIso
from sibutestlab8583.profiles.generico import PERFIL_GENERICO

CODEC = CodecIso8583()


# --------------------------------------------------- piso universal de dominio --


def test_de2_de35_de45_estan_en_el_piso_universal():
    """Punto 19 de B3: aunque hoy solo DE2 se transmite, los tres numeros de
    tarjeta deben seguir protegidos -DE35/45 por si un dia se agregan a un
    perfil, sin que nadie tenga que acordarse de ampliar la lista."""
    assert "2" in CAMPOS_SENSIBLES, "DE2 (PAN)"
    assert "35" in CAMPOS_SENSIBLES, "DE35 (Track 2)"
    assert "45" in CAMPOS_SENSIBLES, "DE45 (Track 1)"


def test_perfil_es_sensible_protege_el_piso_universal_aunque_el_perfil_no_lo_declare():
    """PERFIL_GENERICO.campos_sensibles no necesita mencionar DE35/45 -no son
    campos suyos-, pero `es_sensible()` los sigue reconociendo via el piso."""
    assert PERFIL_GENERICO.es_sensible("2")
    assert PERFIL_GENERICO.es_sensible("35")
    assert PERFIL_GENERICO.es_sensible("45")


def test_perfil_no_marca_sensible_un_campo_de_negocio_cualquiera():
    assert not PERFIL_GENERICO.es_sensible("70")  # DE70, gestion de red (B2)
    assert not PERFIL_GENERICO.es_sensible("41")  # terminal


# ----------------------------------------- autoridad declarativa (METADATOS) --


def test_metadatos_sensibles_y_camposensibles_no_pueden_divergir():
    """Ya existente desde B2 (test_perfil_generico.py), reafirmado aqui: todo
    campo que METADATOS_SENSIBLES declara sensible=True debe reflejarse en el
    piso universal o en perfil.campos_sensibles."""
    from sibutestlab8583.profiles.generico import METADATOS_SENSIBLES

    for numero, metadato in METADATOS_SENSIBLES.items():
        assert metadato.sensible is True
        assert PERFIL_GENERICO.es_sensible(numero)


# ------------------------------------------------- guardias que SI usan perfil --


def test_campos_permitidos_expectativa_excluye_por_perfil_es_sensible():
    from sibutestlab8583.domain.expectativas import campos_permitidos_expectativa
    from sibutestlab8583.domain.modelos import MTI_RESPUESTA_COMPRA

    permitidos = campos_permitidos_expectativa(PERFIL_GENERICO, MTI_RESPUESTA_COMPRA)
    assert "2" not in permitidos
    assert "35" not in permitidos
    assert "45" not in permitidos


def test_campos_de_correlacion_excluye_por_perfil_es_sensible():
    from sibutestlab8583.domain.validacion import campos_de_correlacion
    from sibutestlab8583.domain.modelos import MTI_RESPUESTA_COMPRA

    correlacion = campos_de_correlacion(PERFIL_GENERICO, MTI_RESPUESTA_COMPRA)
    assert "2" not in correlacion
    assert "35" not in correlacion
    assert "45" not in correlacion


# ------------------------------------------------- RAW/HEX/bitmap siguen seguros --


def test_bitmap_hex_revienta_con_de2_real_sin_enmascarar():
    mensaje = MensajeIso(mti="0100", campos={"2": pan_sintetico("6666"), "3": "000000"})
    try:
        CODEC.bitmap_hex(mensaje, PERFIL_GENERICO)
        assert False, "debio reventar: DE2 real sin enmascarar"
    except MensajeSinEnmascararError:
        pass


def test_raw_hex_seguro_revienta_con_de2_real_sin_enmascarar():
    mensaje = MensajeIso(mti="0100", campos={"2": pan_sintetico("6666"), "3": "000000"})
    try:
        CODEC.raw_hex_seguro(mensaje, PERFIL_GENERICO)
        assert False, "debio reventar: DE2 real sin enmascarar"
    except MensajeSinEnmascararError:
        pass


def test_el_guardia_detecta_un_de35_sintetico_sin_enmascarar():
    """DE35 (Track 2) no esta en ESPECIFICACION_GENERICA -no se transmite
    todavia-, pero el GUARDIA en si (la funcion que decide "esto parece un
    numero real") debe seguir reconociendolo como sensible, con datos
    sinteticos generados en ejecucion, nunca un literal de Track real."""
    from sibutestlab8583.adapters.iso8583.codec import _verificar_enmascarado_para_inspeccion

    track2_sintetico = f"{pan_sintetico('6666')}=" + "3012" + "1015400001"
    mensaje = MensajeIso(mti="0100", campos={"35": track2_sintetico})
    try:
        _verificar_enmascarado_para_inspeccion(mensaje, PERFIL_GENERICO)
        assert False, "debio reventar: DE35 sintetico sin enmascarar, con forma de numero real"
    except MensajeSinEnmascararError:
        pass


def test_el_guardia_detecta_un_de45_sintetico_sin_enmascarar():
    """DE45 (Track 1) tampoco esta en ESPECIFICACION_GENERICA todavia -mismo
    caso que DE35-: el guardia debe protegerlo igual, con datos sinteticos."""
    from sibutestlab8583.adapters.iso8583.codec import _verificar_enmascarado_para_inspeccion

    track1_sintetico = f"B{pan_sintetico('6666')}^APELLIDO/NOMBRE^" + "3012" + "1015400001"
    mensaje = MensajeIso(mti="0100", campos={"45": track1_sintetico})
    try:
        _verificar_enmascarado_para_inspeccion(mensaje, PERFIL_GENERICO)
        assert False, "debio reventar: DE45 sintetico sin enmascarar, con forma de numero real"
    except MensajeSinEnmascararError:
        pass


def test_el_guardia_no_revienta_con_de35_45_ya_enmascarados():
    """Un valor que empieza con el caracter de mascara (no `.isdigit()`) no
    debe disparar el guardia -mismo criterio que ya vale para DE2-."""
    from sibutestlab8583.adapters.iso8583.codec import _verificar_enmascarado_para_inspeccion

    mensaje = MensajeIso(mti="0100", campos={"35": "************6666", "45": "************6666"})
    _verificar_enmascarado_para_inspeccion(mensaje, PERFIL_GENERICO)  # no debe reventar


def test_bitmap_y_raw_hex_siguen_funcionando_normalmente_para_un_mensaje_valido():
    """Confirma que la migracion de sensibilidad no rompio el camino feliz:
    un mensaje real, ya enmascarado, sigue calculando bitmap/RAW sin problema."""
    mensaje = MensajeIso(
        mti="0100",
        campos={"2": "************6666", "3": "000000", "4": monto_iso("1000"), "11": "000001"},
    )
    bitmap = CODEC.bitmap_hex(mensaje, PERFIL_GENERICO)
    assert bitmap == bitmap.upper()
    raw, longitud = CODEC.raw_hex_seguro(mensaje, PERFIL_GENERICO)
    assert longitud > 0

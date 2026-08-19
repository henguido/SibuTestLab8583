"""El catalogo generico contiene exactamente lo aprobado, y solo 00 aprueba."""

from __future__ import annotations

from sibutestlab8583.domain.catalogo import CATALOGO_GENERICO

CODIGOS_APROBADOS_EN_PROYECTO = {"00", "05", "14", "51", "54", "94"}


def test_contiene_exactamente_los_seis_codigos_acordados():
    assert set(CATALOGO_GENERICO.codigos) == CODIGOS_APROBADOS_EN_PROYECTO


def test_solo_el_codigo_00_cuenta_como_aprobacion():
    """Estar en el catalogo no es estar aprobado: los otros cinco son rechazos."""
    aprobados = {c for c in CATALOGO_GENERICO.codigos if CATALOGO_GENERICO.es_aprobado(c)}
    assert aprobados == {"00"}


def test_un_codigo_desconocido_nunca_se_aprueba():
    assert not CATALOGO_GENERICO.conoce("91")
    assert not CATALOGO_GENERICO.es_aprobado("91")
    assert not CATALOGO_GENERICO.es_aprobado("")


def test_cada_codigo_tiene_descripcion():
    for codigo in CATALOGO_GENERICO.codigos:
        assert CATALOGO_GENERICO.descripcion(codigo).strip()


def test_el_catalogo_es_independiente_del_perfil():
    """CatalogoDeRespuestas no debe conocer formato ni campos ISO."""
    import sibutestlab8583.domain.catalogo as modulo

    fuente = modulo.__doc__ or ""
    assert "independiente" in fuente.lower()
    assert not hasattr(CATALOGO_GENERICO, "especificacion")
    assert not hasattr(CATALOGO_GENERICO, "obligatorios")

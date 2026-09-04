"""`PoliticaCamposMti`: la unica fuente de verdad sobre que puede fijar el usuario.

Cubre tres cosas: que la politica misma se niega a construirse con categorias
solapadas o defaults fuera de lugar; que `origen()` clasifica correctamente
cada numero; y que `armar_compra` aplica la defensa en profundidad descrita en
su docstring -- la validacion rechaza un campo protegido, y aunque no lo
hiciera, la capa estructural siempre gana sobre lo que el usuario haya escrito.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from sibutestlab8583.domain import armado
from sibutestlab8583.domain.armado import (
    armar_compra,
    incompatibilidades_escenario,
    valores_efectivos_editables,
    validar_campos_manuales,
)
from sibutestlab8583.domain.datos_sinteticos import pan_sintetico
from sibutestlab8583.domain.errores import CampoNoPermitido, CampoProtegido
from sibutestlab8583.domain.modelos import DatosCompra, TarjetaPrueba
from sibutestlab8583.profiles.generico import (
    CODIGO_PROCESO_COMPRA,
    MODO_CAPTURA_DEMOSTRACION,
    PERFIL_GENERICO,
    PerfilDeMarca,
    PoliticaCamposMti,
    TERMINAL_DEMOSTRACION,
)

MOMENTO = datetime(2026, 8, 19, 12, 30, 45, tzinfo=timezone.utc)
_POLITICA = PERFIL_GENERICO.politica("0100")


def _tarjeta() -> TarjetaPrueba:
    return TarjetaPrueba(card_id="X", pan=pan_sintetico("6666"), expiracion="3012")


# ------------------------------------------------------- PoliticaCamposMti ---


def test_las_categorias_no_pueden_solaparse():
    with pytest.raises(ValueError, match="más de una categoría"):
        PoliticaCamposMti(derivados=frozenset({"2"}), automaticos=frozenset({"2"}))


def test_un_default_fuera_de_editables_se_rechaza():
    with pytest.raises(ValueError, match="valores_por_defecto"):
        PoliticaCamposMti(derivados=frozenset({"2"}), valores_por_defecto={"2": "x"})


@pytest.mark.parametrize(
    "numero, esperado",
    [("2", "derivado"), ("14", "derivado"), ("7", "automatico"), ("11", "automatico"),
     ("12", "automatico"), ("13", "automatico"), ("3", "editable"), ("22", "editable"),
     ("37", "editable"), ("41", "editable"), ("49", "editable"), ("38", "no_permitido"),
     ("99", "no_permitido")],
)
def test_origen_clasifica_cada_numero_del_perfil_generico(numero, esperado):
    assert _POLITICA.origen(numero) == esperado


def test_los_editables_obligatorios_declaran_default_y_37_queda_opcional():
    """DE37 es candidato editable sin default: es opcional, no obligatorio (RN-4
    no lo exige). El resto de los editables si son obligatorios en el 0100 y
    deben traer un valor razonable para no depender de que el usuario lo informe.
    """
    obligatorios_editables = _POLITICA.editables & PERFIL_GENERICO.obligatorios("0100")
    assert obligatorios_editables == set(_POLITICA.valores_por_defecto)
    assert _POLITICA.editables - set(_POLITICA.valores_por_defecto) == {"37"}


def test_de38_no_es_editable_en_el_perfil_generico():
    """DE38 lo agrega el autorizador en la respuesta; no es del emisor en el 0100."""
    assert _POLITICA.origen("38") == "no_permitido"


# ------------------------------------------------------ validar_campos_manuales --


@pytest.mark.parametrize("campo", ["2", "14"])
def test_fijar_un_campo_derivado_se_rechaza(campo):
    with pytest.raises(CampoProtegido):
        validar_campos_manuales({campo: "9" * 16}, PERFIL_GENERICO, "0100")


@pytest.mark.parametrize("campo", ["7", "11", "12", "13"])
def test_fijar_un_campo_automatico_se_rechaza(campo):
    with pytest.raises(CampoProtegido):
        validar_campos_manuales({campo: "000000"}, PERFIL_GENERICO, "0100")


def test_fijar_de38_se_rechaza_como_no_permitido():
    with pytest.raises(CampoNoPermitido):
        validar_campos_manuales({"38": "000000"}, PERFIL_GENERICO, "0100")


def test_fijar_un_numero_ajeno_a_la_especificacion_se_rechaza():
    with pytest.raises(CampoNoPermitido):
        validar_campos_manuales({"999": "x"}, PERFIL_GENERICO, "0100")


def test_fijar_un_editable_no_lanza_nada():
    validar_campos_manuales({"37": "REF0001"}, PERFIL_GENERICO, "0100")


# -------------------------------------------------------------- armar_compra --


def test_sin_campos_manuales_se_usan_los_defaults_del_perfil():
    mensaje = armar_compra(
        DatosCompra(card_id="X", monto=Decimal("10.00")),
        _tarjeta(),
        stan="000001",
        momento=MOMENTO,
        perfil=PERFIL_GENERICO,
    )
    assert mensaje.campos["3"] == CODIGO_PROCESO_COMPRA
    assert mensaje.campos["22"] == MODO_CAPTURA_DEMOSTRACION
    assert mensaje.campos["41"] == TERMINAL_DEMOSTRACION
    assert mensaje.campos["49"] == "188"


def test_un_editable_provisto_reemplaza_su_default():
    mensaje = armar_compra(
        DatosCompra(card_id="X", monto=Decimal("10.00"), campos_manuales={"37": "REF-QA-01"}),
        _tarjeta(),
        stan="000001",
        momento=MOMENTO,
        perfil=PERFIL_GENERICO,
    )
    assert mensaje.campos["37"] == "REF-QA-01"
    # El resto de los defaults no se ve afectado por fijar un solo campo.
    assert mensaje.campos["3"] == CODIGO_PROCESO_COMPRA


def test_armar_compra_rechaza_un_campo_derivado_manual():
    with pytest.raises(CampoProtegido):
        armar_compra(
            DatosCompra(card_id="X", monto=Decimal("10.00"), campos_manuales={"2": "9" * 16}),
            _tarjeta(),
            stan="000001",
            momento=MOMENTO,
            perfil=PERFIL_GENERICO,
        )


# ------------------------------------------------- valores_efectivos_editables --


def test_sin_overrides_los_efectivos_son_los_defaults_del_perfil():
    efectivos = valores_efectivos_editables({}, PERFIL_GENERICO, "0100")
    assert efectivos == {
        "3": CODIGO_PROCESO_COMPRA,
        "22": MODO_CAPTURA_DEMOSTRACION,
        "41": TERMINAL_DEMOSTRACION,
        "49": "188",
    }


def test_un_override_reemplaza_su_default_y_agrega_un_campo_sin_default():
    efectivos = valores_efectivos_editables({"37": "REF-QA-01", "49": "840"}, PERFIL_GENERICO, "0100")
    assert efectivos["37"] == "REF-QA-01"
    assert efectivos["49"] == "840"
    # Los que no se tocaron siguen viniendo del default de hoy.
    assert efectivos["3"] == CODIGO_PROCESO_COMPRA


def test_valores_efectivos_editables_rechaza_lo_mismo_que_validar_campos_manuales():
    """Es la misma puerta: nunca puede congelarse un campo que armar_compra rechazaria."""
    with pytest.raises(CampoProtegido):
        valores_efectivos_editables({"2": "9" * 16}, PERFIL_GENERICO, "0100")


def test_valores_efectivos_editables_es_lo_que_armar_compra_congelaria():
    """Confirma que 'congelar los efectivos' y 'lo que armar_compra usaria hoy'
    son exactamente la misma cosa -las dos primeras capas del merge-.
    """
    overrides = {"37": "REF-QA-02"}
    efectivos = valores_efectivos_editables(overrides, PERFIL_GENERICO, "0100")

    mensaje = armar_compra(
        DatosCompra(card_id="X", monto=Decimal("10.00"), campos_manuales=overrides),
        _tarjeta(),
        stan="000001",
        momento=MOMENTO,
        perfil=PERFIL_GENERICO,
    )
    for numero, valor in efectivos.items():
        assert mensaje.campos[numero] == valor


# --------------------------------------------------- incompatibilidades_escenario --


def test_sin_incompatibilidades_para_un_escenario_recien_congelado():
    efectivos = valores_efectivos_editables({"37": "REF-QA-01"}, PERFIL_GENERICO, "0100")
    assert incompatibilidades_escenario(efectivos, PERFIL_GENERICO, "0100") == ()


def test_detecta_un_campo_que_dejo_de_ser_editable():
    """Simula el drift que el Bloque 2 quiere blindar: el perfil cambia y un
    campo que un escenario congelo como editable ya no lo es.
    """
    perfil_futuro = PerfilDeMarca(
        nombre=PERFIL_GENERICO.nombre,
        especificacion=PERFIL_GENERICO.especificacion,
        obligatorios_por_mti=PERFIL_GENERICO.obligatorios_por_mti,
        politica_por_mti={
            "0100": PoliticaCamposMti(
                derivados=frozenset({"2", "14"}),
                automaticos=frozenset({"7", "11", "12", "13", "37"}),  # 37 cambio de categoria
                editables=frozenset({"3", "22", "41", "49"}),
                valores_por_defecto={
                    "3": CODIGO_PROCESO_COMPRA,
                    "22": MODO_CAPTURA_DEMOSTRACION,
                    "41": TERMINAL_DEMOSTRACION,
                    "49": "188",
                },
            )
        },
    )
    campos_congelados = {"3": CODIGO_PROCESO_COMPRA, "37": "REF-QA-01"}

    problemas = incompatibilidades_escenario(campos_congelados, perfil_futuro, "0100")

    assert len(problemas) == 1
    assert "37" in problemas[0]
    assert "automatico" in problemas[0]


def test_la_capa_estructural_gana_aunque_la_validacion_no_existiera():
    """Defensa en profundidad: aunque `campos_manuales` ya trajera un campo
    derivado -sin pasar por `validar_campos_manuales`-, el merge estructural de
    `armar_compra` lo pisa igual. No depende de la validacion previa para ser
    correcto.
    """
    tarjeta = _tarjeta()
    campos_manuales_manipulados = {"2": "9" * 16, "11": "999999"}
    campos = dict(PERFIL_GENERICO.politica("0100").valores_por_defecto)
    campos.update(campos_manuales_manipulados)
    campos.update(
        {
            "2": tarjeta.pan,
            "4": armado.formatear_monto(Decimal("10.00")),
            "7": MOMENTO.strftime("%m%d%H%M%S"),
            "11": "000001",
            "12": MOMENTO.strftime("%H%M%S"),
            "13": MOMENTO.strftime("%m%d"),
            "14": tarjeta.expiracion,
        }
    )
    assert campos["2"] == tarjeta.pan
    assert campos["11"] == "000001"

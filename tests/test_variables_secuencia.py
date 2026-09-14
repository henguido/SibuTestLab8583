"""`application.variables_secuencia`: referencias entre pasos (Fase C2).

Pruebas puras de gramatica (sin red, sin base de datos) mas los casos
adversariales explicitamente pedidos por el checkpoint (punto 22): campos
sensibles rechazados, paso inexistente, forma invalida.
"""

from __future__ import annotations

from sibutestlab8583.application.variables_secuencia import (
    es_referencia_de_paso,
    parece_referencia_de_paso_malformada,
    paso_id_referenciado,
)


def test_reconoce_una_referencia_de_campo_valida():
    assert es_referencia_de_paso("{{step.purchase.response.de38}}")
    assert es_referencia_de_paso("{{step.purchase.request.de37}}")


def test_reconoce_una_referencia_de_metadata_valida():
    assert es_referencia_de_paso("{{step.purchase.execution_id}}")


def test_no_reconoce_un_literal_comun():
    assert not es_referencia_de_paso("000000")
    assert not es_referencia_de_paso("{{stan}}")  # sigue siendo Fase A, no C2
    assert not es_referencia_de_paso("{{amount}}")


def test_no_reconoce_texto_que_no_menciona_step():
    assert not parece_referencia_de_paso_malformada("{{stan}}")
    assert not parece_referencia_de_paso_malformada("un texto cualquiera")


def test_detecta_forma_invalida_de_una_referencia_de_paso():
    # Namespace desconocido (ni request ni response).
    assert parece_referencia_de_paso_malformada("{{step.purchase.metadata.de38}}")
    # Sin numero de campo.
    assert parece_referencia_de_paso_malformada("{{step.purchase.response}}")
    # Mezclada con texto literal -mismo criterio que Fase A: todo el campo
    # es una expresion o no lo es-.
    assert parece_referencia_de_paso_malformada("ABC{{step.purchase.response.de38}}")
    assert parece_referencia_de_paso_malformada("{{step.purchase.response.de38}}XYZ")


def test_paso_id_referenciado_extrae_el_id_de_ambas_formas():
    assert paso_id_referenciado("{{step.purchase.response.de38}}") == "purchase"
    assert paso_id_referenciado("{{step.purchase.execution_id}}") == "purchase"
    assert paso_id_referenciado("000000") is None
    assert paso_id_referenciado("{{stan}}") is None

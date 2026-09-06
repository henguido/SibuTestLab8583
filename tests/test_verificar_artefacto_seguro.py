"""`scripts/verificar_artefacto_seguro.py`: guardia CI especifica sobre el
artefacto `corrida.json` -PAN acotado + claves que nunca deberian aparecer en
un snapshot de corrida.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from sibutestlab8583.domain.datos_sinteticos import pan_sintetico

_RUTA = Path(__file__).resolve().parent.parent / "scripts" / "verificar_artefacto_seguro.py"
_SPEC = importlib.util.spec_from_file_location("verificar_artefacto_seguro", _RUTA)
assert _SPEC is not None and _SPEC.loader is not None
verificar_artefacto_seguro = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(verificar_artefacto_seguro)


def test_un_json_de_corrida_limpio_no_produce_hallazgos():
    contenido = (
        '{"version": 1, "suite_id": "SUI-abc123", "resultado": "pass", '
        '"items": [{"escenario_id": "ESC-1", "resultado": "pass", "detalle": null}]}'
    )
    assert verificar_artefacto_seguro.hallazgos_en(contenido) == []


def test_detecta_una_secuencia_con_largo_de_pan():
    numero_sintetico = pan_sintetico("4321")
    contenido = f'{{"detalle": "numero {numero_sintetico} no coincide"}}'
    hallazgos = verificar_artefacto_seguro.hallazgos_en(contenido)
    assert len(hallazgos) == 1
    assert "dígitos" in hallazgos[0]


def test_no_confunde_un_id_interno_corto_con_un_pan():
    contenido = '{"corrida_id": 42, "orden": 1, "ejecucion_id": 8583}'
    assert verificar_artefacto_seguro.hallazgos_en(contenido) == []


def test_detecta_cada_clave_prohibida():
    for clave in verificar_artefacto_seguro.CLAVES_PROHIBIDAS:
        contenido = f'{{"{clave}": "algo"}}'
        hallazgos = verificar_artefacto_seguro.hallazgos_en(contenido)
        assert hallazgos, f"debio detectar la clave prohibida {clave!r}"


def test_la_deteccion_de_claves_prohibidas_no_distingue_mayusculas():
    contenido = '{"SOLICITUD_ENMASCARADA": "0100..."}'
    assert verificar_artefacto_seguro.hallazgos_en(contenido)


def test_main_devuelve_0_para_un_archivo_limpio(tmp_path):
    archivo = tmp_path / "corrida.json"
    archivo.write_text('{"resultado": "pass"}', encoding="utf-8")
    assert verificar_artefacto_seguro.main([str(archivo)]) == 0


def test_main_devuelve_1_y_mensaje_claro_para_un_archivo_sucio(tmp_path, capsys):
    archivo = tmp_path / "corrida.json"
    archivo.write_text('{"track2": "algo"}', encoding="utf-8")
    codigo = verificar_artefacto_seguro.main([str(archivo)])
    assert codigo == 1
    salida = capsys.readouterr()
    assert "no es seguro para publicar" in salida.err
    assert "track2" in salida.err


def test_main_devuelve_2_si_el_archivo_no_existe(tmp_path):
    codigo = verificar_artefacto_seguro.main([str(tmp_path / "no-existe.json")])
    assert codigo == 2

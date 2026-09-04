"""Persistencia estructurada: esquema, migracion y recorrido real.

Aqui se prueba contra SQLite de verdad, no contra dobles. Cubre las tres cosas
que pueden salir mal en una base: que la columna no exista, que una base
anterior se quede sin ella, y que `inicializar()` no sea idempotente.

Las pruebas puras del formato viven en `test_serializacion.py`.
"""

from __future__ import annotations

import json
import sqlite3
from decimal import Decimal

import pytest

from conftest import TransporteFalso, construir_orquestador
from sibutestlab8583.adapters.persistence.esquema import (
    CARD_ID_DEMO,
    COLUMNAS_AGREGADAS,
    DDL,
    PAN_DEMO,
    inicializar,
)
from sibutestlab8583.adapters.persistence.sqlite_repos import RepositorioEjecucionesSQLite
from sibutestlab8583.application import serializacion as sz
from sibutestlab8583.domain.modelos import DatosCompra, EstadoEjecucion
from sibutestlab8583.profiles.generico import NOMBRE_PERFIL_GENERICO

NOMBRES_NUEVOS = [nombre for nombre, _ in COLUMNAS_AGREGADAS]


def _columnas(ruta, tabla="ejecuciones") -> set[str]:
    with sqlite3.connect(ruta) as conexion:
        return {fila[1] for fila in conexion.execute(f"PRAGMA table_info({tabla})")}


def _filas(ruta) -> list[sqlite3.Row]:
    with sqlite3.connect(ruta) as conexion:
        conexion.row_factory = sqlite3.Row
        return conexion.execute("SELECT * FROM ejecuciones ORDER BY id").fetchall()


async def _compra(base, *, codigo="00", monto="150.00", manuales=None):
    transporte = TransporteFalso(codigo=codigo)
    datos = DatosCompra(card_id=CARD_ID_DEMO, monto=Decimal(monto))
    return await construir_orquestador(base, transporte).ejecutar_compra(datos)


# ------------------------------------------------------------- 1. ESQUEMA ----


async def test_una_base_nueva_trae_las_columnas_json(base):
    assert set(NOMBRES_NUEVOS) <= _columnas(base)


async def test_la_base_nueva_no_necesito_migracion(tmp_path):
    """En una base nueva el DDL ya las crea: la migracion no hace nada."""
    import aiosqlite

    from sibutestlab8583.adapters.persistence.esquema import _migrar_ejecuciones

    ruta = await inicializar(tmp_path / "nueva.db")
    async with aiosqlite.connect(ruta) as conexion:
        agregadas = await _migrar_ejecuciones(conexion)
    assert agregadas == (), "no debia agregar nada"


# ----------------------------------------------------------- 2. MIGRACION ----


def _crear_base_anterior(ruta) -> None:
    """Reproduce el esquema tal como era ANTES de las columnas JSON."""
    anterior = DDL
    for nombre, tipo in COLUMNAS_AGREGADAS:
        anterior = anterior.replace(f"    {nombre}          {tipo},\n", "")
    assert all(n not in anterior for n in NOMBRES_NUEVOS), "el DDL anterior aun las trae"

    with sqlite3.connect(ruta) as conexion:
        conexion.executescript(anterior)
        conexion.execute(
            "INSERT INTO tarjetas_prueba"
            " (card_id, pan, pan_enmascarado, expiracion, descripcion, sintetica, creada_en)"
            " VALUES ('VIEJA-1', '0', '****', '3012', 'previa', 1, '2026-01-01T00:00:00+00:00')"
        )
        conexion.execute(
            "INSERT INTO ejecuciones"
            " (creada_en, card_id, mti_solicitud, monto, moneda, stan, estado,"
            "  solicitud_enmascarada)"
            " VALUES ('2026-01-01T00:00:00+00:00', 'VIEJA-1', '0100', '99.00', '188',"
            "         '000777', 'aprobada', 'MTI=0100 | 3=000000 | 41=A')"
        )
        conexion.commit()


async def test_una_base_anterior_se_migra_sin_perder_filas(tmp_path):
    ruta = tmp_path / "anterior.db"
    _crear_base_anterior(ruta)

    assert not set(NOMBRES_NUEVOS) & _columnas(ruta), "la base de partida no debe tenerlas"
    antes = _filas(ruta)
    assert len(antes) == 1

    await inicializar(ruta)

    assert set(NOMBRES_NUEVOS) <= _columnas(ruta), "la migracion no agrego las columnas"
    despues = _filas(ruta)
    assert len(despues) == 1, "la fila previa se perdio"
    assert despues[0]["stan"] == "000777"
    assert despues[0]["solicitud_enmascarada"] == "MTI=0100 | 3=000000 | 41=A"
    assert despues[0]["solicitud_json"] is None, "no se inventa JSON para lo historico"
    assert despues[0]["respuesta_json"] is None


async def test_una_fila_historica_se_lee_sin_error_por_el_repositorio(tmp_path):
    """El caso que no debe producir un 500: fila vieja, codigo nuevo."""
    ruta = tmp_path / "anterior.db"
    _crear_base_anterior(ruta)
    await inicializar(ruta)

    ejecuciones = await RepositorioEjecucionesSQLite(ruta).listar()
    assert len(ejecuciones) == 1
    historica = ejecuciones[0]
    assert historica.solicitud_json is None
    assert historica.solicitud_enmascarada is not None

    leido = sz.interpretar(historica.solicitud_json, historica.solicitud_enmascarada)
    assert leido.origen == sz.ORIGEN_TEXTO
    assert not leido.fiel, "una fila anterior no puede declararse fiel"
    assert leido.valor("3") == "000000"


# --------------------------------------------------------- 3. IDEMPOTENCIA ---


async def test_inicializar_tres_veces_no_falla_ni_duplica(tmp_path):
    ruta = tmp_path / "repetida.db"
    for _ in range(3):
        await inicializar(ruta)

    assert set(NOMBRES_NUEVOS) <= _columnas(ruta)
    with sqlite3.connect(ruta) as conexion:
        assert conexion.execute("SELECT COUNT(*) FROM tarjetas_prueba").fetchone()[0] == 1
        assert conexion.execute("SELECT COUNT(*) FROM secuencias").fetchone()[0] == 1


async def test_migrar_una_base_anterior_dos_veces_es_idempotente(tmp_path):
    ruta = tmp_path / "anterior.db"
    _crear_base_anterior(ruta)

    await inicializar(ruta)
    tras_la_primera = _columnas(ruta)
    await inicializar(ruta)

    assert len(_filas(ruta)) == 1, "la fila previa se perdio en la segunda pasada"
    assert _columnas(ruta) == tras_la_primera, "la segunda pasada altero el esquema"
    # `PRAGMA table_info` devuelve una fila por columna: si `ALTER TABLE` se
    # hubiera repetido, SQLite habria fallado, pero se comprueba el recuento.
    with sqlite3.connect(ruta) as conexion:
        nombres = [f[1] for f in conexion.execute("PRAGMA table_info(ejecuciones)")]
    assert nombres.count("solicitud_json") == 1
    assert nombres.count("respuesta_json") == 1


async def test_la_secuencia_del_stan_sobrevive_a_la_migracion(tmp_path):
    """`inicializar()` no debe reiniciar un contador ya avanzado."""
    ruta = tmp_path / "anterior.db"
    _crear_base_anterior(ruta)
    with sqlite3.connect(ruta) as conexion:
        conexion.execute("INSERT INTO secuencias (nombre, valor) VALUES ('stan', 41)")
        conexion.commit()

    await inicializar(ruta)

    with sqlite3.connect(ruta) as conexion:
        valor = conexion.execute(
            "SELECT valor FROM secuencias WHERE nombre = 'stan'"
        ).fetchone()[0]
    assert valor == 41


# ------------------------------------------------- 4 y 5. RECORRIDO REAL -----


async def test_una_compra_persiste_json_valido_en_las_dos_columnas(base):
    await _compra(base)
    fila = _filas(base)[0]

    for columna in NOMBRES_NUEVOS:
        assert fila[columna], f"{columna} quedo vacia"
        datos = json.loads(fila[columna])
        assert datos["version"] == sz.VERSION_FORMATO
        assert datos["perfil"] == NOMBRE_PERFIL_GENERICO


async def test_el_json_recupera_mti_campos_y_valores_enmascarados(base):
    resultado = await _compra(base)
    fila = _filas(base)[0]

    solicitud = sz.desde_json(fila["solicitud_json"])
    assert solicitud.fiel
    assert solicitud.mti == "0100"
    assert solicitud.perfil == NOMBRE_PERFIL_GENERICO

    # Exactamente los mismos numeros y valores que el resultado ya enmascarado.
    esperado = dict(resultado.solicitud.campos)
    assert {c.numero: c.valor for c in solicitud.campos} == esperado
    assert solicitud.valor("2") == "************6666"
    assert solicitud.valor("11") == resultado.ejecucion.stan

    respuesta = sz.desde_json(fila["respuesta_json"])
    assert respuesta.fiel
    assert respuesta.mti == "0110"
    assert respuesta.valor("39") == "00"


async def test_la_respuesta_persiste_el_crudo_por_campo(base):
    """Es lo que el formato de texto descartaba: `como_mensaje()` lo perdia."""
    await _compra(base)
    respuesta = sz.desde_json(_filas(base)[0]["respuesta_json"])

    assert respuesta.campos, "la respuesta no trajo campos"
    con_crudo = [c for c in respuesta.campos if c.crudo]
    assert len(con_crudo) == len(respuesta.campos), "algun campo perdio su crudo"
    assert respuesta.valor("39") == "00"
    assert next(c for c in respuesta.campos if c.numero == "39").crudo == "00"


async def test_la_solicitud_no_finge_tener_crudo(base):
    """El codec no lo entrega: la columna no debe inventarlo."""
    await _compra(base)
    solicitud = sz.desde_json(_filas(base)[0]["solicitud_json"])

    assert solicitud.campos
    assert all(c.crudo is None for c in solicitud.campos)


# ------------------------------------ 6. EL DEFECTO, DE PUNTA A PUNTA --------


async def test_un_valor_con_separador_sobrevive_el_viaje_completo(base):
    """Serializar, guardar en SQLite, leer y reconstruir, sin perder nada.

    El campo 41 son ocho caracteres ASCII libres: `A=B | C` cabe de verdad. Con
    el formato de texto queda partido; el JSON lo devuelve intacto.
    """
    hostil = "A=B | C"
    resultado = await _compra(base)
    ejecucion = resultado.ejecucion

    # Se reescribe la fila con el valor hostil usando el mismo serializador que
    # usa el orquestador: lo que se prueba es el viaje, no el armado.
    from sibutestlab8583.domain.modelos import MensajeIso

    mensaje = MensajeIso("0100", {**dict(resultado.solicitud.campos), "41": hostil})
    with sqlite3.connect(base) as conexion:
        conexion.execute(
            "UPDATE ejecuciones SET solicitud_json = ?, solicitud_enmascarada = ?"
            " WHERE id = ?",
            (
                sz.a_json_solicitud(mensaje, NOMBRE_PERFIL_GENERICO),
                sz.a_texto(mensaje),
                ejecucion.id,
            ),
        )
        conexion.commit()

    guardada = await RepositorioEjecucionesSQLite(base).obtener(ejecucion.id)
    leido = sz.interpretar(guardada.solicitud_json, guardada.solicitud_enmascarada)

    assert leido.origen == sz.ORIGEN_JSON
    assert leido.fiel
    assert leido.valor("41") == hostil, "el JSON debe devolverlo intacto"
    assert {c.numero: c.valor for c in leido.campos} == dict(mensaje.campos)

    # Y el formato de texto, sobre la misma fila, sigue perdiendolo: por eso
    # existe la columna nueva.
    del_texto = sz.desde_texto_heredado(guardada.solicitud_enmascarada)
    assert del_texto.valor("41") == "A=B"
    assert not del_texto.fiel


# -------------------------------------------- 7. LECTURA DE LO ALMACENADO ----


# La matriz exhaustiva de contenidos malformados ya vive en
# `test_serializacion.py`, que es pura y rapida. Aqui solo hacen falta los
# cuatro casos que ejercitan algo distinto: el paso por el repositorio.
@pytest.mark.parametrize(
    "json_guardado,texto_guardado",
    [
        (None, None),                                  # nada que leer
        ("{roto", "MTI=0100 | 3=000000"),              # JSON ilegible, con respaldo
        ('{"version":7}', None),                       # version desconocida, sin respaldo
        (None, "basura sin igual"),                    # solo texto, no interpretable
    ],
)
async def test_leer_una_fila_cualquiera_nunca_lanza(base, json_guardado, texto_guardado):
    resultado = await _compra(base)
    with sqlite3.connect(base) as conexion:
        conexion.execute(
            "UPDATE ejecuciones SET solicitud_json = ?, solicitud_enmascarada = ? WHERE id = ?",
            (json_guardado, texto_guardado, resultado.ejecucion.id),
        )
        conexion.commit()

    guardada = await RepositorioEjecucionesSQLite(base).obtener(resultado.ejecucion.id)
    leido = sz.interpretar(guardada.solicitud_json, guardada.solicitud_enmascarada)
    assert isinstance(leido, sz.MensajeSerializado)


# ------------------------------------------------------------ 8. SEGURIDAD ---


async def test_ninguna_columna_de_ejecuciones_contiene_el_pan_completo(base):
    await _compra(base)
    fila = _filas(base)[0]

    for clave in fila.keys():
        assert PAN_DEMO not in str(fila[clave]), f"la columna {clave} expone el PAN"


async def test_las_dos_columnas_json_llevan_el_pan_enmascarado(base):
    await _compra(base)
    fila = _filas(base)[0]

    solicitud = json.loads(fila["solicitud_json"])
    assert solicitud["campos"]["2"]["valor"] == "************6666"
    assert PAN_DEMO not in fila["solicitud_json"]
    assert PAN_DEMO not in fila["respuesta_json"]


async def test_la_tabla_de_ejecuciones_sigue_sin_columna_de_pan(base):
    columnas = _columnas(base)
    for prohibida in ("pan", "pan_completo", "numero_tarjeta"):
        assert prohibida not in columnas


async def test_el_pan_completo_solo_vive_en_el_catalogo_de_tarjetas(base):
    """Comprobado sobre la base entera, tabla por tabla."""
    await _compra(base)
    with sqlite3.connect(base) as conexion:
        tablas = [
            f[0] for f in conexion.execute("SELECT name FROM sqlite_master WHERE type='table'")
        ]
        for tabla in tablas:
            if tabla == "tarjetas_prueba":
                continue
            filas = conexion.execute(f"SELECT * FROM {tabla}").fetchall()
            for fila in filas:
                for valor in fila:
                    assert PAN_DEMO not in str(valor), f"{tabla} expone el PAN completo"


# --------------------------------------------- 9. EJECUCION SIN RESPUESTA ----


def _sin_respuesta(base, fila):
    """Lo que debe cumplirse cuando no llego ninguna respuesta."""
    assert fila["respuesta_json"] is None, "no hubo respuesta: la columna debe quedar nula"
    assert fila["respuesta_enmascarada"] is None
    assert fila["solicitud_json"], "la solicitud si se armo y debe quedar registrada"


async def test_un_timeout_deja_la_columna_de_respuesta_nula(base):
    from sibutestlab8583.domain.modelos import TiempoAgotado

    transporte = TransporteFalso(TiempoAgotado(limite_segundos=0.1))
    resultado = await construir_orquestador(base, transporte).ejecutar_compra(
        DatosCompra(card_id=CARD_ID_DEMO, monto=Decimal("10.00"))
    )

    assert resultado.estado is EstadoEjecucion.TIMEOUT
    _sin_respuesta(base, _filas(base)[0])


async def test_un_fallo_de_codec_deja_la_columna_de_respuesta_nula(base):
    """El codec no pudo codificar: no se envio y no hay nada que interpretar."""
    from conftest import DESTINO_INERTE, MOMENTO_FIJO
    from test_semantica_comunicacion import CodecQueNoCodifica

    from sibutestlab8583.adapters.persistence.sqlite_repos import (
        GeneradorStanSQLite,
        RepositorioTarjetasSQLite,
    )
    from sibutestlab8583.application.orquestador import Orquestador
    from sibutestlab8583.domain.catalogo import CATALOGO_GENERICO
    from sibutestlab8583.profiles.generico import PERFIL_GENERICO

    transporte = TransporteFalso(codigo="00")
    resultado = await Orquestador(
        codec=CodecQueNoCodifica(),
        perfil=PERFIL_GENERICO,
        catalogo=CATALOGO_GENERICO,
        transporte=transporte,
        repositorio_ejecuciones=RepositorioEjecucionesSQLite(base),
        repositorio_tarjetas=RepositorioTarjetasSQLite(base),
        generador_stan=GeneradorStanSQLite(base),
        destino=DESTINO_INERTE,
        reloj=lambda: MOMENTO_FIJO,
    ).ejecutar_compra(DatosCompra(card_id=CARD_ID_DEMO, monto=Decimal("10.00")))

    assert resultado.estado is EstadoEjecucion.NO_ENVIADA
    assert not transporte.fue_invocado, "el codec fallo antes de tocar el transporte"
    _sin_respuesta(base, _filas(base)[0])


async def test_un_mensaje_detenido_por_rn4_igual_deja_su_json(base):
    """El mensaje se armo incompleto, RN-4 lo detuvo, y su estructura se registra.

    Es el caso que hace util la columna: poder ver **que** se habia armado
    cuando la regla lo bloqueo, no solo que se bloqueo.
    """
    transporte = TransporteFalso(codigo="00")
    # DE49 (moneda) es obligatorio pero editable: forzarlo vacio via
    # campos_manuales sigue disparando RN-4, ahora por el camino gobernado
    # por el perfil en vez de una propiedad dedicada de DatosCompra.
    datos = DatosCompra(
        card_id=CARD_ID_DEMO, monto=Decimal("150.00"), campos_manuales={"49": ""}
    )
    resultado = await construir_orquestador(base, transporte).ejecutar_compra(datos)

    assert resultado.estado is EstadoEjecucion.NO_ENVIADA
    assert not transporte.fue_invocado, "RN-4 debe cortar antes del transporte"

    fila = _filas(base)[0]
    solicitud = sz.desde_json(fila["solicitud_json"])
    assert solicitud.fiel
    assert solicitud.valor("49") == "", "se registra tal como se armo, incompleto incluido"
    assert fila["respuesta_json"] is None


# ------------------------------------------------------ 10. IDA Y VUELTA -----


async def test_ida_y_vuelta_completa_para_presentacion(base):
    """Serializar, persistir, leer y reconstruir sin perder numero ni valor."""
    resultado = await _compra(base, monto="1234.56")
    guardada = await RepositorioEjecucionesSQLite(base).obtener(resultado.ejecucion.id)

    solicitud = sz.interpretar(guardada.solicitud_json, guardada.solicitud_enmascarada)
    respuesta = sz.interpretar(guardada.respuesta_json, guardada.respuesta_enmascarada)

    assert solicitud.fiel and respuesta.fiel
    assert solicitud.origen == sz.ORIGEN_JSON and respuesta.origen == sz.ORIGEN_JSON

    # Lo reconstruido coincide campo por campo con lo que devolvio el recorrido.
    assert {c.numero: c.valor for c in solicitud.campos} == dict(resultado.solicitud.campos)
    assert {c.numero: c.valor for c in respuesta.campos} == {
        n: c.valor for n, c in resultado.respuesta.campos.items()
    }
    # Y los campos llegan ordenados por numero, listos para una tabla.
    assert [c.numero for c in solicitud.campos] == sorted(
        (c.numero for c in solicitud.campos), key=int
    )

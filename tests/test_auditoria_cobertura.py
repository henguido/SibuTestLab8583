"""Auditoria de cobertura de los Bloques 3-5 (constructor ISO, escenarios,
expectativas, suites de regresion, CLI): pruebas nuevas que cierran huecos
reales encontrados al leer `application/corredor_suites.py`,
`application/ejecutor_escenarios.py`, `domain/suites.py` y `cli.py` contra lo
que ya cubre `tests/`.

No reemplaza ni modifica ningun test existente. Cada prueba de aqui documenta,
en su docstring, que invariante o comportamiento protege y por que no estaba
ya cubierta.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import subprocess
import sys
from decimal import Decimal

import pytest
from conftest import TransporteFalso, construir_orquestador

from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, DESTINO_ID_DEMO, inicializar
from sibutestlab8583.adapters.persistence.sqlite_repos import (
    RepositorioCorridasSuiteSQLite,
    RepositorioDestinosSQLite,
    RepositorioEscenariosSQLite,
    RepositorioSuitesSQLite,
    RepositorioTarjetasSQLite,
)
from sibutestlab8583.application.conexiones import DatosNuevaConexion, ServicioConexiones
from sibutestlab8583.application.corredor_suites import CorredorDeSuites
from sibutestlab8583.application.ejecutor_escenarios import EjecutorDeEscenarios
from sibutestlab8583.application.escenarios import DatosNuevoEscenario, ServicioEscenarios
from sibutestlab8583.application.suites import DatosEdicionSuite, DatosNuevaSuite, ServicioSuites
from sibutestlab8583.cli import ejecutar_cli
from sibutestlab8583.domain.datos_sinteticos import pan_sintetico
from sibutestlab8583.domain.modelos import (
    EstadoEjecucion,
    EstadoItemCorrida,
    ResultadoGlobalSuite,
    TarjetaPrueba,
)
from sibutestlab8583.domain.modelos import Expectativas
from sibutestlab8583.domain.suites import calcular_resultado_global
from sibutestlab8583.profiles.generico import PERFIL_GENERICO

CODIGO_APROBADO = "00"


def _servicios(base, transporte, *, registro_destinos: list | None = None):
    """Mismo patron que `test_corredor_suites.py::_servicios`, pero con la
    fabrica instrumentada: si se pasa `registro_destinos`, cada llamada real
    (una por escenario que SI llega a construir el orquestador) queda anotada
    como `(host, puerto)`, para poder comprobar que el corredor resuelve la
    conexion correcta de CADA item, en vez de reutilizar la del primero.
    """
    escenarios = ServicioEscenarios(
        RepositorioEscenariosSQLite(base), RepositorioTarjetasSQLite(base),
        RepositorioDestinosSQLite(base), PERFIL_GENERICO,
    )
    conexiones = ServicioConexiones(RepositorioDestinosSQLite(base))

    async def fabrica(destino, tiempo_limite):
        if registro_destinos is not None:
            registro_destinos.append((destino.host, destino.puerto))
        return construir_orquestador(base, transporte, destino=destino, tiempo_limite=tiempo_limite)

    ejecutor = EjecutorDeEscenarios(escenarios, conexiones, fabrica)
    suites = ServicioSuites(RepositorioSuitesSQLite(base), RepositorioEscenariosSQLite(base))
    corridas = RepositorioCorridasSuiteSQLite(base)
    corredor = CorredorDeSuites(suites, escenarios, corridas, ejecutor)
    return suites, escenarios, conexiones, corridas, corredor


async def _crear_escenario(escenarios, nombre, *, card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO, expectativas=None):
    return await escenarios.crear(
        DatosNuevoEscenario(
            nombre=nombre, card_id=card_id, conexion_id=conexion_id,
            monto=Decimal("10.00"), expectativas=expectativas,
        )
    )


# ============================================================================
# Hueco 1: una suite con escenarios que usan MULTIPLES conexiones y tarjetas
# distintas ("multi-variedad"). Ningun test existente en test_corredor_suites.py
# crea mas de una conexion o mas de una tarjeta dentro de la MISMA suite: todos
# los escenarios ahi usan CARD_ID_DEMO/DESTINO_ID_DEMO. Este test comprueba que
# el corredor resuelve la conexion y la tarjeta CORRECTAS para cada item (no
# reutiliza por accidente la resolucion del item anterior), y que un item con
# una conexion inactiva se aisla como ERROR sin afectar a los demas, incluso
# cuando esos demas usan conexiones/tarjetas distintas entre si.
# ============================================================================


async def test_suite_con_conexiones_y_tarjetas_distintas_resuelve_cada_item_por_separado(base):
    suites, escenarios, conexiones, corridas, _ = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    registro: list[tuple[str, int]] = []
    _, _, _, _, corredor = _servicios(
        base, TransporteFalso(codigo=CODIGO_APROBADO), registro_destinos=registro
    )

    # Segunda conexion activa, con host/puerto propios y distintos de la demo.
    await conexiones.crear(
        DatosNuevaConexion(conexion_id="CONEXION-SEC", nombre="Secundaria", host="10.0.0.2", puerto="9001")
    )
    # Conexion inactiva, para el item que debe aislarse como ERROR.
    await conexiones.crear(
        DatosNuevaConexion(conexion_id="CONEXION-INACTIVA", nombre="Caida", host="10.0.0.3", puerto="9002")
    )
    await conexiones.cambiar_estado("CONEXION-INACTIVA", activa=False)

    # Segunda tarjeta activa, distinta de CARD_ID_DEMO.
    await RepositorioTarjetasSQLite(base).guardar(
        TarjetaPrueba(card_id="TARJETA-SEC", pan=pan_sintetico("9876"), expiracion="3012")
    )

    e1 = await _crear_escenario(
        escenarios, "E1-demo",
        card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO,
        expectativas=Expectativas(estado=EstadoEjecucion.APROBADA),
    )
    e2 = await _crear_escenario(
        escenarios, "E2-secundaria",
        card_id="TARJETA-SEC", conexion_id="CONEXION-SEC",
        expectativas=Expectativas(estado=EstadoEjecucion.APROBADA),
    )
    e3 = await _crear_escenario(
        escenarios, "E3-conexion-caida",
        card_id="TARJETA-SEC", conexion_id="CONEXION-INACTIVA",
        expectativas=Expectativas(estado=EstadoEjecucion.APROBADA),
    )
    suite = await suites.crear(
        DatosNuevaSuite(
            nombre="Multi-variedad",
            escenarios=(e1.escenario_id, e2.escenario_id, e3.escenario_id),
        )
    )

    corrida = await corredor.ejecutar(suite.suite_id)

    # La corrida no debe reventar ni contaminarse: 2 PASS reales + 1 ERROR
    # aislado, cada uno con su propia conexion/tarjeta.
    assert corrida.total == 3
    assert corrida.cantidad_pass == 2
    assert corrida.cantidad_error == 1
    assert corrida.resultado_global == ResultadoGlobalSuite.ERROR

    items = await corridas.obtener_items(corrida.corrida_id)
    assert [item.resultado for item in items] == [
        EstadoItemCorrida.PASS, EstadoItemCorrida.PASS, EstadoItemCorrida.ERROR,
    ]

    # La conexion inactiva nunca debio llegar a fabricar un orquestador: solo
    # 2 llamadas reales, y con el host de CADA conexion correcta -no ambas
    # con el mismo host, lo que delataria una resolucion pegada al primer item.
    assert len(registro) == 2
    assert registro[0][0] != registro[1][0]
    assert registro[1] == ("10.0.0.2", 9001)


# ============================================================================
# Hueco 2: `test_editar_la_suite_despues_no_cambia_la_corrida_historica` (en
# test_corredor_suites.py) usa 2 escenarios pero solo comprueba `total` y
# `len(items)` tras editar la suite -nunca el contenido de CADA item
# individual (nombre, resultado, evaluacion_json). Este test cierra ese hueco:
# edita una suite de 3 escenarios (quita uno, reordena) y comprueba que los 3
# items historicos, uno por uno, siguen intactos.
# ============================================================================


async def test_editar_suite_de_varios_escenarios_preserva_cada_item_individualmente(base):
    suites, escenarios, _, corridas, corredor = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    e1 = await _crear_escenario(escenarios, "Primero", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    e2 = await _crear_escenario(escenarios, "Segundo", expectativas=Expectativas(estado=EstadoEjecucion.RECHAZADA))
    e3 = await _crear_escenario(escenarios, "Tercero")  # sin expectativas
    suite = await suites.crear(
        DatosNuevaSuite(nombre="Original", escenarios=(e1.escenario_id, e2.escenario_id, e3.escenario_id))
    )

    corrida = await corredor.ejecutar(suite.suite_id)
    items_originales = await corridas.obtener_items(corrida.corrida_id)
    assert len(items_originales) == 3
    snapshot = [
        (item.orden, item.escenario_id, item.escenario_nombre, item.resultado, item.evaluacion_json)
        for item in items_originales
    ]

    # Edicion agresiva: quita e2, reordena, cambia nombre de la suite.
    await suites.actualizar(
        suite.suite_id,
        DatosEdicionSuite(nombre="Editada", escenarios=(e3.escenario_id, e1.escenario_id)),
    )
    # Tambien renombra un escenario referenciado: el item historico no debe
    # seguir ese nombre nuevo.
    from sibutestlab8583.application.escenarios import DatosEdicionEscenario

    await escenarios.actualizar(
        e1.escenario_id,
        DatosEdicionEscenario(
            nombre="Primero (renombrado)", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO,
            monto=Decimal("10.00"), expectativas=Expectativas(estado=EstadoEjecucion.APROBADA),
        ),
    )

    items_releidos = await corridas.obtener_items(corrida.corrida_id)
    assert len(items_releidos) == 3, "la corrida historica no debe perder ni ganar items"
    snapshot_releido = [
        (item.orden, item.escenario_id, item.escenario_nombre, item.resultado, item.evaluacion_json)
        for item in items_releidos
    ]
    assert snapshot_releido == snapshot, (
        "cada item, uno por uno, debe seguir igual a como quedo en la corrida original"
    )


# ============================================================================
# Hueco 3: `calcular_resultado_global` esta probado combinacion por
# combinacion en test_suites.py, pero NUNCA con `conteos = {}` (el caso vacio),
# y no hay ninguna prueba que confirme, de forma exhaustiva, que el resultado
# SIEMPRE cae dentro de las 5 opciones validas de `ResultadoGlobalSuite` para
# cualquier combinacion de conteos (incluyendo ceros en todas las claves).
# ============================================================================


def test_calcular_resultado_global_conteos_vacios_no_revienta():
    """Documenta el comportamiento actual con un diccionario vacio: el codigo
    de produccion no distingue "vacio" de "todo en cero", asi que cae en la
    ultima rama (PASS). El corredor real nunca llama con un dict vacio -una
    suite vacia se rechaza antes en `CorredorDeSuites.ejecutar`-, pero la
    funcion es publica y pura: debe comportarse de forma predecible incluso
    fuera de ese unico llamador.
    """
    assert calcular_resultado_global({}) == ResultadoGlobalSuite.PASS


def test_calcular_resultado_global_nunca_sale_de_las_cinco_opciones_validas():
    """Invariante exhaustivo: para CUALQUIER combinacion de conteos (0..2 de
    cada estado), el resultado es siempre uno de los 5 valores validos de
    `ResultadoGlobalSuite`. Ningun test existente recorre el espacio de
    combinaciones de forma sistematica -cada uno arma un dict a mano para un
    caso puntual-.
    """
    estados = list(EstadoItemCorrida)
    valores_validos = set(ResultadoGlobalSuite)
    for combinacion in itertools.product(range(3), repeat=len(estados)):
        conteos = dict(zip(estados, combinacion))
        resultado = calcular_resultado_global(conteos)
        assert resultado in valores_validos, f"conteos={conteos} produjo {resultado!r}"


# ============================================================================
# Hueco 4: dos corridas de la MISMA suite ejecutadas "al mismo tiempo"
# (`asyncio.gather`). La suite de STAN (`test_stan.py`) ya prueba la
# atomicidad del generador en aislamiento, pero ningun test ejercita el
# camino completo end-to-end (`CorredorDeSuites.ejecutar` x2 concurrente)
# para confirmar que no hay conflicto de `corrida_id` ni de items cruzados
# entre ambas corridas.
# ============================================================================


async def test_dos_corridas_concurrentes_de_la_misma_suite_no_se_mezclan(base):
    suites, escenarios, _, corridas, corredor = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    e1 = await _crear_escenario(escenarios, "E1", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    suite = await suites.crear(DatosNuevaSuite(nombre="Concurrente", escenarios=(e1.escenario_id,)))

    corrida_a, corrida_b = await asyncio.gather(
        corredor.ejecutar(suite.suite_id), corredor.ejecutar(suite.suite_id)
    )

    assert corrida_a.corrida_id != corrida_b.corrida_id, "cada corrida debe tener su propio id"

    items_a = await corridas.obtener_items(corrida_a.corrida_id)
    items_b = await corridas.obtener_items(corrida_b.corrida_id)
    assert len(items_a) == 1
    assert len(items_b) == 1
    # Cada item debe referenciar SU PROPIA ejecucion, nunca la de la otra corrida.
    assert items_a[0].ejecucion_id != items_b[0].ejecucion_id
    assert corrida_a.resultado_global == ResultadoGlobalSuite.PASS
    assert corrida_b.resultado_global == ResultadoGlobalSuite.PASS


# ============================================================================
# Hueco 5: la CLI solo se prueba de punta a punta con `subprocess` en UN
# smoke test que usa `python -m sibutestlab8583.cli` (nunca el entry point
# real `sibu-run-suite` que instala `pyproject.toml`), y ningun test de
# subprocess comprueba `--format json` con caracteres acentuados a traves
# del script real -que es exactamente el camino de encoding que el `main()`
# de la CLI dice proteger con `reconfigure(encoding="utf-8")`.
# ============================================================================


def test_entry_point_real_sibu_run_suite_devuelve_utf8_valido(tmp_path):
    """Ejecuta el script `sibu-run-suite` instalado de verdad (no `python -m`),
    con `--format text` sobre una corrida con una discrepancia que produce un
    mensaje con tildes (`mensaje_de_discrepancia`), y confirma que el stdout
    decodifica como UTF-8 sin bytes invalidos -el mismo problema que motiva el
    `reconfigure` de `main()`, pero a traves del launcher real, no del import.
    """
    import shutil
    from pathlib import Path

    nombre = "sibu-run-suite.exe" if sys.platform == "win32" else "sibu-run-suite"
    candidato = Path(sys.executable).with_name(nombre)
    ejecutable = str(candidato) if candidato.exists() else shutil.which("sibu-run-suite")
    if ejecutable is None:
        pytest.skip("sibu-run-suite no esta instalado en este entorno (paquete no instalado en modo editable)")

    ruta = tmp_path / "entrypoint.db"
    asyncio.run(inicializar(ruta))

    # Arma una suite con una expectativa que fallara, para que el texto de
    # salida incluya un mensaje de discrepancia con tildes.
    async def _preparar():
        from sibutestlab8583.adapters.persistence.sqlite_repos import (
            RepositorioDestinosSQLite as _D,
            RepositorioEscenariosSQLite as _E,
            RepositorioSuitesSQLite as _S,
            RepositorioTarjetasSQLite as _T,
        )
        from sibutestlab8583.application.escenarios import ServicioEscenarios as _SE
        from sibutestlab8583.application.suites import DatosNuevaSuite as _DNS, ServicioSuites as _SS
        from sibutestlab8583.domain.modelos import ExpectativaCampo

        conexion = await inicializar(ruta)
        servicio_escenarios = _SE(_E(conexion), _T(conexion), _D(conexion), PERFIL_GENERICO)
        creado = await servicio_escenarios.crear(
            DatosNuevoEscenario(
                nombre="Falla con acentos", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO,
                monto=Decimal("10.00"),
                expectativas=Expectativas(campos={"39": ExpectativaCampo(tipo="igual", valor="99")}),
            )
        )
        servicio_suites = _SS(_S(conexion), _E(conexion))
        suite = await servicio_suites.crear(_DNS(nombre="Suite con tildes", escenarios=(creado.escenario_id,)))
        return suite.suite_id

    suite_id = asyncio.run(_preparar())

    import os

    resultado = subprocess.run(
        [ejecutable, "run-suite", suite_id],
        capture_output=True,
        env={**os.environ, "SIBU_DB_PATH": str(ruta)},
    )

    # Nunca decodificar mal: si el launcher no configurara UTF-8 en Windows,
    # esto lanzaria UnicodeDecodeError con la codepagina por defecto.
    texto = resultado.stdout.decode("utf-8")
    assert "Resultado: FAIL" in texto
    assert "Código de respuesta" in texto or "39" in texto

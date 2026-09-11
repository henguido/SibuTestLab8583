"""`CorredorDeSuites`: ejecucion secuencial completa de una suite.

No reimplementa RN-1..RN-4 ni Expected vs Actual: delega enteramente en
`EjecutorDeEscenarios`. Estas pruebas cubren el algoritmo de agregacion
(PASS/FAIL/ERROR/INCOMPLETA/SIN_EXPECTATIVAS), el aislamiento de fallas por
item, la inmutabilidad del snapshot historico, y que `evaluacion_json` se
copie literal solo para PASS/FAIL.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from dataclasses import replace
from decimal import Decimal

import pytest
from conftest import TransporteFalso, construir_orquestador

from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, DESTINO_ID_DEMO
from sibutestlab8583.adapters.persistence.sqlite_repos import (
    RepositorioCorridasSuiteSQLite,
    RepositorioDestinosSQLite,
    RepositorioEjecucionesSQLite,
    RepositorioEscenariosSQLite,
    RepositorioSuitesSQLite,
    RepositorioTarjetasSQLite,
)
from sibutestlab8583.application.conexiones import ServicioConexiones
from sibutestlab8583.application.corredor_suites import (
    CorredorDeSuites,
    CorridaOrigenNoEncontrada,
    SinItemsReintentables,
    SuiteNoEjecutable,
)
from sibutestlab8583.application.ejecutor_escenarios import EjecutorDeEscenarios
from sibutestlab8583.application.escenarios import (
    DatosEdicionEscenario,
    DatosNuevoEscenario,
    ServicioEscenarios,
)
from sibutestlab8583.application.suites import DatosEdicionSuite, DatosNuevaSuite, ServicioSuites
from sibutestlab8583.domain.modelos import (
    CAMPOS_SENSIBLES,
    Ejecucion,
    Escenario,
    EstadoCorridaSuite,
    EstadoEjecucion,
    EstadoItemCorrida,
    ExpectativaCampo,
    Expectativas,
    MensajeIso,
    ResultadoCompra,
    ResultadoGlobalSuite,
    Suite,
)
from sibutestlab8583.profiles.generico import PERFIL_GENERICO

CODIGO_APROBADO = "00"
CODIGO_RECHAZADO = "05"


def _servicios(base, transporte):
    escenarios = ServicioEscenarios(
        RepositorioEscenariosSQLite(base), RepositorioTarjetasSQLite(base),
        RepositorioDestinosSQLite(base), PERFIL_GENERICO,
    )
    conexiones = ServicioConexiones(RepositorioDestinosSQLite(base))

    async def fabrica(destino, tiempo_limite):
        return construir_orquestador(base, transporte, destino=destino, tiempo_limite=tiempo_limite)

    ejecutor = EjecutorDeEscenarios(escenarios, conexiones, fabrica)
    suites = ServicioSuites(RepositorioSuitesSQLite(base), RepositorioEscenariosSQLite(base))
    corridas = RepositorioCorridasSuiteSQLite(base)
    corredor = CorredorDeSuites(suites, escenarios, corridas, ejecutor)
    return suites, escenarios, corridas, corredor


async def _crear_escenario(escenarios: ServicioEscenarios, nombre: str, *, expectativas=None):
    creado = await escenarios.crear(
        DatosNuevoEscenario(
            nombre=nombre, card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO,
            monto=Decimal("10.00"), expectativas=expectativas,
        )
    )
    return creado


# --------------------------------------------------------- casos de guardia --


async def test_ejecutar_una_suite_inexistente_se_rechaza(base):
    _, _, _, corredor = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    with pytest.raises(SuiteNoEjecutable):
        await corredor.ejecutar("NO-EXISTE")


async def test_ejecutar_una_suite_inactiva_se_rechaza(base):
    suites, _, corridas, corredor = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    creada = await suites.crear(DatosNuevaSuite(nombre="X"))
    await suites.cambiar_estado(creada.suite_id, activa=False)
    with pytest.raises(SuiteNoEjecutable):
        await corredor.ejecutar(creada.suite_id)
    assert await corridas.listar() == []


async def test_ejecutar_una_suite_vacia_se_rechaza(base):
    suites, _, corridas, corredor = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    creada = await suites.crear(DatosNuevaSuite(nombre="Vacia"))
    with pytest.raises(SuiteNoEjecutable):
        await corredor.ejecutar(creada.suite_id)
    assert await corridas.listar() == []


# --------------------------------------------------------- resultado global --


async def test_suite_completamente_pass_da_resultado_global_pass(base):
    suites, escenarios, _, corredor = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    e1 = await _crear_escenario(escenarios, "E1", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    e2 = await _crear_escenario(escenarios, "E2", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    suite = await suites.crear(DatosNuevaSuite(nombre="Toda PASS", escenarios=(e1.escenario_id, e2.escenario_id)))

    corrida = await corredor.ejecutar(suite.suite_id)

    assert corrida.estado == EstadoCorridaSuite.FINALIZADA
    assert corrida.resultado_global == ResultadoGlobalSuite.PASS
    assert corrida.total == 2
    assert corrida.cantidad_pass == 2
    assert corrida.cantidad_fail == corrida.cantidad_error == corrida.cantidad_sin_expectativas == 0


async def test_suite_con_un_fail_da_resultado_global_fail(base):
    suites, escenarios, _, corredor = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    e1 = await _crear_escenario(escenarios, "E1", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    e2 = await _crear_escenario(escenarios, "E2", expectativas=Expectativas(estado=EstadoEjecucion.RECHAZADA))
    suite = await suites.crear(DatosNuevaSuite(nombre="Con FAIL", escenarios=(e1.escenario_id, e2.escenario_id)))

    corrida = await corredor.ejecutar(suite.suite_id)

    assert corrida.resultado_global == ResultadoGlobalSuite.FAIL
    assert corrida.cantidad_pass == 1
    assert corrida.cantidad_fail == 1


async def test_mezcla_pass_y_sin_expectativas_da_incompleta(base):
    """El caso central de la correccion: 1 PASS + N SIN_EXPECTATIVAS nunca es PASS."""
    suites, escenarios, _, corredor = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    e1 = await _crear_escenario(escenarios, "E1", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    e2 = await _crear_escenario(escenarios, "E2")  # sin expectativas
    e3 = await _crear_escenario(escenarios, "E3")  # sin expectativas
    suite = await suites.crear(
        DatosNuevaSuite(nombre="Mixta", escenarios=(e1.escenario_id, e2.escenario_id, e3.escenario_id))
    )

    corrida = await corredor.ejecutar(suite.suite_id)

    assert corrida.resultado_global == ResultadoGlobalSuite.INCOMPLETA
    assert corrida.cantidad_pass == 1
    assert corrida.cantidad_sin_expectativas == 2


async def test_todos_sin_expectativas_da_resultado_sin_expectativas(base):
    suites, escenarios, _, corredor = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    e1 = await _crear_escenario(escenarios, "E1")
    suite = await suites.crear(DatosNuevaSuite(nombre="Sin nada", escenarios=(e1.escenario_id,)))

    corrida = await corredor.ejecutar(suite.suite_id)

    assert corrida.resultado_global == ResultadoGlobalSuite.SIN_EXPECTATIVAS
    assert corrida.cantidad_sin_expectativas == 1


async def test_suite_con_error_da_resultado_global_error(base):
    suites, escenarios, _, corredor = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    e1 = await _crear_escenario(escenarios, "E1", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    e2 = await escenarios.crear(
        DatosNuevoEscenario(nombre="Inactivo", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO, monto=Decimal("10.00"))
    )
    await escenarios.cambiar_estado(e2.escenario_id, activo=False)
    suite = await suites.crear(DatosNuevaSuite(nombre="Con error", escenarios=(e1.escenario_id, e2.escenario_id)))

    corrida = await corredor.ejecutar(suite.suite_id)

    assert corrida.resultado_global == ResultadoGlobalSuite.ERROR
    assert corrida.cantidad_pass == 1
    assert corrida.cantidad_error == 1


# ------------------------------------------------- escenario no ejecutable --


async def test_un_escenario_no_ejecutable_no_aborta_los_siguientes(base):
    """Los 4 casos de no-ejecutable ya estan probados uno por uno en
    `test_ejecutor_escenarios.py`; aqui se prueba que el CORREDOR aisla la
    falla como ERROR y sigue con el resto, en vez de abortar la suite.
    """
    suites, escenarios, corridas, corredor = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    e1 = await escenarios.crear(
        DatosNuevoEscenario(nombre="Inactivo", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO, monto=Decimal("10.00"))
    )
    await escenarios.cambiar_estado(e1.escenario_id, activo=False)
    e2 = await _crear_escenario(escenarios, "E2", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    e3 = await _crear_escenario(escenarios, "E3", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    suite = await suites.crear(
        DatosNuevaSuite(nombre="X", escenarios=(e1.escenario_id, e2.escenario_id, e3.escenario_id))
    )

    corrida = await corredor.ejecutar(suite.suite_id)

    assert corrida.total == 3
    assert corrida.cantidad_error == 1
    assert corrida.cantidad_pass == 2, "E2 y E3 SI deben haberse ejecutado"

    items = await corridas.obtener_items(corrida.corrida_id)
    assert items[0].resultado == EstadoItemCorrida.ERROR
    assert items[0].detalle is not None
    assert items[1].resultado == EstadoItemCorrida.PASS
    assert items[2].resultado == EstadoItemCorrida.PASS


async def test_una_excepcion_inesperada_a_mitad_de_la_suite_no_aborta_el_resto(base, monkeypatch):
    suites, escenarios, corridas, corredor = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    e1 = await _crear_escenario(escenarios, "E1", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    e2 = await _crear_escenario(escenarios, "E2", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    suite = await suites.crear(DatosNuevaSuite(nombre="X", escenarios=(e1.escenario_id, e2.escenario_id)))

    llamadas = {"n": 0}
    original = corredor._ejecutor.ejecutar

    async def fallar_la_primera_vez(escenario_id):
        llamadas["n"] += 1
        if llamadas["n"] == 1:
            raise RuntimeError("boom, algo totalmente inesperado")
        return await original(escenario_id)

    monkeypatch.setattr(corredor._ejecutor, "ejecutar", fallar_la_primera_vez)

    corrida = await corredor.ejecutar(suite.suite_id)

    assert corrida.cantidad_error == 1
    assert corrida.cantidad_pass == 1
    items = await corridas.obtener_items(corrida.corrida_id)
    assert items[0].resultado == EstadoItemCorrida.ERROR
    assert items[0].detalle == (
        "Fallo técnico inesperado durante la ejecución. Revise el registro del servidor."
    )
    assert "boom" not in items[0].detalle
    assert items[1].resultado == EstadoItemCorrida.PASS


# --------------------------------------------------------- autosuficiencia --


async def test_evaluacion_json_se_copia_literal_solo_para_pass_y_fail(base):
    suites, escenarios, corridas, corredor = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    e_pass = await _crear_escenario(escenarios, "PASS", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    e_fail = await _crear_escenario(escenarios, "FAIL", expectativas=Expectativas(estado=EstadoEjecucion.RECHAZADA))
    e_sin = await _crear_escenario(escenarios, "SIN")
    suite = await suites.crear(
        DatosNuevaSuite(nombre="X", escenarios=(e_pass.escenario_id, e_fail.escenario_id, e_sin.escenario_id))
    )

    corrida = await corredor.ejecutar(suite.suite_id)
    items = await corridas.obtener_items(corrida.corrida_id)

    item_pass, item_fail, item_sin = items
    assert item_pass.evaluacion_json is not None
    assert json.loads(item_pass.evaluacion_json)["resultado"] == "pass"
    assert item_fail.evaluacion_json is not None
    assert json.loads(item_fail.evaluacion_json)["resultado"] == "fail"
    assert item_sin.evaluacion_json is None


async def test_corrida_explica_discrepancias_desde_su_propio_snapshot_sin_consultar_nada_mas(base):
    """El detalle de una corrida debe poder explicarse solo, sin releer el
    escenario ni el `Ejecucion` referenciado.
    """
    suites, escenarios, corridas, corredor = _servicios(base, TransporteFalso(codigo=CODIGO_RECHAZADO))
    e1 = await _crear_escenario(
        escenarios, "E1",
        expectativas=Expectativas(campos={"39": ExpectativaCampo(tipo="igual", valor="00")}),
    )
    suite = await suites.crear(DatosNuevaSuite(nombre="X", escenarios=(e1.escenario_id,)))

    corrida = await corredor.ejecutar(suite.suite_id)
    [item] = await corridas.obtener_items(corrida.corrida_id)

    datos = json.loads(item.evaluacion_json)
    assert datos["resultado"] == "fail"
    assert datos["discrepancias"][0]["campo"] == "39"
    assert datos["discrepancias"][0]["esperado"] == "00"
    assert datos["discrepancias"][0]["recibido"] == CODIGO_RECHAZADO


async def test_ejecucion_id_referencia_la_ejecucion_real(base):
    suites, escenarios, corridas, corredor = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    e1 = await _crear_escenario(escenarios, "E1", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    suite = await suites.crear(DatosNuevaSuite(nombre="X", escenarios=(e1.escenario_id,)))

    corrida = await corredor.ejecutar(suite.suite_id)
    [item] = await corridas.obtener_items(corrida.corrida_id)
    assert item.ejecucion_id is not None

    from sibutestlab8583.adapters.persistence.sqlite_repos import RepositorioEjecucionesSQLite

    ejecucion = await RepositorioEjecucionesSQLite(base).obtener(item.ejecucion_id)
    assert ejecucion is not None
    assert ejecucion.evaluacion_json == item.evaluacion_json


# --------------------------------------------------------------- inmutabilidad --


async def test_editar_la_suite_despues_no_cambia_la_corrida_historica(base):
    suites, escenarios, corridas, corredor = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    e1 = await _crear_escenario(escenarios, "E1", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    e2 = await _crear_escenario(escenarios, "E2", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    suite = await suites.crear(DatosNuevaSuite(nombre="Original", escenarios=(e1.escenario_id, e2.escenario_id)))

    corrida = await corredor.ejecutar(suite.suite_id)
    assert corrida.total == 2

    await suites.actualizar(suite.suite_id, DatosEdicionSuite(nombre="Editada", escenarios=(e1.escenario_id,)))

    releida = await corridas.obtener(corrida.corrida_id)
    assert releida.total == 2
    assert releida.suite_nombre == "Original"
    items = await corridas.obtener_items(corrida.corrida_id)
    assert len(items) == 2


async def test_editar_expectativas_de_un_escenario_despues_no_cambia_la_corrida_historica(base):
    suites, escenarios, corridas, corredor = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    e1 = await _crear_escenario(escenarios, "E1", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    suite = await suites.crear(DatosNuevaSuite(nombre="X", escenarios=(e1.escenario_id,)))

    corrida = await corredor.ejecutar(suite.suite_id)
    assert corrida.resultado_global == ResultadoGlobalSuite.PASS

    await escenarios.actualizar(
        e1.escenario_id,
        DatosEdicionEscenario(
            nombre="E1", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO, monto=Decimal("10.00"),
            expectativas=Expectativas(estado=EstadoEjecucion.RECHAZADA),
        ),
    )

    releida = await corridas.obtener(corrida.corrida_id)
    assert releida.resultado_global == ResultadoGlobalSuite.PASS
    [item] = await corridas.obtener_items(corrida.corrida_id)
    assert json.loads(item.evaluacion_json)["expectativas"]["estado"] == "aprobada"


# ------------------------------------------------------------ transacciones --


async def test_crear_con_items_deja_todos_los_items_en_no_ejecutado_antes_de_correr(base, monkeypatch):
    """Verifica el presembrado atomico: interceptando `actualizar_item` para
    que nunca corra, los items deben seguir existiendo en NO_EJECUTADO -la
    corrida se abrio y se presembraron todos, en una sola transaccion-.
    """
    suites, escenarios, corridas, corredor = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    e1 = await _crear_escenario(escenarios, "E1")
    e2 = await _crear_escenario(escenarios, "E2")
    suite = await suites.crear(DatosNuevaSuite(nombre="X", escenarios=(e1.escenario_id, e2.escenario_id)))

    # Se reconstruye manualmente solo la fase de apertura, para observar el
    # estado inmediatamente despues de `crear_con_items` sin ejecutar nada.
    suite_obj = await suites.obtener_activa(suite.suite_id)
    from sibutestlab8583.domain.modelos import CorridaSuite, EstadoItemCorrida, ItemCorridaSuite

    items_iniciales = [
        ItemCorridaSuite(
            corrida_id=0, escenario_id=eid, escenario_nombre=eid, orden=i,
            resultado=EstadoItemCorrida.NO_EJECUTADO,
        )
        for i, eid in enumerate(suite_obj.escenarios, start=1)
    ]
    corrida_dominio = CorridaSuite(suite_id=suite_obj.suite_id, suite_nombre=suite_obj.nombre, total=2)
    corrida_id = await corridas.crear_con_items(corrida_dominio, items_iniciales)

    items = await corridas.obtener_items(corrida_id)
    assert len(items) == 2
    assert all(i.resultado == EstadoItemCorrida.NO_EJECUTADO for i in items)
    corrida_abierta = await corridas.obtener(corrida_id)
    assert corrida_abierta.estado == EstadoCorridaSuite.EN_CURSO


# ------------------------------------------------------- defensa en profundidad --


async def test_un_campo_sensible_en_las_expectativas_de_un_escenario_de_la_suite_sigue_rechazado(base):
    """Humo: el corredor no bypassea la defensa en profundidad de Bloque 3 -
    reutiliza `EjecutorDeEscenarios` -> `Orquestador.ejecutar_compra`, que ya
    valida `expectativas` antes de persistir nada.
    """
    suites, escenarios, corridas, corredor = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    e1 = await _crear_escenario(escenarios, "E1", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    suite = await suites.crear(DatosNuevaSuite(nombre="X", escenarios=(e1.escenario_id,)))

    # Se fuerza una expectativa sobre un campo sensible directamente en el
    # objeto de dominio (bypass deliberado de `validar_expectativas` en
    # `ServicioEscenarios.actualizar`, para simular una fila ya corrupta).
    repo_escenarios = RepositorioEscenariosSQLite(base)
    escenario_bruto = await repo_escenarios.obtener(e1.escenario_id)
    campo_sensible = next(iter(CAMPOS_SENSIBLES))
    await repo_escenarios.guardar(
        replace(
            escenario_bruto,
            expectativas=Expectativas(campos={campo_sensible: ExpectativaCampo(tipo="presente")}),
        )
    )

    corrida = await corredor.ejecutar(suite.suite_id)

    assert corrida.resultado_global == ResultadoGlobalSuite.ERROR
    [item] = await corridas.obtener_items(corrida.corrida_id)
    assert item.resultado == EstadoItemCorrida.ERROR
    assert item.evaluacion_json is None
    assert campo_sensible not in (item.detalle or "")


# ------------------------------------------------------------ secuencialidad --


class _EjecutorQueDetectaSolapamiento:
    """Reemplaza a `EjecutorDeEscenarios` para verificar, de forma directa e
    independiente de la base de datos, que el corredor jamas tiene dos
    ejecuciones de escenario "en vuelo" al mismo tiempo -la garantia de
    diseno documentada en el docstring del modulo ("Secuencial a proposito:
    sin `asyncio.gather`, sin concurrencia")-. Si el corredor alguna vez
    pasara a disparar los escenarios en paralelo, `en_vuelo` superaria 1 y la
    prueba fallaria.
    """

    def __init__(self, base) -> None:
        self._ejecuciones = RepositorioEjecucionesSQLite(base)
        self.en_vuelo = 0
        self.maximo_en_vuelo = 0
        self.orden_de_llamadas: list[str] = []
        self._contador = 0

    async def ejecutar(self, escenario_id: str):
        self.orden_de_llamadas.append(escenario_id)
        self.en_vuelo += 1
        self.maximo_en_vuelo = max(self.maximo_en_vuelo, self.en_vuelo)
        try:
            # Cede el control deliberadamente: si el corredor usara
            # `asyncio.gather` en vez de `await` secuencial, este punto es
            # donde otra corrutina podria colarse y hacer que
            # `en_vuelo` suba a 2.
            await asyncio.sleep(0)
            self._contador += 1
            # Fila real en `ejecuciones` -no solo un objeto en memoria-: con
            # `PRAGMA foreign_keys = ON` (ver el fix de Bloque de auditoria en
            # `actualizar_item`) un `ejecucion_id` inventado seria rechazado.
            ejecucion_id = await self._ejecuciones.guardar(
                Ejecucion(
                    card_id=CARD_ID_DEMO,
                    monto=Decimal("10.00"),
                    moneda="188",
                    stan=f"{self._contador:06d}",
                    estado=EstadoEjecucion.APROBADA,
                )
            )
            # `evaluacion_estado=None` (por defecto): el corredor lo clasifica
            # como SIN_EXPECTATIVAS, igual que un escenario sin expectativas.
            ejecucion = await self._ejecuciones.obtener(ejecucion_id)
            return ResultadoCompra(ejecucion=ejecucion, solicitud=MensajeIso(mti="0100"))
        finally:
            self.en_vuelo -= 1


async def test_el_corredor_ejecuta_los_escenarios_uno_a_la_vez_nunca_solapados(base):
    """Confirma en codigo la garantia "Secuencial a proposito" del docstring
    del modulo: sustituye `EjecutorDeEscenarios` por un doble que detecta
    solapamiento, para que un futuro cambio a `asyncio.gather` (u otra forma
    de concurrencia) rompa esta prueba en vez de pasar inadvertido.
    """
    suites = ServicioSuites(RepositorioSuitesSQLite(base), RepositorioEscenariosSQLite(base))
    escenarios = ServicioEscenarios(
        RepositorioEscenariosSQLite(base), RepositorioTarjetasSQLite(base),
        RepositorioDestinosSQLite(base), PERFIL_GENERICO,
    )
    corridas = RepositorioCorridasSuiteSQLite(base)
    e1 = await _crear_escenario(escenarios, "E1")
    e2 = await _crear_escenario(escenarios, "E2")
    e3 = await _crear_escenario(escenarios, "E3")
    suite = await suites.crear(
        DatosNuevaSuite(nombre="Secuencial", escenarios=(e1.escenario_id, e2.escenario_id, e3.escenario_id))
    )

    ejecutor_falso = _EjecutorQueDetectaSolapamiento(base)
    corredor = CorredorDeSuites(suites, escenarios, corridas, ejecutor_falso)

    corrida = await corredor.ejecutar(suite.suite_id)

    assert corrida.resultado_global == ResultadoGlobalSuite.SIN_EXPECTATIVAS
    assert ejecutor_falso.maximo_en_vuelo == 1
    assert ejecutor_falso.orden_de_llamadas == [e1.escenario_id, e2.escenario_id, e3.escenario_id]


# --------------------------------------------------- reintentar fallidos --
#
# `reintentar_fallidos` reutiliza `_correr` (el mismo nucleo que `ejecutar`):
# ninguna de estas pruebas necesita un segundo doble de ejecucion, solo
# variar que items quedaron en la corrida ORIGEN.


async def _corrida_mixta(base):
    """Una suite de 3 escenarios: E1 PASS, E2 FAIL, y E3 desactivado ANTES de
    correr para que de ERROR. Devuelve todo lo necesario para variar el
    escenario despues de la corrida.
    """
    suites, escenarios, corridas, corredor = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    e1 = await _crear_escenario(escenarios, "E1", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    e2 = await _crear_escenario(escenarios, "E2", expectativas=Expectativas(estado=EstadoEjecucion.RECHAZADA))
    e3 = await _crear_escenario(escenarios, "E3", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    await escenarios.cambiar_estado(e3.escenario_id, activo=False)
    suite = await suites.crear(
        DatosNuevaSuite(
            nombre="Mixta reintento",
            escenarios=(e1.escenario_id, e2.escenario_id, e3.escenario_id),
        )
    )
    corrida = await corredor.ejecutar(suite.suite_id)
    return suites, escenarios, corridas, corredor, suite, corrida, e1, e2, e3


async def test_reintentar_fallidos_crea_corrida_con_solo_fail_y_error(base):  # 11
    suites, escenarios, corridas, corredor, suite, corrida, e1, e2, e3 = await _corrida_mixta(base)
    assert corrida.cantidad_pass == 1
    assert corrida.cantidad_fail == 1
    assert corrida.cantidad_error == 1

    nueva = await corredor.reintentar_fallidos(corrida.corrida_id)

    assert nueva.total == 2
    items_nueva = await corridas.obtener_items(nueva.corrida_id)
    ids_nueva = {item.escenario_id for item in items_nueva}
    assert ids_nueva == {e2.escenario_id, e3.escenario_id}
    assert e1.escenario_id not in ids_nueva


async def test_reintentar_sin_fallidos_no_crea_corrida(base):  # 12
    suites, escenarios, corridas, corredor = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    e1 = await _crear_escenario(escenarios, "E1", expectativas=Expectativas(estado=EstadoEjecucion.APROBADA))
    suite = await suites.crear(DatosNuevaSuite(nombre="Todo PASS", escenarios=(e1.escenario_id,)))
    corrida = await corredor.ejecutar(suite.suite_id)
    assert corrida.cantidad_fail == corrida.cantidad_error == 0

    antes = len(await corridas.listar())
    with pytest.raises(SinItemsReintentables):
        await corredor.reintentar_fallidos(corrida.corrida_id)
    assert len(await corridas.listar()) == antes


async def test_reintentar_no_altera_la_corrida_original(base):  # 13
    suites, escenarios, corridas, corredor, suite, corrida, e1, e2, e3 = await _corrida_mixta(base)
    items_originales_antes = await corridas.obtener_items(corrida.corrida_id)

    await corredor.reintentar_fallidos(corrida.corrida_id)

    original_despues = await corridas.obtener(corrida.corrida_id)
    items_originales_despues = await corridas.obtener_items(corrida.corrida_id)
    assert original_despues.cantidad_pass == corrida.cantidad_pass
    assert original_despues.cantidad_fail == corrida.cantidad_fail
    assert original_despues.cantidad_error == corrida.cantidad_error
    assert [i.resultado for i in items_originales_despues] == [i.resultado for i in items_originales_antes]


async def test_reintentar_da_id_y_timestamps_propios(base):  # 14
    suites, escenarios, corridas, corredor, suite, corrida, e1, e2, e3 = await _corrida_mixta(base)

    nueva = await corredor.reintentar_fallidos(corrida.corrida_id)

    assert nueva.corrida_id != corrida.corrida_id
    assert nueva.iniciada_en >= corrida.iniciada_en
    assert nueva.suite_id == corrida.suite_id
    assert nueva.suite_nombre == corrida.suite_nombre
    assert nueva.estado == EstadoCorridaSuite.FINALIZADA


async def test_reintentar_usa_items_historicos_no_membresia_actual_de_suite(base):  # 15, 16
    suites, escenarios, corridas, corredor, suite, corrida, e1, e2, e3 = await _corrida_mixta(base)

    # Se agrega un escenario NUEVO a la suite, que si se ejecutara daria
    # FAIL -pero nunca aparecio en la corrida origen, asi que no debe
    # aparecer en el reintento aunque hoy sea parte de la suite.
    e4 = await _crear_escenario(escenarios, "E4", expectativas=Expectativas(estado=EstadoEjecucion.RECHAZADA))
    await suites.actualizar(
        suite.suite_id,
        DatosEdicionSuite(
            nombre=suite.nombre,
            escenarios=(e1.escenario_id, e2.escenario_id, e3.escenario_id, e4.escenario_id),
        ),
    )

    nueva = await corredor.reintentar_fallidos(corrida.corrida_id)

    items_nueva = await corridas.obtener_items(nueva.corrida_id)
    ids_nueva = {item.escenario_id for item in items_nueva}
    assert e4.escenario_id not in ids_nueva
    assert ids_nueva == {e2.escenario_id, e3.escenario_id}


async def test_reintentar_escenario_desactivado_da_error_controlado_sin_abortar(base):  # 17
    """E3 ya estaba desactivado ANTES de la corrida origen (por eso dio
    ERROR); aqui se reintenta y se comprueba que sigue dando ERROR -con el
    mismo motivo controlado que ya usa una corrida normal- sin que eso
    impida procesar E2, el otro item reintentable.
    """
    suites, escenarios, corridas, corredor, suite, corrida, e1, e2, e3 = await _corrida_mixta(base)

    nueva = await corredor.reintentar_fallidos(corrida.corrida_id)

    items_nueva = {item.escenario_id: item for item in await corridas.obtener_items(nueva.corrida_id)}
    assert items_nueva[e3.escenario_id].resultado == EstadoItemCorrida.ERROR
    assert "inactiv" in items_nueva[e3.escenario_id].detalle.lower()
    # El otro item reintentable se proceso igual -18: un fallo no impide
    # procesar los demas, misma garantia que ya prueba el corredor completo.
    assert items_nueva[e2.escenario_id].resultado == EstadoItemCorrida.FAIL


async def test_reintentar_escenario_eliminado_da_error_controlado_sin_abortar(base):  # 17
    """Los escenarios nunca se borran desde la aplicacion (solo se
    desactivan, ver `ServicioEscenarios`); este caso -fila borrada por fuera
    de la aplicacion- se prueba igual porque `EjecutorDeEscenarios` ya lo
    contempla explicitamente (`EscenarioNoEncontrado`), y el reintento no
    deberia comportarse distinto a una corrida normal frente a esto.
    """
    suites, escenarios, corridas, corredor, suite, corrida, e1, e2, e3 = await _corrida_mixta(base)

    with sqlite3.connect(base) as conexion:
        conexion.execute("DELETE FROM escenarios WHERE escenario_id = ?", (e2.escenario_id,))
        conexion.commit()

    nueva = await corredor.reintentar_fallidos(corrida.corrida_id)

    items_nueva = {item.escenario_id: item for item in await corridas.obtener_items(nueva.corrida_id)}
    assert items_nueva[e2.escenario_id].resultado == EstadoItemCorrida.ERROR
    assert "ya no existe" in items_nueva[e2.escenario_id].detalle.lower()
    # El nombre para mostrar cae al historico -el escenario ya no existe
    # para resolver un nombre actual.
    assert items_nueva[e2.escenario_id].escenario_nombre == "E2"


async def test_reintentar_ejecuta_con_la_configuracion_actual_del_escenario(base):
    """Decision explicita del diseno: el reintento SELECCIONA por snapshot
    historico, pero EJECUTA con la configuracion ACTUAL del escenario -si el
    monto cambio despues de la corrida origen, el reintento usa el nuevo.
    """
    suites, escenarios, corridas, corredor, suite, corrida, e1, e2, e3 = await _corrida_mixta(base)

    # Se corrige E2 para que ahora si cumpla su expectativa.
    await escenarios.actualizar(
        e2.escenario_id,
        DatosEdicionEscenario(
            nombre=e2.nombre, card_id=e2.card_id, conexion_id=e2.conexion_id, monto=e2.monto,
            expectativas=Expectativas(estado=EstadoEjecucion.APROBADA),
        ),
    )

    nueva = await corredor.reintentar_fallidos(corrida.corrida_id)

    items_nueva = {item.escenario_id: item for item in await corridas.obtener_items(nueva.corrida_id)}
    assert items_nueva[e2.escenario_id].resultado == EstadoItemCorrida.PASS


async def test_reintentar_corrida_origen_inexistente_da_error_controlado(base):
    _, _, corridas, corredor = _servicios(base, TransporteFalso(codigo=CODIGO_APROBADO))
    with pytest.raises(CorridaOrigenNoEncontrada):
        await corredor.reintentar_fallidos(9999)

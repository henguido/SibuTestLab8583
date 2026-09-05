"""Auditoria de seguridad ad-hoc (solo lectura de produccion) para los
Bloques 3-5 (expected-vs-actual, suites de regresion, CLI).

Caso adversarial: un `Escenario` con una expectativa sobre un campo SENSIBLE
(DE2, el PAN), construido y guardado DIRECTO contra el repositorio SQLite
-bypaseando `ServicioEscenarios.crear`/`actualizar`, que es donde vive la
validacion "normal"-, y despues ejecutado dentro de una suite via la misma
ruta que usa la CLI (`CorredorDeSuites` + `EjecutorDeEscenarios`). Confirma
que `Orquestador.ejecutar_compra` (defensa en profundidad, ver
`application/orquestador.py::ejecutar_compra`) lo rechaza igual, sin dejar
rastro del PAN en el resultado.

No modifica ningun archivo de produccion. Usa PAN sintetico de
`domain/datos_sinteticos.py`, nunca inventado a mano.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import replace
from decimal import Decimal

from conftest import TransporteFalso, construir_orquestador

from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, DESTINO_ID_DEMO, inicializar
from sibutestlab8583.adapters.persistence.sqlite_repos import (
    RepositorioCorridasSuiteSQLite,
    RepositorioDestinosSQLite,
    RepositorioEscenariosSQLite,
    RepositorioSuitesSQLite,
    RepositorioTarjetasSQLite,
)
from sibutestlab8583.application.conexiones import ServicioConexiones
from sibutestlab8583.application.corredor_suites import CorredorDeSuites
from sibutestlab8583.application.ejecutor_escenarios import EjecutorDeEscenarios
from sibutestlab8583.application.escenarios import DatosNuevoEscenario, ServicioEscenarios
from sibutestlab8583.application.suites import DatosNuevaSuite, ServicioSuites
from sibutestlab8583.cli import ejecutar_cli
from sibutestlab8583.domain.datos_sinteticos import pan_sintetico
from sibutestlab8583.domain.expectativas import validar_expectativas
from sibutestlab8583.domain.modelos import ExpectativaCampo, Expectativas
from sibutestlab8583.profiles.generico import PERFIL_GENERICO

PAN_ADVERSARIAL = pan_sintetico("41112")  # solo vive en memoria durante el test


class _ComposicionPrueba:
    def __init__(self, base, transporte):
        escenarios = ServicioEscenarios(
            RepositorioEscenariosSQLite(base), RepositorioTarjetasSQLite(base),
            RepositorioDestinosSQLite(base), PERFIL_GENERICO,
        )
        conexiones = ServicioConexiones(RepositorioDestinosSQLite(base))

        async def fabrica(destino, tiempo_limite):
            return construir_orquestador(base, transporte, destino=destino, tiempo_limite=tiempo_limite)

        ejecutor = EjecutorDeEscenarios(escenarios, conexiones, fabrica)
        self.administracion_escenarios = escenarios
        self.administracion_suites = ServicioSuites(
            RepositorioSuitesSQLite(base), RepositorioEscenariosSQLite(base)
        )
        self.corridas_suite = RepositorioCorridasSuiteSQLite(base)
        self.corredor_suites = CorredorDeSuites(
            self.administracion_suites, escenarios, self.corridas_suite, ejecutor,
        )
        self.descripciones_de_campos = {"39": "Código de respuesta"}


def _base(tmp_path):
    ruta = tmp_path / "auditoria.db"
    asyncio.run(inicializar(ruta))
    return ruta


def test_validar_expectativas_directa_rechaza_de2_y_de35():
    """`validar_expectativas` (domain/expectativas.py) es la funcion pura que
    hace el rechazo real; confirma que ambos campos sensibles (CAMPOS_SENSIBLES
    = {"2","35"}) estan cubiertos, no solo el 2.
    """
    for campo_sensible in ("2", "35"):
        try:
            validar_expectativas(
                Expectativas(campos={campo_sensible: ExpectativaCampo(tipo="presente")}),
                PERFIL_GENERICO,
                "0110",
            )
            assert False, f"debio rechazar el campo {campo_sensible}"
        except ValueError:
            pass


def test_orquestador_rechaza_expectativa_sensible_aunque_bypasee_servicio_escenarios(tmp_path):
    """Caso adversarial completo: un `Escenario` con expectativa sobre DE2 se
    guarda DIRECTO en el repositorio (bypaseando `ServicioEscenarios.crear`,
    que es lo unico que ya lo hubiera bloqueado), y se ejecuta por el mismo
    camino que usa la CLI (`CorredorDeSuites`/`EjecutorDeEscenarios`).

    Confirma que `Orquestador.ejecutar_compra` (defensa en profundidad
    explicita en su propio docstring) revienta la expectativa igual, y que el
    fallo se aisla como un item ERROR de la suite -nunca un crash de la
    corrida completa, nunca un PASS/FAIL evaluado sobre un campo sensible-.
    """
    base = _base(tmp_path)

    async def _armar_bypass() -> str:
        servicio_escenarios = ServicioEscenarios(
            RepositorioEscenariosSQLite(base), RepositorioTarjetasSQLite(base),
            RepositorioDestinosSQLite(base), PERFIL_GENERICO,
        )
        # 1) Crear un escenario LEGITIMO (sin expectativas), pasando por el
        #    servicio -para que quede en un estado valido salvo por el campo
        #    que vamos a forzar despues-.
        creado = await servicio_escenarios.crear(
            DatosNuevoEscenario(
                nombre="bypass-DE2", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO,
                monto=Decimal("10.00"),
            )
        )
        # 2) Forzar la expectativa adversarial DIRECTO contra el objeto de
        #    dominio y el repositorio, sin pasar por
        #    ServicioEscenarios.actualizar (que la hubiera rechazado).
        repo = RepositorioEscenariosSQLite(base)
        escenario_crudo = await repo.obtener(creado.escenario_id)
        forzado = replace(
            escenario_crudo,
            expectativas=Expectativas(campos={"2": ExpectativaCampo(tipo="igual", valor=PAN_ADVERSARIAL)}),
        )
        await repo.guardar(forzado)  # el repositorio NO valida: es solo persistencia

        # Confirma que el bypass funciono: el escenario guardado SI tiene la
        # expectativa sensible (si esto fallara, el resto del test no probaria
        # nada real).
        releido = await repo.obtener(creado.escenario_id)
        assert releido.expectativas is not None
        assert "2" in releido.expectativas.campos

        servicio_suites = ServicioSuites(
            RepositorioSuitesSQLite(base), RepositorioEscenariosSQLite(base)
        )
        suite = await servicio_suites.crear(
            DatosNuevaSuite(nombre="Suite bypass", escenarios=(creado.escenario_id,))
        )
        return suite.suite_id

    suite_id = asyncio.run(_armar_bypass())
    composicion = _ComposicionPrueba(base, TransporteFalso(codigo="00"))

    # Ejecuta exactamente por el camino de la CLI (`sibu-run-suite run-suite --format json`).
    codigo = ejecutar_cli(["run-suite", suite_id, "--format", "json"], composicion=composicion)

    # ejecutar_cli ya imprimio a stdout/stderr reales; releemos desde la BD
    # para inspeccionar el resultado persistido sin depender de capsys aqui.
    corridas = asyncio.run(composicion.corridas_suite.listar())
    assert len(corridas) == 1
    corrida = corridas[0]
    items = asyncio.run(composicion.corridas_suite.obtener_items(corrida.corrida_id))
    [item] = items

    # El escenario con la expectativa adversarial debe terminar en ERROR, NUNCA
    # en PASS ni en FAIL (que implicarian que la expectativa sensible SI se evaluo).
    assert item.resultado.value == "error", (
        "Orquestador.ejecutar_compra debio rechazar la expectativa sobre el "
        "campo 2 y aislarla como ERROR de item, no evaluarla"
    )
    assert item.evaluacion_json is None, "un item ERROR nunca debe traer snapshot de evaluacion"

    # El PAN adversarial jamas debe aparecer en ningun snapshot persistido.
    assert PAN_ADVERSARIAL not in (item.detalle or "")

    # El codigo de salida de la CLI debe reflejar ERROR (2), nunca 0/1 (que
    # implicarian PASS/FAIL evaluado sobre datos sensibles).
    assert codigo == 2


def test_mensaje_error_de_orquestador_no_ecoa_el_valor_forzado(tmp_path):
    """El mensaje de `ValueError` de `validar_expectativas` es texto fijo con
    el NUMERO de campo (aceptable, es metadato de config, no dato de tarjeta),
    nunca el VALOR de la expectativa (que en el caso adversarial seria un PAN).
    """
    expectativa = Expectativas(campos={"2": ExpectativaCampo(tipo="igual", valor=PAN_ADVERSARIAL)})
    try:
        validar_expectativas(expectativa, PERFIL_GENERICO, "0110")
        assert False, "debio rechazar"
    except ValueError as error:
        mensaje = str(error)
        assert PAN_ADVERSARIAL not in mensaje
        assert not re.search(r"(?<!\d)\d{12,19}(?!\d)", mensaje), (
            "el mensaje de error no debe contener nada con forma de PAN"
        )

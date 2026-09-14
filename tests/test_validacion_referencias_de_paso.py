"""Validacion de referencias de paso AL GUARDAR la definicion (Fase C2,
punto 10/11 del checkpoint): rechazar referencias hacia adelante, hacia si
mismo, o hacia un paso inexistente, ANTES de ejecutar -nunca en la corrida-.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, DESTINO_ID_DEMO
from sibutestlab8583.adapters.persistence.sqlite_repos import (
    RepositorioEscenariosSQLite,
    RepositorioSecuenciasSQLite,
)
from sibutestlab8583.application.escenarios import DatosNuevoEscenario, ServicioEscenarios
from sibutestlab8583.application.secuencias import (
    DatosNuevaSecuencia,
    DatosPaso,
    ServicioSecuencias,
)
from sibutestlab8583.domain.modelos import ORIGEN_PASO_INDEPENDIENTE, MTI_COMPRA_FINANCIERA
from sibutestlab8583.profiles.generico import PERFIL_GENERICO


async def _servicio_escenarios(base) -> ServicioEscenarios:
    from sibutestlab8583.adapters.persistence.sqlite_repos import (
        RepositorioDestinosSQLite,
        RepositorioTarjetasSQLite,
    )

    return ServicioEscenarios(
        RepositorioEscenariosSQLite(base), RepositorioTarjetasSQLite(base),
        RepositorioDestinosSQLite(base), PERFIL_GENERICO,
    )


async def _crear_escenario(escenarios, nombre, *, campos_manuales=None):
    return await escenarios.crear(
        DatosNuevoEscenario(
            nombre=nombre, conexion_id=DESTINO_ID_DEMO, mti=MTI_COMPRA_FINANCIERA,
            card_id=CARD_ID_DEMO, monto=Decimal("10.00"),
            campos_manuales=campos_manuales or {},
        )
    )


async def test_una_referencia_hacia_un_paso_futuro_se_rechaza(base):
    escenarios = await _servicio_escenarios(base)
    secuencias = ServicioSecuencias(RepositorioSecuenciasSQLite(base), RepositorioEscenariosSQLite(base))

    paso1 = await _crear_escenario(
        escenarios, "Paso 1", campos_manuales={"37": "{{step.segunda.response.de38}}"}
    )
    paso2 = await _crear_escenario(escenarios, "Paso 2 (futuro)")

    with pytest.raises(ValueError, match="ANTERIOR"):
        await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="Referencia hacia adelante",
                pasos=[
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso1.escenario_id,
                        paso_id="primera",
                    ),
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso2.escenario_id,
                        paso_id="segunda",
                    ),
                ],
            )
        )


async def test_una_referencia_a_un_paso_inexistente_se_rechaza(base):
    escenarios = await _servicio_escenarios(base)
    secuencias = ServicioSecuencias(RepositorioSecuenciasSQLite(base), RepositorioEscenariosSQLite(base))

    paso1 = await _crear_escenario(
        escenarios, "Paso unico", campos_manuales={"37": "{{step.fantasma.response.de38}}"}
    )

    with pytest.raises(ValueError, match="no existe"):
        await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="Referencia a paso fantasma",
                pasos=[
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso1.escenario_id,
                        paso_id="unico",
                    ),
                ],
            )
        )


async def test_dos_pasos_no_pueden_compartir_el_mismo_paso_id(base):
    escenarios = await _servicio_escenarios(base)
    secuencias = ServicioSecuencias(RepositorioSecuenciasSQLite(base), RepositorioEscenariosSQLite(base))

    paso1 = await _crear_escenario(escenarios, "Paso 1")
    paso2 = await _crear_escenario(escenarios, "Paso 2")

    with pytest.raises(ValueError, match="ya se usó"):
        await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="IDs repetidos",
                pasos=[
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso1.escenario_id,
                        paso_id="repetido",
                    ),
                    DatosPaso(
                        origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso2.escenario_id,
                        paso_id="repetido",
                    ),
                ],
            )
        )


async def test_un_paso_id_se_genera_automaticamente_si_no_se_indica(base):
    escenarios = await _servicio_escenarios(base)
    secuencias = ServicioSecuencias(RepositorioSecuenciasSQLite(base), RepositorioEscenariosSQLite(base))
    paso1 = await _crear_escenario(escenarios, "Paso sin id explicito")

    creada = await secuencias.crear(
        DatosNuevaSecuencia(
            nombre="Sin paso_id explicito",
            pasos=[DatosPaso(origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso1.escenario_id)],
        )
    )
    assert creada.pasos[0].paso_id == "paso1"


async def test_una_referencia_valida_hacia_un_paso_anterior_se_acepta(base):
    escenarios = await _servicio_escenarios(base)
    secuencias = ServicioSecuencias(RepositorioSecuenciasSQLite(base), RepositorioEscenariosSQLite(base))

    paso1 = await _crear_escenario(escenarios, "Paso 1")
    paso2 = await _crear_escenario(
        escenarios, "Paso 2", campos_manuales={"37": "{{step.primera.response.de38}}"}
    )

    creada = await secuencias.crear(
        DatosNuevaSecuencia(
            nombre="Referencia valida",
            pasos=[
                DatosPaso(
                    origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso1.escenario_id,
                    paso_id="primera",
                ),
                DatosPaso(
                    origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=paso2.escenario_id,
                    paso_id="segunda",
                ),
            ],
        )
    )
    assert len(creada.pasos) == 2

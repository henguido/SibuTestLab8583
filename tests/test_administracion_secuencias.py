"""`ServicioSecuencias`: validacion al crear una secuencia (C1).

Real SQLite (sin dobles): usa `RepositorioSecuenciasSQLite` y
`RepositorioEscenariosSQLite` reales -la validacion de "el escenario
existe" y "el paso derivado solo puede apuntar a un paso ANTERIOR" no tiene
sentido probarla contra un doble en memoria que nunca reproduciria un
catalogo real.
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
from sibutestlab8583.domain.modelos import (
    ORIGEN_PASO_DERIVADO,
    ORIGEN_PASO_INDEPENDIENTE,
    MTI_COMPRA_FINANCIERA,
)
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


async def _crear_escenario_financiero(escenarios: ServicioEscenarios, nombre: str):
    return await escenarios.crear(
        DatosNuevoEscenario(
            nombre=nombre, conexion_id=DESTINO_ID_DEMO, mti=MTI_COMPRA_FINANCIERA,
            card_id=CARD_ID_DEMO, monto=Decimal("10.00"),
        )
    )


async def test_una_secuencia_sin_nombre_se_rechaza(base):
    escenarios = await _servicio_escenarios(base)
    secuencias = ServicioSecuencias(RepositorioSecuenciasSQLite(base), RepositorioEscenariosSQLite(base))
    escenario = await _crear_escenario_financiero(escenarios, "Financiera A")
    with pytest.raises(ValueError):
        await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="  ",
                pasos=[DatosPaso(origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=escenario.escenario_id)],
            )
        )


async def test_una_secuencia_sin_pasos_se_rechaza(base):
    secuencias = ServicioSecuencias(RepositorioSecuenciasSQLite(base), RepositorioEscenariosSQLite(base))
    with pytest.raises(ValueError):
        await secuencias.crear(DatosNuevaSecuencia(nombre="Vacía", pasos=[]))


async def test_un_paso_independiente_con_escenario_inexistente_se_rechaza(base):
    secuencias = ServicioSecuencias(RepositorioSecuenciasSQLite(base), RepositorioEscenariosSQLite(base))
    with pytest.raises(ValueError):
        await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="Con escenario fantasma",
                pasos=[DatosPaso(origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id="NO-EXISTE")],
            )
        )


async def test_un_paso_derivado_no_puede_apuntar_hacia_adelante(base):
    escenarios = await _servicio_escenarios(base)
    secuencias = ServicioSecuencias(RepositorioSecuenciasSQLite(base), RepositorioEscenariosSQLite(base))
    escenario = await _crear_escenario_financiero(escenarios, "Financiera B")
    with pytest.raises(ValueError):
        await secuencias.crear(
            DatosNuevaSecuencia(
                nombre="Orden invertido",
                pasos=[
                    DatosPaso(origen_tipo=ORIGEN_PASO_DERIVADO, origen_paso_orden=2),
                    DatosPaso(origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=escenario.escenario_id),
                ],
            )
        )


async def test_una_secuencia_valida_se_crea_y_se_puede_releer(base):
    escenarios = await _servicio_escenarios(base)
    secuencias = ServicioSecuencias(RepositorioSecuenciasSQLite(base), RepositorioEscenariosSQLite(base))
    escenario = await _crear_escenario_financiero(escenarios, "Financiera C")

    creada = await secuencias.crear(
        DatosNuevaSecuencia(
            nombre="Compra + reverso",
            pasos=[
                DatosPaso(origen_tipo=ORIGEN_PASO_INDEPENDIENTE, escenario_id=escenario.escenario_id),
                DatosPaso(origen_tipo=ORIGEN_PASO_DERIVADO, origen_paso_orden=1),
            ],
        )
    )
    assert len(creada.pasos) == 2
    assert creada.pasos[0].orden == 1
    assert creada.pasos[1].origen_paso_orden == 1

    releida = await secuencias.obtener(creada.secuencia_id)
    assert releida is not None
    assert releida.nombre == "Compra + reverso"
    assert len(releida.pasos) == 2

    todas = await secuencias.listar()
    assert creada.secuencia_id in [s.secuencia_id for s in todas]

    activa = await secuencias.obtener_activa(creada.secuencia_id)
    assert activa is not None

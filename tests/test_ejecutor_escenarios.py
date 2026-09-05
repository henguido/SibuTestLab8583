"""`EjecutorDeEscenarios`: la unica implementacion de "escenario_id -> ejecucion
real", reutilizada tanto por la ruta `/escenarios/{id}/ejecutar` como por
`CorredorDeSuites`. Se prueba aqui contra SQLite real y un transporte falso.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from conftest import TransporteFalso, construir_orquestador

from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, DESTINO_ID_DEMO
from sibutestlab8583.adapters.persistence.sqlite_repos import (
    RepositorioDestinosSQLite,
    RepositorioEscenariosSQLite,
    RepositorioTarjetasSQLite,
)
from sibutestlab8583.application.conexiones import ServicioConexiones
from sibutestlab8583.application.ejecutor_escenarios import (
    EjecutorDeEscenarios,
    EscenarioNoEjecutable,
)
from sibutestlab8583.application.escenarios import EscenarioNoEncontrado, ServicioEscenarios
from sibutestlab8583.domain.modelos import Escenario, EstadoEjecucion
from sibutestlab8583.profiles.generico import PERFIL_GENERICO


def _fabrica(base, transporte):
    async def fabrica(destino, tiempo_limite):
        return construir_orquestador(base, transporte, destino=destino, tiempo_limite=tiempo_limite)

    return fabrica


def _ejecutor(base, transporte) -> EjecutorDeEscenarios:
    escenarios = ServicioEscenarios(
        RepositorioEscenariosSQLite(base), RepositorioTarjetasSQLite(base),
        RepositorioDestinosSQLite(base), PERFIL_GENERICO,
    )
    conexiones = ServicioConexiones(RepositorioDestinosSQLite(base))
    return EjecutorDeEscenarios(escenarios, conexiones, _fabrica(base, transporte))


async def _sembrar_escenario(base, escenario_id: str, **overrides) -> None:
    base_kwargs = dict(
        escenario_id=escenario_id, nombre=f"Escenario {escenario_id}", perfil="generico",
        mti="0100", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO, monto=Decimal("10.00"),
    )
    base_kwargs.update(overrides)
    await RepositorioEscenariosSQLite(base).guardar(Escenario(**base_kwargs))


async def test_ejecutar_un_escenario_inexistente_lanza_escenario_no_encontrado(base):
    with pytest.raises(EscenarioNoEncontrado):
        await _ejecutor(base, TransporteFalso(codigo="00")).ejecutar("NO-EXISTE")


async def test_ejecutar_un_escenario_inactivo_lanza_escenario_no_ejecutable(base):
    await _sembrar_escenario(base, "ESC-INACTIVO", activo=False)
    with pytest.raises(EscenarioNoEjecutable):
        await _ejecutor(base, TransporteFalso(codigo="00")).ejecutar("ESC-INACTIVO")


async def test_ejecutar_un_escenario_con_tarjeta_inactiva_lanza_escenario_no_ejecutable(base):
    from dataclasses import replace

    from sibutestlab8583.domain.datos_sinteticos import pan_sintetico
    from sibutestlab8583.domain.modelos import TarjetaPrueba

    await RepositorioTarjetasSQLite(base).guardar(
        TarjetaPrueba(card_id="TARJETA-INACTIVA", pan=pan_sintetico("1234"), expiracion="3012")
    )
    tarjeta = await RepositorioTarjetasSQLite(base).obtener("TARJETA-INACTIVA")
    await RepositorioTarjetasSQLite(base).guardar(replace(tarjeta, activa=False))
    await _sembrar_escenario(base, "ESC-TARJETA-INACTIVA", card_id="TARJETA-INACTIVA")

    with pytest.raises(EscenarioNoEjecutable):
        await _ejecutor(base, TransporteFalso(codigo="00")).ejecutar("ESC-TARJETA-INACTIVA")


async def test_ejecutar_un_escenario_con_conexion_inactiva_lanza_escenario_no_ejecutable(base):
    from sibutestlab8583.application.conexiones import DatosNuevaConexion

    conexiones = ServicioConexiones(RepositorioDestinosSQLite(base))
    await conexiones.crear(
        DatosNuevaConexion(conexion_id="CONEXION-X", nombre="d", host="10.0.0.1", puerto="9000")
    )
    await conexiones.cambiar_estado("CONEXION-X", activa=False)
    await _sembrar_escenario(base, "ESC-CONEXION-INACTIVA", conexion_id="CONEXION-X")

    with pytest.raises(EscenarioNoEjecutable):
        await _ejecutor(base, TransporteFalso(codigo="00")).ejecutar("ESC-CONEXION-INACTIVA")


async def test_ejecutar_un_escenario_incompatible_con_el_perfil_lanza_escenario_no_ejecutable(base):
    from dataclasses import replace

    await _sembrar_escenario(base, "ESC-PERFIL-VIEJO")
    repo = RepositorioEscenariosSQLite(base)
    escenario = await repo.obtener("ESC-PERFIL-VIEJO")
    await repo.guardar(replace(escenario, perfil="otro-perfil-hipotetico"))

    with pytest.raises(EscenarioNoEjecutable):
        await _ejecutor(base, TransporteFalso(codigo="00")).ejecutar("ESC-PERFIL-VIEJO")


async def test_ejecutar_un_escenario_sano_delega_en_el_orquestador_y_persiste(base):
    await _sembrar_escenario(base, "ESC-SANO")
    resultado = await _ejecutor(base, TransporteFalso(codigo="00")).ejecutar("ESC-SANO")
    assert resultado.ejecucion.estado is EstadoEjecucion.APROBADA
    assert resultado.ejecucion.escenario_id == "ESC-SANO"
    assert resultado.ejecucion.id is not None


async def test_ejecutar_pasa_las_expectativas_del_escenario_tal_cual(base):
    from sibutestlab8583.domain.modelos import EstadoEjecucion as EE
    from sibutestlab8583.domain.modelos import ExpectativaCampo, Expectativas

    await _sembrar_escenario(
        base, "ESC-CON-EXPECTATIVAS",
        expectativas=Expectativas(estado=EE.APROBADA, campos={"39": ExpectativaCampo(tipo="igual", valor="00")}),
    )
    resultado = await _ejecutor(base, TransporteFalso(codigo="00")).ejecutar("ESC-CON-EXPECTATIVAS")
    assert resultado.ejecucion.evaluacion_estado == "pass"

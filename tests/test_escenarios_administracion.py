"""Administracion de escenarios: `ServicioEscenarios` contra SQLite real.

No se prueba aqui la capa web: eso vive en `test_web_escenarios.py`. Aqui se
prueba el servicio de aplicacion y su persistencia real: que "crear"/"Guardar
cambios" congelen los valores EFECTIVOS (no solo lo que el usuario toco), que
`diagnosticar` detecte tarjeta/conexion no disponibles y campos incompatibles,
y que duplicar/activar/desactivar se comporten igual que en tarjetas y
conexiones.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, DESTINO_ID_DEMO
from sibutestlab8583.adapters.persistence.sqlite_repos import (
    RepositorioDestinosSQLite,
    RepositorioEscenariosSQLite,
    RepositorioTarjetasSQLite,
)
from sibutestlab8583.application.conexiones import DatosNuevaConexion, ServicioConexiones
from sibutestlab8583.application.escenarios import (
    DatosEdicionEscenario,
    DatosNuevoEscenario,
    EscenarioNoEncontrado,
    ServicioEscenarios,
)
from sibutestlab8583.application.tarjetas import DatosNuevaTarjeta, ServicioTarjetas
from sibutestlab8583.domain.datos_sinteticos import pan_sintetico
from sibutestlab8583.domain.modelos import CAMPOS_SENSIBLES, EstadoEjecucion, ExpectativaCampo, Expectativas
from sibutestlab8583.profiles.generico import (
    CODIGO_PROCESO_COMPRA,
    MODO_CAPTURA_DEMOSTRACION,
    PERFIL_GENERICO,
    TERMINAL_DEMOSTRACION,
)


def _servicio(base) -> ServicioEscenarios:
    return ServicioEscenarios(
        RepositorioEscenariosSQLite(base),
        RepositorioTarjetasSQLite(base),
        RepositorioDestinosSQLite(base),
        PERFIL_GENERICO,
    )


# --------------------------------------------------------------- listar/leer --


async def test_listar_arranca_vacio(base):
    assert await _servicio(base).listar() == []


async def test_obtener_un_escenario_inexistente_devuelve_none(base):
    assert await _servicio(base).obtener("NO-EXISTE") is None


async def test_obtener_activo_devuelve_none_si_esta_desactivado(base):
    servicio = _servicio(base)
    creado = await servicio.crear(
        DatosNuevoEscenario(
            nombre="X", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO, monto=Decimal("10.00")
        )
    )
    await servicio.cambiar_estado(creado.escenario_id, activo=False)
    assert await servicio.obtener_activo(creado.escenario_id) is None
    # Pero "obtener" (a secas) lo sigue devolviendo: inactivo se puede ver.
    assert await servicio.obtener(creado.escenario_id) is not None


async def test_buscar_filtra_por_substring_de_nombre_sin_distinguir_mayusculas(base):
    servicio = _servicio(base)
    await servicio.crear(
        DatosNuevoEscenario(
            nombre="Compra aprobada CRC",
            card_id=CARD_ID_DEMO,
            conexion_id=DESTINO_ID_DEMO,
            monto=Decimal("10.00"),
        )
    )
    await servicio.crear(
        DatosNuevoEscenario(
            nombre="Rechazo por fondos",
            card_id=CARD_ID_DEMO,
            conexion_id=DESTINO_ID_DEMO,
            monto=Decimal("10.00"),
        )
    )
    resultado = await servicio.listar(buscar="aprobada")
    assert [e.nombre for e in resultado] == ["Compra aprobada CRC"]
    assert len(await servicio.listar(buscar="")) == 2
    assert len(await servicio.listar()) == 2


# ------------------------------------------------------------------- crear ---


async def test_crear_congela_los_valores_efectivos_no_solo_los_overrides(base):
    """El corazon del ajuste 1: 3/22/41/49 quedan en campos_manuales aunque
    vinieran del default del perfil, no solo lo que el usuario escribio.
    """
    servicio = _servicio(base)
    creado = await servicio.crear(
        DatosNuevoEscenario(
            nombre="Compra básica",
            card_id=CARD_ID_DEMO,
            conexion_id=DESTINO_ID_DEMO,
            monto=Decimal("150.00"),
            campos_manuales={"37": "REF-QA-01"},
        )
    )
    assert dict(creado.campos_manuales) == {
        "3": CODIGO_PROCESO_COMPRA,
        "22": MODO_CAPTURA_DEMOSTRACION,
        "37": "REF-QA-01",
        "41": TERMINAL_DEMOSTRACION,
        "49": "188",
    }


async def test_crear_asigna_un_escenario_id_autogenerado(base):
    creado = await _servicio(base).crear(
        DatosNuevoEscenario(
            nombre="X", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO, monto=Decimal("10.00")
        )
    )
    assert creado.escenario_id
    assert creado.escenario_id.startswith("ESC-")


async def test_crear_dos_veces_da_ids_distintos(base):
    servicio = _servicio(base)
    datos = DatosNuevoEscenario(
        nombre="X", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO, monto=Decimal("10.00")
    )
    primero = await servicio.crear(datos)
    segundo = await servicio.crear(datos)
    assert primero.escenario_id != segundo.escenario_id


async def test_crear_sin_nombre_se_rechaza(base):
    with pytest.raises(ValueError):
        await _servicio(base).crear(
            DatosNuevoEscenario(
                nombre="", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO,
                monto=Decimal("10.00"),
            )
        )


async def test_crear_con_tarjeta_inexistente_se_rechaza(base):
    with pytest.raises(ValueError, match="tarjeta"):
        await _servicio(base).crear(
            DatosNuevoEscenario(
                nombre="X", card_id="NO-EXISTE", conexion_id=DESTINO_ID_DEMO,
                monto=Decimal("10.00"),
            )
        )


async def test_crear_con_conexion_inexistente_se_rechaza(base):
    with pytest.raises(ValueError, match="conexión"):
        await _servicio(base).crear(
            DatosNuevoEscenario(
                nombre="X", card_id=CARD_ID_DEMO, conexion_id="NO-EXISTE",
                monto=Decimal("10.00"),
            )
        )


async def test_crear_con_tarjeta_inactiva_se_permite(base):
    """Un escenario puede referenciar una tarjeta inactiva: eso solo bloquea
    la reejecucion (`diagnosticar`), no el guardado -guardar es siempre
    posible; ejecutar es lo que se condiciona-.
    """
    tarjetas_servicio = ServicioTarjetas(RepositorioTarjetasSQLite(base))
    await tarjetas_servicio.crear(
        DatosNuevaTarjeta(
            card_id="TARJETA-INACTIVA", descripcion="d", pan=pan_sintetico("5678"),
            expiracion="3012",
        )
    )
    await tarjetas_servicio.cambiar_estado("TARJETA-INACTIVA", activa=False)

    creado = await _servicio(base).crear(
        DatosNuevoEscenario(
            nombre="X", card_id="TARJETA-INACTIVA", conexion_id=DESTINO_ID_DEMO,
            monto=Decimal("10.00"),
        )
    )
    assert creado.card_id == "TARJETA-INACTIVA"


async def test_crear_con_un_campo_protegido_se_rechaza(base):
    with pytest.raises(ValueError):
        await _servicio(base).crear(
            DatosNuevoEscenario(
                nombre="X", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO,
                monto=Decimal("10.00"), campos_manuales={"2": "9" * 16},
            )
        )


async def test_el_perfil_del_escenario_creado_es_el_activo(base):
    creado = await _servicio(base).crear(
        DatosNuevoEscenario(
            nombre="X", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO, monto=Decimal("10.00")
        )
    )
    assert creado.perfil == PERFIL_GENERICO.nombre


# ------------------------------------------------------------------ editar ---


async def test_actualizar_vuelve_a_congelar_los_efectivos_de_hoy(base):
    servicio = _servicio(base)
    creado = await servicio.crear(
        DatosNuevoEscenario(
            nombre="X", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO,
            monto=Decimal("10.00"), campos_manuales={"37": "REF-1"},
        )
    )
    actualizado = await servicio.actualizar(
        creado.escenario_id,
        DatosEdicionEscenario(
            nombre="X renombrado", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO,
            monto=Decimal("20.00"), campos_manuales={"37": "REF-2"},
        ),
    )
    assert actualizado.nombre == "X renombrado"
    assert actualizado.monto == Decimal("20.00")
    assert dict(actualizado.campos_manuales)["37"] == "REF-2"
    assert dict(actualizado.campos_manuales)["3"] == CODIGO_PROCESO_COMPRA


async def test_actualizar_un_escenario_inexistente_falla_con_su_propia_excepcion(base):
    with pytest.raises(EscenarioNoEncontrado):
        await _servicio(base).actualizar(
            "NO-EXISTE",
            DatosEdicionEscenario(
                nombre="X", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO,
                monto=Decimal("10.00"),
            ),
        )


async def test_el_escenario_id_no_es_parte_de_los_datos_de_edicion():
    assert not hasattr(
        DatosEdicionEscenario(
            nombre="X", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO,
            monto=Decimal("10.00"),
        ),
        "escenario_id",
    )


# ---------------------------------------------------------------- duplicar ---


async def test_duplicar_crea_una_copia_independiente_con_nombre_sufijado(base):
    servicio = _servicio(base)
    creado = await servicio.crear(
        DatosNuevoEscenario(
            nombre="Original", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO,
            monto=Decimal("10.00"), campos_manuales={"37": "REF-1"},
        )
    )
    copia = await servicio.duplicar(creado.escenario_id)

    assert copia.escenario_id != creado.escenario_id
    assert copia.nombre == "Original (copia)"
    assert copia.card_id == creado.card_id
    assert dict(copia.campos_manuales) == dict(creado.campos_manuales)
    assert copia.activo

    # Editar la copia no debe afectar el original.
    await servicio.actualizar(
        copia.escenario_id,
        DatosEdicionEscenario(
            nombre="Copia editada", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO,
            monto=Decimal("99.00"),
        ),
    )
    original_sin_cambios = await servicio.obtener(creado.escenario_id)
    assert original_sin_cambios.nombre == "Original"
    assert original_sin_cambios.monto == Decimal("10.00")


async def test_duplicar_un_escenario_inexistente_falla(base):
    with pytest.raises(EscenarioNoEncontrado):
        await _servicio(base).duplicar("NO-EXISTE")


# ------------------------------------------------------- activar/desactivar --


async def test_desactivar_no_borra_la_fila(base):
    servicio = _servicio(base)
    creado = await servicio.crear(
        DatosNuevoEscenario(
            nombre="X", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO, monto=Decimal("10.00")
        )
    )
    desactivado = await servicio.cambiar_estado(creado.escenario_id, activo=False)
    assert desactivado.activo is False
    assert await servicio.obtener(creado.escenario_id) is not None


async def test_reactivar_un_escenario_inactivo(base):
    servicio = _servicio(base)
    creado = await servicio.crear(
        DatosNuevoEscenario(
            nombre="X", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO, monto=Decimal("10.00")
        )
    )
    await servicio.cambiar_estado(creado.escenario_id, activo=False)
    reactivado = await servicio.cambiar_estado(creado.escenario_id, activo=True)
    assert reactivado.activo is True


async def test_cambiar_estado_de_un_escenario_inexistente_falla(base):
    with pytest.raises(EscenarioNoEncontrado):
        await _servicio(base).cambiar_estado("NO-EXISTE", activo=False)


# -------------------------------------------------------------- diagnosticar --


async def test_diagnosticar_un_escenario_sano_no_esta_bloqueado(base):
    servicio = _servicio(base)
    creado = await servicio.crear(
        DatosNuevoEscenario(
            nombre="X", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO, monto=Decimal("10.00")
        )
    )
    diagnostico = await servicio.diagnosticar(creado)
    assert diagnostico.tarjeta_disponible
    assert diagnostico.conexion_disponible
    assert diagnostico.incompatibilidades == ()
    assert not diagnostico.bloqueado


async def test_diagnosticar_detecta_tarjeta_desactivada(base):
    tarjetas_servicio = ServicioTarjetas(RepositorioTarjetasSQLite(base))
    await tarjetas_servicio.crear(
        DatosNuevaTarjeta(
            card_id="TARJETA-X", descripcion="d", pan=pan_sintetico("1234"), expiracion="3012"
        )
    )
    servicio = _servicio(base)
    creado = await servicio.crear(
        DatosNuevoEscenario(
            nombre="X", card_id="TARJETA-X", conexion_id=DESTINO_ID_DEMO, monto=Decimal("10.00")
        )
    )
    await tarjetas_servicio.cambiar_estado("TARJETA-X", activa=False)

    diagnostico = await servicio.diagnosticar(creado)
    assert not diagnostico.tarjeta_disponible
    assert diagnostico.bloqueado


async def test_diagnosticar_detecta_conexion_desactivada(base):
    conexiones_servicio = ServicioConexiones(RepositorioDestinosSQLite(base))
    await conexiones_servicio.crear(
        DatosNuevaConexion(conexion_id="CONEXION-X", nombre="d", host="10.0.0.1", puerto="9000")
    )
    servicio = _servicio(base)
    creado = await servicio.crear(
        DatosNuevoEscenario(
            nombre="X", card_id=CARD_ID_DEMO, conexion_id="CONEXION-X", monto=Decimal("10.00")
        )
    )
    await conexiones_servicio.cambiar_estado("CONEXION-X", activa=False)

    diagnostico = await servicio.diagnosticar(creado)
    assert not diagnostico.conexion_disponible
    assert diagnostico.bloqueado


# --------------------------------------------------------- expectativas ---


async def test_crear_con_expectativas_validas_las_persiste(base):
    expectativas = Expectativas(
        estado=EstadoEjecucion.APROBADA,
        campos={"39": ExpectativaCampo(tipo="igual", valor="00")},
    )
    creado = await _servicio(base).crear(
        DatosNuevoEscenario(
            nombre="X", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO, monto=Decimal("10.00"),
            expectativas=expectativas,
        )
    )
    assert creado.expectativas.estado == EstadoEjecucion.APROBADA
    assert dict(creado.expectativas.campos)["39"].valor == "00"


async def test_crear_con_expectativa_de_campo_sensible_se_rechaza(base):
    campo_sensible = next(iter(CAMPOS_SENSIBLES))
    expectativas = Expectativas(campos={campo_sensible: ExpectativaCampo(tipo="presente")})
    with pytest.raises(ValueError):
        await _servicio(base).crear(
            DatosNuevoEscenario(
                nombre="X", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO,
                monto=Decimal("10.00"), expectativas=expectativas,
            )
        )


async def test_crear_sin_expectativas_deja_el_campo_en_none(base):
    creado = await _servicio(base).crear(
        DatosNuevoEscenario(
            nombre="X", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO, monto=Decimal("10.00")
        )
    )
    assert creado.expectativas is None


async def test_actualizar_reemplaza_las_expectativas_enteras_no_las_fusiona(base):
    servicio = _servicio(base)
    creado = await servicio.crear(
        DatosNuevoEscenario(
            nombre="X", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO, monto=Decimal("10.00"),
            expectativas=Expectativas(
                estado=EstadoEjecucion.APROBADA,
                campos={"39": ExpectativaCampo(tipo="igual", valor="00")},
            ),
        )
    )
    actualizado = await servicio.actualizar(
        creado.escenario_id,
        DatosEdicionEscenario(
            nombre="X", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO, monto=Decimal("10.00"),
            expectativas=Expectativas(estado=EstadoEjecucion.RECHAZADA),
        ),
    )
    assert actualizado.expectativas.estado == EstadoEjecucion.RECHAZADA
    assert dict(actualizado.expectativas.campos) == {}


async def test_actualizar_con_expectativa_de_campo_sensible_se_rechaza(base):
    servicio = _servicio(base)
    creado = await servicio.crear(
        DatosNuevoEscenario(
            nombre="X", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO, monto=Decimal("10.00")
        )
    )
    campo_sensible = next(iter(CAMPOS_SENSIBLES))
    with pytest.raises(ValueError):
        await servicio.actualizar(
            creado.escenario_id,
            DatosEdicionEscenario(
                nombre="X", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO,
                monto=Decimal("10.00"),
                expectativas=Expectativas(campos={campo_sensible: ExpectativaCampo(tipo="presente")}),
            ),
        )


async def test_diagnosticar_detecta_un_campo_esperado_que_ya_no_esta_permitido(base):
    servicio = _servicio(base)
    campo_sensible = next(iter(CAMPOS_SENSIBLES))
    creado = await servicio.crear(
        DatosNuevoEscenario(
            nombre="X", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO, monto=Decimal("10.00"),
            expectativas=Expectativas(estado=EstadoEjecucion.APROBADA),
        )
    )
    # Se fuerza directamente en el objeto de dominio (bypass de la validacion
    # de `crear`): simula una politica que se volvio mas estricta despues.
    con_campo_ahora_prohibido = replace(
        creado,
        expectativas=Expectativas(campos={campo_sensible: ExpectativaCampo(tipo="presente")}),
    )
    diagnostico = await servicio.diagnosticar(con_campo_ahora_prohibido)
    assert diagnostico.bloqueado
    assert any(campo_sensible in problema for problema in diagnostico.incompatibilidades)


async def test_diagnosticar_detecta_perfil_distinto(base):
    from sibutestlab8583.profiles.generico import PerfilDeMarca

    servicio = _servicio(base)
    creado = await servicio.crear(
        DatosNuevoEscenario(
            nombre="X", card_id=CARD_ID_DEMO, conexion_id=DESTINO_ID_DEMO, monto=Decimal("10.00")
        )
    )
    con_perfil_falso = replace(creado, perfil="otro-perfil-hipotetico")

    diagnostico = await servicio.diagnosticar(con_perfil_falso)
    assert diagnostico.bloqueado
    assert len(diagnostico.incompatibilidades) == 1
    assert "otro-perfil-hipotetico" in diagnostico.incompatibilidades[0]

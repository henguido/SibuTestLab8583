"""`Orquestador.ejecutar_compra` con `escenario_id`/`escenario_nombre`.

El orquestador no sabe que es un escenario -no importa `application.escenarios`
ni conoce `RepositorioEscenarios`-: solo copia lo que el llamador ya resolvio
a la `Ejecucion`, para trazabilidad en el historial. Reejecutar un escenario
es, literalmente, llamar esto con el mismo `DatosCompra` de siempre: no hay
una segunda ruta de ejecucion en el dominio.

`ejecuciones.escenario_id` es una FK real hacia `escenarios`, asi que estas
pruebas siembran una fila de escenario antes de asociarla -igual que ya hace
falta sembrar una tarjeta real para `ejecuciones.card_id`-.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from conftest import TransporteFalso, construir_orquestador

from sibutestlab8583.adapters.persistence.esquema import CARD_ID_DEMO, DESTINO_ID_DEMO
from sibutestlab8583.adapters.persistence.sqlite_repos import (
    RepositorioDestinosSQLite,
    RepositorioEjecucionesSQLite,
    RepositorioEscenariosSQLite,
    RepositorioTarjetasSQLite,
)
from sibutestlab8583.application.escenarios import (
    DatosEdicionEscenario,
    DatosNuevoEscenario,
    ServicioEscenarios,
)
from sibutestlab8583.domain.modelos import (
    CAMPOS_SENSIBLES,
    DatosCompra,
    Escenario,
    EstadoEjecucion,
    ExpectativaCampo,
    Expectativas,
)
from sibutestlab8583.profiles.generico import PERFIL_GENERICO


async def _sembrar_escenario(base, escenario_id: str, nombre: str, card_id: str = CARD_ID_DEMO):
    await RepositorioEscenariosSQLite(base).guardar(
        Escenario(
            escenario_id=escenario_id,
            nombre=nombre,
            perfil="generico",
            mti="0100",
            card_id=card_id,
            conexion_id="LOCAL-DEMO",
            monto=Decimal("10.00"),
        )
    )


async def test_ejecutar_compra_sin_escenario_no_persiste_ninguna_referencia(base, datos_compra):
    resultado = await construir_orquestador(base, TransporteFalso(codigo="00")).ejecutar_compra(
        datos_compra
    )
    assert resultado.ejecucion.escenario_id is None
    assert resultado.ejecucion.escenario_nombre is None


async def test_ejecutar_compra_con_escenario_copia_id_y_nombre_a_la_ejecucion(base, datos_compra):
    await _sembrar_escenario(base, "ESC-01", "Compra aprobada CRC")
    resultado = await construir_orquestador(base, TransporteFalso(codigo="00")).ejecutar_compra(
        datos_compra, escenario_id="ESC-01", escenario_nombre="Compra aprobada CRC"
    )
    assert resultado.ejecucion.escenario_id == "ESC-01"
    assert resultado.ejecucion.escenario_nombre == "Compra aprobada CRC"


async def test_el_escenario_asociado_se_persiste_y_se_puede_releer(base, datos_compra):
    await _sembrar_escenario(base, "ESC-02", "Con persistencia real")
    await construir_orquestador(base, TransporteFalso(codigo="00")).ejecutar_compra(
        datos_compra, escenario_id="ESC-02", escenario_nombre="Con persistencia real"
    )
    guardadas = await RepositorioEjecucionesSQLite(base).listar()
    assert guardadas[0].escenario_id == "ESC-02"
    assert guardadas[0].escenario_nombre == "Con persistencia real"


async def test_una_ejecucion_no_enviada_tambien_conserva_el_escenario_asociado(base):
    """El escenario se copia en TODAS las ramas de `_registrar`, no solo en la
    de exito: una compra sin campos obligatorios sigue siendo trazable a su
    escenario de origen.
    """
    from sibutestlab8583.adapters.persistence.sqlite_repos import RepositorioTarjetasSQLite
    from sibutestlab8583.domain.datos_sinteticos import pan_sintetico
    from sibutestlab8583.domain.modelos import TarjetaPrueba

    await RepositorioTarjetasSQLite(base).guardar(
        TarjetaPrueba(card_id="SIN-VENC-ESC", pan=pan_sintetico("3333"), expiracion="")
    )
    await _sembrar_escenario(base, "ESC-03", "Con vencimiento vacío", card_id="SIN-VENC-ESC")
    resultado = await construir_orquestador(base, TransporteFalso()).ejecutar_compra(
        DatosCompra(card_id="SIN-VENC-ESC", monto=Decimal("10.00")),
        escenario_id="ESC-03",
        escenario_nombre="Con vencimiento vacío",
    )
    assert resultado.ejecucion.escenario_id == "ESC-03"


async def test_reejecutar_es_la_misma_llamada_que_una_compra_nueva(base):
    """No hay una segunda ruta de "reejecucion" en el dominio: es literalmente
    `ejecutar_compra` de nuevo, con el `DatosCompra` que el escenario guarda.
    """
    await _sembrar_escenario(base, "ESC-04", "X")
    datos = DatosCompra(
        card_id=CARD_ID_DEMO, monto=Decimal("42.00"), campos_manuales={"37": "REF-1"}
    )
    orquestador = construir_orquestador(base, TransporteFalso(codigo="00"))

    primera = await orquestador.ejecutar_compra(datos, escenario_id="ESC-04", escenario_nombre="X")
    segunda = await orquestador.ejecutar_compra(datos, escenario_id="ESC-04", escenario_nombre="X")

    assert primera.ejecucion.id != segunda.ejecucion.id
    assert primera.ejecucion.escenario_id == segunda.ejecucion.escenario_id == "ESC-04"
    # El STAN es distinto -viene de una secuencia real-, prueba de que cada
    # reejecucion es una ejecucion nueva, no una reutilizada.
    assert primera.ejecucion.stan != segunda.ejecucion.stan


async def test_renombrar_un_escenario_no_altera_el_nombre_ya_registrado_en_el_historico(base):
    """`escenario_nombre` en `Ejecucion` es una copia, no una referencia: el
    historico debe seguir mostrando el nombre vigente EN EL MOMENTO de esa
    ejecucion, aunque el escenario se renombre despues. Es el mismo principio
    que ya protege `destino_host`/`destino_puerto` frente a editar una
    conexion (ver `Ejecucion` en domain/modelos.py).
    """
    servicio = ServicioEscenarios(
        RepositorioEscenariosSQLite(base),
        RepositorioTarjetasSQLite(base),
        RepositorioDestinosSQLite(base),
        PERFIL_GENERICO,
    )

    # 1. Crear el escenario con su nombre original.
    creado = await servicio.crear(
        DatosNuevoEscenario(
            nombre="Compra aprobada CRC",
            card_id=CARD_ID_DEMO,
            conexion_id=DESTINO_ID_DEMO,
            monto=Decimal("10.00"),
        )
    )

    # 2. Ejecutarlo -exactamente como lo haria la web, pasando el id y el
    #    nombre YA resueltos del escenario en ese momento-.
    orquestador = construir_orquestador(base, TransporteFalso(codigo="00"))
    resultado = await orquestador.ejecutar_compra(
        DatosCompra(
            card_id=creado.card_id, monto=creado.monto, campos_manuales=creado.campos_manuales
        ),
        escenario_id=creado.escenario_id,
        escenario_nombre=creado.nombre,
    )

    # 3. La Ejecucion persistida trae el id y el nombre de ese momento.
    assert resultado.ejecucion.escenario_id == creado.escenario_id
    assert resultado.ejecucion.escenario_nombre == "Compra aprobada CRC"

    # 4. Renombrar el escenario.
    await servicio.actualizar(
        creado.escenario_id,
        DatosEdicionEscenario(
            nombre="Compra aprobada CRC v2",
            card_id=creado.card_id,
            conexion_id=creado.conexion_id,
            monto=creado.monto,
            campos_manuales=creado.campos_manuales,
        ),
    )

    # 5-6. La ejecucion historica, releida de la base, sigue mostrando el
    #      nombre con el que se registro -no el nombre actual del escenario-.
    historica = await RepositorioEjecucionesSQLite(base).obtener(resultado.ejecucion.id)
    assert historica.escenario_id == creado.escenario_id
    assert historica.escenario_nombre == "Compra aprobada CRC"

    # 7. Una ejecucion NUEVA, posterior al renombre, si debe llevar el nombre
    #    vigente -al reejecutar, quien llama vuelve a resolver el escenario y
    #    le pasa su nombre de HOY, no el que tenia al crearse-.
    actualizado = await servicio.obtener(creado.escenario_id)
    nueva = await orquestador.ejecutar_compra(
        DatosCompra(
            card_id=actualizado.card_id,
            monto=actualizado.monto,
            campos_manuales=actualizado.campos_manuales,
        ),
        escenario_id=actualizado.escenario_id,
        escenario_nombre=actualizado.nombre,
    )
    assert nueva.ejecucion.escenario_nombre == "Compra aprobada CRC v2"

    # La primera ejecucion, releida una vez mas, sigue intacta.
    historica_de_nuevo = await RepositorioEjecucionesSQLite(base).obtener(resultado.ejecucion.id)
    assert historica_de_nuevo.escenario_nombre == "Compra aprobada CRC"


# --------------------------------------------------------- expectativas ---
#
# El orquestador NO conoce escenarios, pero SI evalua expectativas -es una
# funcion de dominio pura que el orquestador aplica el mismo, igual que ya
# aplica RN-1/RN-3-. Estas pruebas verifican que la evaluacion se calcule y
# se persista correctamente en cada rama, y sobre todo que quede congelada:
# editar el escenario despues NUNCA debe cambiar una evaluacion ya registrada.


async def test_sin_expectativas_no_persiste_evaluacion(base, datos_compra):
    resultado = await construir_orquestador(base, TransporteFalso(codigo="00")).ejecutar_compra(
        datos_compra
    )
    assert resultado.ejecucion.evaluacion_estado is None
    assert resultado.ejecucion.evaluacion_json is None


async def test_expectativa_de_estado_cumplida_persiste_pass(base, datos_compra):
    resultado = await construir_orquestador(base, TransporteFalso(codigo="00")).ejecutar_compra(
        datos_compra, expectativas=Expectativas(estado=EstadoEjecucion.APROBADA)
    )
    assert resultado.ejecucion.evaluacion_estado == "pass"

    guardada = await RepositorioEjecucionesSQLite(base).obtener(resultado.ejecucion.id)
    assert guardada.evaluacion_estado == "pass"
    assert guardada.evaluacion_json is not None


async def test_expectativa_de_estado_incumplida_persiste_fail(base, datos_compra):
    resultado = await construir_orquestador(base, TransporteFalso(codigo="05")).ejecutar_compra(
        datos_compra, expectativas=Expectativas(estado=EstadoEjecucion.APROBADA)
    )
    assert resultado.ejecucion.evaluacion_estado == "fail"


async def test_expectativa_de_campo_igual_cumplida_es_pass(base, datos_compra):
    resultado = await construir_orquestador(base, TransporteFalso(codigo="00")).ejecutar_compra(
        datos_compra,
        expectativas=Expectativas(campos={"39": ExpectativaCampo(tipo="igual", valor="00")}),
    )
    assert resultado.ejecucion.evaluacion_estado == "pass"


async def test_expectativa_de_campo_igual_incumplida_es_fail(base, datos_compra):
    resultado = await construir_orquestador(base, TransporteFalso(codigo="05")).ejecutar_compra(
        datos_compra,
        expectativas=Expectativas(campos={"39": ExpectativaCampo(tipo="igual", valor="00")}),
    )
    assert resultado.ejecucion.evaluacion_estado == "fail"


async def test_expectativa_de_campo_presente_y_ausente(base, datos_compra):
    """DE38 (codigo de autorizacion) no forma parte de la correlacion RN-3
    del perfil generico, asi que el doble de transporte nunca lo incluye en
    la respuesta: es un campo genuinamente ausente para esta prueba.
    """
    resultado_ausente = await construir_orquestador(base, TransporteFalso(codigo="00")).ejecutar_compra(
        datos_compra, expectativas=Expectativas(campos={"38": ExpectativaCampo(tipo="ausente")})
    )
    assert resultado_ausente.ejecucion.evaluacion_estado == "pass"

    resultado_presente = await construir_orquestador(base, TransporteFalso(codigo="00")).ejecutar_compra(
        datos_compra, expectativas=Expectativas(campos={"38": ExpectativaCampo(tipo="presente")})
    )
    assert resultado_presente.ejecucion.evaluacion_estado == "fail"


async def test_timeout_esperado_y_obtenido_persiste_pass(base, datos_compra):
    from sibutestlab8583.domain.modelos import TiempoAgotado

    resultado = await construir_orquestador(
        base, TransporteFalso(TiempoAgotado(limite_segundos=0.01)), tiempo_limite=0.01
    ).ejecutar_compra(datos_compra, expectativas=Expectativas(estado=EstadoEjecucion.TIMEOUT))
    assert resultado.ejecucion.evaluacion_estado == "pass"


async def test_evaluacion_json_no_contiene_ningun_campo_sensible(base, datos_compra):
    """Defensa en profundidad a nivel de persistencia: aunque alguien lograra
    construir una `Expectativas` con un campo sensible (bypaseando
    `validar_expectativas`), el snapshot solo serializa los campos que la
    propia expectativa declara -nunca "todos los campos que llegaron"-, asi
    que el PAN nunca podria aparecer aqui de todos modos.
    """
    resultado = await construir_orquestador(base, TransporteFalso(codigo="00")).ejecutar_compra(
        datos_compra, expectativas=Expectativas(campos={"39": ExpectativaCampo(tipo="igual", valor="00")})
    )
    assert "2" not in resultado.ejecucion.evaluacion_json
    assert "35" not in resultado.ejecucion.evaluacion_json


async def test_editar_las_expectativas_del_escenario_no_altera_la_evaluacion_ya_registrada(base):
    """El caso critico del Bloque 3: una ejecucion historica es un snapshot.
    Cambiar las expectativas del escenario despues no debe voltear un PASS a
    FAIL (ni viceversa) en una ejecucion ya persistida -mismo principio que ya
    protege `escenario_nombre` frente a un renombre-.
    """
    servicio = ServicioEscenarios(
        RepositorioEscenariosSQLite(base),
        RepositorioTarjetasSQLite(base),
        RepositorioDestinosSQLite(base),
        PERFIL_GENERICO,
    )
    creado = await servicio.crear(
        DatosNuevoEscenario(
            nombre="Con expectativa de aprobacion",
            card_id=CARD_ID_DEMO,
            conexion_id=DESTINO_ID_DEMO,
            monto=Decimal("10.00"),
            expectativas=Expectativas(estado=EstadoEjecucion.APROBADA),
        )
    )

    orquestador = construir_orquestador(base, TransporteFalso(codigo="00"))
    resultado = await orquestador.ejecutar_compra(
        DatosCompra(card_id=creado.card_id, monto=creado.monto),
        escenario_id=creado.escenario_id,
        escenario_nombre=creado.nombre,
        expectativas=creado.expectativas,
    )
    assert resultado.ejecucion.evaluacion_estado == "pass"

    # Se edita el escenario para esperar ahora lo opuesto.
    await servicio.actualizar(
        creado.escenario_id,
        DatosEdicionEscenario(
            nombre=creado.nombre,
            card_id=creado.card_id,
            conexion_id=creado.conexion_id,
            monto=creado.monto,
            expectativas=Expectativas(estado=EstadoEjecucion.RECHAZADA),
        ),
    )

    # La ejecucion historica, releida de la base, conserva su PASS original.
    historica = await RepositorioEjecucionesSQLite(base).obtener(resultado.ejecucion.id)
    assert historica.evaluacion_estado == "pass"
    import json

    assert json.loads(historica.evaluacion_json)["expectativas"]["estado"] == "aprobada"


# ----------------------------------------- frontera de seguridad en el orquestador ---
#
# La garantia "un campo sensible nunca llega a evaluacion_json" no puede
# depender solo de que la peticion haya pasado por web/app.py o por
# ServicioEscenarios: el Orquestador es reutilizable directamente por
# cualquier llamador interno (un futuro motor de regresion o de carga, por
# ejemplo), y ese llamador podria construir un `Expectativas` a mano sin pasar
# por ninguna validacion previa. Estas pruebas llaman a `ejecutar_compra`
# igual que ese llamador interno lo haria: sin pasar por la web ni por
# `ServicioEscenarios` en absoluto.


async def test_orquestador_directo_con_expectativa_de2_se_rechaza_y_no_persiste_nada(
    base, datos_compra
):
    expectativas = Expectativas(
        campos={"2": ExpectativaCampo(tipo="igual", valor="VALOR-SINTETICO")}
    )
    with pytest.raises(ValueError):
        await construir_orquestador(base, TransporteFalso(codigo="00")).ejecutar_compra(
            datos_compra, expectativas=expectativas
        )

    assert await RepositorioEjecucionesSQLite(base).listar() == []


async def test_orquestador_directo_con_expectativa_de35_se_rechaza_y_no_persiste_nada(
    base, datos_compra
):
    expectativas = Expectativas(
        campos={"35": ExpectativaCampo(tipo="presente")}
    )
    with pytest.raises(ValueError):
        await construir_orquestador(base, TransporteFalso(codigo="00")).ejecutar_compra(
            datos_compra, expectativas=expectativas
        )

    assert await RepositorioEjecucionesSQLite(base).listar() == []


async def test_orquestador_directo_con_campo_sensible_generico_se_rechaza(base, datos_compra):
    """Generaliza la prueba anterior a todo `CAMPOS_SENSIBLES`, no solo DE2/DE35."""
    for campo_sensible in CAMPOS_SENSIBLES:
        expectativas = Expectativas(campos={campo_sensible: ExpectativaCampo(tipo="presente")})
        with pytest.raises(ValueError):
            await construir_orquestador(base, TransporteFalso(codigo="00")).ejecutar_compra(
                datos_compra, expectativas=expectativas
            )
    assert await RepositorioEjecucionesSQLite(base).listar() == []


async def test_orquestador_directo_con_campo_no_permitido_por_el_perfil_se_rechaza(
    base, datos_compra
):
    """No solo sensibles: un numero que el perfil ni siquiera declara en su
    especificacion para el MTI de respuesta tambien debe rechazarse.
    """
    expectativas = Expectativas(campos={"999": ExpectativaCampo(tipo="presente")})
    with pytest.raises(ValueError):
        await construir_orquestador(base, TransporteFalso(codigo="00")).ejecutar_compra(
            datos_compra, expectativas=expectativas
        )

    assert await RepositorioEjecucionesSQLite(base).listar() == []


async def test_orquestador_directo_con_expectativa_de39_valida_sigue_funcionando(
    base, datos_compra
):
    """El endurecimiento no debe romper el camino feliz: DE39 sigue permitido,
    y la ejecucion se evalua y persiste con normalidad.
    """
    expectativas = Expectativas(campos={"39": ExpectativaCampo(tipo="igual", valor="00")})
    resultado = await construir_orquestador(base, TransporteFalso(codigo="00")).ejecutar_compra(
        datos_compra, expectativas=expectativas
    )
    assert resultado.ejecucion.evaluacion_estado == "pass"
    assert len(await RepositorioEjecucionesSQLite(base).listar()) == 1

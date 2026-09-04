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
from sibutestlab8583.domain.modelos import DatosCompra, Escenario
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

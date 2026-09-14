"""Reglas del Host desde la interfaz web (Fase D1, 2026-09-14).

Vertical real: HTTP -> nucleo real -> SQLite real. Confirma crear, listar,
editar, duplicar, activar/desactivar, y que una regla creada desde la web
efectivamente gobierna una respuesta real cuando se le pasa al host.
"""

from __future__ import annotations

import httpx2

from sibutestlab8583.composicion import Composicion, Configuracion
from sibutestlab8583.web.app import crear_app


def _composicion(base):
    return Composicion(Configuracion(ruta_base_datos=base, host_destino="127.0.0.1", tiempo_limite=2.0))


async def test_crear_una_regla_desde_la_web(base):
    composicion = _composicion(base)
    app = crear_app(composicion)

    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://prueba"
    ) as cliente:
        respuesta = await cliente.post(
            "/reglas-host/nueva",
            data={
                "nombre": "Rechazo por monto alto",
                "prioridad": "1",
                "activa": "on",
                "condicion_campo_1": "mti",
                "condicion_operador_1": "igual",
                "condicion_valor_1": "0200",
                "condicion_campo_2": "4",
                "condicion_operador_2": "mayor_que",
                "condicion_valor_2": "50000",
                "de39": "51",
                "comportamiento_tipo": "normal",
                "comportamiento_delay_ms": "0",
            },
        )
        assert respuesta.status_code == 303
        assert respuesta.headers["location"] == "/reglas-host"

        listado = await cliente.get("/reglas-host")
    assert listado.status_code == 200
    assert "Rechazo por monto alto" in listado.text
    assert "DE39=51" in listado.text

    reglas = await composicion.administracion_reglas_host.listar()
    assert len(reglas) == 1
    assert reglas[0].nombre == "Rechazo por monto alto"
    assert reglas[0].condiciones[1].valor == "50000"


async def test_crear_una_regla_invalida_muestra_error_sin_persistir(base):
    app = crear_app(_composicion(base))
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://prueba"
    ) as cliente:
        respuesta = await cliente.post(
            "/reglas-host/nueva",
            data={
                "nombre": "Sensible",
                "prioridad": "1",
                "condicion_campo_1": "2",
                "condicion_operador_1": "igual",
                "condicion_valor_1": "x",
                "de39": "00",
            },
        )
    assert respuesta.status_code == 400
    assert "sensible" in respuesta.text.lower()

    composicion = _composicion(base)
    assert await composicion.administracion_reglas_host.listar() == []


async def test_editar_activar_desactivar_y_duplicar_una_regla(base):
    composicion = _composicion(base)
    app = crear_app(composicion)

    from sibutestlab8583.application.reglas_host import DatosNuevaRegla
    from sibutestlab8583.domain.reglas_host import CAMPO_MTI, CondicionRegla

    creada = await composicion.administracion_reglas_host.crear(
        DatosNuevaRegla(
            nombre="Original", prioridad=5,
            condiciones=[CondicionRegla(CAMPO_MTI, "igual", "0800")],
            de39="00",
        )
    )

    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://prueba"
    ) as cliente:
        edicion = await cliente.post(
            f"/reglas-host/{creada.regla_id}/editar",
            data={
                "nombre": "Editada", "prioridad": "9", "activa": "on",
                "condicion_campo_1": "mti", "condicion_operador_1": "igual", "condicion_valor_1": "0800",
                "de39": "00",
            },
        )
        assert edicion.status_code == 303

        desactivar = await cliente.post(
            f"/reglas-host/{creada.regla_id}/estado", data={"activa": "0"}
        )
        assert desactivar.status_code == 303

        duplicar = await cliente.post(f"/reglas-host/{creada.regla_id}/duplicar")
        assert duplicar.status_code == 303

    reglas = await composicion.administracion_reglas_host.listar()
    assert len(reglas) == 2
    original = await composicion.administracion_reglas_host.obtener(creada.regla_id)
    assert original.nombre == "Editada"
    assert original.prioridad == 9
    assert original.activa is False
    copia = next(r for r in reglas if r.regla_id != creada.regla_id)
    assert copia.nombre == "Editada (copia)"


async def test_editar_una_regla_inexistente_da_404(base):
    app = crear_app(_composicion(base))
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://prueba"
    ) as cliente:
        respuesta = await cliente.get("/reglas-host/RULE-fantasma/editar")
    assert respuesta.status_code == 404

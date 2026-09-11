"""Capa web con dobles del orquestador.

Se prueba la interfaz, no el nucleo: el nucleo ya tiene sus propias pruebas. Lo
que importa aqui es que cada desenlace se presente distinto, que un error de
entrada no produzca un 500 y que el PAN completo no llegue nunca al navegador.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sibutestlab8583.adapters.iso8583.codec import CodecIso8583
from sibutestlab8583.adapters.persistence.esquema import (
    CARD_ID_DEMO,
    DESTINO_HOST_DEMO,
    DESTINO_ID_DEMO,
    DESTINO_NOMBRE_DEMO,
    DESTINO_PUERTO_DEMO,
    PAN_DEMO,
)
from sibutestlab8583.application.consultas import PaginaHistorial, TarjetaListada
from sibutestlab8583.application.conexiones import ServicioConexiones
from sibutestlab8583.application.tarjetas import ServicioTarjetas
from sibutestlab8583.domain.datos_sinteticos import monto_iso
from sibutestlab8583.application.orquestador import TarjetaDesconocida
from sibutestlab8583.domain.modelos import (
    MTI_RESPUESTA_COMPRA,
    CampoInterpretado,
    DestinoGuardado,
    Ejecucion,
    EstadoEjecucion,
    MensajeInterpretado,
    MensajeIso,
    ResultadoCompra,
    TarjetaPrueba,
)
from sibutestlab8583.profiles.generico import METADATOS_CAMPOS_0100, PERFIL_GENERICO
from sibutestlab8583.web.app import crear_app

MOMENTO = datetime(2026, 8, 19, 12, 0, 0, tzinfo=timezone.utc)


class ConsultasFalsas:
    def __init__(self, ejecuciones=()):
        self._ejecuciones = list(ejecuciones)

    async def tarjetas(self):
        return [
            TarjetaListada(
                card_id=CARD_ID_DEMO,
                pan_enmascarado="************6666",
                descripcion="Tarjeta de demostración",
                sintetica=True,
            )
        ]

    async def ejecuciones_recientes(self, limite=20):
        return self._ejecuciones

    async def historial(self, filtro, pagina=1, tam_pagina=20):
        """Filtra y pagina en memoria -mismo comportamiento observable que el
        repositorio SQLite real, para un doble que nunca abre una base-.
        """
        def cumple(ejecucion) -> bool:
            if filtro.desde and ejecucion.creada_en.date().isoformat() < filtro.desde:
                return False
            if filtro.hasta and ejecucion.creada_en.date().isoformat() > filtro.hasta:
                return False
            if filtro.estado is not None and ejecucion.estado != filtro.estado:
                return False
            if filtro.evaluacion == "sin_expectativas" and ejecucion.evaluacion_estado is not None:
                return False
            if filtro.evaluacion in ("pass", "fail") and ejecucion.evaluacion_estado != filtro.evaluacion:
                return False
            if filtro.card_id and ejecucion.card_id != filtro.card_id:
                return False
            if filtro.destino:
                destino = f"{ejecucion.destino_host or ''}:{ejecucion.destino_puerto or ''}"
                if filtro.destino not in destino:
                    return False
            if filtro.stan and filtro.stan not in ejecucion.stan:
                return False
            return True

        coinciden = [e for e in self._ejecuciones if cumple(e)]
        total = len(coinciden)
        inicio = (pagina - 1) * tam_pagina
        pagina_items = coinciden[inicio : inicio + tam_pagina]
        return PaginaHistorial(
            ejecuciones=pagina_items, total=total, pagina=pagina, tam_pagina=tam_pagina
        )

    async def detalle_ejecucion(self, id_ejecucion):
        """Detalle de la ejecucion que se le haya dado, interpretada de verdad.

        Usa el mismo `interpretar()` que la aplicacion real: el doble sustituye
        la persistencia, no la logica de lectura.
        """
        from sibutestlab8583.application.consultas import DetalleEjecucion
        from sibutestlab8583.application.serializacion import interpretar

        for ejecucion in self._ejecuciones:
            if ejecucion.id == id_ejecucion:
                return DetalleEjecucion(
                    ejecucion=ejecucion,
                    solicitud=interpretar(
                        ejecucion.solicitud_json, ejecucion.solicitud_enmascarada
                    ),
                    respuesta=interpretar(
                        ejecucion.respuesta_json, ejecucion.respuesta_enmascarada
                    ),
                )
        return None


class RepositorioTarjetasFalso:
    """Doble en memoria de `RepositorioTarjetas`, para probar la web sin SQLite.

    `ServicioTarjetas` es real: lo que se sustituye es solo la persistencia,
    igual que `ConsultasFalsas` sustituye la lectura de ejecuciones. Asi la
    validacion de negocio (PAN, Luhn, vencimiento) se ejercita de verdad en las
    pruebas de la capa web, no se reimplementa en un doble.
    """

    def __init__(self, tarjetas=()):
        self._tarjetas = {t.card_id: t for t in tarjetas}

    async def obtener(self, card_id):
        return self._tarjetas.get(card_id)

    async def listar(self):
        return sorted(self._tarjetas.values(), key=lambda t: t.card_id)

    async def guardar(self, tarjeta):
        self._tarjetas[tarjeta.card_id] = tarjeta


class RepositorioDestinosFalso:
    """Doble en memoria de `RepositorioDestinos`, mismo patron que las tarjetas.

    El nombre sigue siendo "destinos" porque es el puerto de dominio existente
    (`domain.puertos.RepositorioDestinos`, de una fase anterior); la capa de
    aplicacion que lo consume presenta el concepto como "conexion".
    """

    def __init__(self, destinos=()):
        self._destinos = {d.destino_id: d for d in destinos}

    async def obtener(self, destino_id):
        return self._destinos.get(destino_id)

    async def listar(self):
        return sorted(self._destinos.values(), key=lambda d: d.destino_id)

    async def guardar(self, destino):
        self._destinos[destino.destino_id] = destino


class RepositorioEscenariosFalso:
    """Doble en memoria de `RepositorioEscenarios`, mismo patron que las tarjetas.

    `ruta_espejo`, si se pasa, es la base SQLite real que usan las suites de
    este mismo archivo (`ComposicionFalsa`): esa base SI aplica la FK de
    `suite_escenarios.escenario_id -> escenarios.escenario_id`, asi que cada
    escenario que se guarda aqui (en memoria) se refleja tambien alli, con
    una fila minima -mismo criterio que un espejo de solo lo indispensable
    para que la restriccion de integridad no falle en un doble que nunca
    pretendio ser la base real de escenarios.
    """

    def __init__(self, escenarios=(), *, ruta_espejo=None):
        self._escenarios = {e.escenario_id: e for e in escenarios}
        self._ruta_espejo = ruta_espejo

    async def obtener(self, escenario_id):
        return self._escenarios.get(escenario_id)

    async def listar(self):
        return sorted(self._escenarios.values(), key=lambda e: e.nombre)

    async def guardar(self, escenario):
        self._escenarios[escenario.escenario_id] = escenario
        if self._ruta_espejo is not None:
            self._reflejar(escenario)

    def _reflejar(self, escenario) -> None:
        import json
        import sqlite3

        with sqlite3.connect(self._ruta_espejo) as conexion:
            conexion.execute(
                "INSERT INTO escenarios"
                " (escenario_id, nombre, perfil, mti, card_id, conexion_id, monto,"
                "  campos_json, expected_json, activo, creado_en, actualizado_en)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                " ON CONFLICT(escenario_id) DO UPDATE SET"
                "   nombre = excluded.nombre, activo = excluded.activo",
                (
                    escenario.escenario_id, escenario.nombre, escenario.perfil, escenario.mti,
                    escenario.card_id, escenario.conexion_id, str(escenario.monto),
                    json.dumps({"version": 1, "campos": dict(escenario.campos_manuales)}),
                    None, int(escenario.activo),
                    escenario.creado_en.isoformat(), escenario.actualizado_en.isoformat(),
                ),
            )
            conexion.commit()


#: Conexion de demostracion para los dobles de la capa web, mismo identificador
#: y valores que siembra `esquema.py`.
_CONEXION_DEMO_FALSA = DestinoGuardado(
    destino_id=DESTINO_ID_DEMO,
    nombre=DESTINO_NOMBRE_DEMO,
    host=DESTINO_HOST_DEMO,
    puerto=DESTINO_PUERTO_DEMO,
    activo=True,
)


class OrquestadorFalso:
    def __init__(self, resultado=None, error=None):
        self._resultado = resultado
        self._error = error
        #: Ultimos `DatosCompra` recibidos, para que las pruebas de la capa web
        #: verifiquen lo que `_interpretar_formulario` de verdad construyo, sin
        #: necesitar un orquestador real ni SQLite.
        self.ultimos_datos = None
        #: Ultimo escenario asociado (id, nombre) con el que se llamo, o
        #: (None, None) si la ejecucion no partio de ninguno.
        self.ultimo_escenario_id = None
        self.ultimo_escenario_nombre = None
        #: Ultimas `Expectativas` recibidas (o None), para que las pruebas
        #: verifiquen que `/compra` lee y reenvia lo que el formulario trae.
        self.ultimas_expectativas = None
        #: Ruta de la base real de suites (asignada por `ComposicionFalsa`,
        #: si corresponde). El `Ejecucion` enlatado que este doble devuelve
        #: nunca pasa por `RepositorioEjecucionesSQLite.guardar` -no hay
        #: persistencia real detras de este orquestador-, pero
        #: `RepositorioCorridasSuiteSQLite.actualizar_item` SI exige que
        #: `ejecucion_id` exista de verdad en `ejecuciones` (FK). Por eso se
        #: refleja aqui la fila minima que le corresponde, la primera vez que
        #: se devuelve ese `Ejecucion` enlatado -mismo principio que ya usa
        #: `RepositorioEscenariosFalso._reflejar` para escenarios.
        self._ruta_espejo = None
        self._ejecucion_reflejada = False

    async def ejecutar_compra(
        self, datos, *, escenario_id=None, escenario_nombre=None, expectativas=None
    ):
        self.ultimos_datos = datos
        self.ultimo_escenario_id = escenario_id
        self.ultimo_escenario_nombre = escenario_nombre
        self.ultimas_expectativas = expectativas
        if self._error is not None:
            raise self._error
        if (
            self._resultado is not None
            and self._ruta_espejo is not None
            and not self._ejecucion_reflejada
        ):
            self._reflejar_ejecucion()
        return self._resultado

    def _reflejar_ejecucion(self) -> None:
        import sqlite3

        ejecucion = self._resultado.ejecucion
        with sqlite3.connect(self._ruta_espejo) as conexion:
            conexion.execute(
                "INSERT OR IGNORE INTO ejecuciones"
                " (id, creada_en, card_id, mti_solicitud, monto, moneda, stan, estado)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    ejecucion.id, ejecucion.creada_en.isoformat(), ejecucion.card_id,
                    ejecucion.mti_solicitud, str(ejecucion.monto), ejecucion.moneda,
                    ejecucion.stan, ejecucion.estado.value,
                ),
            )
            conexion.commit()
        self._ejecucion_reflejada = True


#: Tarjeta de demostracion para los dobles de la capa web. El PAN es el mismo
#: que ya siembra `esquema.py` (generado en ejecucion, nunca literal).
_TARJETA_DEMO_FALSA = TarjetaPrueba(
    card_id=CARD_ID_DEMO,
    pan=PAN_DEMO,
    expiracion="3012",
    descripcion="Tarjeta de demostración",
    sintetica=True,
    activa=True,
)


class ComposicionFalsa:
    def __init__(
        self,
        resultado=None,
        error=None,
        ejecuciones=(),
        tarjetas=None,
        destinos=None,
        escenarios=None,
        verificador_conexion=None,
    ):
        from sibutestlab8583.application.escenarios import ServicioEscenarios
        from sibutestlab8583.composicion import Configuracion

        self.configuracion = Configuracion(
            ruta_base_datos="no-se-usa.db", host_destino="127.0.0.1", puerto_destino=8583
        )
        self.consultas = ConsultasFalsas(ejecuciones)
        self.descripciones_de_campos = {"2": "Número de tarjeta (PAN)", "4": "Monto"}
        self.perfil = PERFIL_GENERICO
        self.metadatos_de_campos_0100 = METADATOS_CAMPOS_0100
        self._codec_real = CodecIso8583()
        self._orquestador = OrquestadorFalso(resultado, error)
        self._repositorio_tarjetas = RepositorioTarjetasFalso(
            tarjetas if tarjetas is not None else [_TARJETA_DEMO_FALSA]
        )
        self._repositorio_destinos = RepositorioDestinosFalso(
            destinos if destinos is not None else [_CONEXION_DEMO_FALSA]
        )
        self.administracion_tarjetas = ServicioTarjetas(self._repositorio_tarjetas)
        self.administracion_conexiones = ServicioConexiones(
            self._repositorio_destinos, verificador_conexion
        )

        from sibutestlab8583.adapters.persistence.sqlite_repos import (
            RepositorioCorridasSuiteSQLite,
            RepositorioSuitesSQLite,
        )
        from sibutestlab8583.application.corredor_suites import CorredorDeSuites
        from sibutestlab8583.application.suites import ServicioSuites

        # Las suites usan SQLite real -no hay un doble en memoria para ellas-
        # porque su repositorio necesita una base real (tablas + FKs) y este
        # archivo ya construye `ComposicionFalsa` sin ninguna: se abre una
        # base temporal propia, invisible para el resto de las pruebas de
        # este archivo, que no la tocan. El DDL se aplica sincronicamente
        # (sqlite3, no aiosqlite) porque `__init__` no es async. Se crea ANTES
        # que `RepositorioEscenariosFalso` para poder pasarle su ruta como
        # espejo: la FK real de `suite_escenarios` exige que el escenario
        # exista tambien en la tabla `escenarios` de esta base.
        import sqlite3
        import tempfile

        from sibutestlab8583.adapters.persistence.esquema import DDL

        self._ruta_suites = Path(tempfile.mkstemp(suffix=".db")[1])
        with sqlite3.connect(self._ruta_suites) as conexion:
            conexion.executescript(DDL)
        self._orquestador._ruta_espejo = self._ruta_suites

        self.administracion_escenarios = ServicioEscenarios(
            RepositorioEscenariosFalso(
                escenarios if escenarios is not None else [], ruta_espejo=self._ruta_suites
            ),
            self._repositorio_tarjetas,
            self._repositorio_destinos,
            PERFIL_GENERICO,
        )

        self._repositorio_suites = RepositorioSuitesSQLite(self._ruta_suites)
        self._repositorio_corridas_suite = RepositorioCorridasSuiteSQLite(self._ruta_suites)
        self.administracion_suites = ServicioSuites(
            self._repositorio_suites, self.administracion_escenarios._escenarios
        )
        self.corridas_suite = self._repositorio_corridas_suite
        self.corredor_suites = CorredorDeSuites(
            self.administracion_suites,
            self.administracion_escenarios,
            self._repositorio_corridas_suite,
            self.ejecutor_escenarios,
        )

        from sibutestlab8583.application.comparacion_corridas import ServicioComparacionCorridas

        self.comparador_corridas = ServicioComparacionCorridas(self._repositorio_corridas_suite)

    def bitmap_hex(self, mensaje):
        try:
            return self._codec_real.bitmap_hex(mensaje, self.perfil)
        except Exception:
            return None

    def raw_hex_seguro(self, mensaje):
        try:
            return self._codec_real.raw_hex_seguro(mensaje, self.perfil)
        except Exception:
            return None

    @property
    def vista_previa(self):
        from sibutestlab8583.application.vista_previa import ServicioVistaPrevia

        return ServicioVistaPrevia(self._repositorio_tarjetas, self._codec_real, self.perfil)

    async def orquestador(self, destino, *, tiempo_limite=None):
        #: Ultimo `DestinoTcp` y timeout con el que la web pidio un orquestador:
        #: permite verificar la resolucion servidor-autoritativa de la conexion
        #: sin montar un transporte real.
        self.ultimo_destino = destino
        self.ultimo_tiempo_limite = tiempo_limite
        return self._orquestador

    @property
    def ejecutor_escenarios(self):
        from sibutestlab8583.application.ejecutor_escenarios import EjecutorDeEscenarios

        return EjecutorDeEscenarios(
            self.administracion_escenarios,
            self.administracion_conexiones,
            lambda destino, tiempo_limite: self.orquestador(destino, tiempo_limite=tiempo_limite),
        )


def _resultado(
    estado, *, codigo=None, con_respuesta=True, motivos=(),
    escenario_id=None, escenario_nombre=None,
    evaluacion_estado=None, evaluacion_json=None,
):
    from sibutestlab8583.application.serializacion import (
        a_json_respuesta,
        a_json_solicitud,
        a_texto,
    )

    solicitud = MensajeIso("0100", {"2": "************6666", "4": monto_iso("15000")})
    respuesta = None
    if con_respuesta:
        respuesta = MensajeInterpretado(
            MTI_RESPUESTA_COMPRA,
            {"39": CampoInterpretado("39", codigo or "00", codigo or "00", "Código de respuesta")},
        )
    ejecucion = Ejecucion(
        id=11,
        card_id=CARD_ID_DEMO,
        monto=Decimal("150.00"),
        moneda="188",
        stan="000042",
        estado=estado,
        mti_respuesta=MTI_RESPUESTA_COMPRA if con_respuesta else None,
        codigo_respuesta=codigo,
        destino_host="127.0.0.1",
        destino_puerto=8583,
        # Las dos representaciones, como las escribe el orquestador real: el
        # doble sustituye la base de datos, no el formato de lo que guarda.
        solicitud_enmascarada=a_texto(solicitud),
        respuesta_enmascarada=a_texto(respuesta.como_mensaje()) if respuesta else None,
        solicitud_json=a_json_solicitud(solicitud, "generico"),
        respuesta_json=a_json_respuesta(respuesta, "generico") if respuesta else None,
        latencia_ms=7,
        escenario_id=escenario_id,
        escenario_nombre=escenario_nombre,
        evaluacion_estado=evaluacion_estado,
        evaluacion_json=evaluacion_json,
        creada_en=MOMENTO,
    )
    return ResultadoCompra(
        ejecucion=ejecucion,
        solicitud=solicitud,
        respuesta=respuesta,
        motivos=tuple(motivos),
    )


def _cliente(**kwargs) -> TestClient:
    return TestClient(crear_app(ComposicionFalsa(**kwargs)))


FORMULARIO = {"card_id": CARD_ID_DEMO, "monto": "150.00", "conexion_id": DESTINO_ID_DEMO}


# ------------------------------------------------------------------ pantalla --


def test_la_pantalla_de_compra_responde():
    respuesta = _cliente().get("/")
    assert respuesta.status_code == 200
    # El rotulo paso a "Nueva transaccion" (con tilde en la interfaz) en el
    # rediseno: la pantalla ya no habla de "compra" sino del recorrido completo.
    assert "Nueva transacción" in respuesta.text
    assert "SibuTestLab8583" in respuesta.text


def test_la_tarjeta_se_muestra_solo_enmascarada():
    texto = _cliente().get("/").text
    assert "************6666" in texto
    assert PAN_DEMO not in texto


def test_no_hay_campo_para_escribir_el_pan():
    """El PAN se obtiene por card_id; el usuario nunca lo teclea."""
    texto = _cliente().get("/").text.lower()
    assert 'name="card_id"' in texto
    for prohibido in ('name="pan"', 'name="numero_tarjeta"', 'name="tarjeta"'):
        assert prohibido not in texto


# ------------------------------------------------------------- cada desenlace --


def test_una_compra_aprobada_muestra_el_resultado():
    respuesta = _cliente(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00")).post(
        "/compra", data=FORMULARIO
    )
    assert respuesta.status_code == 200
    assert "Transacción aprobada" in respuesta.text
    assert "000042" in respuesta.text
    assert "7 ms" in respuesta.text


def test_el_resultado_muestra_el_bitmap_de_la_solicitud_y_la_respuesta():
    texto = _cliente(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00")).post(
        "/compra", data=FORMULARIO
    ).text
    assert texto.count("Bitmap") >= 2  # uno para la solicitud, otro para la respuesta
    assert "campos activos: 2, 4" in texto  # solicitud: los dos campos de _resultado()
    assert "campos activos: 39" in texto  # respuesta: solo el codigo de respuesta


def test_el_resultado_muestra_la_comparacion_request_vs_response():
    texto = _cliente(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00")).post(
        "/compra", data=FORMULARIO
    ).text
    assert "Request vs Response" in texto
    assert "Solo en la respuesta" in texto  # DE39 solo viaja en la respuesta
    # La comparacion Request/Response nunca usa el par pass/fail de Expected/Actual.
    assert 'chip--fail">Diferente' not in texto
    assert 'chip--pass">Coincide' not in texto


def test_la_comparacion_request_response_no_expone_el_pan_completo():
    texto = _cliente(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00")).post(
        "/compra", data=FORMULARIO
    ).text
    assert PAN_DEMO not in texto
    assert "************6666" in texto


def test_el_resultado_muestra_raw_hex_seguro_con_su_longitud():
    texto = _cliente(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00")).post(
        "/compra", data=FORMULARIO
    ).text
    assert "RAW/HEX" in texto
    assert "bytes" in texto
    assert "reconstruida" in texto  # rotulo explicito: no son los bytes reales transmitidos


def test_el_raw_hex_del_resultado_nunca_contiene_el_pan_completo():
    texto = _cliente(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00")).post(
        "/compra", data=FORMULARIO
    ).text
    assert PAN_DEMO not in texto


def test_un_rechazo_no_aparece_como_aprobacion():
    texto = _cliente(resultado=_resultado(EstadoEjecucion.RECHAZADA, codigo="05")).post(
        "/compra", data=FORMULARIO
    ).text
    assert "Transacción rechazada" in texto
    assert "Transacción aprobada" not in texto


def test_un_timeout_se_representa_distinto_de_un_rechazo():
    texto = _cliente(
        resultado=_resultado(EstadoEjecucion.TIMEOUT, con_respuesta=False)
    ).post("/compra", data=FORMULARIO).text
    assert "Sin respuesta" in texto
    assert "Transacción rechazada" not in texto
    assert "Transacción aprobada" not in texto
    assert 'class="aviso timeout"' in texto


def test_una_respuesta_invalida_no_aparece_como_exito():
    texto = _cliente(
        resultado=_resultado(
            EstadoEjecucion.INVALIDA, codigo="00", motivos=("el campo 11 no corresponde",)
        )
    ).post("/compra", data=FORMULARIO).text
    assert "Respuesta inválida" in texto
    assert "Transacción aprobada" not in texto
    assert "el campo 11 no corresponde" in texto


def test_un_mensaje_incompleto_se_distingue():
    texto = _cliente(
        resultado=_resultado(
            EstadoEjecucion.NO_ENVIADA, con_respuesta=False, motivos=("faltan campos: 14",)
        )
    ).post("/compra", data=FORMULARIO).text
    assert "no se envió" in texto
    assert 'class="aviso no-enviada"' in texto


def test_un_fallo_de_conexion_no_se_presenta_como_rechazo():
    """Ahora llega como resultado persistido, no como excepcion."""
    texto = _cliente(
        resultado=_resultado(EstadoEjecucion.ERROR_CONEXION, con_respuesta=False)
    ).post("/compra", data=FORMULARIO).text
    assert "No fue posible establecer conexión con el destino" in texto
    assert "Transacción rechazada" not in texto
    assert "Transacción aprobada" not in texto


# --------------------------------------------------------- expectativas ---


def test_sin_expectativas_el_resultado_no_muestra_pass_ni_fail():
    """Ausencia de expectativa nunca es un PASS implicito."""
    texto = _cliente(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00")).post(
        "/compra", data=FORMULARIO
    ).text
    assert "Sin expectativas" in texto
    assert 'data-evaluacion="pass"' not in texto
    assert 'data-evaluacion="fail"' not in texto


def test_una_evaluacion_pass_se_muestra_en_el_resultado():
    texto = _cliente(
        resultado=_resultado(
            EstadoEjecucion.APROBADA, codigo="00",
            evaluacion_estado="pass",
            evaluacion_json=(
                '{"version":1,"resultado":"pass",'
                '"expectativas":{"estado":"aprobada","campos":{}},"discrepancias":[]}'
            ),
        )
    ).post("/compra", data=FORMULARIO).text
    assert "PASS" in texto
    assert 'data-evaluacion="pass"' in texto


def test_una_evaluacion_fail_muestra_las_discrepancias():
    texto = _cliente(
        resultado=_resultado(
            EstadoEjecucion.RECHAZADA, codigo="05",
            evaluacion_estado="fail",
            evaluacion_json=(
                '{"version":1,"resultado":"fail",'
                '"expectativas":{"estado":"aprobada","campos":{}},'
                '"discrepancias":[{"criterio":"estado","campo":null,"tipo":null,'
                '"esperado":"aprobada","recibido":"rechazada"}]}'
            ),
        )
    ).post("/compra", data=FORMULARIO).text
    assert "FAIL" in texto
    assert 'data-evaluacion="fail"' in texto
    assert "aprobada" in texto and "rechazada" in texto
    assert "Sin respuesta del destino" not in texto, "no debe confundirse con un timeout"
    assert "El intercambio se interrumpió" not in texto, "tampoco con una transmision"


# --------------------------------------------------------- entradas invalidas --


@pytest.mark.parametrize(
    "campo,valor",
    [("monto", "abc"), ("monto", "-5"), ("monto", "0"), ("monto", ""),
     ("conexion_id", ""), ("conexion_id", "NO-EXISTE")],
)
def test_una_entrada_invalida_produce_respuesta_controlada_y_no_500(campo, valor):
    respuesta = _cliente().post("/compra", data={**FORMULARIO, campo: valor})
    assert respuesta.status_code == 400, "debe ser un error de entrada, no un fallo del servidor"
    assert "Revise los datos" in respuesta.text
    assert "Traceback" not in respuesta.text


def test_una_tarjeta_inexistente_se_informa_sin_traza():
    respuesta = _cliente(error=TarjetaDesconocida("no existe")).post("/compra", data=FORMULARIO)
    assert respuesta.status_code == 400
    assert "No existe la tarjeta" in respuesta.text
    assert "Traceback" not in respuesta.text


def test_un_error_inesperado_no_expone_detalles_internos():
    from sibutestlab8583.domain.errores import ErrorDelSimulador

    class ErrorInterno(ErrorDelSimulador):
        """Error del simulador sin traduccion especifica en presentacion."""

    respuesta = _cliente(error=ErrorInterno("detalle interno confidencial")).post(
        "/compra", data=FORMULARIO
    )
    assert "detalle interno confidencial" not in respuesta.text
    assert "Ocurrió un error inesperado" in respuesta.text


# ------------------------------------------------------------------ isoscopio --


def test_el_isoscopio_muestra_campos_con_descripcion_y_nunca_el_pan():
    texto = _cliente(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00")).post(
        "/compra", data=FORMULARIO
    ).text
    assert "Isoscopio · solicitud 0100" in texto
    assert "Isoscopio · respuesta 0110" in texto
    assert "Número de tarjeta (PAN)" in texto
    assert "************6666" in texto
    assert PAN_DEMO not in texto
    assert "enmascarado" in texto


# ------------------------------------------------------------------ historial --


def test_el_historial_lista_las_ejecuciones():
    ejecucion = _resultado(EstadoEjecucion.APROBADA, codigo="00").ejecucion
    respuesta = _cliente(ejecuciones=[ejecucion]).get("/historial")
    assert respuesta.status_code == 200
    assert CARD_ID_DEMO in respuesta.text
    assert "150.00" in respuesta.text
    assert "aprobada" in respuesta.text
    assert PAN_DEMO not in respuesta.text


def test_el_historial_vacio_no_falla():
    respuesta = _cliente().get("/historial")
    assert respuesta.status_code == 200
    assert "Todavía no hay ejecuciones" in respuesta.text


def test_el_historial_muestra_el_nombre_del_escenario_no_su_id_opaco():
    ejecucion = _resultado(
        EstadoEjecucion.APROBADA, codigo="00",
        escenario_id="ESC-5bb7f2", escenario_nombre="Compra aprobada CRC",
    ).ejecucion
    respuesta = _cliente(ejecuciones=[ejecucion]).get("/historial")
    assert "Compra aprobada CRC" in respuesta.text
    # El id opaco solo puede aparecer en el href del enlace (para poder
    # cargarlo), nunca como texto visible.
    assert ">ESC-5bb7f2<" not in respuesta.text
    assert "Escenario: ESC-5bb7f2" not in respuesta.text


def test_el_historial_sin_escenario_no_muestra_ninguna_referencia():
    ejecucion = _resultado(EstadoEjecucion.APROBADA, codigo="00").ejecucion
    respuesta = _cliente(ejecuciones=[ejecucion]).get("/historial")
    assert "Escenario:" not in respuesta.text


# ------------------------------------------------------------ campos_manuales --


def test_un_campo_editable_enviado_llega_a_datos_compra():
    composicion = ComposicionFalsa(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00"))
    cliente = TestClient(crear_app(composicion))
    respuesta = cliente.post("/compra", data={**FORMULARIO, "campo_37": "REF-QA-01"})
    assert respuesta.status_code == 200
    assert composicion._orquestador.ultimos_datos.campos_manuales == {"37": "REF-QA-01"}


def test_un_campo_editable_en_blanco_no_llega_a_datos_compra():
    """Un campo editable sin tocar no debe pisar el default de la politica: no
    se incluye en `campos_manuales` cuando llega vacio (ver `_interpretar_formulario`).
    """
    composicion = ComposicionFalsa(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00"))
    cliente = TestClient(crear_app(composicion))
    respuesta = cliente.post("/compra", data=FORMULARIO)
    assert respuesta.status_code == 200
    assert composicion._orquestador.ultimos_datos.campos_manuales == {}


def test_un_campo_protegido_en_el_post_bruto_se_ignora_sin_llegar_al_dominio():
    """El servidor no lee `campo_2` (DE2 es derivado) del formulario en absoluto:
    la ruta solo construye `campos_manuales` a partir de lo que el perfil declare
    editable. Un `campo_2` manipulado en el POST nunca alcanza `DatosCompra`, asi
    que ni siquiera hace falta que el dominio lo rechace para que quede sin efecto.
    """
    composicion = ComposicionFalsa(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00"))
    cliente = TestClient(crear_app(composicion))
    respuesta = cliente.post("/compra", data={**FORMULARIO, "campo_2": "9" * 16})
    assert respuesta.status_code == 200
    assert "2" not in composicion._orquestador.ultimos_datos.campos_manuales


def test_forzar_una_expectativa_de_de2_en_compra_se_rechaza_con_400():
    """`/compra` lee expectativas del mismo formulario bruto que `/escenarios`:
    la misma manipulacion (un `tipo_esperado_2` a mano) debe rechazarse aqui
    tambien, no solo en el alta de escenarios. La ejecucion no debe siquiera
    llegar al orquestador.
    """
    composicion = ComposicionFalsa(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00"))
    cliente = TestClient(crear_app(composicion))
    respuesta = cliente.post("/compra", data={**FORMULARIO, "tipo_esperado_2": "presente"})
    assert respuesta.status_code == 400
    assert "no está permitido" in respuesta.text
    assert composicion._orquestador.ultimos_datos is None


# --------------------------------------------------------------- conexion ----
#
# El formulario nunca transporta host, puerto ni timeout: solo `conexion_id`.
# No existe ningun campo de texto libre para probar un "tamper" de host/puerto
# porque ese campo ya no existe en el contrato -la version anterior de estas
# pruebas comprobaba que un host manipulado se ignoraba; ahora ni siquiera hay
# donde escribirlo, lo cual es la version mas fuerte de la misma garantia-.


# ------------------------------------------ campos opcionales (Bloque 2/3) ----
#
# "+ Agregar campo"/"Quitar" comparten el mismo POST "/" que ya usaba "Cambiar
# conexion" -reenvia todo el formulario, sin ejecutar ninguna transaccion-.


def test_get_compra_ofrece_los_cinco_opcionales_cuando_ninguno_esta_activo():
    composicion = ComposicionFalsa()
    cliente = TestClient(crear_app(composicion))
    respuesta = cliente.get("/")
    assert respuesta.status_code == 200
    for numero in ("18", "25", "32", "42", "43"):
        assert f'value="{numero}"' in respuesta.text
    assert 'name="campo_18"' not in respuesta.text


def test_agregar_un_opcional_lo_muestra_como_fila_y_lo_saca_del_catalogo():
    composicion = ComposicionFalsa()
    cliente = TestClient(crear_app(composicion))
    respuesta = cliente.post(
        "/", data={**FORMULARIO, "candidato_opcional": "18", "agregar_opcional": "1"}
    )
    assert respuesta.status_code == 200
    assert 'name="campo_18"' in respuesta.text
    # Ya no es un candidato para agregar de nuevo: el catalogo restante no lo repite.
    assert 'value="18">DE18' not in respuesta.text


def test_quitar_un_opcional_no_reintroduce_el_candidato_del_select():
    """Regresion: el `<select>` de '+ Agregar campo' viaja siempre en el POST,
    sin importar que boton se haya pulsado. Si `quitar_opcional` se procesara
    sin distinguir el boton que realmente se pulso, el valor que haya quedado
    en ese `<select>` se agregaria por error al mismo tiempo que se quita otro.
    """
    composicion = ComposicionFalsa()
    cliente = TestClient(crear_app(composicion))
    # Estado de partida: DE42 ya activo (como si una pantalla previa lo hubiera
    # agregado), con el <select> de candidatos apuntando a DE18 (su default).
    respuesta = cliente.post(
        "/",
        data={
            **FORMULARIO,
            "opcionales_activos": "42",
            "campo_42": "MERCH0000000001",
            "candidato_opcional": "18",
            "quitar_opcional": "42",
        },
    )
    assert respuesta.status_code == 200
    assert 'name="campo_42"' not in respuesta.text
    assert 'name="campo_18"' not in respuesta.text


def test_un_opcional_agregado_con_valor_valido_llega_a_datos_compra():
    composicion = ComposicionFalsa(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00"))
    cliente = TestClient(crear_app(composicion))
    respuesta = cliente.post(
        "/compra",
        data={**FORMULARIO, "opcionales_activos": "18", "campo_18": "5411"},
    )
    assert respuesta.status_code == 200
    assert composicion._orquestador.ultimos_datos.campos_manuales == {"18": "5411"}


def test_un_opcional_con_longitud_incorrecta_da_error_especifico_sin_ejecutar():
    composicion = ComposicionFalsa(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00"))
    cliente = TestClient(crear_app(composicion))
    respuesta = cliente.post(
        "/compra",
        data={**FORMULARIO, "opcionales_activos": "18", "campo_18": "54"},
    )
    assert respuesta.status_code == 400
    assert "DE18" in respuesta.text
    assert "exactamente 4" in respuesta.text
    assert composicion._orquestador.ultimos_datos is None


def test_un_opcional_no_numerico_da_error_especifico():
    composicion = ComposicionFalsa(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00"))
    cliente = TestClient(crear_app(composicion))
    respuesta = cliente.post(
        "/compra",
        data={**FORMULARIO, "opcionales_activos": "18", "campo_18": "ABCD"},
    )
    assert respuesta.status_code == 400
    assert "dígitos" in respuesta.text
    assert composicion._orquestador.ultimos_datos is None


def test_un_campo_no_opcional_manipulado_via_opcionales_activos_no_llega_a_datos_compra():
    """Adversarial: un atacante manipula el campo oculto `opcionales_activos`
    para incluir un numero que NO es opcional (38, "codigo de autorizacion",
    que el autorizador agrega en su respuesta -nunca el emisor en el 0100-),
    junto con un `campo_38` con un valor cualquiera. `_leer_opcionales_activos`
    intersecta siempre con `politica.opcionales`, asi que "38" nunca entra a
    `numeros_a_leer` y `campo_38` queda sin leer, sin que haga falta que el
    dominio lo rechace explicitamente para que quede sin efecto -mismo
    criterio que ya protege a los derivados/automaticos-.
    """
    composicion = ComposicionFalsa(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00"))
    cliente = TestClient(crear_app(composicion))
    respuesta = cliente.post(
        "/compra", data={**FORMULARIO, "opcionales_activos": "38", "campo_38": "000999"}
    )
    assert respuesta.status_code == 200
    assert "38" not in composicion._orquestador.ultimos_datos.campos_manuales


def test_agregar_un_candidato_opcional_inexistente_no_agrega_nada():
    """Adversarial: `candidato_opcional` manipulado a un numero que el perfil
    no declara como opcional (p. ej. "999", o "38" que es un campo real pero
    no opcional). El servidor solo agrega si `candidato in politica.opcionales`.
    """
    composicion = ComposicionFalsa()
    cliente = TestClient(crear_app(composicion))
    respuesta = cliente.post(
        "/", data={**FORMULARIO, "candidato_opcional": "999", "agregar_opcional": "1"}
    )
    assert respuesta.status_code == 200
    assert 'name="campo_999"' not in respuesta.text


def test_un_editable_preexistente_con_forma_distinta_del_default_sigue_funcionando():
    """Garantia de no-regresion: la nueva validacion de forma NO se aplica a
    los editables preexistentes (3/22/37/41/49) -ver docstring de
    `validar_forma_de_opcionales`-, asi que un valor como este (mas corto que
    el largo fijo de DE37) sigue aceptandose igual que antes de esta iteracion.
    """
    composicion = ComposicionFalsa(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00"))
    cliente = TestClient(crear_app(composicion))
    respuesta = cliente.post("/compra", data={**FORMULARIO, "campo_37": "REF-QA-01"})
    assert respuesta.status_code == 200
    assert composicion._orquestador.ultimos_datos.campos_manuales == {"37": "REF-QA-01"}


def test_una_conexion_activa_resuelve_host_puerto_y_timeout_desde_persistencia():
    conexion_propia = DestinoGuardado(
        destino_id="QA-01", nombre="QA", host="10.20.30.40", puerto=9583, timeout=25.0
    )
    composicion = ComposicionFalsa(
        resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00"),
        destinos=[conexion_propia],
    )
    cliente = TestClient(crear_app(composicion))
    respuesta = cliente.post(
        "/compra", data={"card_id": CARD_ID_DEMO, "monto": "150.00", "conexion_id": "QA-01"}
    )
    assert respuesta.status_code == 200
    assert composicion.ultimo_destino.host == "10.20.30.40"
    assert composicion.ultimo_destino.puerto == 9583
    assert composicion.ultimo_tiempo_limite == 25.0


def test_una_conexion_inactiva_se_rechaza_aunque_se_fuerce_su_id():
    conexion_inactiva = DestinoGuardado(
        destino_id="INACTIVA", nombre="Inactiva", host="10.0.0.9", puerto=9999, activo=False
    )
    composicion = ComposicionFalsa(
        resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00"),
        destinos=[conexion_inactiva],
    )
    cliente = TestClient(crear_app(composicion))
    respuesta = cliente.post(
        "/compra", data={"card_id": CARD_ID_DEMO, "monto": "150.00", "conexion_id": "INACTIVA"}
    )
    assert respuesta.status_code == 400
    assert "Revise los datos" in respuesta.text
    assert composicion._orquestador.ultimos_datos is None, "no debio llegar a ejecutarse"


def test_una_conexion_inexistente_se_rechaza():
    composicion = ComposicionFalsa(resultado=_resultado(EstadoEjecucion.APROBADA, codigo="00"))
    cliente = TestClient(crear_app(composicion))
    respuesta = cliente.post(
        "/compra", data={"card_id": CARD_ID_DEMO, "monto": "150.00", "conexion_id": "NO-EXISTE"}
    )
    assert respuesta.status_code == 400
    assert "Revise los datos" in respuesta.text


def test_el_formulario_de_compra_no_ofrece_ningun_campo_de_host_puerto_o_timeout():
    """La conexion no se configura desde Nueva transaccion: ver Configuración → Conexiones."""
    texto = _cliente().get("/").text.lower()
    for prohibido in ('name="host"', 'name="puerto"', 'name="timeout"'):
        assert prohibido not in texto


# ----------------------------------------------- conservar datos al cambiar --
#
# Mejora funcional posterior a la entrega: cambiar de conexion no debe borrar
# lo que ya se habia escrito en el constructor. El boton "Cambiar" somete el
# mismo <form> por GET (`ir_a_conexion`); `pantalla_compra` reconstruye
# `enviado` desde la querystring resultante.


def test_cambiar_de_conexion_conserva_tarjeta_monto_y_campos_editables():
    """El mecanismo es POST /, no GET: el navegador entrega los campos en el
    cuerpo de la peticion, nunca en la URL ni en la querystring.
    """
    segunda_conexion = DestinoGuardado(
        destino_id="QA-02", nombre="QA 2", host="10.20.30.41", puerto=9584
    )
    composicion = ComposicionFalsa(destinos=[_CONEXION_DEMO_FALSA, segunda_conexion])
    cliente = TestClient(crear_app(composicion))

    respuesta = cliente.post(
        "/",
        data={
            "conexion_id": DESTINO_ID_DEMO,  # valor VIEJO, en el campo oculto
            "escenario_id": "",
            "ir_a_conexion": "QA-02",
            "card_id": CARD_ID_DEMO,
            "monto": "275.50",
            "campo_37": "REF-QA-99",
            "nombre": "Escenario a medio armar",
        },
    )
    assert respuesta.status_code == 200
    assert respuesta.request.url.query == b"" or not respuesta.request.url.query, (
        "el POST no debe convertirse en una URL con querystring"
    )
    texto = respuesta.text
    assert 'value="QA-02"' in texto  # la conexion nueva quedo seleccionada
    assert re.search(rf'name="card_id" value="{CARD_ID_DEMO}"\s*checked', texto)
    assert "275.50" in texto
    assert "REF-QA-99" in texto
    assert "Escenario a medio armar" in texto


def test_cambiar_conexion_no_ejecuta_ni_guarda_nada():
    """POST / re-renderiza el constructor; no debe tocar el orquestador ni
    el servicio de escenarios bajo ninguna circunstancia.
    """
    composicion = ComposicionFalsa(
        destinos=[
            _CONEXION_DEMO_FALSA,
            DestinoGuardado(destino_id="QA-02", nombre="QA 2", host="10.20.30.41", puerto=9584),
        ],
    )
    cliente = TestClient(crear_app(composicion))
    respuesta = cliente.post(
        "/",
        data={"ir_a_conexion": "QA-02", "card_id": CARD_ID_DEMO, "monto": "", "nombre": "X"},
    )
    assert respuesta.status_code == 200
    assert composicion._orquestador.ultimos_datos is None, "no debio ejecutar ninguna transaccion"


def test_los_botones_de_cambiar_conexion_no_bloquean_por_validacion_nativa():
    """Hallazgo de revisión: el botón que somete el formulario para cambiar de
    conexión debe llevar `formnovalidate`. Sin eso, un navegador real bloquea
    el envío cuando `monto` (campo `required`) está vacío o cuando cualquier
    otro campo requerido del formulario no lo cumple, impidiendo cambiar de
    conexión y -peor- sin perder lo escrito, contradiciendo el propósito de
    esta mejora. `TestClient` no ejecuta validación HTML5, así que esto no lo
    detectaría un test funcional contra el servidor: se verifica el marcado.
    Confirmado además con un clic real en navegador (monto vacío e inválido).
    El botón hereda el método POST del propio `<form>` -sin `formmethod`, a
    diferencia del mecanismo anterior (GET), que exponía los valores en la URL.
    """
    segunda_conexion = DestinoGuardado(
        destino_id="QA-02", nombre="QA 2", host="10.20.30.41", puerto=9584
    )
    composicion = ComposicionFalsa(destinos=[_CONEXION_DEMO_FALSA, segunda_conexion])
    texto = TestClient(crear_app(composicion)).get("/").text
    botones = re.findall(r'<button[^>]*name="ir_a_conexion"[^>]*>', texto)
    assert len(botones) == 2
    for boton in botones:
        assert "formnovalidate" in boton
        assert 'formaction="/"' in boton
        assert "formmethod" not in boton, "no debe forzar GET: hereda el POST del formulario"


def test_un_enlace_comun_con_solo_conexion_id_no_dispara_la_conservacion():
    """Un enlace ordinario (historial, escenarios) nunca trae `monto`: debe
    seguir comportandose exactamente igual que antes de esta mejora.
    """
    respuesta = _cliente().get("/", params={"conexion_id": DESTINO_ID_DEMO})
    assert respuesta.status_code == 200
    # Sin `enviado`, la primera tarjeta activa se preselecciona como siempre.
    assert 'checked' in respuesta.text


def test_falla_al_guardar_una_suite_conserva_los_escenarios_marcados_y_su_orden():
    import sqlite3
    import tempfile

    from sibutestlab8583.adapters.persistence.esquema import DDL
    from sibutestlab8583.composicion import Composicion, Configuracion

    ruta = Path(tempfile.mkstemp(suffix=".db")[1])
    with sqlite3.connect(ruta) as conexion:
        conexion.executescript(DDL)
        ahora = "2026-08-19T12:00:00+00:00"
        conexion.execute(
            "INSERT INTO tarjetas_prueba (card_id, pan, pan_enmascarado, expiracion, creada_en)"
            " VALUES (?, ?, ?, ?, ?)",
            (CARD_ID_DEMO, PAN_DEMO, "************6666", "3012", ahora),
        )
        conexion.execute(
            "INSERT INTO destinos (destino_id, nombre, host, puerto, creado_en) VALUES (?, ?, ?, ?, ?)",
            (DESTINO_ID_DEMO, DESTINO_NOMBRE_DEMO, DESTINO_HOST_DEMO, DESTINO_PUERTO_DEMO, ahora),
        )
        for escenario_id, nombre in (("ESC-1", "Uno"), ("ESC-2", "Dos")):
            conexion.execute(
                "INSERT INTO escenarios"
                " (escenario_id, nombre, perfil, mti, card_id, conexion_id, monto, creado_en, actualizado_en)"
                " VALUES (?, ?, 'generico', '0100', ?, ?, '150.00', ?, ?)",
                (escenario_id, nombre, CARD_ID_DEMO, DESTINO_ID_DEMO, ahora, ahora),
            )
        conexion.commit()

    composicion = Composicion(Configuracion(ruta_base_datos=ruta))
    cliente = TestClient(crear_app(composicion))

    # Orden invalido (repetido) a proposito: dispara el ValueError de
    # `_leer_escenarios_de_suite`, pero ESC-1 y ESC-2 quedaron marcados.
    respuesta = cliente.post(
        "/suites",
        data={
            "nombre": "Suite nueva",
            "descripcion": "",
            "incluir_ESC-1": "on",
            "orden_ESC-1": "1",
            "incluir_ESC-2": "on",
            "orden_ESC-2": "1",
        },
    )
    assert respuesta.status_code == 400
    texto = respuesta.text
    assert "mismo número de orden" in texto
    # Los dos checkboxes siguen marcados y con el texto de orden que se escribio.
    assert texto.count('checked') >= 2 or texto.count("checked>") >= 2


def test_falla_al_guardar_una_suite_conserva_el_texto_de_orden_no_numerico():
    """Version mas estricta del hallazgo anterior: el texto de "orden" debe
    preservarse LITERAL -incluso si no es un numero valido-, y un escenario
    que la persona NO marco no debe aparecer marcado (no "todo se selecciona
    en el error", solo lo que de verdad se habia elegido).
    """
    import sqlite3
    import tempfile

    from sibutestlab8583.adapters.persistence.esquema import DDL
    from sibutestlab8583.composicion import Composicion, Configuracion

    ruta = Path(tempfile.mkstemp(suffix=".db")[1])
    with sqlite3.connect(ruta) as conexion:
        conexion.executescript(DDL)
        ahora = "2026-08-19T12:00:00+00:00"
        conexion.execute(
            "INSERT INTO tarjetas_prueba (card_id, pan, pan_enmascarado, expiracion, creada_en)"
            " VALUES (?, ?, ?, ?, ?)",
            (CARD_ID_DEMO, PAN_DEMO, "************6666", "3012", ahora),
        )
        conexion.execute(
            "INSERT INTO destinos (destino_id, nombre, host, puerto, creado_en) VALUES (?, ?, ?, ?, ?)",
            (DESTINO_ID_DEMO, DESTINO_NOMBRE_DEMO, DESTINO_HOST_DEMO, DESTINO_PUERTO_DEMO, ahora),
        )
        for escenario_id, nombre in (("ESC-1", "Uno"), ("ESC-2", "Dos"), ("ESC-3", "Tres")):
            conexion.execute(
                "INSERT INTO escenarios"
                " (escenario_id, nombre, perfil, mti, card_id, conexion_id, monto, creado_en, actualizado_en)"
                " VALUES (?, ?, 'generico', '0100', ?, ?, '150.00', ?, ?)",
                (escenario_id, nombre, CARD_ID_DEMO, DESTINO_ID_DEMO, ahora, ahora),
            )
        conexion.commit()

    composicion = Composicion(Configuracion(ruta_base_datos=ruta))
    cliente = TestClient(crear_app(composicion))

    # ESC-1 e ESC-2 marcados con un orden NO numerico; ESC-3 deliberadamente
    # NO se marca.
    respuesta = cliente.post(
        "/suites",
        data={
            "nombre": "Suite nueva",
            "descripcion": "",
            "incluir_ESC-1": "on",
            "orden_ESC-1": "primero",
            "incluir_ESC-2": "on",
            "orden_ESC-2": "2",
        },
    )
    assert respuesta.status_code == 400
    texto = respuesta.text
    assert "debe ser un número entero" in texto
    entrada_esc1 = re.search(r'<input[^>]*orden_ESC-1[^>]*>', texto)
    entrada_esc2 = re.search(r'<input[^>]*orden_ESC-2[^>]*>', texto)
    assert entrada_esc1 is not None and 'value="primero"' in entrada_esc1.group(0)
    assert entrada_esc2 is not None and 'value="2"' in entrada_esc2.group(0)
    # ESC-3 no se marco: su fila no debe llevar `checked`.
    fila_esc3 = re.search(r'name="incluir_ESC-3"[^>]*', texto)
    assert fila_esc3 is not None
    assert "checked" not in fila_esc3.group(0)

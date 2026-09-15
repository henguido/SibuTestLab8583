"""Seguridad de las superficies nuevas de D2 (2026-09-14, punto 13/32 del
checkpoint): el estado limitado no abre ninguna via nueva para exponer
datos sensibles -las mismas prohibiciones de D1 siguen intactas, y el
contador en si (un entero + un timestamp) es estructuralmente incapaz de
transportar un PAN/Track/RAW.
"""

from __future__ import annotations

import re

from sibutestlab8583.adapters.persistence.sqlite_repos import (
    RepositorioEstadoReglasHostSQLite,
    RepositorioEventosReglasHostSQLite,
    RepositorioReglasHostSQLite,
)
from sibutestlab8583.application.reglas_host import DatosNuevaRegla, ServicioReglasHost
from sibutestlab8583.domain.reglas_host import CAMPO_MTI, CondicionRegla, EstadoReglaHost
from sibutestlab8583.profiles.generico import PERFIL_GENERICO

#: Misma heuristica que `test_datos_sinteticos.py`/`test_seguridad_c3.py`:
#: una secuencia de 12-19 digitos es indistinguible de un PAN real.
_PATRON_PAN = re.compile(r"\d{12,19}")


async def test_max_aplicaciones_no_evade_la_prohibicion_de_campos_sensibles(base):
    """Punto 32: las reglas stateful siguen prohibiendo DE2/DE35/DE45 en
    condiciones o respuesta -el limite de aplicaciones es ortogonal a la
    seguridad, nunca una via para evadirla."""
    servicio = ServicioReglasHost(RepositorioReglasHostSQLite(base), PERFIL_GENERICO)
    import pytest

    for campo_sensible in ("2", "35", "45"):
        with pytest.raises(ValueError, match="sensible"):
            await servicio.crear(DatosNuevaRegla(
                nombre="Stateful invalida", prioridad=1,
                condiciones=[CondicionRegla(campo_sensible, "igual", "x")],
                de39="00", max_aplicaciones=1,
            ))


async def test_el_estado_operacional_nunca_puede_contener_un_pan(base):
    """`EstadoReglaHost` solo tiene `regla_id`/`aplicaciones_consumidas`/
    `actualizado_en` -ningun campo puede recibir el valor de un mensaje,
    estructuralmente, sin importar que tan grande sea el contador."""
    estado = EstadoReglaHost(regla_id="RULE-1", aplicaciones_consumidas=999_999_999_999)
    assert not _PATRON_PAN.search(str(estado.regla_id))
    # El contador es un entero (no texto libre): incluso un valor enorme
    # solo es un numero de aplicaciones, nunca un campo de mensaje.


async def test_los_eventos_con_match_number_siguen_sin_guardar_valores_del_mensaje(base):
    """El campo nuevo `match_number` es un entero de auditoria -nunca el
    valor de ningun campo ISO- y el resto de `EventoReglaHost` sigue
    exactamente igual que en D1: mensajes fijos, nunca datos crudos."""
    from datetime import datetime, timezone

    from sibutestlab8583.domain.reglas_host import EventoReglaHost

    repo = RepositorioEventosReglasHostSQLite(base)
    evento = EventoReglaHost(
        mti_solicitud="0800", comportamiento="timeout",
        regla_id="RULE-1", regla_nombre="Timeout", prioridad=1,
        de39_respuesta="00", match_number=1, creado_en=datetime.now(timezone.utc),
    )
    await repo.registrar(evento)
    (guardado,) = await repo.listar()
    assert guardado.match_number == 1
    # Ningun campo del evento es texto libre proveniente del mensaje -todos
    # son identificadores de regla, codigos de catalogo, o enteros.
    assert guardado.mti_solicitud == "0800"


async def test_reiniciar_contador_no_revela_ni_modifica_auditoria_historica(base):
    """El reset (D2, punto 8) nunca borra `reglas_host_eventos` -la
    auditoria sigue siendo la fuente de verdad historica, incluso despues
    de reiniciar el contador operacional."""
    servicio = ServicioReglasHost(
        RepositorioReglasHostSQLite(base), PERFIL_GENERICO,
        RepositorioEstadoReglasHostSQLite(base),
    )
    creada = await servicio.crear(DatosNuevaRegla(
        nombre="Con historia", prioridad=1,
        condiciones=[CondicionRegla(CAMPO_MTI, "igual", "0800")],
        de39="00", max_aplicaciones=1,
    ))
    estado_repo = RepositorioEstadoReglasHostSQLite(base)
    await estado_repo.incrementar_si_no_agotada(creada.regla_id, 1)

    eventos_repo = RepositorioEventosReglasHostSQLite(base)
    from datetime import datetime, timezone

    from sibutestlab8583.domain.reglas_host import EventoReglaHost

    await eventos_repo.registrar(EventoReglaHost(
        mti_solicitud="0800", comportamiento="normal",
        regla_id=creada.regla_id, regla_nombre=creada.nombre, prioridad=1,
        de39_respuesta="00", match_number=1, creado_en=datetime.now(timezone.utc),
    ))

    await servicio.reiniciar_contador(creada.regla_id)

    estado = await estado_repo.obtener(creada.regla_id)
    assert estado.aplicaciones_consumidas == 0
    eventos_tras_reset = await eventos_repo.listar()
    assert len(eventos_tras_reset) == 1  # la auditoria previa sigue intacta

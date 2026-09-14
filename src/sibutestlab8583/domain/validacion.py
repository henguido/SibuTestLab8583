"""Las cuatro reglas de negocio de PROYECTO.md seccion 4.

Funciones **puras**: sin red, sin base de datos, sin reloj, sin estado global.
Esa pureza es lo que las hace comprobables con pruebas rapidas y deterministas,
y es un limite arquitectonico que no se cruza.

Reparto de las reglas:

- RN-4 vive en `validar_envio`, y se aplica **antes** de codificar.
- RN-1 y RN-3 viven en `evaluar_respuesta`.
- RN-2 **no vive aqui**: un tiempo de espera agotado no es una respuesta
  recibida, asi que no hay nada que evaluar. El transporte devuelve
  `TiempoAgotado` y el orquestador lo convierte en el resultado de ejecucion.
"""

from __future__ import annotations

from typing import Mapping

from .catalogo import CatalogoDeRespuestas
from .modelos import EstadoEjecucion, MensajeIso, ResultadoValidacion

#: Campo ISO que transporta el codigo de respuesta. Lo interpreta el catalogo.
CAMPO_CODIGO_RESPUESTA = "39"


def validar_envio(mensaje: MensajeIso, perfil) -> ResultadoValidacion:
    """RN-4: un mensaje sin un campo obligatorio de su MTI no debe enviarse.

    Se ejecuta antes del codec. El perfil decide cuales son los obligatorios;
    esta funcion no conoce ninguna marca.
    """
    if not perfil.soporta(mensaje.mti):
        return ResultadoValidacion(
            valido=False,
            motivos=(f"el perfil {perfil.nombre!r} no soporta el MTI {mensaje.mti!r}",),
        )

    presentes = mensaje.numeros_presentes()
    faltantes = tuple(sorted(perfil.obligatorios(mensaje.mti) - presentes, key=int))
    if faltantes:
        return ResultadoValidacion(
            valido=False,
            faltantes=faltantes,
            motivos=(
                "faltan campos obligatorios para el MTI "
                f"{mensaje.mti}: {', '.join(faltantes)}",
            ),
        )
    return ResultadoValidacion.ok()


def campos_de_correlacion(perfil, mti_respuesta: str) -> frozenset[str]:
    """Campos que la respuesta debe devolver identicos a la solicitud (RN-3).

    Se derivan del perfil, no se inventan: son los obligatorios de la respuesta
    menos el codigo de respuesta, que por definicion lo origina el autorizador y
    no viaja en la solicitud, y menos los campos sensibles -`perfil.es_sensible()`,
    mismo criterio que `domain/expectativas.py::campos_permitidos_expectativa`,
    B3 2026-09-13-: su valor nunca debe interpolarse en un motivo de texto
    libre, que se persiste sin pasar por `.enmascarado()` -ver
    `_discrepancias_de_correlacion`-.
    """
    return frozenset(
        n for n in perfil.obligatorios(mti_respuesta)
        if n != CAMPO_CODIGO_RESPUESTA and not perfil.es_sensible(n)
    )


def evaluar_respuesta(
    envio: MensajeIso,
    respuesta: MensajeIso,
    catalogo: CatalogoDeRespuestas,
    perfil,
) -> tuple[EstadoEjecucion, tuple[str, ...]]:
    """RN-3 y luego RN-1. Devuelve el estado y los motivos.

    **El orden importa y es deliberado.** RN-3 se comprueba primero: una
    respuesta cuyo campo 39 diga "aprobada" pero que no corresponda a la
    solicitud enviada es `INVALIDA`, nunca `APROBADA`. Invertir el orden
    convertiria el simulador en una fuente de falsos positivos, que es
    exactamente lo que PROYECTO.md seccion 7.6 obliga a poder detectar.

    Nunca devuelve TIMEOUT: si no hubo respuesta, no se llama a esta funcion.
    """
    discrepancias = _discrepancias_de_correlacion(envio, respuesta, perfil)
    if discrepancias:
        return EstadoEjecucion.INVALIDA, discrepancias
    return _interpretar_codigo(respuesta, catalogo)


def _discrepancias_de_correlacion(
    envio: MensajeIso, respuesta: MensajeIso, perfil
) -> tuple[str, ...]:
    """RN-3: en que la respuesta no corresponde a la solicitud enviada.

    Vacio significa que si corresponde. Comprueba tres cosas: que el MTI sea el
    esperado, que la respuesta traiga sus obligatorios, y que los campos de
    correlacion vuelvan identicos.
    """
    motivos: list[str] = []
    mti_esperado = mti_de_respuesta(envio.mti)

    if respuesta.mti != mti_esperado:
        motivos.append(f"MTI inesperado: se esperaba {mti_esperado} y llegó {respuesta.mti}")

    obligatorios = (
        perfil.obligatorios(respuesta.mti) if perfil.soporta(respuesta.mti) else frozenset()
    )
    faltantes = sorted(obligatorios - respuesta.numeros_presentes(), key=int)
    if faltantes:
        motivos.append(f"la respuesta no trae campos obligatorios: {', '.join(faltantes)}")

    if perfil.soporta(mti_esperado):
        for numero in sorted(campos_de_correlacion(perfil, mti_esperado), key=int):
            esperado = envio.campos.get(numero)
            if esperado is None:
                continue  # no viajaba en la solicitud: nada que correlacionar
            recibido = respuesta.campos.get(numero)
            if recibido != esperado:
                motivos.append(
                    f"el campo {numero} no corresponde a la solicitud: "
                    f"se envió {esperado!r} y volvió {recibido!r}"
                )
    return tuple(motivos)


def _interpretar_codigo(
    respuesta: MensajeIso, catalogo: CatalogoDeRespuestas
) -> tuple[EstadoEjecucion, tuple[str, ...]]:
    """RN-1: aprobado es lo que el catalogo configurado diga, no un codigo fijo."""
    codigo = respuesta.campos.get(CAMPO_CODIGO_RESPUESTA)
    if codigo is None:
        return EstadoEjecucion.INVALIDA, ("la respuesta no trae el campo 39",)

    if catalogo.es_aprobado(codigo):
        return EstadoEjecucion.APROBADA, ()

    if not catalogo.conoce(codigo):
        return (
            EstadoEjecucion.RECHAZADA,
            (f"código {codigo} desconocido para el catálogo {catalogo.nombre!r}",),
        )
    return EstadoEjecucion.RECHAZADA, (f"{codigo}: {catalogo.descripcion(codigo)}",)


#: Tercer digito del MTI (funcion del mensaje) -> tercer digito de su
#: respuesta, segun la convencion generica de ISO 8583: 0 (request) responde
#: con 1 (request response); 2 (advice) responde con 3 (advice response).
#: B8 (2026-09-14, aviso de reverso): completa lo que la version anterior de
#: esta funcion dejaba pendiente ("los reversos con correlacion cruzada
#: -0420/0430- son un caso distinto, fuera de esta funcion") -no es una
#: regla nueva inventada para este laboratorio, es la misma tabla de
#: funciones que el estandar ya define para cualquier MTI.
_TERCER_DIGITO_DE_RESPUESTA: Mapping[str, str] = {"0": "1", "2": "3"}


def mti_de_respuesta(mti_solicitud: str) -> str:
    """En ISO 8583 la respuesta a un mensaje se deriva cambiando el tercer
    digito (funcion) segun `_TERCER_DIGITO_DE_RESPUESTA`: 0x00 -> 0x10
    (request -> request response), 0x20 -> 0x30 (advice -> advice response).

    Publica (sin guion bajo) a partir de B1: ademas de usarla este modulo
    para RN-3, `application/orquestador.py` la usa para derivar el MTI de
    respuesta esperado en vez de asumir el literal de compra -es la misma
    regla generica de ISO 8583, no una segunda definicion-. Verificada
    genericamente para 0100/0110, 0200/0210, 0400/0410 y 0800/0810 (jornada
    de agentes, 2026-09-12), y para 0420/0430 (B8, 2026-09-14, aviso de
    reverso): ambos casos son la misma regla de digito-de-funcion, no dos
    reglas distintas.
    """
    tercer_digito = mti_solicitud[2]
    return mti_solicitud[:2] + _TERCER_DIGITO_DE_RESPUESTA[tercer_digito] + mti_solicitud[3:]

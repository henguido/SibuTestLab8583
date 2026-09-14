"""Errores controlados del proyecto.

Los adaptadores traducen aqui los errores de sus librerias para que el
orquestador y el dominio no tengan que conocer `pyiso8583` ni `asyncio`.

Las condiciones de red **no** son errores aqui: el transporte las devuelve como
resultado —`TiempoAgotado` y `FalloDeConexion` en `modelos.py`—, porque para una
herramienta de pruebas son observaciones que hay que registrar. Por eso no existe
ninguna excepcion de transporte en este modulo.
"""

from __future__ import annotations


class ErrorDelSimulador(Exception):
    """Raiz de todos los errores propios. Permite capturarlos como familia."""


class ErrorDeCodec(ErrorDelSimulador):
    """Fallo al convertir entre el dominio y los bytes ISO 8583."""


class ErrorDeCodificacion(ErrorDeCodec):
    """El mensaje del dominio no pudo convertirse a bytes con el perfil dado."""


class ErrorDeDecodificacion(ErrorDeCodec):
    """Los bytes recibidos no pudieron interpretarse con el perfil dado."""


class ErrorDeFraming(ErrorDelSimulador):
    """El enmarcado o desenmarcado del stream fallo.

    Cubre un payload de largo invalido, un prefijo incompleto y un stream que
    se corta antes de completar el mensaje anunciado.
    """


class ErrorDeCamposManuales(ErrorDelSimulador, ValueError):
    """Un campo manual no procede para el MTI que se esta armando.

    Es `ValueError` ademas de `ErrorDelSimulador` para que la capa web lo trate
    igual que cualquier otro error de entrada (400, sin traza), sin necesitar un
    manejador nuevo.
    """


class CampoNoPermitido(ErrorDeCamposManuales):
    """El campo no esta declarado como editable para este MTI."""


class CampoProtegido(ErrorDeCamposManuales):
    """El campo es derivado o automatico: no puede fijarse manualmente."""


class CampoConFormaInvalida(ErrorDeCamposManuales):
    """El campo es editable/opcional -su origen esta permitido-, pero el valor
    dado no tiene la forma que su metadata declara (tipo o longitud)."""


class ErrorDeVariableDinamica(ErrorDelSimulador, ValueError):
    """Raiz de los errores de resolucion de variables dinamicas (`{{...}}`).

    Es `ValueError` por el mismo motivo que `ErrorDeCamposManuales`: la capa
    web debe poder tratarla como error de entrada (400, sin traza).
    """


class ExpresionMalformada(ErrorDeVariableDinamica):
    """El valor tiene `{{`/`}}` pero no calza la gramatica de una variable."""


class VariableDesconocida(ErrorDeVariableDinamica):
    """La expresion tiene una forma valida, pero el nombre no existe."""


class VariableNoDisponible(ErrorDeVariableDinamica):
    """La variable existe, pero no se puede resolver en este contexto (ej.
    `{{amount}}` en una operacion sin monto, como un echo de red)."""


class ExpresionDePasoMalformada(ErrorDeVariableDinamica):
    """`{{step...}}` no calza la gramatica de una referencia de paso -mismo
    principio que `ExpresionMalformada`, C2: no se adivina la intencion de
    una referencia a medio escribir."""


class PasoDeSecuenciaDesconocido(ErrorDeVariableDinamica):
    """El `paso_id` referenciado no existe en esta secuencia. Se valida al
    guardar la definicion (punto 10 del checkpoint C2) -nunca en ejecucion,
    si se puede evitar-."""


class ReferenciaDePasoHaciaAdelante(ErrorDeVariableDinamica):
    """Un paso referencia a otro paso que no es estrictamente ANTERIOR (por
    `orden`) -incluida una referencia a si mismo-. Las variables entre pasos
    solo pueden resolverse cuando el paso origen ya termino; C2 sigue siendo
    una secuencia lineal, asi que "anterior" se valida comparando `orden",
    sin necesitar un grafo de dependencias."""


class PasoDeSecuenciaNoEjecutado(ErrorDeVariableDinamica):
    """El paso origen referenciado no produjo ninguna ejecucion en ESTA
    corrida (nunca corrio, o `EjecutorDeSecuencia` no le asigno un
    `ejecucion_id` -ver `application.ejecutor_secuencia`). Nunca se
    devuelve `None` en silencio: una referencia a un paso sin resultado es
    un error de precondicion, no un dato ausente."""


class CampoDeEjecucionSensible(ErrorDeVariableDinamica):
    """El campo ISO referenciado (`{{step.X.response.deNN}}`) es sensible
    -`domain.modelos.CAMPOS_SENSIBLES` o `perfil.es_sensible()`-. Rechazado
    SIEMPRE, sin importar si el campo esta presente o no en el mensaje: la
    autoridad de sensibilidad ya consolidada (B3/B6/B7) nunca se duplica ni
    se relaja para este mecanismo."""


class CampoDeEjecucionNoDisponible(ErrorDeVariableDinamica):
    """El campo ISO referenciado es valido y no sensible, pero el mensaje
    (solicitud o respuesta) del paso origen no lo trae. Nunca se resuelve a
    cadena vacia."""


class MetadataDeEjecucionDesconocida(ErrorDeVariableDinamica):
    """El namespace/campo de metadata referenciado (algo distinto de
    `request`/`response`/`execution_id`) no existe. Cubre tambien un
    numero de campo ISO que el perfil activo no declara en absoluto -nunca
    se asume un tipo o forma para un campo desconocido."""


class ErrorDeOperacionDerivada(ErrorDelSimulador, ValueError):
    """Raiz de errores al construir una operacion derivada (reverso, B7).

    Es `ValueError` por el mismo motivo que `ErrorDeCamposManuales`: la capa
    web debe poder tratarla como error de entrada (400, sin traza), sin
    necesitar un manejador nuevo.
    """


class EjecucionOrigenNoEncontrada(ErrorDeOperacionDerivada):
    """No existe ninguna ejecucion con el id de origen dado."""


class EjecucionOrigenNoElegible(ErrorDeOperacionDerivada):
    """La ejecucion de origen existe, pero
    `domain.elegibilidad_reverso.puede_generar_operacion_derivada` (B6) la
    rechaza -por ejemplo, una 0200 rechazada, una 0100, un echo, o una
    ejecucion sin respuesta valida-. La autoridad de esta comprobacion es
    siempre del servidor: un POST no puede forzar un origen no elegible."""


class ReferenciaOrigenIncompleta(ErrorDeOperacionDerivada):
    """El snapshot de la ejecucion origen no trae un dato imprescindible
    para construir la operacion derivada (monto, moneda o terminal). No
    deberia ocurrir para una ejecucion elegible real -senala un snapshot
    corrupto, no un caso de negocio valido-."""


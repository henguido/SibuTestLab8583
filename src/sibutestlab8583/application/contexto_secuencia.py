"""Contexto de una corrida de secuencia en curso (Fase C1).

Deliberadamente DISTINTO de `domain.variables.ContextoResolucion` (Fase A):
aquel resuelve valores `{{...}}` DENTRO de un mensaje que se esta armando,
en el momento en que ya se conoce el STAN/momento de ESA ejecucion. Este
resuelve "que ejecucion produjo el paso N de ESTA corrida" -un problema de
otra naturaleza: ubicar el resultado de un paso YA TERMINADO y ya
persistido, no interpolar texto.

API EXPLICITA, NUNCA UN DICCIONARIO MAGICO
===========================================
`ContextoSecuencia` no expone `contexto["paso1"]["response"]["37"]` ni nada
parecido: solo `registrar()`/`ejecucion_id_de()`, ambos tipados. C1 no
necesita mas que esto (ver docstring de `application.ejecutor_secuencia`):
`Orquestador.ejecutar_reverso_financiero` ya sabe resolver+validar+construir
la `ReferenciaEjecucion` de forma segura a partir de un `ejecucion_id`
crudo (via `referencia_origen_elegible`, B6/B7) -este contexto solo necesita
entregarle CUAL `ejecucion_id` corresponde a que paso, nunca reconstruir el
snapshot el mismo.

Un futuro C2 (`{{step.N.campo}}`, NO implementado aqui) agregaria un metodo
`referencia_de(nombre_paso)` que delegue en `referencia_origen_elegible` de
la misma manera, con su propio scope de variables cerrado -ver
docs/roadmap/SIBU_3.md para el diseno prospectivo-.
"""

from __future__ import annotations


class ContextoSecuencia:
    """Mapa `{orden_del_paso: ejecucion_id}`, llenado SOLO cuando un paso
    termina de ejecutarse y produce una `Ejecucion` real -nunca antes, nunca
    especulativamente-. Vive exactamente mientras dura una corrida; nunca se
    persiste ni se comparte entre corridas distintas.
    """

    def __init__(self) -> None:
        self._ejecuciones_por_orden: dict[int, int] = {}

    def registrar(self, orden: int, ejecucion_id: int) -> None:
        self._ejecuciones_por_orden[orden] = ejecucion_id

    def ejecucion_id_de(self, orden: int) -> int | None:
        """`None` si ese paso todavia no corrio, o corrio sin llegar a
        producir ninguna `Ejecucion` (ver `application.ejecutor_secuencia`,
        casos que reventan ANTES de tocar el orquestador)."""
        return self._ejecuciones_por_orden.get(orden)

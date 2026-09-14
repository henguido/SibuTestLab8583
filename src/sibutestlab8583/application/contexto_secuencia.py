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

C2 (`{{step.<paso_id>.campo}}`, ver `application/variables_secuencia.py`) reusa
el MISMO mapa, indexado tambien por `paso_id` -el identificador ESTABLE del
paso (`PasoSecuencia.paso_id`), nunca por `orden`: una referencia de texto
sobrevive a un futuro reordenamiento de la secuencia, mientras que el
vinculo estructural de C1 (`origen_paso_orden`, para un paso DERIVADO) sigue
usando `orden` sin cambios -son dos mecanismos distintos, coexistiendo a
proposito (ver docstring de `application.variables_secuencia`).
"""

from __future__ import annotations


class ContextoSecuencia:
    """Dos mapas equivalentes -`{orden: ejecucion_id}` (C1) y
    `{paso_id: ejecucion_id}` (C2)-, llenados SOLO cuando un paso termina de
    ejecutarse y produce una `Ejecucion` real -nunca antes, nunca
    especulativamente-. Vive exactamente mientras dura una corrida; nunca se
    persiste ni se comparte entre corridas distintas.
    """

    def __init__(self) -> None:
        self._ejecuciones_por_orden: dict[int, int] = {}
        self._ejecuciones_por_paso_id: dict[str, int] = {}

    def registrar(self, orden: int, ejecucion_id: int, *, paso_id: str | None = None) -> None:
        self._ejecuciones_por_orden[orden] = ejecucion_id
        if paso_id is not None:
            self._ejecuciones_por_paso_id[paso_id] = ejecucion_id

    def ejecucion_id_de(self, orden: int) -> int | None:
        """`None` si ese paso todavia no corrio, o corrio sin llegar a
        producir ninguna `Ejecucion` (ver `application.ejecutor_secuencia`,
        casos que reventan ANTES de tocar el orquestador)."""
        return self._ejecuciones_por_orden.get(orden)

    def ejecucion_id_de_paso_id(self, paso_id: str) -> int | None:
        """Igual que `ejecucion_id_de`, pero por identificador ESTABLE de
        paso (C2) en vez de por `orden` -ver `application.
        variables_secuencia.resolver_referencia_de_paso`."""
        return self._ejecuciones_por_paso_id.get(paso_id)

# CLAUDE.md — SibuTestLab8583

Instrucciones permanentes para Claude Code en este repositorio.
**`PROYECTO.md` es la fuente autoritativa de alcance.** Ante cualquier conflicto, manda
`PROYECTO.md`.

## Objetivo

Simulador de transacciones ISO 8583: construir un mensaje de compra, enviarlo por TCP a un
sistema receptor, interpretar y validar la respuesta, y persistir la ejecución. Proyecto final
del curso SINT-732.

## Alcance actual

**Únicamente compra `0100` → TCP → respuesta `0110`.**

Fuera de alcance, y no se diseñan ni se implementan: retiros, consultas de saldo, reversos,
OCT, AFT, refunds, anulaciones, verificaciones de cuenta, catálogos de códigos por marca y
paneles de métricas elaborados. Si una tarea parece requerir algo de esta lista, detenerse y
preguntar antes de escribir nada.

## Stack acordado — todavía no implementado

Python · FastAPI · HTML con Jinja y JavaScript mínimo · SQLite mediante `aiosqlite` ·
`pyiso8583` · TCP asíncrono con `asyncio`.

Sin React, sin frontend independiente, sin paso de compilación. Docker es un mecanismo de
distribución posterior, nunca una dependencia para desarrollar.

## Arquitectura y desacoplamiento

Dirección de dependencia: **`web → application service → dominio/puertos → adaptadores`**.

Reglas que no se rompen:

- La web no conoce SQLite, ni sockets, ni detalles de `pyiso8583`.
- El transporte **no conoce ISO 8583**: recibe bytes opacos y delega el enmarcado y el
  desenmarcado a `FramingStrategy`.
- El framing es un contrato aparte, no lógica incrustada en el transporte. Su único consumidor
  es el transporte: ni la web ni el orquestador conocen el formato concreto.
- La validación de reglas de negocio se mantiene pura: sin red, sin base de datos.
- La persistencia vive detrás de un puerto **asíncrono**; el dominio no conoce el motor.
- El codec recibe el perfil como parámetro; no conoce marcas.

Detalle en `docs/arquitectura/ARQUITECTURA.md`.

## PerfilDeMarca ≠ CatalogoDeRespuestas

Dos ejes de configuración independientes. **Nunca acoplarlos.**

- `PerfilDeMarca` define formato, codificación, campos y obligatorios por MTI.
- `CatalogoDeRespuestas` define qué código del campo 39 cuenta como aprobado.

**Prohibido inventar especificaciones de Visa o Mastercard.** Los perfiles reales solo se
implementan cuando existan en el proyecto los documentos autorizados que definan esos formatos.
Mientras tanto se trabaja con un único perfil genérico. No crear archivos de marca con valores
plausibles pero inventados: un archivo vacío es preferible a uno falso.

## Datos de tarjeta y datos sensibles

Las tarjetas del contexto real son de ambiente de pruebas, nunca de producción, pero siguen
siendo PAN reales.

**La política distingue tres ámbitos. No se confunden:**

| Ámbito | Regla |
|---|---|
| **Navegador** | Nunca recibe el PAN completo. Solo la representación enmascarada |
| **Logs, historial y ejecuciones** | Nunca guardan el PAN completo |
| **Procesamiento transaccional** | **Sí** puede usar el PAN completo obtenido del catálogo local, para construir el `0100` y transmitirlo al host simulado o a un switch de QA autorizado |

El tercer ámbito es el que hace falsa cualquier frase del tipo "el número completo nunca sale
del servidor": sin el PAN no hay transacción que enviar. Lo que no debe salir es hacia el
navegador, los logs y el historial.

Reglas concretas: 

- Nunca registrar el PAN completo en logs, en la bitácora ni en Git.
- **El repositorio no contiene PAN completos, ni reales ni sintéticos.** Un literal con largo de
  tarjeta es indistinguible de uno real para un escáner de secretos o una auditoría. Los valores
  sintéticos que necesitan las pruebas y los datos de demostración **se generan en ejecución**
  con `domain/datos_sinteticos.py`. Una prueba de la suite hace fallar el build si aparece en
  cualquier archivo versionable una secuencia de 12 a 19 dígitos.
- El catálogo local de tarjetas de QA sí puede contener el PAN completo **en la base de datos**:
  es imprescindible para construir la transacción, y es el único lugar donde vive. Ejecuciones,
  historial y logs no lo duplican.
- Las ejecuciones referencian la tarjeta mediante `card_id`, no por PAN.
- Fuera de su pantalla de mantenimiento, mostrar solo `************1234`. Esto incluye el
  isoscopio: enmascarar los campos que transportan datos de tarjeta.
- El archivo SQLite que contenga tarjetas reales de QA no se versiona.
- Nunca versionar secretos, credenciales ni archivos `.env`.

## Comportamiento con Git

- **Nunca `--force`.** Nunca `push --force`, ni siquiera "con lease".
- **No reescribir historial** —`amend`, `rebase`, `reset --hard`, `filter-branch`— salvo
  instrucción expresa del usuario en el momento.
- Commits pequeños y coherentes: un cambio conceptual por commit.
- Verificar qué queda en staging antes de confirmar; agregar archivos por nombre explícito en
  lugar de `git add .`.
- No hacer commit ni push por iniciativa propia: solo cuando el usuario lo pida.

## Mantenimiento de la documentación

- Actualizar `CONTEXTO.md` después de cada iteración significativa, siguiendo sus propias reglas
  de mantenimiento.
- Registrar en `BITACORA.md` las decisiones, correcciones de rumbo, retroalimentación recibida y
  entradas de gobernanza cuando corresponda.
- `CONTEXTO.md` es memoria operativa; `BITACORA.md` es evidencia académica del proceso. No
  mezclar sus contenidos.

## Verificación antes de afirmar

**Nunca declarar algo implementado, funcionando o corregido sin haberlo verificado contra el
código y contra Git.** Que una decisión esté aprobada no significa que exista. Antes de afirmar
que algo está hecho: leer el archivo, ejecutar la prueba o consultar `git log`, y mostrar la
evidencia. Si no se pudo verificar, decirlo explícitamente.

# Contexto del proyecto SibuTestLab8583

Memoria operativa para que una sesión nueva recupere el estado del proyecto sin depender del chat.
No sustituye a `BITACORA.md` (evidencia académica, justificaciones, gobernanza) ni duplica
`PROYECTO.md` (enunciado autoritativo del alcance).

**Última actualización:** 2026-08-12

## Estado actual

**Fase:** arranque y definición de arquitectura (Sesión 4 del calendario de `PROYECTO.md` §9).

| | |
|---|---|
| Remoto | `https://github.com/henguido/SibuTestLab8583.git` |
| Rama | `main`, con seguimiento de `origin/main` |
| Commits | 1 — `d2b8e77` |
| Versionado | `PROYECTO.md`, `FICHA-APROBACION.md`, y nada más |

**No existe todavía:** ninguna implementación del simulador (cero archivos de código),
`CLAUDE.md`, `BITACORA.md`, `README.md`, documento de arquitectura, diagramas, `.gitignore`,
`.gitattributes`, integración continua, dependencias, ni skill propio en `.claude/`.

## Decisiones vigentes

Todas aprobadas. **Ninguna implementada.**

| Ámbito | Decisión |
|---|---|
| Lenguaje | Python |
| Interfaz | Aplicación web; la CLI quedó descartada |
| Backend | FastAPI con HTML renderizado en el servidor y JavaScript mínimo. Sin React ni frontend independiente |
| Persistencia | SQLite detrás de una interfaz de repositorio, para sustituirla por PostgreSQL sin tocar el dominio |
| Codec ISO 8583 | `pyiso8583`; recibe la especificación como parámetro, lo que sirve de punto de inyección de perfiles |
| Transporte TCP | Asíncrono desde el inicio (`asyncio.open_connection()`), para que el motor de carga reutilice el mismo contrato sin reescritura |
| Perfiles de marca | La arquitectura contempla Visa y Mastercard, pero **no se inventan sus especificaciones**: solo se implementan con documentos autorizados dentro del proyecto |
| Catálogo de respuestas | Genérico para la demostración: `00`, `05`, `14`, `51`, `54`, `94` |
| Portabilidad | Ejecutable en local, en infraestructura bancaria, en contenedor o como servicio cloud. Docker es distribución posterior, no dependencia para desarrollar |

**`PerfilDeMarca` ≠ `CatalogoDeRespuestas`** — ejes independientes que no deben mezclarse: el
perfil define formato, codificación, campos y obligatorios por MTI; el catálogo determina qué
código del campo 39 cuenta como aprobado. Por eso contemplar perfiles de *formato* de Visa y
Mastercard no contradice el alcance: lo excluido son los catálogos de *respuesta* por marca.

**Gobernanza de PAN.** Tarjetas de ambiente de pruebas, nunca de producción, pero PAN reales:

- Nunca registrar el PAN completo en logs, en la bitácora ni en Git.
- Las ejecuciones referencian la tarjeta mediante un identificador interno.
- Fuera de su pantalla de mantenimiento, mostrar solo `************1234`.
- El archivo SQLite que contenga tarjetas reales de QA no debe versionarse.

## Arquitectura acordada — todavía no implementada

Recorrido: `web → orquestador → armar · validar · enviar · interpretar · evaluar · persistir`

| Módulo | Responsabilidad | Límite |
|---|---|---|
| Codec | Codificar y decodificar mensajes ISO | Recibe el perfil como parámetro; no conoce marcas |
| Validación | Las cuatro reglas de negocio | Funciones puras: sin red, sin base de datos |
| Transporte | Enviar bytes y esperar respuesta con tiempo límite | **No conoce ISO 8583.** El framing vive aquí, porque `pyiso8583` no lo cubre |
| Repositorios | Guardar ejecuciones, leer catálogos | Puerto abstracto; el dominio no conoce el motor de base de datos |
| Host simulado | Recibir 0100 y responder 0110 | Proceso aparte; usa el mismo perfil que el cliente |
| Orquestador | Secuenciar el recorrido | Única pieza que conoce a todas las demás |

El motor de carga es fase posterior y reutilizará esos módulos sin modificarlos.

## Historial de avances

| Fecha | Hito |
|---|---|
| 2026-08-04 | Se redactan `PROYECTO.md` y `FICHA-APROBACION.md`; la ficha queda aprobada sin preguntas para el docente |
| 2026-08-12 | Se define el stack y la arquitectura: web con FastAPI, SQLite tras un puerto, `pyiso8583`, perfiles de marca y gobernanza de PAN |
| 2026-08-12 | Corrección de rumbo: el transporte pasa de sockets bloqueantes en threadpool a asíncrono con `asyncio` |
| 2026-08-12 | Se inicializa Git en `main`, commit `d2b8e77` con los dos documentos aprobados, `origin` configurado y `main` publicado con push normal |

El detalle histórico y sus justificaciones pertenecen a `BITACORA.md` y a Git.

## Decisiones pendientes

1. Cómo escribir en SQLite desde código asíncrono sin bloquear el event loop (el driver es síncrono).
2. Formato exacto del framing TCP (prefijo de longitud).
3. Especificaciones reales de Visa y Mastercard, y si los obligatorios por MTI son propios de cada marca — bloqueadas por falta de documentos autorizados.
4. Esquema y columnas de la base de datos.
5. Si el motor de carga corre dentro del proceso web o aparte.
6. Estrategia de datos de demostración reproducibles para un clon limpio, sin PAN reales.
7. Contenido de `.gitignore` y `.gitattributes`.
8. Herramienta y configuración de integración continua.

## Restricciones de alcance

Fuente autoritativa: `PROYECTO.md`. Recorrido único aprobado: compra `0100` → TCP → respuesta
`0110`. Fuera de alcance: retiros, consultas de saldo, reversos, OCT, AFT, refunds, anulaciones,
verificaciones de cuenta, catálogos de códigos por marca y paneles de métricas elaborados.

Las cuatro reglas cubiertas por pruebas automatizadas tratan sobre: aprobación según el catálogo
configurado (RN-1), timeout a los 10 s contado aparte del rechazo (RN-2), validez de la respuesta
más allá del código (RN-3) y bloqueo del envío si falta un campo obligatorio del MTI (RN-4).
**Enunciado autoritativo en `PROYECTO.md` §4.**

## Próximo paso

Cerrar este archivo y luego, en la misma iteración de la Sesión 4: crear la **arquitectura
inicial**, `CLAUDE.md` y abrir `BITACORA.md`. La arquitectura debe resolver o declarar
provisionales las decisiones pendientes 1 y 2.

## Archivos importantes

| Archivo | Para qué sirve |
|---|---|
| `PROYECTO.md` | Enunciado autoritativo: alcance, reglas, calendario, criterios de entrega |
| `FICHA-APROBACION.md` | Resumen de una página, aprobado por el docente |
| `CONTEXTO.md` | Este archivo: memoria operativa del estado actual |
| `CLAUDE.md` | Instrucciones permanentes para Claude Code *(no existe todavía)* |
| `BITACORA.md` | Evidencia académica del proceso y la gobernanza *(no existe todavía)* |

## Instrucciones para retomar en una sesión nueva

1. Leer `PROYECTO.md`.
2. Leer `CLAUDE.md` cuando exista.
3. Leer `CONTEXTO.md`.
4. Consultar `BITACORA.md` cuando se necesite entender decisiones históricas.
5. Ejecutar `git status` y revisar el historial reciente.
6. **Contrastar siempre este archivo contra el código y Git antes de asumir que algo existe.**

Ante cualquier contradicción, **Git y el código son la fuente de verdad**.

## Reglas de mantenimiento

Actualizar tras cada iteración significativa. Registrar hechos, no intenciones: nunca declarar algo
implementado solo porque fue aprobado. "Estado actual" es la fotografía del presente; "Historial de
avances" es acumulativo y solo de hitos; "Próximo paso" se actualiza siempre. Si una decisión
cambia, actualizar "Decisiones vigentes" y dejar la evidencia en el historial. Nunca incluir
secretos, PAN completos ni credenciales.

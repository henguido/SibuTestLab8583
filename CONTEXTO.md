# Contexto del proyecto SibuTestLab8583

Memoria operativa para que una sesión nueva recupere el estado del proyecto sin depender del chat.
No sustituye a `BITACORA.md` (evidencia académica, justificaciones, gobernanza) ni duplica
`PROYECTO.md` (enunciado autoritativo del alcance) ni `ARQUITECTURA.md` (diseño detallado).

**Última actualización:** 2026-08-13

## Estado actual

**Fase:** cierre de la Sesión 4 del calendario de `PROYECTO.md` §9 — arquitectura documentada,
sin código.

| | |
|---|---|
| Remoto | `https://github.com/henguido/SibuTestLab8583.git` |
| Rama | `main`, con seguimiento de `origin/main` |
| Archivos existentes | `PROYECTO.md`, `FICHA-APROBACION.md`, `CONTEXTO.md`, `CLAUDE.md`, `BITACORA.md`, `.gitignore`, `.gitattributes`, `docs/arquitectura/` (documento y dos diagramas) |

Para el estado exacto de Git —commits, `HEAD`, qué está publicado— consultar `git log` y
`git status`, no este archivo.

**Todavía no existe código funcional del simulador.** Tampoco `README.md`, `src/`, dependencias
declaradas, base de datos, integración continua, ni skill propio en `.claude/`.

## Decisiones vigentes

Todas acordadas. **Aún no implementadas en código funcional.**

| Ámbito | Decisión |
|---|---|
| Lenguaje | Python |
| Interfaz | Aplicación web; la CLI quedó descartada |
| Backend | FastAPI con HTML renderizado en el servidor y JavaScript mínimo. Sin React ni frontend independiente |
| Persistencia | Contrato de repositorio **asíncrono**; adaptador inicial SQLite con `aiosqlite` para el MVP. PostgreSQL es evolución futura y no se implementa ahora |
| Codec ISO 8583 | `pyiso8583`; recibe la especificación como parámetro, lo que sirve de punto de inyección de perfiles |
| Transporte TCP | Asíncrono desde el inicio (`asyncio.open_connection()`), para que el motor de carga reutilice el mismo contrato sin reescritura |
| Framing | Contrato independiente (`FramingStrategy`), invocado por el transporte y solo por él; la web y el orquestador no conocen el formato. Sin formato concreto asignado todavía |
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

Documento completo en `docs/arquitectura/ARQUITECTURA.md`, con diagramas versionados en
`componentes.mmd` y `flujo-compra.mmd`. Aquí solo lo indispensable para orientarse:

Dirección de dependencia: `web → application service → dominio/puertos → adaptadores`.

Módulos: web, orquestador, perfiles, codec ISO 8583, validación, transporte TCP, framing,
persistencia, host simulado, y motor de carga como fase posterior.

Tres límites que no se cruzan: la web no conoce SQLite, sockets ni `pyiso8583`; el transporte no
conoce ISO 8583 —recibe bytes opacos y delega el enmarcado a `FramingStrategy`—; la validación de
reglas de negocio es pura y RN-4 se aplica antes de codificar.

## Historial de avances

| Fecha | Hito |
|---|---|
| 2026-08-04 | Se redactan `PROYECTO.md` y `FICHA-APROBACION.md`; la ficha queda aprobada sin preguntas para el docente |
| 2026-08-12 | Se define el stack y la arquitectura: web con FastAPI, SQLite tras un puerto, `pyiso8583`, perfiles de marca y gobernanza de PAN |
| 2026-08-12 | Corrección de rumbo: el transporte pasa de sockets bloqueantes en threadpool a asíncrono con `asyncio` |
| 2026-08-12 | Se inicializa Git en `main`, commit `d2b8e77` con los dos documentos aprobados, `origin` configurado y `main` publicado con push normal |
| 2026-08-12 | Commit `4269e03` incorpora `CONTEXTO.md` como memoria operativa del proyecto |
| 2026-08-13 | Primera iteración arquitectónica: se crean `CLAUDE.md`, `BITACORA.md`, `.gitignore`, `.gitattributes` y `docs/arquitectura/`. Se decide persistencia asíncrona con `aiosqlite` y framing como contrato independiente |

El detalle histórico y sus justificaciones pertenecen a `BITACORA.md` y a Git.

## Decisiones pendientes

1. Formato concreto del framing TCP (el contrato existe; el formato no está asignado).
2. Especificaciones reales de Visa y Mastercard, y si los obligatorios por MTI son propios de cada marca — bloqueadas por falta de documentos autorizados.
3. Esquema y columnas de la base de datos.
4. Si el motor de carga corre dentro del proceso web o aparte.
5. Estrategia de datos de demostración reproducibles para un clon limpio, sin PAN reales.
6. Herramienta y configuración de integración continua.
7. Mecanismo concreto para detectar si el simulador afirma que una prueba fue exitosa sin serlo (`PROYECTO.md` §7.6).
8. Cifrado en reposo del catálogo de tarjetas de QA — fuera del alcance académico, necesario para una evolución comercial.

## Restricciones de alcance

Fuente autoritativa: `PROYECTO.md`. Recorrido único aprobado: compra `0100` → TCP → respuesta
`0110`. Fuera de alcance: retiros, consultas de saldo, reversos, OCT, AFT, refunds, anulaciones,
verificaciones de cuenta, catálogos de códigos por marca y paneles de métricas elaborados.

Las cuatro reglas cubiertas por pruebas automatizadas tratan sobre: aprobación según el catálogo
configurado (RN-1), timeout a los 10 s contado aparte del rechazo (RN-2), validez de la respuesta
más allá del código (RN-3) y bloqueo del envío si falta un campo obligatorio del MTI (RN-4).
**Enunciado autoritativo en `PROYECTO.md` §4.**

## Próximo paso

Sesión 5 (18 de agosto): recorrido de compra `0100`/`0110` funcionando de extremo a extremo, con
persistencia real, contra el host simulado. Es la primera iteración que produce código.

## Archivos importantes

| Archivo | Para qué sirve |
|---|---|
| `PROYECTO.md` | Enunciado autoritativo: alcance, reglas, calendario, criterios de entrega |
| `FICHA-APROBACION.md` | Resumen de una página, aprobado por el docente |
| `CLAUDE.md` | Instrucciones permanentes para Claude Code en este repositorio |
| `CONTEXTO.md` | Este archivo: memoria operativa del estado actual |
| `BITACORA.md` | Evidencia académica del proceso, decisiones y gobernanza |
| `docs/arquitectura/ARQUITECTURA.md` | Módulos, contratos y decisiones de diseño |
| `docs/arquitectura/*.mmd` | Diagramas Mermaid: componentes y flujo de compra |

## Instrucciones para retomar en una sesión nueva

1. Leer `PROYECTO.md`.
2. Leer `CLAUDE.md`.
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
secretos, PAN completos ni credenciales. No duplicar aquí información dinámica que Git provee de
forma autoritativa —cantidad de commits, SHA de `HEAD`—: conservar SHA solo cuando identifiquen
un hito histórico concreto.

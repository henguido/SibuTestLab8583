# Contexto del proyecto SibuTestLab8583

Memoria operativa para que una sesión nueva recupere el estado del proyecto sin depender del chat.
No sustituye a `BITACORA.md` (evidencia académica, justificaciones, gobernanza) ni duplica
`PROYECTO.md` (enunciado autoritativo del alcance) ni `ARQUITECTURA.md` (diseño detallado).

**Última actualización:** 2026-08-19

## Estado actual

**Fase:** Sesión 6 — integración continua definida y refactorización aplicada. El simulador se
usa desde el navegador sobre el recorrido real.

| | |
|---|---|
| Remoto | `https://github.com/henguido/SibuTestLab8583.git` |
| Rama | `main`, con seguimiento de `origin/main` |
| Documentos | `PROYECTO.md`, `FICHA-APROBACION.md`, `CONTEXTO.md`, `CLAUDE.md`, `BITACORA.md`, `docs/arquitectura/` (documento y dos diagramas) |
| Proyecto Python | `pyproject.toml` instalable, `src/sibutestlab8583/` y `tests/` |

Para el estado exacto de Git —commits, `HEAD`, qué está publicado— consultar `git log` y
`git status`, no este archivo.

**Qué funciona y está verificado:** una compra completa `0100 → TCP → 0110` contra el host
simulado propio, con codec, framing, transporte y SQLite reales, terminando en una ejecución
persistida y enmascarada. Las cuatro reglas de negocio están implementadas y probadas. El
paquete se instala en modo editable y `sibu-init-db` inicializa la base de forma idempotente.
Y desde el navegador: formulario de compra, resultado con isoscopio enmascarado e historial.
**101 pruebas en verde** sobre **Python 3.13.3**, la única versión instalada en la máquina.

**Todavía NO existe:** el motor de carga, los perfiles reales de Visa y Mastercard, `README.md`,
Docker, skill propio en `.claude/` ni autenticación. El workflow de CI ya está escrito, pero
**todavía no se ha ejecutado**: no hay resultados de Python 3.11 ni 3.12.

## Decisiones vigentes

Acordadas y, salvo donde se indique, **ya implementadas y probadas**.

| Ámbito | Decisión |
|---|---|
| Lenguaje | Python |
| Interfaz | Aplicación web; la CLI quedó descartada |
| Backend | FastAPI con HTML renderizado en el servidor y JavaScript mínimo. Sin React ni frontend independiente |
| Persistencia | Contrato de repositorio **asíncrono**; adaptador inicial SQLite con `aiosqlite` para el MVP. PostgreSQL es evolución futura y no se implementa ahora |
| Codec ISO 8583 | `pyiso8583`; recibe la especificación como parámetro, lo que sirve de punto de inyección de perfiles |
| Transporte TCP | Asíncrono desde el inicio (`asyncio.open_connection()`), para que el motor de carga reutilice el mismo contrato sin reescritura |
| Framing | Contrato independiente (`FramingStrategy`), invocado por el transporte y solo por él; la web y el orquestador no conocen el formato. Implementado un framing **de demostración**: prefijo binario de 2 bytes big-endian. El de un switch real dependerá de su especificación |
| Perfiles de marca | La arquitectura contempla Visa y Mastercard, pero **no se inventan sus especificaciones**: solo se implementan con documentos autorizados dentro del proyecto. Hoy existe únicamente el perfil genérico |
| Catálogo de respuestas | Genérico para la demostración: `00`, `05`, `14`, `51`, `54`, `94` |
| Portabilidad | Ejecutable en local, en infraestructura bancaria, en contenedor o como servicio cloud. Docker es distribución posterior, no dependencia para desarrollar |

**`PerfilDeMarca` ≠ `CatalogoDeRespuestas`** — ejes independientes que no deben mezclarse: el
perfil define formato, codificación, campos y obligatorios por MTI; el catálogo determina qué
código del campo 39 cuenta como aprobado. Por eso contemplar perfiles de *formato* de Visa y
Mastercard no contradice el alcance: lo excluido son los catálogos de *respuesta* por marca.

**Gobernanza de PAN.** Tarjetas de ambiente de pruebas, nunca de producción, pero PAN reales.
Tres ámbitos que no se confunden: el **navegador** nunca recibe el PAN completo; **logs,
historial y ejecuciones** nunca lo guardan; el **procesamiento transaccional sí lo usa**, tomado
del catálogo local, para construir el `0100` y transmitirlo. Sin el PAN no hay transacción que
enviar.

- Nunca registrar el PAN completo en logs, en la bitácora ni en Git.
- **El repositorio no contiene PAN completos, ni reales ni sintéticos**; los valores sintéticos
  necesarios para pruebas y demostración se generan en ejecución. Una prueba de la suite lo
  vigila automáticamente.
- Las ejecuciones referencian la tarjeta mediante un identificador interno.
- Fuera de su pantalla de mantenimiento, mostrar solo `************1234`.
- El archivo SQLite que contenga tarjetas reales de QA no debe versionarse.

## Arquitectura

Documento completo en `docs/arquitectura/ARQUITECTURA.md`, con diagramas versionados en
`componentes.mmd` y `flujo-compra.mmd`. Aquí solo lo indispensable para orientarse:

Dirección de dependencia: `web → application service → dominio/puertos → adaptadores`.

Módulos implementados: web, composición, orquestador, consultas, perfiles, codec ISO 8583,
validación, framing, transporte TCP, persistencia y host simulado. Pendiente: motor de carga.

La infraestructura se cablea en un solo lugar, `composicion.py`. La web recibe esa composición
por inyección y no construye adaptadores en sus endpoints.

RN-3 compara los campos **3, 4, 7, 11 y 41**, derivados del perfil (obligatorios de la respuesta
menos el campo 39). RN-3 se evalúa **antes** que RN-1: una respuesta aprobada que no corresponde
a la solicitud es `Invalida`, nunca `Aprobada`. Ese orden es el mecanismo contra falsos positivos
que exige `PROYECTO.md` §7.6.

Framing de demostración: prefijo binario de 2 bytes big-endian con la longitud del payload. No se
atribuye a ninguna marca.

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
| 2026-08-17 | Commit `5072c51` publica esa iteración arquitectónica |
| 2026-08-17 | Fundación ejecutable: proyecto Python instalable, modelos de dominio, perfil genérico, catálogo, persistencia SQLite asíncrona con inicialización idempotente. Commit `93708f0` |
| 2026-08-19 | Núcleo transaccional: codec, las cuatro reglas de negocio, framing de demostración, transporte TCP asíncrono, host simulado y orquestador. Commit `de84818` |
| 2026-08-19 | Interfaz web con FastAPI y Jinja: formulario, resultado, isoscopio enmascarado e historial sobre el núcleo real. Commit `dc8cc8b` |
| 2026-08-19 | Workflow de GitHub Actions con matriz 3.11/3.12/3.13 y refactorización de lo acumulado. Sin funcionalidad nueva; 101 pruebas en verde |

El detalle histórico y sus justificaciones pertenecen a `BITACORA.md` y a Git.

## Decisiones pendientes

1. Formato concreto del framing para un switch QA real. El de demostración existe (prefijo de 2 bytes); el del ambiente real dependerá de su especificación.
2. Especificaciones reales de Visa y Mastercard, y si los obligatorios por MTI son propios de cada marca — bloqueadas por falta de documentos autorizados.
3. Compatibilidad con Python 3.11 y 3.12. `requires-python` sigue declarando `>=3.13` porque es la única versión comprobada. El CI ya prueba las tres versiones usando `pip install --ignore-requires-python`, que ejecuta el código sin alterar el metadata. **Ampliar el rango solo cuando el CI muestre las tres en verde.**
4. Si el motor de carga corre dentro del proceso web o aparte.
5. Si un fallo de conexión debe persistirse como ejecución. Hoy la excepción sube, la web la informa, pero no queda rastro en el historial. Resolverlo exigiría un estado nuevo en el núcleo.
5. Estrategia de datos de demostración reproducibles para un clon limpio, sin PAN reales.
6. Si conviene añadir un trabajo de CI en Windows: hoy el workflow corre en Linux y todo lo verificado localmente fue en Windows.
7. Otros escenarios de falso positivo (`PROYECTO.md` §7.6). El primero ya está cubierto: una respuesta con código aprobado pero correlación incorrecta se registra `Invalida`. Faltan los demás casos.
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

Observar el primer resultado del CI. Si las tres versiones de Python pasan, ampliar
`requires-python` a `>=3.11` con esa evidencia. Después, `README.md` usando el procedimiento de
instalación que el CI haya demostrado reproducible, y la Sesión 7: skill de arranque y motor de
pruebas de carga.

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
| `pyproject.toml` | Dependencias, empaquetado y configuración de `pytest` |
| `src/sibutestlab8583/` | Código: `domain/`, `application/`, `web/`, `profiles/`, `adapters/`, `composicion.py` |
| `.github/workflows/tests.yml` | CI: suite en Python 3.11/3.12/3.13 y verificación de clon limpio |
| `tests/` | Pruebas técnicas de la fundación |

Para levantar el proyecto desde cero: crear un entorno virtual, `pip install -e ".[dev]"`,
`sibu-init-db` y `pytest`. La demostración usa dos terminales: `sibu-host-demo` levanta el host
simulado y `uvicorn sibutestlab8583.web.app:app` la interfaz web. La web **no** levanta el host
simulado: la arquitectura lo mantiene como proceso aparte.

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

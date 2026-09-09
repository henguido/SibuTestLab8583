# Contexto del proyecto SibuTestLab8583

Memoria operativa para que una sesión nueva recupere el estado del proyecto sin depender del chat.
No sustituye a `BITACORA.md` (evidencia académica, justificaciones, gobernanza) ni duplica
`PROYECTO.md` (enunciado autoritativo del alcance) ni `ARQUITECTURA.md` (diseño detallado).

**Última actualización:** 2026-09-07 (cinco mejoras funcionales posteriores al cierre, revisadas
críticamente y con el hallazgo de exposición en la URL ya resuelto)

## Estado actual

**Iteración posterior al cierre (2026-09-07):** cinco mejoras funcionales pedidas explícitamente
por el usuario después de la entrega académica, ya implementadas y verificadas (código,
`pytest -q` y navegador): (1) el historial persiste `Ejecucion.motivo_detalle` -causa concreta
y segura de un fallo, distinta de "no disponible" para filas anteriores a este campo; nunca
texto crudo de una excepción de terceros, ver más abajo-; (2) `/historial` admite filtros
(fecha, estado, PASS/FAIL/sin expectativas, tarjeta, destino, STAN) y paginación
(`FiltroHistorial` en el dominio, `RepositorioEjecuciones.buscar`); (3) el constructor conserva
tarjeta/monto/campos/expectativas/nombre al cambiar de conexión -el botón "Cambiar" somete el
formulario por **POST** a `/` (`cambiar_conexion` en `web/app.py`), nunca por GET: los valores
viajan en el cuerpo de la petición, nunca en la URL ni en el historial del navegador ni en los
logs de acceso del servidor- y una suite con orden inválido conserva los escenarios ya marcados;
(4) `resultado.html` ofrece "Editar y volver a ejecutar" y "Guardar como escenario"
(`GET /?ejecucion_id={id}`), que recuperan la configuración usada sin tocar el PAN -incluidas
las expectativas, tomadas del snapshot propio de la ejecución (`evaluacion_json`), nunca del
escenario que la originó aunque éste se haya editado después-; (5) `corrida_detalle.html`
descarga JSON/CSV reutilizando `application/exportacion_corridas.py` sin re-ejecutar la suite.
Detalle completo, archivo por archivo, en `BITACORA.md` (entradas "Cinco mejoras funcionales
posteriores a la entrega", "Revisión crítica de las cinco mejoras" y "Cierre del hallazgo de
datos del formulario en la URL"). Suite: **941 passed, 2 skipped** (antes 897). Sin commit ni
push.

**Fase:** la Fase 1 (módulo de Configuración) queda **funcionalmente congelada para esta
entrega** (decisión del 2026-08-26). Los sub-bloques pendientes —exponer los ocho campos de
laboratorio, la administración visual de catálogos y de destinos, la integración posterior de
Track 1/Track 2 en el mensaje ISO, los perfiles reales de marca, el isoscopio 2.0 y el motor
de carga— pasan a trabajo futuro sin fecha, sin haberse eliminado del horizonte del proyecto.
El trabajo activo pasa al cierre académico: documentación final, documento de negocio,
arquitectura, presentación y revisión contra la consigna.

Tras el congelamiento del 2026-08-26, se retomó trabajo funcional adicional no cubierto por
esa decisión: Bloque 5 —escenarios reutilizables (`ServicioEscenarios`), validación
expected-vs-actual, suites de regresión (`ServicioSuites`, `CorredorDeSuites`) y una CLI
`sibu-run-suite` para ejecutarlas sin navegador— y Bloque 6 —integración CI genérica de
referencia (`scripts/ci_esperar_host.py`, `scripts/sembrar_suite_demo.py`,
`scripts/verificar_artefacto_seguro.py`, `.github/workflows/ci-suite-demo.yml`), documentada
en `docs/ci/INTEGRACION_CI.md`—. Ambos ya están commiteados e implementados; no son parte del
congelamiento de Fase 1 (Configuración), que sigue vigente tal como se decidió.

Sin commitear todavía en el working tree: Bloque 7 —reporte portable JSON/CSV de una corrida
ya persistida (`sibu-run-suite export-run`, `application/exportacion_corridas.py`)—, la
corrección de un cuelgue de CI en Python 3.12 en `tests/test_conexiones_administracion.py`
(ver «Historial de avances», 2026-09-06), y cuatro correcciones puntuales del Ciclo 6 de cierre
(2026-09-07): el doble salto de línea de `export-run --format csv` a stdout, un mensaje de
error específico para `evaluacion_json` corrupto en la CLI, un test de
`tests/test_politica_campos.py` que antes no invocaba `armar_compra` de verdad, y `newline=""`
al escribir `--out` para que Windows no traduzca los `\n` deliberados a `\r\n` (ver «Historial
de avances», 2026-09-07).

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
persistida y enmascarada. Las cuatro reglas de negocio están implementadas y probadas. RN-1
clasifica según el **catálogo persistido en SQLite**, leído en cada compra mediante
`RepositorioCatalogosSQLite` — ya no según una constante fija en memoria; editar la tabla
`codigos_respuesta` cambia el comportamiento sin reiniciar la aplicación. El
paquete se instala en modo editable y `sibu-init-db` inicializa la base de forma idempotente.
Y desde el navegador: pantalla de nueva transacción, resultado con resumen e isoscopio
enmascarado, e historial **navegable**: cada ejecución tiene su detalle en `/historial/{id}`,
con los campos ISO de la solicitud y de la respuesta. **897 pruebas en verde — cifra de
cierre que se publicó académicamente**, con Bloque 7, el fix de Python 3.12 y las cuatro
correcciones del Ciclo 6 ya incluidas (decisión tomada en la revisión final del 2026-09-07;
ver «Historial de avances» para el detalle de cada corrección), incluidas 29 específicas de
RN-1 a RN-4 (`tests/test_reglas_negocio.py`). **Superada por la iteración posterior al
cierre** descrita arriba: la suite actual da 941 passed, 2 skipped. El CI ejecuta la suite en Python
3.11, 3.12 y 3.13, corre aparte las cuatro reglas de negocio, y en un job propio
(`clon-limpio`) comprueba que el repositorio no contenga artefactos locales versionados y que
se instale respetando el metadata declarado. Aparte de eso, y de forma manual —no es
evidencia de CI—, el 2026-09-03 se validó en Windows la reproducibilidad completa desde un
clon separado, sin `.venv` ni base SQLite previa: recorrido manual completo, 436 passed, RN-1
a RN-4 con 29 passed y guardia de PAN en `passed`.

Persistencia base para la Fase 1 de Configuración (sub-bloque 2, sin interfaz todavía):
`TarjetaPrueba.activa` (con lectura y escritura reales en `RepositorioTarjetasSQLite`, incluido el
upsert) y la tabla `destinos`, con su entidad `DestinoGuardado`, su puerto `RepositorioDestinos` y
su adaptador `RepositorioDestinosSQLite`, sembrada con un único destino `LOCAL-DEMO`. `DestinoTcp`
no cambió. Una ejecución sigue guardando `destino_host`/`destino_puerto` como valores propios, sin
clave foránea hacia `destinos`: editar o desactivar un destino no debe alterar el historial ya
registrado. La migración aditiva se generalizó (`_migrar(conexion, tabla, columnas)`) y se probó
contra una base anterior real —con tarjeta, ejecución, secuencia STAN y el esquema previo de
`ejecuciones` a la vez— comprobando que ninguno de esos datos se pierde ni se modifica, ni siquiera
tras una segunda inicialización.

Módulo de Configuración con interfaz propia (sub-bloque 3/4): `GET /configuracion` muestra tres
bloques —Tarjetas de prueba, Códigos de respuesta, Destinos—, y solo el primero enlaza a algo
real; Códigos y Destinos siguen marcados «Próximamente», sin ruta propia todavía. La
administración de tarjetas es completa: listar, crear, editar y activar/desactivar, con
`ServicioTarjetas` (`application/tarjetas.py`) construido solo sobre `RepositorioTarjetas` (sin
cambios de contrato). `card_id` es requerido e inmutable tras crear. El PAN completo solo se
recibe en ese formulario, nunca se reexpone (ni en éxito ni en error), y `TarjetaAdministrada` no
tiene campo para el PAN completo. Un PAN que falla Luhn queda `sintetica=True` sin fricción; uno
que pasa Luhn exige la casilla de confirmación QA. En edición, «Nuevo PAN» vacío conserva el
número y el tipo actuales. Toda mutación exitosa redirige (303) a `/configuracion/tarjetas`;
`POST .../estado` valida estrictamente `"0"`/`"1"`, sin convertir un valor manipulado en booleano.
Sin filtrar todavía tarjetas inactivas en la pantalla de compra: esa integración es un sub-bloque
posterior.

`TarjetaPrueba` se amplió (sub-bloque 5) con ocho campos de laboratorio: `titular`,
`service_code`, `discretionary_data`, `cvv`, `cvv2`, `icvv`, `card_sequence_number`,
`pin_block_laboratorio` — todos `str = ""`, persistidos en `tarjetas_prueba` y leídos/escritos
por `RepositorioTarjetasSQLite`. **No se persisten Track1 ni Track2 completos, ni overrides de
track**: se derivarán más adelante desde PAN + titular + expiración + service code +
discretionary data, sin crear una segunda fuente del PAN. **El PIN en claro no se modela en
ningún campo**; `pin_block_laboratorio` es un valor con forma de PIN Block para pruebas de
laboratorio, no uno criptográficamente válido. `application/tarjetas.py`, `ServicioTarjetas`,
`TarjetaAdministrada` y la interfaz todavía no exponen estos campos; el perfil genérico y el
mensaje ISO no cambiaron — nada de esto viaja todavía en el 0100/0110.

Track 1 y Track 2 tienen ya una **derivación pura de dominio** (sub-bloque 6,
`domain/tracks.py`): dos funciones sin I/O que arman la representación lógica a partir de
PAN, titular, expiración, service code y discretionary data, con 51 pruebas propias
(`tests/test_tracks.py`). **Nada las invoca todavía**: el perfil genérico sigue sin DE35 ni
DE45, el codec no las codifica, y no viajan en ningún `0100` real. `application/tarjetas.py`,
`ServicioTarjetas`, `TarjetaAdministrada` y la interfaz tampoco las exponen.

La interfaz tiene identidad propia: cinta con la marca `SibuTestLab8583` y el subtítulo
`Laboratorio de pruebas ISO 8583`, navegación entre `Nueva transacción`, `Historial` y
`Configuración`, y una hoja de estilos propia en `src/sibutestlab8583/web/estatico/sibu.css`,
servida en `/estatico`.
Los siete desenlaces se presentan con cuatro pistas simultáneas —señal gráfica, rótulo corto,
título y explicación— para no depender del color. Todo el texto visible lleva ortografía española
completa; identificadores, enums, clases, tokens y valores de `data-estado` se mantienen en ASCII,
y una prueba lo comprueba en ambos sentidos. Contraste medido: el peor de los siete es
5.89:1 y el peor par de texto 5.42:1, ambos por encima del mínimo AA de 4.5:1.

**Todavía NO existe:** administración visual de códigos de respuesta ni de destinos, selector de
destino ni filtro de tarjetas activas en la pantalla de compra, el modo avanzado ISO 8583 para
editar campos de la solicitud, el isoscopio 2.0 —comparar solicitud contra respuesta y mostrar el
bitmap—, el motor de carga, los perfiles reales de Visa y Mastercard, Docker ni autenticación.
**DE35 y DE45 tampoco se transmiten**: Track 1 y Track 2 existen solo como derivación de
dominio (ver arriba).

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
| Perfiles de marca | La arquitectura contempla Visa y Mastercard, pero **no se inventan sus especificaciones**: solo se implementan a partir de documentación de marca disponible y aprobada como fuente. Esa documentación ya existe y **no se versiona**; los perfiles **siguen sin implementarse**. Hoy existe únicamente el perfil genérico |
| Catálogo de respuestas | Genérico para la demostración: `00`, `05`, `14`, `51`, `54`, `94`. Persistido en SQLite (`codigos_respuesta`) y leído en cada compra vía `RepositorioCatalogosSQLite`, sin caché; `CATALOGO_GENERICO` (en `domain/catalogo.py`) queda solo como semilla de `inicializar()`, no como fuente activa en ejecución. Catálogo activo configurable con `Configuracion.catalogo_activo` / variable `SIBU_CATALOGO`, con el genérico como valor por defecto |
| Portabilidad | Ejecutable en local, en infraestructura bancaria, en contenedor o como servicio cloud. Docker es distribución posterior, no dependencia para desarrollar |
| Python soportado | `>=3.13`, no una versión exacta. Comprobado con 3.13.x en la máquina de desarrollo original y con 3.14.7 en una segunda máquina, vía `demo.cmd` |

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
- **DE 14, fecha de vencimiento: decisión tomada.** Permanece visible y se persiste **sin
  enmascarar** en esta etapa, asociada a la tarjeta de prueba. Por eso
  `CAMPOS_SENSIBLES = {"2", "35"}` es deliberado y el campo 14 **no** se le añade.

## Arquitectura

Documento completo en `docs/arquitectura/ARQUITECTURA.md`, con diagramas versionados en
`componentes.mmd` y `flujo-compra.mmd`. Aquí solo lo indispensable para orientarse:

Dirección de dependencia: `web → application service → dominio/puertos → adaptadores`.

Módulos implementados: web, composición, orquestador, consultas, perfiles, codec ISO 8583,
validación, framing, transporte TCP, persistencia, generador de STAN, host simulado,
escenarios reutilizables, suites de regresión con su corredor, CLI de suites (Bloque 5),
integración CI genérica de referencia (Bloque 6) y reporte de exportación de corridas en
JSON/CSV (Bloque 7). Pendiente: motor de carga.

El número de trazabilidad (campo 11) lo entrega el puerto `GeneradorStan`, con una secuencia
persistente en la tabla `secuencias` e incrementada con una sola sentencia
`UPDATE … RETURNING`, atómica frente a peticiones concurrentes. Tras `999999` reinicia el ciclo.

La infraestructura se cablea en un solo lugar, `composicion.py`. La web recibe esa composición
por inyección y no construye adaptadores en sus endpoints.

La presentación de la web vive en `web/presentacion.py`: `AVISOS` es la única fuente de cómo se
rotula cada estado —tono, señal, etiqueta corta, título y explicación— y `SECCIONES` la única
fuente de la navegación. Las plantillas no duplican ninguna de las dos listas. Solo se declaran
secciones cuya ruta existe: `Tarjetas de prueba` está prevista y no se muestra todavía.

Ocho pantallas: nueva transacción, resultado, historial, **detalle de una ejecución**
(`/historial/{id}`), no encontrado, y administración de Configuración (portada, listado de
tarjetas, alta/edición de tarjetas). Los componentes que dos de ellas comparten
—el isoscopio, el banner de estado y el resumen de métricas— viven como macros en
`plantillas/_piezas.html`; se extrajo solo lo que ya tenía dos consumidores reales. El detalle
lee los campos con `application/serializacion.py` y **declara en pantalla cuando una ejecución
proviene del formato de texto anterior**, cuya fidelidad no es demostrable.

Cada ejecución guarda **dos** representaciones de cada mensaje, ya enmascaradas: el texto
delimitado de siempre, legible de un vistazo, y una estructurada en JSON con `version`, `mti`,
`perfil` y `campos`. La segunda existe porque la primera parte un valor que contenga su separador
`` | ``, e inventa un campo inexistente al leerlo. `application/serializacion.py` concentra la
escritura y una lectura que **nunca lanza** y que marca como no fiel todo lo que provenga del
formato anterior, porque su fidelidad no es demostrable. La respuesta conserva `crudo` por campo;
la solicitud no, porque el codec no lo entrega.

RN-3 compara los campos **3, 4, 7, 11 y 41**, derivados del perfil (obligatorios de la respuesta
menos el campo 39). RN-3 se evalúa **antes** que RN-1: una respuesta aprobada que no corresponde
a la solicitud es `Invalida`, nunca `Aprobada`. Ese orden es el mecanismo contra falsos positivos
que exige `PROYECTO.md` §7.6.

Framing de demostración: prefijo binario de 2 bytes big-endian con la longitud del payload. No se
atribuye a ninguna marca.

Tres límites que no se cruzan: la web no conoce SQLite, sockets ni `pyiso8583`; el transporte no
conoce ISO 8583 —recibe bytes opacos y delega el enmarcado a `FramingStrategy`—; la validación de
reglas de negocio es pura y RN-4 se aplica antes de codificar.

**Siete estados de ejecución**, y todo intento queda persistido. Se distinguen por lo que cada
situación permite **demostrar**, no por la excepción que la originó:

- `APROBADA`, `RECHAZADA`, `INVALIDA` — llegó una respuesta que se pudo evaluar.
- `TIMEOUT` — **exactamente** RN-2: la conexión se estableció, la escritura local terminó sin
  error, se esperó y no llegó respuesta completa dentro del límite. **No** afirma que el destino
  recibiera ni procesara el mensaje: eso no es observable desde este cliente.
- `ERROR_CONEXION` — no hubo sesión TCP. Demostrable que nada se transmitió.
- `ERROR_TRANSMISION` — hubo sesión TCP y el intercambio quedó **indeterminado**. **No** se
  puede afirmar cuánto recibió el destino, así que está prohibido decir que no se envió.
- `NO_ENVIADA` — **no se llegó a intentar transmisión por la red**: falta un obligatorio (RN-4),
  el codec falló, o el framing de salida rechazó el payload antes de conectar. Ahí sí es
  demostrable. No se dice «no llegó al transporte», porque el framing es parte del transporte.

El transporte devuelve estos desenlaces como resultado: ninguna excepción de `asyncio` ni ningún
`OSError` cruza su contrato.

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
| 2026-08-19 | Workflow de GitHub Actions con matriz 3.11/3.12/3.13 y refactorización de lo acumulado. Commit `deb7f63`; CI en verde en las tres versiones |
| 2026-08-19 | Auditoría de producto en cinco perspectivas, sin tocar código. Se ordenan los hallazgos en P0, P1 y P2 |
| 2026-08-19 | P0-1: el STAN pasa a una secuencia persistente y atómica tras el puerto `GeneradorStan`. Commit `8557c4c` |
| 2026-08-19 | P0-2 y P0-3: se distinguen y se persisten los siete desenlaces; `FalloDeTransmision` separa lo indeterminado de lo demostrable. Commit `78ecc59` |
| 2026-08-20 | Rediseño de la interfaz: identidad propia, navegación, resumen de resultado, isoscopio legible e historial completo. Hoja de estilos propia con tokens, sin framework ni JavaScript. Ortografía española completa en todo el texto visible. Commit `ede40c0` |
| 2026-08-23 | Persistencia estructurada: columnas `solicitud_json` y `respuesta_json`, migración SQLite idempotente y lectura tolerante. Corrige que el formato de texto delimitado partiera un valor que contuviera el separador. Commit `d6a78b1` |
| 2026-08-24 | Detalle navegable de una ejecución en `/historial/{id}`, con 404 propio. El isoscopio, el banner de estado y el resumen pasan a macros compartidas. Revisión visual humana antes del commit |
| 2026-08-24 | D-1: RN-1 pasa a usar el catálogo persistido en SQLite (`RepositorioCatalogosSQLite`) en vez de la constante `CATALOGO_GENERICO`. `Composicion.orquestador()` pasa a asíncrono y consulta la base en cada llamada, sin caché. Sin cambios de esquema ni de interfaz |
| 2026-08-24 | Fase 1, sub-bloque 2: `TarjetaPrueba.activa` con lectura/escritura reales; tabla `destinos` con `DestinoGuardado`, `RepositorioDestinos` y `RepositorioDestinosSQLite`, semilla `LOCAL-DEMO`; migración aditiva generalizada, probada contra una base anterior real completa. Sin interfaz |
| 2026-08-25 | Fase 1, sub-bloque 3/4: `GET /configuracion` (tres bloques, solo Tarjetas enlaza a algo real) y administración web completa de tarjetas (`ServicioTarjetas`): crear, editar, activar/desactivar. `card_id` inmutable, PAN completo solo en el formulario administrativo y nunca reexpuesto, validación Luhn con confirmación QA, redirect 303 tras mutaciones, `/estado` con validación estricta de entrada. Sin filtro de tarjetas activas en la compra todavía |
| 2026-08-25 | Fase 1, sub-bloque 5: `TarjetaPrueba` gana ocho campos de laboratorio (titular, service_code, discretionary_data, cvv, cvv2, icvv, card_sequence_number, pin_block_laboratorio), persistidos en SQLite con migración aditiva. Sin Track1/Track2 completos ni overrides persistentes, sin PIN en claro, sin cambios en `ServicioTarjetas`, la interfaz ni el perfil genérico |
| 2026-08-26 | Fase 1, sub-bloque 6: derivación pura de Track 1 y Track 2 en `domain/tracks.py`, 51 pruebas nuevas (385→436 en la suite). No transmiten DE35/DE45 todavía; nada del proyecto las invoca. Commit `725d316` |
| 2026-08-26 | Decisión: se congela el crecimiento funcional —incluida la Fase 1 restante y el motor de carga— para priorizar el cierre de entregables académicos. `PROYECTO.md` no se modifica. Decisión de trabajo, sin commit propio |
| 2026-09-03 | `README.md` y `demo.cmd`: procedimiento manual y camino rápido de arranque en Windows. Reproducibilidad desde clon limpio validada manualmente en dos máquinas distintas; CRLF ajustado en `.gitattributes` para `.cmd`. Commit `633be24` |
| 2026-09-03 | Skill de Claude Code `levantar-demo` (`.claude/skills/levantar-demo/SKILL.md`): reutiliza `demo.cmd` y verifica HTTP y TCP de forma independiente, sin remediación automática. Commit `ba07853` |
| 2026-09-04 | Mejora del constructor ISO y gestión de conexiones. Commit `044a565` |
| 2026-09-04 | Escenarios reutilizables (`ServicioEscenarios`) y reejecución de una transacción guardada. Commit `c75f67e` |
| 2026-09-04 | Bloque 5: validación expected-vs-actual sobre una ejecución, con defensa en profundidad en `Orquestador.ejecutar_compra` además de la capa web. Commit `1aad67f` |
| 2026-09-04 | Bloque 5: suites de regresión (`ServicioSuites`, `CorredorDeSuites`), ejecución secuencial con aislamiento de fallas por escenario, snapshot histórico inmutable de cada corrida. Commit `97ae8cb` |
| 2026-09-05 | Bloque 5: CLI `sibu-run-suite` (`list-suites`/`run-suite`, texto o JSON, códigos de salida 0-6/130), reutilizando el mismo `CorredorDeSuites` que la web. Auditoría nocturna: fix de FK real en `RepositorioCorridasSuiteSQLite.actualizar_item`, cobertura de seguridad/persistencia ampliada. Commit `2b5b268` |
| 2026-09-05 | Bloque 6: integración CI genérica de referencia (`scripts/ci_esperar_host.py`, `scripts/sembrar_suite_demo.py`, `scripts/verificar_artefacto_seguro.py`), workflow `.github/workflows/ci-suite-demo.yml`, documentado en `docs/ci/INTEGRACION_CI.md`. Ejecutado y verificado en GitHub Actions real (run 34001652509, SUCCESS). Commit `da8eb72` |
| 2026-09-06 | Hallazgo de CI: el job "Suite en Python 3.12" de `tests.yml` se colgaba indefinidamente. Causa raíz: `tests/test_conexiones_administracion.py` usaba un handler de conexión (`lambda r, w: None`) que nunca cerraba el `writer`; bajo Python 3.11 `asyncio.Server.wait_closed()` no esperaba de verdad las conexiones activas (casi no-op), y Python 3.12 lo corrigió (CPython gh-123720, mismo problema real ya parcheado en uvicorn), por lo que una conexión sin cerrar cuelga `async with servidor:` para siempre. Reproducido en real en GitHub Actions (rama temporal `diagnostico/python312-hang`); corregido cerrando el writer explícitamente en el handler. Mismo nodeid verificado PASS en 3.11.16, 3.12.14 y 3.13.15 tras el fix |
| 2026-09-06 | Bloque 7: reporte portable de una corrida ya persistida, JSON (versión 1) y CSV, vía `sibu-run-suite export-run CORRIDA_ID --format json|csv [--out ARCHIVO]`, en el servicio neutral nuevo `application/exportacion_corridas.py`, reutilizado por `cli.py` sin acoplar interfaces entre sí. Sin PDF/Excel/HTML. Auditado en paralelo (arquitectura, seguridad, CSV/JSON, CLI/Windows, persistencia, calidad de tests), sin hallazgos P0 |
| 2026-09-07 | Ciclo 6 de cierre: cuatro correcciones puntuales sobre Bloque 7 y su cobertura. (1) `export-run --format csv` a stdout imprimía una línea en blanco de más (doble salto de línea); corregido en `cli.py`. (2) La CLI mostraba el mensaje genérico de fallo técnico cuando `evaluacion_json` de una corrida persistida no era JSON válido; se agrega `MENSAJE_EVALUACION_CORRUPTA` para ese caso específico. (3) `tests/test_politica_campos.py::test_la_capa_estructural_gana_aunque_la_validacion_no_existiera` era tautológico -armaba el merge a mano en vez de invocar `armar_compra`-; reescrito para invocar `armar_compra` real, neutralizando `validar_campos_manuales` con `monkeypatch` para poder ejercer el camino que esa validación normalmente bloquea. (4) `export-run --out archivo` en Windows traducía cada `\n` a `\r\n` pese al `lineterminator="\n"` explícito de `reporte_a_csv` (`Path.write_text()` sin `newline=""`); corregido agregando `newline=""`. Suite completa: 897 pruebas (antes 895) |
| 2026-09-07 | Iteración posterior al cierre, cinco mejoras funcionales pedidas por el usuario: (1) `Ejecucion.motivo_detalle` persiste la causa concreta de un fallo (antes solo se mostraba en el resultado inmediato); (2) `FiltroHistorial` + `RepositorioEjecuciones.buscar` dan filtros y paginación a `/historial`; (3) el selector de conexión pasa a vivir dentro del `<form>` del constructor (conserva tarjeta/monto/campos/expectativas al cambiar de conexión) y `_formulario_suite` conserva la selección de escenarios tras un error de validación; (4) `GET /?ejecucion_id={id}` recupera la configuración de una ejecución pasada para "Editar y volver a ejecutar"/"Guardar como escenario" en `resultado.html`, sin tocar el PAN; (5) `/suites/corridas/{id}/exportar.json`/`.csv` descargan el reporte ya persistido, reutilizando `application/exportacion_corridas.py` sin re-ejecutar la suite. Verificado en navegador de punta a punta (host simulado + web en puertos y base aislados). Suite: 921 passed, 2 skipped (antes 897). Sin commit. Detalle completo en `BITACORA.md` |
| 2026-09-07 | Revisión crítica de las cinco mejoras: 3 defectos corregidos (reutilizar ejecución no explicaba tarjeta/conexión no disponible ni advertía sobre datos del formato heredado; `formnovalidate` verificado con clic real, no solo JS; faltaba prueba de migración de `motivo_detalle`) y 1 hallazgo documentado sin corregir todavía (datos del formulario viajando en la URL al cambiar de conexión). Suite: 937 passed, 2 skipped |
| 2026-09-07 | Cierre del hallazgo de la URL: "Cambiar conexión" pasa de GET a **POST** (`POST /`, `cambiar_conexion` en `web/app.py`) -sin sessionStorage ni borrador alguno-, así que monto/campos/nombre viajan en el cuerpo de la petición, nunca en la URL, el historial del navegador ni el log de acceso del servidor; verificado con clics reales y con el log de un servidor aislado. Se verificó además que las expectativas recuperadas de una ejecución nunca dependen del escenario que la originó, aunque éste se edite después (antes solo lo afirmaba el docstring, sin prueba). `motivo_detalle`: se confirmó que `CodecIso8583` sí incrustaba el texto libre de `pyiso8583` (`EncodeError`/`DecodeError`); corregido para usar solo `error.field` y redactar el mensaje enteramente con texto propio del proyecto. Suite: 941 passed, 2 skipped |

El detalle histórico y sus justificaciones pertenecen a `BITACORA.md` y a Git.

## Decisiones pendientes

Los ítems 2 y 4 quedan además congelados como trabajo futuro por la decisión del 2026-08-26
(ver «Fase», arriba): se listan aquí como decisiones de diseño abiertas para cuando se
retomen, no como trabajo en curso.

1. Formato concreto del framing para un switch QA real. El de demostración existe (prefijo de 2 bytes); el del ambiente real dependerá de su especificación.
2. Especificaciones reales de Visa y Mastercard, y si los obligatorios por MTI son propios de cada marca. **Ya no está bloqueado por falta de documentación**, que existe y se cita en `BITACORA.md`. Falta el análisis y la implementación: nada de su contenido se ha verificado todavía.
3. Compatibilidad con Python 3.11 y 3.12. `requires-python` sigue declarando `>=3.13` porque es la única versión comprobada. El CI ya prueba las tres versiones usando `pip install --ignore-requires-python`, que ejecuta el código sin alterar el metadata. **Ampliar el rango solo cuando el CI muestre las tres en verde.**
4. Si el motor de carga corre dentro del proceso web o aparte.
5. Si conviene añadir un trabajo de CI en Windows: hoy el workflow corre en Linux y todo lo verificado localmente fue en Windows.
6. Otros escenarios de falso positivo (`PROYECTO.md` §7.6). El primero ya está cubierto: una respuesta con código aprobado pero correlación incorrecta se registra `Invalida`. Faltan los demás casos.
7. Cifrado en reposo del catálogo de tarjetas de QA — fuera del alcance académico, necesario para una evolución comercial.

## Restricciones de alcance

Fuente autoritativa: `PROYECTO.md`. Recorrido único aprobado: compra `0100` → TCP → respuesta
`0110`. Fuera de alcance: retiros, consultas de saldo, reversos, OCT, AFT, refunds, anulaciones,
verificaciones de cuenta, catálogos de códigos por marca y paneles de métricas elaborados.

Las cuatro reglas cubiertas por pruebas automatizadas tratan sobre: aprobación según el catálogo
configurado (RN-1), timeout a los 10 s contado aparte del rechazo (RN-2), validez de la respuesta
más allá del código (RN-3) y bloqueo del envío si falta un campo obligatorio del MTI (RN-4).
**Enunciado autoritativo en `PROYECTO.md` §4.**

## Próximo paso

Las cinco mejoras funcionales pedidas el 2026-09-07 (ver «Estado actual» e «Historial de
avances») están implementadas y verificadas, pero **sin commit ni push todavía** -queda para
cuando el usuario lo pida-. Aparte de eso, el trabajo activo sigue siendo el cierre académico:
documentación final, documento de negocio, arquitectura, presentación y revisión contra la
consigna de `PROYECTO.md`. Ya resuelto dentro de ese cierre: reproducibilidad desde clon limpio
(`README.md`, `demo.cmd`) y el skill de Claude Code `levantar-demo`.

La Fase 1 (módulo de Configuración) quedó cerrada en el sub-bloque 6 (**derivación pura de
Track 1 y Track 2**) y congelada para esta entrega junto con el motor de carga (ver «Fase»,
arriba). No hay sub-bloques planificados hasta que se retome ese trabajo: quedan como trabajo
futuro sin fecha exponer los ocho campos de laboratorio en `ServicioTarjetas` y en la
interfaz, la integración posterior de Track1/Track2 en el mensaje ISO, la administración
visual de códigos de respuesta y de destinos, la integración con la compra (selector de
destino, filtro de tarjetas activas), el constructor avanzado y el modo avanzado ISO 8583,
y el isoscopio 2.0.

Pendiente aparte, sin relación con el congelamiento: ampliar `requires-python` a `>=3.11`,
para lo que el CI ya aportó evidencia.

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
| `src/sibutestlab8583/web/estatico/sibu.css` | Hoja de estilos única de la interfaz: tokens, componentes y cortes responsive |
| `src/sibutestlab8583/web/plantillas/_piezas.html` | Macros compartidas: señales SVG, pastilla de estado y métrica |
| `src/sibutestlab8583/application/serializacion.py` | Representación persistida de un mensaje ISO y su lectura tolerante |
| `src/sibutestlab8583/web/plantillas/detalle.html` | Detalle de una ejecución histórica: resumen, isoscopios y evidencia persistida |
| `.github/workflows/tests.yml` | CI: suite en Python 3.11/3.12/3.13 y verificación de clon limpio |
| `tests/` | Pruebas técnicas de la fundación |
| `README.md` | Procedimiento manual completo: clonar, instalar, inicializar, levantar y probar |
| `demo.cmd` | Camino rápido de arranque en Windows; reproduce los mismos pasos operativos que `README.md` |
| `.claude/skills/levantar-demo/SKILL.md` | Skill de Claude Code: ejecuta `demo.cmd` y verifica HTTP/TCP de forma independiente |
| `src/sibutestlab8583/cli.py` | CLI `sibu-run-suite`: `list-suites`/`run-suite`/`export-run`, texto/JSON/CSV, códigos de salida para CI |
| `src/sibutestlab8583/application/exportacion_corridas.py` | Bloque 7: reporte neutral (JSON/CSV) de una corrida ya persistida, reutilizable por CLI y web |
| `scripts/` | Utilidades de pipeline para Bloque 6 (no son parte del paquete instalado): siembra demo idempotente, espera TCP, guardia de seguridad del artefacto |
| `.github/workflows/ci-suite-demo.yml` | Bloque 6: workflow de referencia que ejecuta una suite demo end-to-end en GitHub Actions |
| `docs/ci/INTEGRACION_CI.md` | Contrato de integración CI genérico y su adaptación a otros proveedores |

Para levantar el proyecto desde cero: crear un entorno virtual, `pip install -e ".[dev]"`,
`sibu-init-db` y `pytest`. La demostración usa dos terminales: `sibu-host-demo` levanta el host
simulado y `uvicorn sibutestlab8583.web.app:app` la interfaz web. La web **no** levanta el host
simulado: la arquitectura lo mantiene como proceso aparte. En Windows, `demo.cmd` automatiza
esta misma secuencia y agrega su propia verificación de disponibilidad antes de abrir el
navegador.

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

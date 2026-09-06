# Arquitectura · SibuTestLab8583

Documento de arquitectura, con límite de dos páginas más los diagramas versionados (espíritu de
`PROYECTO.md` §7.2). El detalle histórico de cómo se llegó a cada decisión —sub-bloques,
correcciones de rumbo, retroalimentación— vive en `BITACORA.md`; aquí solo el diseño vigente.

Diagramas: [`componentes.mmd`](componentes.mmd) y [`flujo-compra.mmd`](flujo-compra.mmd).

## Estado actual

Implementado: web, composición, orquestador, consultas, perfiles, codec ISO 8583, validación,
framing, transporte TCP, persistencia SQLite, generador de STAN, host simulado, administración
web de tarjetas y de destinos (Conexiones), la derivación pura de Track 1/Track 2, escenarios
reutilizables con expected-vs-actual, suites de regresión con su corredor secuencial, una CLI
(`sibu-run-suite`) que ejecuta una suite sin navegador, apta para CI, y una integración CI
genérica de referencia (GitHub Actions) que la invoca automáticamente en cada push —ver
`docs/ci/INTEGRACION_CI.md`. **Sin implementar:** motor de carga, perfiles reales de Visa y
Mastercard, modo avanzado ISO 8583, isoscopio 2.0. La
arquitectura está cubierta por pruebas automatizadas y CI; el estado exacto de la suite se
mantiene en `CONTEXTO.md` y en el pipeline, no aquí.

## Alcance del diseño

Un único recorrido: **compra `0100` → TCP → respuesta `0110`**. No se diseñan componentes para
reversos, retiros, consultas de saldo, OCT, AFT, refunds ni anulaciones. Ningún módulo recibe
generalidad "por si acaso" para MTIs fuera de alcance.

## Desacoplamiento

Dirección de dependencia, en un solo sentido:

```
web  →  application service  →  dominio / puertos  →  adaptadores
```

El dominio define los puertos; los adaptadores los implementan. Ningún módulo del dominio
importa un adaptador. Tres límites que no se cruzan:

1. **La web no conoce infraestructura** — ni SQLite, ni sockets, ni la forma de los
   diccionarios de `pyiso8583`. Recibe y muestra objetos del dominio.
2. **El transporte no conoce ISO 8583** — recibe bytes opacos y delega el enmarcado y el
   desenmarcado a `FramingStrategy`. Ni la web ni el orquestador conocen el formato concreto.
3. **La validación es pura** — sin red, sin base de datos, sin estado global. Es lo que hace
   verificables las cuatro reglas de negocio con pruebas rápidas y deterministas.

## Módulos

| Módulo | Capa | Responsabilidad |
|---|---|---|
| **Web** | Interfaz | Nueva transacción, resultado, historial, detalle de una ejecución, no encontrado, Configuración (tarjetas, conexiones), Escenarios, Suites y Corridas de suite. Delgada: sin lógica de negocio, sin parsing, sin JavaScript |
| **Composición** | Raíz de composición | Único lugar donde se cablean perfil, catálogo, codec, framing, transporte y repositorios. La web depende de ella y no construye infraestructura en sus endpoints. El catálogo de respuestas se lee de SQLite en cada compra, sin caché |
| **Orquestador** (application service) | Aplicación | Secuencia el recorrido: armar → validar (RN-4) → codificar → enviar → interpretar → evaluar → persistir. Persiste todo intento, incluidos los que no llegan a la red |
| **Perfiles** | Dominio | `PerfilDeMarca` activo: formato y campos obligatorios por MTI |
| **Track 1 / Track 2** | Dominio | Derivación pura (`domain/tracks.py`), sin I/O, de la representación lógica de pista a partir de PAN, titular, expiración, service code y discretionary data. **No transmitida:** el perfil no declara DE35 ni DE45, y ningún otro módulo la invoca todavía |
| **Validación** | Dominio | Las cuatro reglas de negocio de `PROYECTO.md` §4. Funciones puras |
| **Codec ISO 8583** | Adaptador | Codifica y decodifica sobre `pyiso8583`. Recibe la especificación como parámetro; no conoce marcas |
| **Transporte TCP** | Adaptador | Abre conexión, envía, espera respuesta con tiempo límite. Asíncrono. Clasifica el desenlace por fase, para que no poder conectar no se confunda con no recibir respuesta |
| **Framing** | Puerto + adaptador | Delimita mensajes dentro del stream TCP. Único consumidor: el transporte |
| **Persistencia** | Puerto + adaptador | Repositorios de ejecuciones, tarjetas de prueba, catálogos y destinos. Puerto asíncrono; adaptador SQLite |
| **Host simulado** | Proceso aparte | Servidor TCP que recibe `0100` y responde `0110` según el catálogo configurado. Reutiliza codec y framing |
| **Escenarios** | Aplicación | `ServicioEscenarios`: casos reutilizables (guardar, editar, duplicar, activar/desactivar), con expectativas opcionales (expected-vs-actual) evaluadas por el propio `Orquestador` |
| **Suites y corredor** | Aplicación | `ServicioSuites` agrupa escenarios en un orden fijo; `CorredorDeSuites` los ejecuta secuencialmente reutilizando `EjecutorDeEscenarios` (la misma resolución que usa la reejecución individual), persiste cada `CorridaSuite`/`ItemCorridaSuite` y calcula el resultado global (PASS/FAIL/ERROR/INCOMPLETA/SIN_EXPECTATIVAS) |
| **CLI (`sibu-run-suite`)** | Interfaz | Ejecuta una suite sin navegador, apta para CI: mismo `CorredorDeSuites` que la web, códigos de salida por resultado, salida texto o JSON. No depende de `web/` |
| **Integración CI** | Scripts + adaptador | `scripts/sembrar_suite_demo.py` (siembra idempotente), `scripts/ci_esperar_host.py` (espera TCP), `scripts/verificar_artefacto_seguro.py` (guardia sobre el artefacto); todo reutilizable por cualquier proveedor. `.github/workflows/ci-suite-demo.yml` es la única pieza específica de GitHub. Detalle en `docs/ci/INTEGRACION_CI.md` |
| **Motor de carga** | *Fase posterior* | Repite el recorrido con múltiples tareas concurrentes y agrega métricas. **No implementado** |

## Contratos principales

Conceptuales, no firmas definitivas de implementación.

| Contrato | Operaciones | Notas |
|---|---|---|
| `Codec` | `codificar(mensaje, perfil) → bytes`<br>`decodificar(bytes, perfil) → MensajeInterpretado` | `MensajeInterpretado` conserva valor, bytes crudos y descripción por campo: alimenta el isoscopio |
| `Validacion` | `validar_envio(mensaje, perfil) → Resultado`<br>`evaluar_respuesta(envio, respuesta, catalogo, perfil) → Aprobada \| Rechazada \| Invalida` | Puras. RN-4 se aplica **antes** de codificar. RN-3 se evalúa **antes** que RN-1: una respuesta aprobada que no corresponde a la solicitud es `Invalida`, nunca `Aprobada` — es el mecanismo contra falsos positivos de `PROYECTO.md` §7.6 |
| `Transporte` | `enviar(bytes, destino, tiempo_limite) → bytes \| TiempoAgotado \| FalloDeConexion \| FalloDeTransmision` *(asíncrono)* | Ninguna excepción de `asyncio` ni `OSError` cruza este contrato; se clasifica por fase —conectar / enviar / esperar—, no por la excepción que la originó. Única excepción real: `ErrorDeFraming` desde `preparar()`, antes de conectar |
| `FramingStrategy` | `preparar(bytes) → bytes`<br>`leer_mensaje_completo(stream) → bytes` *(asíncrono)* | Lo invoca solo el transporte |
| `GeneradorStan` | `siguiente() → str` *(asíncrono)* | Campo 11. Puerto, no función suelta, porque la unicidad exige estado compartido y duradero |
| `RepositorioEjecuciones` | `guardar(ejecucion) → id`<br>`obtener(id)`<br>`listar(limite)` *(asíncronos)* | El dominio no conoce el motor de base de datos |
| `RepositorioTarjetas` | `obtener(card_id)`, `listar()`, `guardar(tarjeta)` *(asíncronos)* | Único lugar que devuelve el PAN completo. Las ejecuciones referencian `card_id`, nunca el PAN |
| `RepositorioCatalogos` | `catalogo_respuestas(nombre)` *(asíncrono)* | Leído en cada compra, sin caché: editar la tabla se refleja sin reiniciar |
| `RepositorioDestinos` | `obtener(destino_id)`, `listar()`, `guardar(destino)` *(asíncronos)* | `guardar` es upsert. Sin clave foránea desde `ejecuciones`: una ejecución guarda host/puerto como valores propios, para que editar o desactivar un destino no reescriba el historial |

El orquestador depende de estos contratos, no de sus implementaciones: permite probarlo con
dobles de prueba y es lo que hará posible que el motor de carga reutilice transporte,
validación y persistencia sin modificarlos.

## Flujo de una compra

`0100 → TCP → 0110`, detallado en [`flujo-compra.mmd`](flujo-compra.mmd). El transporte no
lanza excepciones por condiciones de red: devuelve un resultado que el orquestador convierte en
estado persistido, clasificado por **fase**, porque eso determina qué se puede demostrar:

| Fase | Falla | Resultado | Estado |
|---|---|---|---|
| Enmarcar | `preparar()` rechaza | `ErrorDeFraming` | `NO_ENVIADA` |
| Conectar | rechazo, ruta, DNS, tiempo | `FalloDeConexion` | `ERROR_CONEXION` |
| Enviar | `drain()` falla o se agota | `FalloDeTransmision` | `ERROR_TRANSMISION` |
| Esperar | se agota el tiempo | `TiempoAgotado` | `TIMEOUT` (RN-2) |
| Esperar | canal roto o desenmarcado incompleto | `FalloDeTransmision` | `ERROR_TRANSMISION` |

`ERROR_TRANSMISION` existe porque, tras `drain()`, no es demostrable cuánto recibió el destino:
llamarlo "no se envió" sería la afirmación más cara posible en un simulador de pagos. Los
estados con respuesta —`APROBADA`, `RECHAZADA`, `INVALIDA`— salen de `evaluar_respuesta` (ver
Contratos). Todo intento queda persistido, incluidos los que nunca tocan la red.

## Persistencia

Contrato de repositorio **asíncrono**; adaptador inicial SQLite mediante `aiosqlite`.
PostgreSQL queda como evolución futura, no implementada: se escribe un único adaptador, no un
segundo solo para probar el puerto. El puerto asíncrono evita bloquear el event loop y mantiene
el motor sustituible sin tocar el dominio.

Cada ejecución guarda su mensaje y el de respuesta en dos formas: un texto enmascarado de
siempre, y una estructura JSON (`version`, `mti`, `perfil`, `campos`) que declara su propia
fidelidad — nunca se afirma "fiel" sobre una fila leída del formato de texto anterior, porque
esa fidelidad no es demostrable. Migraciones aditivas e idempotentes (`ALTER TABLE ... ADD
COLUMN` solo para lo que falte); ninguna fila existente se pierde ni se reinterpreta.

## Framing y transporte

`pyiso8583` convierte entre bytes y diccionario, pero no delimita mensajes dentro de un stream
TCP. Esa responsabilidad se aísla en `FramingStrategy`, cuyo único consumidor es el transporte
— la web y el orquestador no conocen el formato concreto. El framing de demostración (prefijo
binario de 2 bytes, big-endian) no se atribuye a ninguna marca; el de un switch real dependerá
de su especificación.

## Perfiles y catálogo de respuestas

Dos ejes de configuración **independientes**: `PerfilDeMarca` (formato, codificación,
obligatorios por MTI) y `CatalogoDeRespuestas` (qué código del campo 39 cuenta como aprobado).
Acoplarlos sería un diseño confuso: el perfil alimenta RN-4, el catálogo alimenta RN-1. Hoy
existe un único perfil genérico; los perfiles reales de Visa y Mastercard son un punto de
extensión contemplado pero no implementado — no se inventan sus especificaciones. El catálogo
activo se lee de SQLite en cada compra (`Configuracion.catalogo_activo` / `SIBU_CATALOGO`), no
de una constante en memoria.

## Datos sensibles

El enmascaramiento del PAN es una restricción de diseño, no una limpieza posterior. El catálogo
de tarjetas de QA (`tarjetas_prueba`, no versionado) es el único lugar que puede contener el
PAN completo, porque sin él no hay transacción que construir; ejecuciones, historial y logs
nunca lo duplican, y lo referencian por `card_id`. Fuera de la pantalla de mantenimiento,
cualquier representación usa `************1234`. Política completa en `CLAUDE.md`.

## Componentes futuros, claramente separados

No implementados hoy, y no se diseñan generalidades anticipadas para ellos: **motor de carga**
(repetir el recorrido con concurrencia y métricas, reutilizando transporte, validación y
persistencia sin modificarlos), **perfiles reales de Visa y Mastercard** (documentación de
marca ya citada en `BITACORA.md`; análisis e implementación pendientes), **framing de un switch
real** (depende de su especificación), **modo avanzado ISO 8583** e **isoscopio 2.0** (comparar
solicitud contra respuesta y mostrar el bitmap).

## Decisiones abiertas

| Qué no se decidió | Cuándo se decide |
|---|---|
| Formato concreto del framing para un switch real | Depende de la especificación del ambiente |
| Si los obligatorios por MTI son propios de cada marca | Al analizar la documentación de Visa/Mastercard ya disponible |
| Si el motor de carga corre dentro del proceso web o aparte | Al construir el motor de carga |
| Cifrado en reposo del catálogo de tarjetas de QA | Fuera del alcance académico; necesario para una evolución comercial |

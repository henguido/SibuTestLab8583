# Arquitectura · SibuTestLab8583

Borrador inicial. Deliberadamente conciso: el entregable final tiene límite de dos páginas
aparte de los diagramas.

**Este documento se escribió antes del código**, para fijar la forma acordada según
`PROYECTO.md` §7.2. Desde entonces se implementó: hoy existen la web, la composición, el
orquestador, las consultas, los perfiles, el codec, la validación, el framing, el transporte TCP,
la persistencia, el generador de STAN y el host simulado. Sigue **sin implementar** el motor de
carga. El estado exacto lo dan `git log` y la suite de pruebas, no este documento.

Diagramas: [`componentes.mmd`](componentes.mmd) y [`flujo-compra.mmd`](flujo-compra.mmd).

## Alcance del diseño

Un único recorrido: **compra `0100` → TCP → respuesta `0110`**. No se diseñan componentes para
reversos, retiros, consultas de saldo, OCT, AFT, refunds ni anulaciones. Ningún módulo recibe
generalidad "por si acaso" para MTIs fuera de alcance.

## Dirección de dependencia

```
web  →  application service  →  dominio / puertos  →  adaptadores
```

Las flechas van en un solo sentido. El dominio define los puertos; los adaptadores los
implementan. Ningún módulo del dominio importa un adaptador.

Tres límites que no se cruzan:

1. **La web no conoce infraestructura.** No sabe de SQLite, ni de sockets, ni de la forma de los
   diccionarios de `pyiso8583`. Recibe y muestra objetos del dominio.
2. **El transporte no conoce ISO 8583.** Recibe bytes opacos y delega el enmarcado y el
   desenmarcado a `FramingStrategy`. Si el transporte tuviera que leer un campo ISO para
   funcionar, el diseño estaría mal. Ni la web ni el orquestador conocen el formato concreto de
   framing.
3. **La validación es pura.** Sin red, sin base de datos, sin estado global. Es la condición que
   hace verificables las cuatro reglas de negocio con pruebas rápidas y deterministas.

## Módulos

| Módulo | Capa | Responsabilidad |
|---|---|---|
| **Web** | Interfaz | Cinco pantallas: nueva transacción, resultado, historial, detalle de una ejecución (`/historial/{id}`) y no encontrado. Delgada: sin lógica de negocio, sin parsing y sin JavaScript. Se divide en rutas (`web/app.py`), presentación (`web/presentacion.py`), plantillas Jinja con macros compartidas en `_piezas.html`, y una hoja de estilos propia servida en `/estatico` |
| **Composición** | Raíz de composición | Único lugar donde se cablean perfil, catálogo, codec, framing, transporte y repositorios. La web depende de ella y no construye infraestructura en sus endpoints. `orquestador()` es asíncrono y lee el catálogo de respuestas de SQLite en cada llamada, sin cachearlo: editar `codigos_respuesta` se refleja sin reiniciar la aplicación |
| **Orquestador** (application service) | Aplicación | Secuencia el recorrido: armar → validar (RN-4) → codificar → enviar → interpretar → evaluar → persistir. Convierte los resultados del transporte en estados de ejecución: `TiempoAgotado` en `TIMEOUT` (RN-2), `FalloDeConexion` en `ERROR_CONEXION` y `FalloDeTransmision` en `ERROR_TRANSMISION`. **Persiste todo intento**, incluidos los que no llegan a la red. Única pieza que conoce a todas las demás |
| **Perfiles** | Dominio | Provee el `PerfilDeMarca` activo: especificación de formato y campos obligatorios por MTI |
| **Codec ISO 8583** | Adaptador | Codifica y decodifica mensajes sobre `pyiso8583`. Recibe la especificación como parámetro; no conoce marcas. Traduce los errores de la librería a errores del dominio |
| **Validación** | Dominio | Las cuatro reglas de negocio de `PROYECTO.md` §4. Funciones puras |
| **Transporte TCP** | Adaptador | Abre conexión, envía, espera respuesta con tiempo límite. Asíncrono (`asyncio`). No conoce ISO 8583: recibe bytes opacos y delega el enmarcado y el desenmarcado a `FramingStrategy`. Clasifica el desenlace por fase, para que no poder conectar no se confunda con no recibir respuesta |
| **Framing** | Puerto + adaptador | Delimita mensajes dentro del stream TCP. Contrato propio, cuyo único consumidor es el transporte |
| **Persistencia** | Puerto + adaptador | Repositorios de ejecuciones, tarjetas de prueba y catálogos. Puerto asíncrono; adaptador SQLite |
| **Host simulado** | Proceso aparte | Servidor TCP que recibe `0100` y responde `0110` según el catálogo configurado. Reutiliza codec y framing |
| **Motor de carga** | *Fase posterior* | Repite el recorrido con múltiples tareas concurrentes y agrega métricas. **No se implementa ahora** |

## Contratos

Contratos conceptuales entre módulos. No son firmas definitivas ni implementación.

| Contrato | Operaciones | Notas |
|---|---|---|
| `Codec` | `codificar(mensaje, perfil) → bytes`<br>`decodificar(bytes, perfil) → MensajeInterpretado` | `MensajeInterpretado` conserva, por campo, el valor decodificado, los bytes crudos y su descripción: es lo que alimenta el isoscopio |
| `Perfiles` | `perfil_activo() → PerfilDeMarca`<br>`PerfilDeMarca.obligatorios(mti) → conjunto de campos` | La especificación de formato se entrega al codec; los obligatorios alimentan RN-4 |
| `Validacion` | `validar_envio(mensaje, perfil) → Resultado`<br>`evaluar_respuesta(envio, respuesta, catalogo, perfil) → Aprobada \| Rechazada \| Invalida` | Puras. RN-4 en la primera, y se aplica **antes** de codificar. RN-1 y RN-3 en la segunda, **en ese orden inverso**: RN-3 primero, porque una respuesta aprobada que no corresponde a la solicitud es `Invalida`. `evaluar_respuesta` recibe también el perfil: qué campos deben correlacionar es una definición del perfil, no del catálogo. Un `Timeout` no es una respuesta recibida, así que no sale de aquí |
| `Transporte` | `enviar(bytes, destino, tiempo_limite) → bytes \| TiempoAgotado \| FalloDeConexion \| FalloDeTransmision` *(asíncrono)* | **Ninguna excepción de `asyncio` ni ningún `OSError` cruza este contrato.** Los cuatro resultados se distinguen por lo que cada uno permite *demostrar*: `FalloDeConexion` = no hubo sesión TCP, así que nada se transmitió; `FalloDeTransmision` = hubo sesión y el intercambio quedó **indeterminado**, no se puede afirmar cuánto recibió el destino; `TiempoAgotado` = se conectó, el drenaje terminó, se esperó y no llegó respuesta — esto y solo esto es RN-2. Única excepción que sí sale: `ErrorDeFraming` desde `preparar()`, que corre antes de conectar |
| `FramingStrategy` | `preparar(bytes) → bytes`<br>`leer_mensaje_completo(stream) → bytes` *(asíncrono)* | Lo invoca el transporte, nunca el orquestador ni la web. Ver más abajo |
| `GeneradorStan` | `siguiente() → str` *(asíncrono)* | Entrega el campo 11. Es un puerto y no una función porque la unicidad exige estado compartido y duradero: entre peticiones, entre peticiones concurrentes y entre reinicios |
| `RepositorioEjecuciones` | `guardar(ejecucion) → id`<br>`obtener(id) → Ejecucion \| None`<br>`listar(limite) → Ejecucion[]` *(asíncronos)* | El dominio no conoce el motor de base de datos. `guardar` devuelve el identificador asignado, que es lo que permitirá enlazar el detalle de una ejecución |
| `RepositorioCatalogos` | `catalogo_respuestas()`, `tarjetas_prueba()` *(asíncronos)* | Las tarjetas se referencian por identificador interno, nunca por PAN |
| `RepositorioDestinos` | `obtener(destino_id)`, `listar()`, `guardar(destino)` *(asíncronos)* | Catálogo de destinos administrados (`DestinoGuardado`). `guardar` es un upsert por `destino_id`. No hay clave foránea desde `ejecuciones`: una ejecución guarda `destino_host`/`destino_puerto` como valores propios, para que editar o desactivar un destino no reescriba el historial |

El orquestador depende de estos contratos, no de sus implementaciones. Esto permite probarlo con
dobles de prueba y es lo que hará posible que el motor de carga reutilice transporte, validación
y persistencia sin modificarlos.

## Decisión: los desenlaces de comunicación se clasifican por lo que se puede demostrar

El transporte no lanza excepciones por condiciones de red. Devuelve `bytes`,
`TiempoAgotado`, `FalloDeConexion` o `FalloDeTransmision`, y el orquestador los
convierte en estados persistidos.

**Fase → resultado.** La clasificación no depende de qué excepción se produjo, sino
de en qué fase, porque eso es lo que determina qué se puede afirmar:

| Fase | Falla | Resultado | Estado | ¿Se puede afirmar que nada se transmitió? |
|---|---|---|---|---|
| 0. Enmarcar | `preparar()` rechaza | lanza `ErrorDeFraming` | `NO_ENVIADA` | **Sí** — corre antes de conectar |
| 1. Conectar | rechazo, ruta, DNS, tiempo | `FalloDeConexion` | `ERROR_CONEXION` | **Sí** — no hubo canal |
| 2. Enviar | `drain()` falla o se agota | `FalloDeTransmision` | `ERROR_TRANSMISION` | **No** |
| 3. Esperar | se agota el tiempo | `TiempoAgotado` | `TIMEOUT` | *(es RN-2; tampoco se puede afirmar que el destino recibiera)* |
| 3. Esperar | canal roto o desenmarcado incompleto | `FalloDeTransmision` | `ERROR_TRANSMISION` | **No** |

**`NO_ENVIADA` significa «no se llegó a intentar transmisión por la red»**, no «no llegó al
transporte»: `preparar()` pertenece precisamente al transporte, así que ahí el mensaje sí llegó a
él. Lo que no ocurrió fue el intento de transmisión.

**Por qué la fase 2 no es un error de conexión.** Cuando `open_connection` retornó,
la sesión TCP existió. `write()` solo encola en el buffer local y `drain()` habla de
ese buffer, no de la aplicación remota: si falla, pudieron salir cero bytes, algunos
o todos, y TCP no se lo dice al programa. Llamarlo "error de conexión" afirmaría que
no hubo canal, lo cual es falso; llamarlo "no se envió" afirmaría algo indemostrable.
En pagos esa afirmación es la más cara posible: es exactamente el caso que obliga a
sospechar que la transacción pudo procesarse.

**Por qué RN-2 no incluye ninguno de los dos.** RN-2 exige cuatro premisas
observables **desde este cliente**: la conexión TCP se estableció, la escritura y el
drenaje locales terminaron sin error, se empezó a esperar, y no llegó respuesta
completa dentro del límite. Un fallo en las fases 1 o 2 rompe alguna de las tres
primeras.

**Lo que `TIMEOUT` tampoco afirma.** Que el drenaje local termine sin error no
demuestra que la aplicación remota recibiera ni procesara el mensaje: `drain()` habla
del buffer local, no del par. Por eso el estado se describe como «se esperó y no
llegó respuesta», nunca como «la solicitud fue transmitida» ni «el destino recibió».

**Framing antes y después de conectar.** `preparar()` corre en la fase 0 y su fallo
es `NO_ENVIADA`, porque nada tocó la red. `leer_mensaje_completo()` corre en la fase
3 y su fallo es `ERROR_TRANSMISION`: es el **mecanismo de transporte** el que no pudo
delimitar un mensaje. Distinto de una **respuesta ISO completa que llega y no se
puede decodificar**, que sigue siendo `INVALIDA` porque sí hubo respuesta que
evaluar. La frontera es si llegó un mensaje completo o no.

**`NO_ENVIADA` agrupa por consecuencia demostrable.** Cubre RN-4, el fallo del codec
y el rechazo del framing en la fase 0. Las tres comparten que nada salió, y en las
tres eso es verificable. La causa concreta viaja en los motivos.

## Decisión: los desenlaces de comunicación son resultados, no excepciones

El transporte no lanza excepciones por condiciones de red. Devuelve `bytes`,
`TiempoAgotado` o `FalloDeConexion`, y el orquestador los convierte en estados
persistidos.

**Por qué resultado y no excepción.** Para una herramienta de pruebas, que el
destino no esté disponible es una observación que hay que registrar, no una
anomalía que haya que propagar. Además, mezclar ambas formas —un desenlace como
resultado y otro como excepción— obligaba al orquestador a tener dos caminos para
la misma categoría de cosa, y era la razón por la que un fallo de conexión
desaparecía del historial.

**Por qué RN-2 no incluye el fallo de conexión.** RN-2 dice: se envió y no
respondieron dentro del límite. Un fallo al conectar no cumple la premisa: nunca
hubo una solicitud en vuelo. Contarlos juntos daría un diagnóstico equivocado,
porque «el switch no contesta» y «no llegó a haber conversación» se investigan de
forma distinta. El transporte distingue por **fase**: conectar, enviar, esperar.
Solo un tiempo agotado en la tercera fase es RN-2.

**`NO_ENVIADA` agrupa por consecuencia, no por causa.** Cubre que falte un campo
obligatorio (RN-4), que el codec no pueda codificar y que el framing rechace el
payload. Las tres comparten lo único que importa operativamente: nada salió de la
máquina. La causa concreta viaja en los motivos de la ejecución, así que partirla
en un estado por causa multiplicaría estados sin darle a QA una distinción útil.

## Decisión: persistencia asíncrona

Adoptar transporte asíncrono trasladó el problema de bloqueo al driver de base de datos, que en
SQLite es síncrono: una escritura bloqueante dentro del event loop congelaría el servidor.

- El **contrato del repositorio es asíncrono**.
- El **adaptador inicial es SQLite**, mediante **`aiosqlite`** para el MVP.
- **PostgreSQL queda como evolución futura y no se implementa ahora.** Se escribe un único
  adaptador; no se construye un segundo para demostrar que el puerto funciona.

El puerto asíncrono es lo que mantiene sustituible el motor sin tocar el dominio, y evita
bloquear el event loop tanto en el recorrido puntual como, más adelante, bajo carga.

## Decisión: framing como contrato independiente

`pyiso8583` convierte entre bytes y diccionario, pero no delimita mensajes dentro de un stream
TCP. Esa responsabilidad es propia y se aísla en un contrato:

`FramingStrategy` — preparar un payload para transmisión, y determinar y leer un mensaje
completo desde un stream.

**El transporte es su único consumidor:** recibe bytes opacos del orquestador y delega en
`FramingStrategy` el enmarcado al enviar y el desenmarcado al recibir. La web y el orquestador
no conocen el formato concreto.

Se separa del transporte porque el formato de delimitación depende del ambiente receptor,
mientras que abrir una conexión y esperar bytes no. Y se separa del codec porque el framing no
interpreta contenido ISO: solo sabe dónde termina un mensaje.

**No se atribuye todavía ningún framing concreto a Visa ni a Mastercard.** Para el host simulado
podrá seleccionarse después un framing de demostración; el framing del switch real dependerá de
la especificación del ambiente.

## Perfiles y catálogo

Dos ejes de configuración **independientes**, inyectados por separado:

- **`PerfilDeMarca`** — formato, codificación, campos y obligatorios por MTI. Es lo que el codec
  entrega a `pyiso8583` y lo que alimenta RN-4.
- **`CatalogoDeRespuestas`** — qué código del campo 39 cuenta como aprobado. Alimenta RN-1. Para
  la demostración académica: `00`, `05`, `14`, `51`, `54`, `94`.

**El catálogo activo se lee de SQLite, no de una constante.** `RepositorioCatalogosSQLite` existía
desde antes, pero hasta el sub-bloque D-1 (Fase 1 de Configuración) ningún punto de producción lo
consumía: `Composicion` fijaba `CATALOGO_GENERICO` una sola vez en `__init__`, así que la tabla
`codigos_respuesta` estaba desconectada del comportamiento real de RN-1. Ahora `Composicion`
instancia el repositorio y `orquestador()` (asíncrono) consulta `catalogo_respuestas(nombre)` en
cada construcción — sin caché, para que un cambio en la base no exija reiniciar el proceso. El
nombre del catálogo activo es `Configuracion.catalogo_activo` (variable `SIBU_CATALOGO`, por
defecto el genérico). `CATALOGO_GENERICO` **queda como semilla** de `inicializar()`
(`adapters/persistence/esquema.py`), no como fuente activa. RN-3 sigue evaluándose antes que RN-1
dentro de `Orquestador.ejecutar_compra`: ese orden no formaba parte de esta deuda y no se tocó.
Sin cambios de esquema —`codigos_respuesta` ya tenía la forma multi-catálogo— ni de interfaz.

La arquitectura contempla perfiles de Visa y de Mastercard como punto de extensión. **No se
crean ni se inventan especificaciones de ninguna marca**: los perfiles reales solo se implementan
a partir de documentación de marca disponible y aprobada como fuente. Esa documentación **ya
existe** —se registra en `BITACORA.md`—, no se versiona en este repositorio y no se copia su
contenido aquí. **Los perfiles siguen sin implementarse:** falta analizar cada documento y
derivar de él la especificación, y nada de eso se ha hecho todavía. Mientras tanto se trabaja con
un único perfil genérico.

## Persistencia base para tarjetas y destinos (Fase 1, sub-bloque 2)

Segundo sub-bloque del módulo de Configuración. Solo esquema, dominio, puerto y adaptador — **sin
interfaz todavía**: no existe `/configuracion` ni ninguna pantalla de administración.

- **`tarjetas_prueba.activa`.** Columna nueva, `INTEGER NOT NULL DEFAULT 1`. A diferencia de un
  esquema propuesto sin consumidor, se conecta de inmediato: `TarjetaPrueba` gana el campo
  `activa: bool = True`, y `RepositorioTarjetasSQLite` la lee en `obtener()`/`listar()` y la
  escribe en `guardar()`, cuyo `ON CONFLICT ... DO UPDATE` también la actualiza. Ningún flujo
  filtra todavía tarjetas inactivas: eso pertenece a la integración con la compra, en un
  sub-bloque posterior.
- **Tabla `destinos` y `DestinoGuardado`.** `DestinoGuardado` es la entidad administrada
  (identificador, nombre, host, puerto, estado activo/inactivo) con un método `a_destino_tcp()`
  que la proyecta al valor mínimo que el transporte necesita. **`DestinoTcp` no cambió**: sigue
  siendo exactamente el mismo valor que ya viajaba al transporte. `RepositorioDestinos` (puerto) y
  `RepositorioDestinosSQLite` (adaptador) siguen el mismo patrón de `guardar` como upsert que ya
  tenían las tarjetas. Se siembra un único destino, `LOCAL-DEMO` (`127.0.0.1:8583`).
- **Sin clave foránea de `ejecuciones` a `destinos`.** `Ejecucion.destino_host` y `destino_puerto`
  ya eran valores propios de la fila, no una referencia — la misma decisión que ya regía para
  tarjetas y ejecuciones (`destino_host`/`destino_puerto` como valores, §«No borrar históricos» de
  `BITACORA.md`). Se mantiene a propósito al crear `destinos`: editar o desactivar un destino no
  debe alterar el historial ya registrado.
- **Migración generalizada.** `_migrar_ejecuciones(conexion)` se generalizó en
  `_migrar(conexion, tabla, columnas)`, capaz de agregar columnas a cualquier tabla; se conservó
  como envoltorio de compatibilidad porque una prueba existente la invoca por nombre. Sigue siendo
  aditiva e idempotente: ninguna fila existente se modifica, y correr `inicializar()` dos veces no
  duplica nada.
- **Compatibilidad, comprobada contra una base anterior real y completa.** Una prueba reconstruye
  una base con tarjeta, ejecución, secuencia STAN y el esquema previo de `ejecuciones` —todo a la
  vez, sin `activa` ni `destinos`— y comprueba, tras `inicializar()` y otra vez tras una segunda
  llamada, que la tarjeta, la ejecución (comparada campo por campo) y la secuencia STAN no
  cambian, y que `LOCAL-DEMO` no se duplica.

**319 pruebas en verde** (302 + 17).

Contemplar perfiles de *formato* por marca no contradice la exclusión de alcance de
`FICHA-APROBACION.md`, porque lo excluido son los catálogos de *códigos de respuesta* por marca.
Son conceptos distintos.

## Configuración y administración de tarjetas (Fase 1, sub-bloque 3/4)

Tercer y cuarto sub-bloque de la Fase 1, combinados en una sola iteración visual: la portada del
módulo (`GET /configuracion`) y la administración web completa de tarjetas, sobre la persistencia
del sub-bloque 2.

- **`Configuración` es la tercera entrada de `presentacion.SECCIONES`**, la misma fuente única que
  ya recorre `base.html`. `GET /configuracion` muestra tres bloques —Tarjetas de prueba, Códigos
  de respuesta, Destinos—; solo el primero enlaza a una ruta real. Códigos y Destinos siguen
  marcados «Próximamente»: **no se enlaza a una ruta que no existe**, la misma regla que ya
  aplicaba `SECCIONES`.
- **`ServicioTarjetas`** (`application/tarjetas.py`) es el servicio de aplicación: listar, obtener,
  crear, actualizar, cambiar estado. Se construye solo con el puerto `RepositorioTarjetas`, que
  **no ganó ningún método nuevo**: `guardar()`, ya un upsert desde el sub-bloque 2, alcanza para
  todo el CRUD. La web valida la forma del formulario; el servicio valida el negocio (PAN, Luhn,
  vencimiento, unicidad de `card_id`) y persiste. `TarjetaAdministrada` —lo único que la web puede
  ver— no tiene ningún campo para el PAN completo, igual que `TarjetaListada` en `consultas.py`.
- **`card_id` es requerido e inmutable tras crear.** Su familia de caracteres (`[A-Za-z0-9_-]`)
  reutiliza la que ya seguían los identificadores existentes del proyecto; no se le impone un
  largo máximo, porque ningún campo ISO lleva el `card_id`, la columna SQLite es `TEXT` sin
  límite, y el proyecto no define ninguna cota de longitud para identificadores en ningún otro
  lugar — un número inventado habría sido una regla de negocio sin respaldo.
- **Política de PAN en esta pantalla, y solo en esta pantalla.** El PAN completo se recibe por
  `POST`, nunca en la URL. Un error de validación no repuebla el campo del PAN, ni el que ya
  existía. Falla Luhn → `sintetica=True` sin fricción; pasa Luhn → exige la casilla de
  confirmación QA, y sin marcarla se rechaza sin repetir el número. En edición, «Nuevo PAN» vacío
  conserva el PAN y el tipo actuales. El pie de página global dejó de afirmar que la interfaz
  «nunca» recibe el número completo, porque con esta pantalla eso deja de ser cierto; ahora dice
  la excepción exacta que `CLAUDE.md` ya definía.
- **Activar/desactivar reutiliza `TarjetaPrueba.activa`** (sub-bloque 2): no borra la fila, no
  toca el PAN, no modifica ninguna ejecución que referencie la tarjeta. `POST
  .../{card_id}/estado` valida estrictamente su entrada —solo `"0"` o `"1"`— y rechaza cualquier
  otro valor con un error HTML propio, en vez de convertirlo silenciosamente en `False`. Esta
  iteración no filtra tarjetas inactivas en la pantalla de compra: es un sub-bloque posterior.
- **Mutaciones y errores.** Crear, editar y cambiar estado, si tienen éxito, responden con un
  `redirect` HTTP 303 a `/configuracion/tarjetas` —la única pantalla del proyecto que redirige en
  vez de renderizar el resultado directamente, decisión explícita para evitar reenvíos duplicados
  de un formulario administrativo—. Todo error de validación re-renderiza el formulario o el
  listado con el mismo patrón de banner que ya usa `compra.html`; una tarjeta inexistente responde
  404 con `no_encontrado.html`, la misma plantilla que ya usaba `/historial/{id}`.

**380 pruebas en verde** (319 + 27 de `test_tarjetas_administracion.py` + 22 de
`test_web_configuracion.py` + 6 de crecimiento en `SECCIONES`/`PANTALLAS` + 6 de una prueba
paramétrica de valores manipulados en `/estado`).

## Decisión: la presentación es una capa, no una decoración de la plantilla

Cómo se rotula un desenlace es una decisión, y las decisiones no viven repartidas en el HTML.
`web/presentacion.py` concentra dos tablas y las plantillas no duplican ninguna:

- `AVISOS` asocia cada `EstadoEjecucion` con **cuatro** pistas: `senal` (dibujo), `etiqueta`
  (rótulo corto para tablas), `titulo` y `detalle`. El color es una quinta pista, definida en el
  CSS a partir de `tono`. Una prueba comprueba que no falte ningún estado y que ninguna de las
  tres primeras se repita entre estados.
- `SECCIONES` define la navegación. La plantilla base la recorre; añadir una sección es una línea
  en un solo lugar. **Solo se declaran secciones cuya ruta existe:** una prueba recorre
  `SECCIONES` y comprueba que cada ruta responda `200`.

Por qué `senal` no se deriva de `tono`: no son biyectivos. El tono `error` lo comparten
`ERROR_CONEXION` y los errores técnicos de `aviso_de_error`, y cada caso merece su propio dibujo.

### Por qué el color nunca va solo

Un fallo de infraestructura y un rechazo del autorizador se investigan de forma distinta, y quien
no distingue rojos no debe quedarse sin saber cuál de los dos ocurrió. Cada desenlace se
reconoce por señal, rótulo y texto antes de llegar al color. Contraste medido sobre los tokens:
el peor de los siete estados es 5.89:1 y el peor par de texto 5.42:1, ambos sobre el mínimo AA
de 4.5:1.

### Por qué la hoja de estilos es un archivo y no un bloque en la plantilla

Creció lo suficiente para merecer su propio archivo: el navegador la cachea, se edita como CSS y
las plantillas quedan solo con estructura. Es la única pieza estática que se monta. Todo color,
espacio, radio, sombra y tamaño sale de un token declarado en `:root`; ningún bloque posterior
escribe un literal de color. No hay framework, ni JavaScript, ni paso de compilación.

## Decisión: la representación persistida es estructurada, no un texto delimitado

Una ejecución guarda el mensaje que se armó y el que llegó. La primera implementación usaba un
solo formato de texto, `MTI=0100 | 2=**** | 3=000000`, unido por `` | `` y **sin escape**. Se lee
deduciendo dónde termina cada valor a partir de la forma del texto, y por eso es frágil: se
comprobó que un valor que contenga el separador queda partido y el lector **inventa un campo que
nunca existió**. Para una herramienta de pruebas de pagos, un registro que muestra un campo
inexistente es peor que no tener registro.

La corrección **no fue escapar el separador** sino añadir una representación donde la frontera de
cada valor la declara el formato:

| Columna | Para qué |
|---|---|
| `solicitud_enmascarada`, `respuesta_enmascarada` | Texto de siempre. Se conservan por compatibilidad con lo ya escrito y porque son legibles de un vistazo |
| `solicitud_json`, `respuesta_json` | Representación fiel. Es la que se lee cuando existe |

```json
{"version": 1, "mti": "0100", "perfil": "generico",
 "campos": {"2": {"valor": "************6666"}, "3": {"valor": "000000"}}}
```

`version` describe la **estructura del JSON**, no el mensaje ISO: permite que un lector futuro
distinga formatos leyendo una declaración en vez de deducirlos por su forma, que es exactamente el
defecto que se está corrigiendo. `perfil` es otro eje: dice con qué especificación se armó el
mensaje. La descripción de cada campo **no** se persiste: se re-deriva del perfil al leer.

### Dónde vive, y por qué ahí

`application/serializacion.py`, con funciones puras. En `adapters` obligaría a la capa de lectura
a depender de un adaptador; en `domain` obligaría al dominio a conocer un formato de
almacenamiento. Lo necesitan dos piezas de aplicación: el orquestador al escribir y las consultas
al leer.

### Lectura tolerante, y qué significa «fiel»

`interpretar()` prioriza el JSON; si no hay o no se pudo leer, cae al texto anterior; si tampoco,
devuelve un resultado indisponible. **Nunca lanza**: una fila antigua o corrupta no debe producir
un error del servidor.

El resultado trae una bandera `fiel` que distingue dos cosas que no deben confundirse:

- **`True`** solo cuando se leyó un JSON de una versión conocida.
- **`False`** siempre que provenga del texto anterior, *incluso si parece haberse leído bien*. La
  razón es demostrativa: `41=A` es indistinguible de un `41=A | B` truncado. No se puede
  **demostrar** fidelidad, y este proyecto no afirma lo que no puede demostrar.

Un JSON que declare una versión desconocida **no se interpreta**: leer una estructura que el
programa no conoce sería inventar significado. Se declara y se deja indisponible.

### Migración sin recrear la base

El proyecto no usa Alembic. `CREATE TABLE IF NOT EXISTS` no altera una tabla existente, así que
`inicializar()` comprueba `PRAGMA table_info` y ejecuta `ALTER TABLE ... ADD COLUMN` solo para lo
que falte. Es idempotente y **no modifica ninguna fila**. Las filas anteriores conservan `NULL`
en las columnas nuevas: no se reconstruye su JSON, porque reconstruirlo sería inventarlo.

### Límite conocido: no hay `crudo` de la solicitud

El JSON de la **respuesta** lleva `crudo` por campo, porque `MensajeInterpretado` lo trae del
codec y `enmascarado()` también lo enmascara. El de la **solicitud** no: `Codec.codificar`
devuelve bytes y descarta el documento codificado de `pyiso8583`, así que ese dato **no existe** en
el flujo actual y no se inventa. Recuperarlo exige cambiar el contrato del codec y pertenece al
isoscopio 2.0.

**Nunca se persisten los bytes crudos completos de un `0100`**, ni en hexadecimal: contienen el
PAN completo, y eso pondría una segunda copia del número fuera de `tarjetas_prueba`.

## Decisión: el detalle histórico lee, no reinterpreta

`GET /historial/{id}` muestra una ejecución ya registrada. Todo lo que necesita existe: el puerto
`RepositorioEjecuciones` ya declaraba `obtener(id)` y la representación estructurada ya estaba
persistida. Lo que se añadió es una proyección de lectura, no una capa nueva.

```
web/app.py  →  ServicioConsultas.detalle_ejecucion(id)  →  RepositorioEjecuciones.obtener(id)
                                                        →  serializacion.interpretar(json, texto)
```

**La web no interpreta y la plantilla tampoco.** Decidir entre la representación estructurada y
la de texto anterior es una regla de lectura de datos persistidos, así que vive en la capa de
aplicación; la presentación solo convierte el resultado en filas y el nombre de cada campo se
re-deriva del perfil activo. Un número que el perfil no conozca sale como `Campo 63`.

**El identificador se recibe como cadena, no como entero.** Declarado `int`, FastAPI respondería
su propio 422 en JSON ante `/historial/abc`, y el usuario vería un error crudo en vez de una
página del producto. Convirtiéndolo en la ruta, tanto un identificador no numérico como uno
inexistente terminan en la misma respuesta 404 con HTML propio.

### Lo que la pantalla afirma, y lo que no

- Cuando una ejecución proviene del formato de texto anterior, **se declara una sola vez, antes
  de las tablas**, que los campos se recuperaron de esa representación y que no puede
  garantizarse una reconstrucción exacta. No se afirma que haya habido corrupción: eso no se
  sabe. Solo que la fidelidad no es demostrable.
- Cuando no hubo respuesta —`NO_ENVIADA`, `ERROR_CONEXION`, `ERROR_TRANSMISION`, `TIMEOUT`— no se
  muestra una tabla vacía que parezca una `0110` que no existió, sino la explicación del estado
  tomada de `AVISOS`, más la advertencia de que **el motivo concreto no se conserva**.
- La columna con la representación transmitida aparece solo cuando el dato existe de verdad: la
  hay en la respuesta leída del JSON, y no la hay ni en la solicitud —el codec no la entrega— ni
  en una fila leída del texto anterior.

### Componentes compartidos

El isoscopio vivía dentro de `resultado.html`; al aparecer el segundo consumidor se movió a
`plantillas/_piezas.html` junto con el banner de estado y el resumen de métricas. La regla que se
aplicó es que **se extrae solo lo que ya tiene dos consumidores reales**, no lo que podría
tenerlos: la cabecera de panel es una línea y envolverla habría convertido la plantilla en un
framework de componentes.

## Datos sensibles en el diseño

El enmascaramiento del PAN es una restricción de diseño, no una limpieza posterior: el logging y
el esquema de persistencia se construyen enmascarando desde el borde, y el isoscopio enmascara
los campos que transportan datos de tarjeta. Política completa en `CLAUDE.md`.

Esto obliga a distinguir dos lugares distintos dentro de la misma base de datos:

- **Catálogo de tarjetas de QA.** Puede necesitar contener el **PAN completo**, porque sin él no
  se puede construir una transacción real contra el switch. Es el único lugar donde el PAN
  completo vive.
- **El archivo SQLite que lo contenga nunca se versiona.** Está excluido en `.gitignore`.
- **Ejecuciones, historial y logs no duplican el PAN completo.** Ninguna de esas tres cosas
  vuelve a almacenar el número.
- **Las ejecuciones referencian `card_id`**, el identificador interno de la tarjeta. Cualquier
  representación visible fuera de la pantalla de mantenimiento usa el PAN enmascarado
  (`************1234`).

**DE 14, fecha de vencimiento: decidido.** Permanece visible y se persiste **sin enmascarar** en
esta etapa, asociada a la tarjeta de prueba. Es dato de tarjeta pero no es el PAN, y el enmascarado
que exige la política se define sobre `CAMPOS_SENSIBLES = {"2", "35"}`. Que el 14 no esté ahí es
**deliberado**, no un olvido: no se le añade. Si una evolución comercial exigiera tratarlo como
dato sensible, sería una decisión nueva y explícita.

**No se decide todavía el cifrado en reposo.** Queda como decisión abierta: para el alcance
académico basta con no versionar el archivo, pero una evolución comercial tendría que resolverlo.

## Decisiones abiertas

| Qué no se decidió | Cuándo se decide |
|---|---|
| Formato concreto del framing para un switch real | Depende de la especificación del ambiente. El de demostración ya existe |
| Especificaciones de Visa y Mastercard, y si los obligatorios por MTI son propios de cada marca | Ya hay documentación de marca disponible como fuente; falta el análisis y la implementación |
| Si el motor de carga corre dentro del proceso web o aparte | Al construir el motor de carga |
| Estrategia de datos de demostración reproducibles para un clon limpio | Antes de la entrega |
| Cifrado en reposo del catálogo de tarjetas de QA | Fuera del alcance académico; necesario para una evolución comercial |

**Ya decididas, antes abiertas.** El esquema y las columnas de la base se fijaron al construir el
recorrido de extremo a extremo y se documentan más abajo. La integración continua se resolvió en
la Sesión 6 con GitHub Actions y matriz 3.11/3.12/3.13. **El campo 14 ya está decidido** y se
describe en «Datos sensibles en el diseño».

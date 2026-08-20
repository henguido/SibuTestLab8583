# Arquitectura · SibuTestLab8583

Borrador inicial. Deliberadamente conciso: el entregable final tiene límite de dos páginas
aparte de los diagramas.

**Nada de lo aquí descrito está implementado.** Este documento fija la forma acordada antes de
escribir código, según `PROYECTO.md` §7.2.

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
| **Web** | Interfaz | Formulario de compra, isoscopio (campos ISO interpretados) e historial de ejecuciones. Delgada: sin lógica de negocio |
| **Composición** | Raíz de composición | Único lugar donde se cablean perfil, catálogo, codec, framing, transporte y repositorios. La web depende de ella y no construye infraestructura en sus endpoints |
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
| `RepositorioEjecuciones` | `guardar(ejecucion)` *(asíncrono)* | El dominio no conoce el motor de base de datos |
| `RepositorioCatalogos` | `catalogo_respuestas()`, `tarjetas_prueba()` *(asíncronos)* | Las tarjetas se referencian por identificador interno, nunca por PAN |

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

La arquitectura contempla perfiles de Visa y de Mastercard como punto de extensión. **No se
crean ni se inventan especificaciones de ninguna marca**: los perfiles reales solo se
implementan cuando existan en el proyecto los documentos autorizados que definan esos formatos.
Mientras tanto se trabaja con un único perfil genérico.

Contemplar perfiles de *formato* por marca no contradice la exclusión de alcance de
`FICHA-APROBACION.md`, porque lo excluido son los catálogos de *códigos de respuesta* por marca.
Son conceptos distintos.

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

**No se decide todavía el cifrado en reposo.** Queda como decisión abierta: para el alcance
académico basta con no versionar el archivo, pero una evolución comercial tendría que resolverlo.

## Decisiones abiertas

| Qué no se decidió | Cuándo se decide |
|---|---|
| Formato concreto del framing | Al construir el host simulado; el del switch real depende del ambiente |
| Especificaciones de Visa y Mastercard, y si los obligatorios por MTI son propios de cada marca | Bloqueado: requiere documentos autorizados dentro del proyecto |
| Esquema y columnas de la base de datos | Al construir el recorrido de extremo a extremo |
| Si el motor de carga corre dentro del proceso web o aparte | Al construir el motor de carga |
| Estrategia de datos de demostración reproducibles para un clon limpio | Antes de la entrega |
| Cifrado en reposo del catálogo de tarjetas de QA | Fuera del alcance académico; necesario para una evolución comercial |
| Herramienta y configuración de integración continua | Sesión 6 |

# Bitácora de desarrollo · SibuTestLab8583

Evidencia académica del proceso: decisiones y sus razones, correcciones de rumbo,
retroalimentación y gobernanza. Solo se registran hechos ya ocurridos.

`CONTEXTO.md` cumple una función distinta: es la memoria operativa del estado presente. Esta
bitácora es acumulativa y no se reescribe.

---

## 2026-08-04 · Aprobación del caso

Se redactan `PROYECTO.md` (enunciado completo) y `FICHA-APROBACION.md` (resumen de una página).
La ficha queda aprobada sin observaciones: la sección "Preguntas para el docente" registra
"Ninguna" y "Excepciones abiertas" registra "Ninguna".

Queda fijado el alcance —compra `0100`/`0110`—, las cuatro reglas de negocio, el catálogo
genérico de seis códigos para la demostración y el calendario de cinco semanas. `PROYECTO.md`
§11 deja deliberadamente sin decidir la arquitectura, el modelo de datos y el stack, porque el
criterio 2 de la rúbrica evalúa precisamente esas decisiones y tomarlas sin fundamento no
adelanta nada.

## 2026-08-12 · Punto de partida verificado y primera propuesta técnica

Se inspecciona la carpeta del proyecto: contenía únicamente los dos documentos aprobados y
**no era un repositorio Git**. No había código, configuración ni historial previo.

Primera propuesta: Python, SQLite y una interfaz de línea de comandos. **Por qué Python:**
maneja bytes y sockets con biblioteca estándar, es legible para defender arquitectura y reglas
de negocio, y `pytest` cubre bien el requisito de pruebas automatizadas.

## 2026-08-12 · Cambio de CLI a aplicación web · corrección de rumbo

**Qué se decidió:** descartar la CLI y adoptar una aplicación web con FastAPI, vistas HTML
renderizadas en el servidor y JavaScript mínimo. Sin React, sin Next.js, sin frontend
independiente.

**Por qué:** el prototipo debe poder evolucionar hacia un producto utilizable por equipos de QA
e ingeniería y eventualmente por usuarios menos especializados; una CLI no sirve para eso.
FastAPI además expone OpenAPI, de modo que un frontend futuro puede consumir la misma API sin
reescribir el backend. La interfaz web es también donde vivirá el "isoscopio" de
`PROYECTO.md` §3.

**Costo asumido:** una interfaz web cuesta más esfuerzo que una CLI, contra un presupuesto de
cuatro horas semanales.

## 2026-08-12 · `pyiso8583` como motor de codificación

**Qué se decidió:** usar `pyiso8583` para serializar y deserializar mensajes, manteniendo las
especificaciones fuera del motor de negocio.

**Por qué:** se verificó contra su documentación que su API es `encode(doc, spec)` y
`decode(s, spec)`, recibiendo la especificación como diccionario en cada llamada. Esa firma
*es* el punto de inyección de perfiles que el diseño necesitaba, así que se adopta en lugar de
construir uno propio. Se confirmó también que no cubre el framing TCP ni la obligatoriedad de
campos por MTI: ambas cosas quedan como responsabilidad propia, lo que conviene porque mantiene
las reglas de negocio en código propio y probado.

## 2026-08-12 · SQLite detrás de un puerto de repositorio

**Qué se decidió:** SQLite como persistencia inicial, detrás de una interfaz de repositorio, con
PostgreSQL como evolución futura no implementada.

**Por qué:** es una base de datos real y transaccional que no exige instalar ni levantar un
servidor, lo que sostiene el requisito de que el profesor pueda clonar y ejecutar desde cero.
El puerto mantiene el motor sustituible sin tocar la lógica del dominio.

## 2026-08-12 · Separación `PerfilDeMarca` / `CatalogoDeRespuestas`

**Qué se decidió:** tratar como conceptos independientes el perfil de formato de cada marca y el
catálogo de interpretación del campo 39.

**Por qué:** la especificación que consume `pyiso8583` describe formato y codificación, pero no
dice qué campos son obligatorios para un `0100` ni qué código significa aprobado. Son tres cosas
distintas y mezclarlas produciría un diseño confuso. El perfil alimenta la regla RN-4; el
catálogo alimenta la regla RN-1.

**Riesgo identificado y su tratamiento:** `FICHA-APROBACION.md`, ya aprobada, excluye del
alcance los catálogos de códigos por marca. Contemplar perfiles de *formato* de Visa y
Mastercard no contradice esa exclusión, porque lo excluido son los catálogos de *respuesta*.
La distinción se documenta explícitamente para que no se lea como expansión del alcance.

## 2026-08-12 · Transporte asíncrono · corrección de rumbo

**Qué se decidió:** transporte TCP asíncrono desde el inicio, con `asyncio.open_connection()`,
descartando la propuesta previa de sockets bloqueantes ejecutados en el threadpool de FastAPI.

**Por qué:** el mismo contrato de transporte debe servir después al motor de pruebas de carga
—múltiples tareas concurrentes sobre el mismo transporte— sin tener que reescribirlo. La
propuesta original resolvía el problema inmediato del event loop pero habría obligado a
rehacer el conector en la Sesión 7.

**Consecuencia detectada en el momento:** ir asíncrono traslada el problema de bloqueo al driver
de SQLite, que es síncrono. Se registró como decisión pendiente en lugar de dejarla implícita.

## 2026-08-12 · Política de gobernanza del PAN

**Qué se decidió:** nunca registrar el PAN completo en logs, en la bitácora ni en Git;
referenciar las tarjetas por identificador interno; mostrar solo `************1234` fuera de la
pantalla de mantenimiento; no versionar el archivo SQLite que contenga tarjetas reales de QA.

**Por qué:** aunque las tarjetas provienen de un ambiente de pruebas y no de producción, siguen
siendo PAN reales de una institución financiera. `PROYECTO.md` §7.6 convierte esta vigilancia en
entregable evaluado. La política se fija antes de escribir la primera línea de código, porque el
enmascaramiento debe estar en el diseño del logging y del esquema, no añadirse después.

## 2026-08-12 · Creación del repositorio Git

Se inicializa el repositorio con rama `main` desde el primer momento —sin crear `master` y
renombrar—, se crea el commit `d2b8e77` que contiene exclusivamente `PROYECTO.md` y
`FICHA-APROBACION.md`, se configura `origin` hacia `github.com/henguido/SibuTestLab8583` y se
publica `main` con un push normal.

**Por qué aislar así el primer commit:** deja los documentos aprobados como punto de partida
histórico verificable, sin mezclarlos con código ni configuración generada después.

Antes de publicar se verificó con `git ls-remote` que el remoto estuviera vacío, de modo que un
push normal no pudiera sobrescribir trabajo ajeno.

## 2026-08-12 · Creación de `CONTEXTO.md`

Se incorpora `CONTEXTO.md` en el commit `4269e03` como memoria operativa entre sesiones.

**Por qué:** permite que una sesión nueva de Claude Code recupere el estado del proyecto sin
depender del historial de chat, que no persiste.

**Retroalimentación recibida y aplicada:** la primera versión tenía 238 líneas. El usuario
señaló que una memoria operativa de ese tamaño se convierte en una segunda bitácora y duplica
`PROYECTO.md`. Se redujo a 133 líneas resumiendo las reglas de negocio en lugar de copiarlas,
recortando el historial a hitos y eliminando el diagrama redundante.

## 2026-08-13 · Corrección de proceso: autorreferencia en `CONTEXTO.md`

**Qué ocurrió:** `CONTEXTO.md` se escribió antes del commit que lo incorporó, de modo que su
sección "Estado actual" afirmaba que existía un solo commit y que el propio archivo todavía no
estaba versionado. Ambas afirmaciones eran ciertas al redactarse y dejaron de serlo al
publicarse `4269e03`.

**Naturaleza del problema:** es una **corrección de proceso**, no una afirmación falsa del
agente. Los datos eran correctos en el momento de escribirse; el defecto está en haber incluido
en el documento información que el propio acto de versionarlo invalida.

**Qué se corrigió, en el commit `28a766d`:** se eliminó la cantidad de commits del estado
actual, se remite a `git log` y `git status` para el estado exacto del repositorio, se registró
el hito `4269e03` en el historial y se agregó a las reglas de mantenimiento la prohibición de
duplicar información dinámica que Git provee de forma autoritativa.

**Aprendizaje:** un documento que describe el repositorio no puede contener datos que el commit
que lo introduce invalida. Los SHA se conservan solo cuando identifican un hito histórico
concreto, nunca como estado actual.

## 2026-08-13 · Primera iteración arquitectónica

Se crean `CLAUDE.md`, esta bitácora, `.gitignore`, `.gitattributes` y
`docs/arquitectura/` con `ARQUITECTURA.md`, `componentes.mmd` y `flujo-compra.mmd`.
Corresponde a los entregables de la Sesión 4 del calendario de `PROYECTO.md` §9.

**Decisión tomada en esta iteración — persistencia asíncrona:** el contrato del repositorio será
asíncrono y el adaptador inicial usará `aiosqlite`. **Por qué:** cierra la consecuencia detectada
al adoptar transporte asíncrono, evitando bloquear el event loop al persistir, y mantiene el
motor sustituible. PostgreSQL queda como evolución futura y no se implementa.

**Decisión tomada en esta iteración — framing como contrato independiente:** se define
`FramingStrategy` separada del transporte, con la responsabilidad de preparar un payload para
transmisión y de determinar y leer un mensaje completo desde un stream. **Por qué:** el formato
de delimitación depende del ambiente receptor y no debe quedar incrustado en el transporte ni
confundirse con el contenido ISO. No se atribuye todavía ningún framing concreto a Visa ni a
Mastercard.

**Diagramas en Mermaid (`.mmd`):** se eligen por ser texto plano, versionables y comparables en
un `diff`, frente a imágenes binarias que Git no puede comparar.

No se escribió código del simulador en esta iteración.

## 2026-08-17 · Fundación ejecutable · primera iteración con código

Se construye la base sobre la que se montará el recorrido de compra: proyecto Python
instalable, modelos de dominio, perfil genérico, catálogo, persistencia SQLite asíncrona y
pruebas técnicas. 20 pruebas en verde. **No** se implementaron transporte TCP, host simulado,
framing concreto, codec como adaptador, orquestador ni interfaz web.

**Versiones de dependencias: verificadas, no inventadas.** Se creó un entorno virtual y se
instalaron las dependencias sin fijar versión para observar qué resuelve realmente el entorno
(Python 3.13.3). Los **límites inferiores** declarados en `pyproject.toml` son exactamente lo
resuelto —no restringen el rango superior, que admite versiones posteriores sin comprobar—:
`pyiso8583` 4.0.1, `aiosqlite` 0.22.1, `fastapi` 0.141.1, `uvicorn` 0.52.3, `jinja2` 3.1.6,
`pytest` 9.1.1, `pytest-asyncio` 1.4.0. FastAPI, uvicorn y jinja2 se declaran aunque todavía
no se usen, porque son el backend ya aprobado.

**Modelo de datos.** Tres tablas: `tarjetas_prueba`, `codigos_respuesta` y `ejecuciones`.
La política de PAN quedó incrustada en el esquema, no delegada a la disciplina de quien
programe: `ejecuciones` **no tiene columna para el PAN**, referencia `card_id` mediante clave
foránea, y guarda los mensajes en columnas `solicitud_enmascarada` y `respuesta_enmascarada`.

**Decisión derivada — mensajes persistidos enmascarados.** `PROYECTO.md` §5 exige persistir los
mensajes enviados y sus respuestas, pero un `0100` contiene el PAN en el campo 2. Guardar el
mensaje crudo duplicaría el PAN y violaría la política. Se resuelve persistiendo el mensaje con
los campos sensibles —2 y 35— ya enmascarados. Se cumplen ambos requisitos sin sacrificar
ninguno. El enmascaramiento vive en un solo módulo, `domain/enmascarado.py`, para que la regla
no se reimplemente en cada borde.

**Campos del perfil genérico — decisión técnica de este proyecto.** `PROYECTO.md` fija el
alcance y las reglas de negocio pero **no define campos ISO**. Ante esa ausencia se eligió el
conjunto mínimo que hace que un `0100` describa una compra concreta: 2 (PAN), 3 (código de
proceso), 4 (monto), 7 (fecha y hora de transmisión), 11 (STAN, para correlacionar solicitud y
respuesta), 14 (vencimiento), 22 (modo de captura), 41 (terminal) y 49 (moneda). Para el `0110`:
39 (código de respuesta, sin el cual RN-1 no puede aplicarse) más 3, 4, 7, 11 y 41, que deben
volver iguales para poder comprobar la respuesta según RN-3. La especificación además soporta
12, 13, 37 y 38 sin exigirlos.

**Esto no es la especificación de ninguna marca**, y está advertido en el encabezado del propio
módulo. Los perfiles de Visa y Mastercard siguen sin implementarse: requieren documentos
autorizados dentro del proyecto.

**Ajustes respecto de la arquitectura.** Ninguno de fondo; dos de alcance de esta iteración:

- No se crearon `application/`, `adapters/iso8583/` ni `web/`. Habrían quedado vacíos, y la
  instrucción vigente es no anticipar módulos. Se crearán cuando tengan contenido.
- El codec todavía no existe como adaptador. Para no dar por buena una especificación que solo
  *parece* correcta, las pruebas del perfil usan `pyiso8583` directamente para codificar y
  volver a decodificar un `0100` y un `0110`. Es validación de la especificación, no el
  adaptador.

**Defecto encontrado y corregido en la misma iteración.** `pyproject.toml` declaraba
`readme = "README.md"` apuntando a un archivo que no existe, lo que habría roto la construcción
del paquete en un clon limpio. Se detectó al verificar y se eliminó la línea; `README.md` no
corresponde a esta iteración.

**Datos de demostración.** Se siembra una única tarjeta sintética, marcada como tal en el
esquema. Su número se genera en ejecución y no se inserta ningún PAN real. Ver la entrada
siguiente sobre el endurecimiento de esta política.

## 2026-08-17 · Endurecimiento de la política de PAN y verificación de `requires-python`

Tres correcciones pedidas tras revisar la fundación, antes de registrarla.

**Ningún PAN completo en Git, ni siquiera sintético.** La versión anterior sembraba y probaba con
literales de dieciséis dígitos. Eran inventados, pero un literal con largo de tarjeta es
indistinguible de uno real para un escáner de secretos, para una auditoría y para quien lea el
repositorio por primera vez: que sea falso lo sabe quien lo escribió, no quien lo encuentra.

Se agregó `domain/datos_sinteticos.py`, que construye los números en ejecución a partir de un
sufijo corto y un dígito de relleno. `pan_sintetico("6666")` produce un número de dieciséis
dígitos terminado en `6666`. La tarjeta de demostración y las tres tarjetas de prueba pasaron a
generarse así, y el monto del campo 4 se formatea con `monto_iso()` en lugar de escribirse como
literal de doce dígitos. **Ninguna prueba se debilitó**: siguen comparando valores exactos, solo
que calculados.

La política se convirtió además en una comprobación automática:
`test_ningun_archivo_versionable_contiene_un_pan_completo` recorre todo lo que Git versionaría y
falla si encuentra una secuencia de 12 a 19 dígitos. Se verificó que la guardia **realmente
falla** introduciendo temporalmente un archivo con un número de dieciséis dígitos: la prueba lo
detectó y falló. Una prueba que nunca falla no protege nada.

El escaneo tras la refactorización encontró una última ocurrencia, en el texto de esta misma
bitácora, que también se eliminó.

**`requires-python` corregido de `>=3.11` a `>=3.13`.** La declaración anterior afirmaba un
soporte que nadie había comprobado. Se inventarió la máquina: el lanzador `py -0p` reporta una
única versión, 3.13, y `AppData/Local/Programs/Python/` contiene solo `Python313`; la entrada de
`WindowsApps` es el alias de la Microsoft Store, no un intérprete instalado. **No es posible
probar 3.11 ni 3.12 aquí**, así que se declara únicamente el rango verificado.

**Esto no afirma incompatibilidad.** El código no usa ninguna característica exclusiva de 3.13 y
probablemente funcione en 3.11 y 3.12; simplemente no se declara un soporte que no se probó.
Declarar `>=3.13` es más estrecho que la realidad esperada, y esa estrechez es deliberada: es
preferible a prometer compatibilidad sin evidencia. En la Sesión 6, CI deberá ejecutar una matriz
de versiones y ampliar `requires-python` si la evidencia lo permite. No se modificó código para
"soportar" versiones que no se pueden ejecutar aquí.

**Revalidación de la inicialización.** Sobre una base borrada y creada de nuevo, ejecutada dos
veces: seis códigos de respuesta, una tarjeta sintética, cero duplicados, `ejecuciones` sin
columna de PAN, y ninguna base SQLite visible para Git. La suite quedó en 28 pruebas.

## 2026-08-19 · Núcleo transaccional de extremo a extremo

Se implementan codec, validación de las cuatro reglas, framing, transporte TCP asíncrono, host
simulado y orquestador. Una compra viaja por TCP real hasta el host simulado y vuelve.
La suite pasa de 30 a 75 pruebas. **No** se implementaron FastAPI, HTML, isoscopio web ni motor
de carga.

**Framing elegido: prefijo binario de 2 bytes, big-endian, con la longitud del payload.**
Es el framing de demostración de SibuTestLab8583 y no se atribuye a ninguna marca. Razones:
es simple, suficiente para los mensajes de la demostración, y corresponde a un patrón utilizado
por implementaciones de ISO 8583 sobre TCP. **No representa una especificación de Visa ni de
Mastercard, ni pretende ser un framing universal de ISO 8583.** Big-endian es el orden de red y
`int.from_bytes` lo resuelve sin ambigüedad de plataforma; dos bytes admiten 65 535, muy por
encima de un `0100` de este perfil. Se descartó la longitud en ASCII porque obliga a decidir relleno y codificación,
y difumina el límite entre enmarcado y contenido. Se descartó un delimitador centinela porque el
payload es binario y podría contenerlo. El framing del switch real dependerá de su
especificación y será otra `FramingStrategy`, sin tocar el transporte.

**Campos que compara RN-3.** Se derivan del perfil, no se inventan: son los obligatorios de la
respuesta menos el campo 39, que por definición lo origina el autorizador y no viaja en la
solicitud. Con el perfil genérico son **3 (código de proceso), 4 (monto), 7 (fecha y hora de
transmisión), 11 (STAN) y 41 (terminal)**. Además se comprueba que el MTI sea el `0110`
esperado y que la respuesta traiga sus obligatorios.

**Mecanismo concreto contra falsos positivos (`PROYECTO.md` §7.6).** El orden de evaluación es
deliberado: **RN-3 se comprueba antes que RN-1**. Una respuesta cuyo campo 39 diga `00` pero
cuyo STAN no corresponda a la solicitud enviada se registra como `INVALIDA`, nunca como
`APROBADA`. Invertir ese orden convertiría el simulador en una fuente de falsos positivos, que
es exactamente lo que la sección 7.6 obliga a poder detectar. Está probado de dos formas: una
prueba parametrizada altera *cada* campo de correlación y exige `INVALIDA`, y una prueba de
integración levanta el host simulado configurado para responder `00` con un STAN ajeno.

### Correcciones surgidas durante la implementación

**Bloqueo al detener el host simulado.** La primera versión mantenía la conexión abierta con
`asyncio.sleep(3600)` para provocar el caso de RN-2. La suite se colgó: desde Python 3.12,
`Server.wait_closed()` espera a que terminen los manejadores activos, de modo que apagar el host
esperaba una hora. Se sustituyó por un `asyncio.Event` de apagado que `detener()` avisa **antes**
de cerrar. El diagnóstico salió de razonar sobre la semántica de `wait_closed()`, no de tantear.

**Comportamiento observado con un puerto cerrado.** Se escribió una prueba que conectaba a un
puerto cerrado de loopback esperando `ErrorDeConexion`, y falló. Hecho observado, comprobado con
un script aparte: **en el entorno Windows probado, una conexión a un puerto loopback cerrado
agotó el tiempo de espera en lugar de producir un rechazo inmediato** —también con un puerto
efímero recién liberado—. No se generaliza ese comportamiento a otros sistemas ni a otras
configuraciones de red, y **las pruebas no dependen de él**: la prueba pasó a forzar el fallo de
conexión con un host irresoluble, que es portable.

**La guardia de PAN detectó una violación propia.** Al escribir la prueba de RN-3 se usó un
literal de doce dígitos como valor alterado. `test_ningun_archivo_versionable_contiene_un_pan_completo`
lo detectó y falló el build. Se sustituyó por un valor construido alterando el primer carácter y
conservando el largo. Es la segunda vez que esa guardia justifica su existencia.

**Divergencia con `ARQUITECTURA.md`, corregida en el documento.** El contrato documentado era
`evaluar_respuesta(envio, respuesta, catalogo)`. Al implementar RN-3 quedó claro que **qué campos
deben correlacionar es una definición del perfil**, no del catálogo, así que la firma real recibe
también el perfil. Se actualizó el documento porque la firma anterior había dejado de ser cierta;
no se cambió ninguna decisión de fondo.

**Sin cambios en el esquema de la base de datos.** Las columnas `solicitud_enmascarada` y
`respuesta_enmascarada` bastaron para persistir los mensajes. El orquestador serializa siempre la
versión enmascarada, y `_serializar` verifica que ningún campo sensible llegue en claro: si un
cambio futuro colara un PAN completo hacia la persistencia, falla en el acto en lugar de
guardarlo.

## 2026-08-19 · Interfaz web mínima

Se añade la capa `web/` con FastAPI y plantillas Jinja sobre el núcleo ya aprobado, sin
modificarlo. La suite pasa de 75 a 101 pruebas. **No** se implementaron motor de carga, perfiles
de marca, CI, Docker, skill de `.claude/` ni autenticación.

**Cómo se compusieron las dependencias.** Se creó una raíz de composición explícita,
`composicion.py`, con dos piezas: una `Configuracion` inmutable —ruta de la base, host y puerto de
destino, límite de tiempo— que puede leerse del entorno, y una clase `Composicion` que cablea
perfil, catálogo, codec, framing, transporte y repositorios. Los endpoints **no construyen
infraestructura**: reciben la composición por inyección de dependencias de FastAPI y le piden un
orquestador. El orquestador se construye por petición porque el destino lo elige el usuario en el
formulario; es cableado barato, ya que los repositorios abren su conexión por operación. Esa
inyección es también lo que permite que las pruebas sustituyan la composición entera por un doble
sin tocar la aplicación.

**Cómo se evita que el navegador reciba el PAN completo.** No por disciplina en las plantillas,
que sería frágil, sino por construcción: `ServicioConsultas.tarjetas()` devuelve un
`TarjetaListada` que **no tiene** campo para el PAN completo. Aunque una plantilla quisiera
mostrarlo, no lo tiene disponible. Para los mensajes, el orquestador ya devuelve la solicitud y la
respuesta enmascaradas, y la capa web no vuelve a implementar la política: la recibe hecha.
Comprobado sobre el HTML real: ninguna de las tres páginas contiene el número completo, y el
isoscopio lo muestra enmascarado con la marca «enmascarado».

**Precisión aplicada a la redacción de la política.** La primera versión de la pantalla decía que
el número completo "nunca sale del servidor". Es falso para este simulador: el PAN completo viaja
en el campo 2 del `0100` que el servidor transmite al host simulado o a un switch de QA
autorizado; sin él no hay transacción que enviar. La política correcta distingue **tres ámbitos**:
el navegador nunca recibe el PAN completo; los logs, el historial y las ejecuciones nunca lo
guardan; y el procesamiento transaccional sí lo usa, tomado del catálogo local. La frase se
sustituyó en la interfaz y la distinción quedó explícita en `CLAUDE.md` y `CONTEXTO.md`.

**Cómo se manejan los errores de infraestructura.** La web traduce cada fallo a un aviso con
título, explicación y tono visual propio, sin exponer trazas ni el texto de la excepción. Los seis
desenlaces se distinguen a simple vista: aprobada, rechazada, inválida, sin respuesta, mensaje
incompleto y fallo de conexión. Ese último merece énfasis: **no poder conectar no es un rechazo
del autorizador**, y presentarlos igual induciría a error a quien prueba.

**Decisión sobre los campos del formulario.** Se declararon con valor por defecto vacío en lugar
de obligatorios. Con `Form(...)`, FastAPI responde su propio 422 en JSON ante un campo vacío, y el
usuario vería un error crudo en vez del formulario con la explicación. Con valor por defecto, la
validación propia produce un 400 que vuelve a renderizar la pantalla con el mensaje.

**Isoscopio: solicitud y respuesta no son simétricos.** La respuesta trae representación cruda
porque `MensajeInterpretado` la conserva desde el decode. La solicitud no la lleva: se conserva
como valores del dominio, y reconstruir bytes para mostrarlos sería inventar un dato que nadie
observó. Se muestra la columna solo donde el dato existe de verdad.

**Dependencias no obvias.** El cliente de pruebas de esta versión de Starlette exige **`httpx2`**,
no `httpx`: es un paquete distinto, la línea sucesora de `httpx`, instalado desde PyPI, y
`starlette 1.6.0` lo declara como `httpx2>=2.0.0` en su extra `full`. Además,
`python-multipart` es necesario para que FastAPI lea formularios.

**Qué significa y qué no significa `httpx2>=2.12.0`.** La versión comprobada en este entorno es
`httpx2` 2.12.0; 2.12.0 queda como **límite inferior provisional**. El rango permite versiones
posteriores aún no comprobadas, y la reproducibilidad exacta del conjunto de dependencias se
resolverá posteriormente con el mecanismo de congelado y CI del proyecto. Lo mismo vale para las
demás dependencias: declarar el mínimo verificado no equivale a restringir el rango a lo
verificado.

**La prueba vertical usa cliente asíncrono.** El `TestClient` síncrono bloquearía el event loop en
el que corre el host simulado, de modo que la conexión nunca se atendería. Se usa
`httpx2.ASGITransport` con `AsyncClient`, que ejecuta la aplicación en el mismo loop.

**Sin cambios en el núcleo.** No se tocó ninguna regla, contrato ni módulo del núcleo
transaccional. Lo añadido fue `application/consultas.py`, que es solo lectura, y la raíz de
composición. `ARQUITECTURA.md` se actualizó únicamente para incorporar la raíz de composición a la
tabla de módulos, que había quedado incompleta.

**Hueco identificado, no resuelto en esta iteración.** Un fallo de conexión no se persiste: la
excepción sube y no queda rastro en `ejecuciones`. La web lo informa correctamente, pero el
historial no registra el intento. Resolverlo exigiría un estado nuevo en el núcleo, y esta
iteración tenía instrucción de no modificarlo. Queda anotado como decisión pendiente.

**La guardia de PAN volvió a detectar una violación propia**, la tercera: un literal de doce
dígitos como monto en las pruebas de la web. Sustituido por `monto_iso()`.

## 2026-08-19 · Integración continua y refactorización

Se añade `.github/workflows/tests.yml` y se corrigen problemas reales del código acumulado. **No
se añadió funcionalidad**: ni motor de carga, ni perfiles de marca, ni cambios de alcance o de
reglas. La suite sigue en 101 pruebas, en verde antes y después de refactorizar.

### Diseño del CI

Tres trabajos, sin despliegues y sin secretos, disparados por `push` y por `pull_request`.
Cada uno demuestra una cosa distinta:

- **`suite`** — compatibilidad experimental. Matriz de Python 3.11, 3.12 y 3.13 sobre
  `ubuntu-latest`, con `fail-fast: false` para ver el resultado de las tres aunque una falle.
  Corre la suite completa **una sola vez** por versión.
- **`reglas-negocio`** — RN-1 a RN-4 visibles. Trabajo aparte sobre 3.13 que ejecuta solo
  `tests/test_reglas_negocio.py -v`, para que la evidencia de `PROYECTO.md` §4 se lea de un
  vistazo sin repetir esa ejecución dentro de cada miembro de la matriz.
- **`clon-limpio`** — instalación normal. Comprueba que un clon recién hecho no trae artefactos
  locales, instala **respetando el metadata declarado**, inicializa la base desde cero dos veces
  y corre la suite.

**Ejecuta en Linux, y todo lo verificado hasta ahora fue en Windows.** Eso es deliberado: aporta
evidencia nueva sobre rutas y finales de línea. Queda pendiente decidir si conviene añadir un
trabajo en Windows.

### Cómo se prueban 3.11 y 3.12 sin falsear el metadata

`pyproject.toml` declara `requires-python = ">=3.13"` porque 3.13 era lo único instalable en la
máquina de desarrollo. Bajar ese valor *antes* de tener evidencia sería declarar un soporte que
nadie comprobó —el error que ya se corrigió una vez—, y modificar el archivo dentro del CI sería
falsear lo que el repositorio dice.

**Primera propuesta, descartada por imprecisa.** Se planteó `pip install --ignore-requires-python`
para todo el paso de instalación. El usuario señaló el defecto: esa opción se aplica a **toda la
resolución**, de modo que una dependencia que genuinamente no soporte 3.11 se instalaría igual y
la incompatibilidad quedaría enmascarada. El experimento habría dado un falso verde.

**La forma correcta separa las dos cosas.** El trabajo de matriz:

1. lee `pyproject.toml` con `tomllib` y extrae `project.dependencies` y
   `project.optional-dependencies.dev` —así la lista no puede desincronizarse de lo declarado,
   porque no hay una segunda copia que mantener—;
2. las escribe a un archivo en `$RUNNER_TEMP`;
3. las instala con `pip install -r`, **sin ignorar nada**: si alguna declara no soportar esa
   versión de Python, falla ahí, que es exactamente lo que queremos saber;
4. instala solo nuestro paquete con `--no-deps --ignore-requires-python -e .`.

`--no-deps` es lo que garantiza que el paso 4 no reabra la resolución con la restricción ignorada.
Así **lo único que se ignora provisionalmente es el `requires-python` de este proyecto**, que es
justamente la afirmación que se está poniendo a prueba. Ningún archivo cambia: el metadata sigue
diciendo la verdad y el CI produce la evidencia que falta. El trabajo `clon-limpio` instala con
`pip install -e ".[dev]"` sin ignorar nada, de modo que también se comprueba que el metadata
declarado funciona tal cual para quien reciba el repositorio.

**Solo si las tres versiones pasan** tendrá sentido ampliar `requires-python` a `>=3.11`, y esa
ampliación será entonces un hecho verificado y no una suposición. **Al momento de escribir esto el
workflow todavía no se ha ejecutado**: no hay ningún resultado de 3.11 ni de 3.12.

### Sobre los markers de pruebas

Se evaluó añadir un marker `regla_negocio` y se decidió **no hacerlo**. Las pruebas ya viven en
`tests/test_reglas_negocio.py` y se llaman `test_rn1_…`, `test_rn2_…`, `test_rn3_…` y `test_rn4_…`.
Un marker sería metadata duplicada que puede desincronizarse del nombre y del archivo sin que nada
falle. El trabajo `reglas-negocio`, que corre ese archivo con `-v`, da la misma visibilidad al
docente sin nada que mantener.

### Guardias de seguridad en CI

La guardia de PAN ya corre como parte de la suite. Se añadió además un paso que revisa **qué
archivos están versionados** —`.env`, `.db`, `.sqlite`, `.venv/`, `settings.local.json`—, que es
una comprobación distinta y no duplicada: la guardia de la suite revisa el *contenido*, y un `.env`
sin dígitos la pasaría sin problema. Son tres líneas de shell, no un script.

### Refactorizaciones realizadas

Cada una responde a un problema concreto, no a estética. Las 101 pruebas existentes pasan sin
cambios funcionales en sus aserciones, lo que aporta evidencia de que las refactorizaciones
conservaron **el comportamiento actualmente cubierto por la suite**. Una suite solo protege lo
que cubre: no es una demostración de equivalencia total.

1. **`web/app.py`: las rutas salen de la fábrica.** `crear_app` tenía 119 líneas porque las tres
   rutas vivían anidadas dentro. La clausura no capturaba nada: la composición llega por `Depends`,
   no por el ámbito. Pasaron a un `APIRouter` de módulo. Cada ruta se lee y se prueba por separado
   y la fábrica queda en ocho líneas.
2. **`web/app.py`: el endpoint de compra baja de 65 líneas.** Se extrajeron
   `_interpretar_formulario` —validación de entrada— y `presentacion.contexto_de_resultado`
   —armado del contexto de plantilla—. El endpoint queda con lo suyo: validar, delegar, elegir
   plantilla.
3. **`domain/validacion.py`: una función por regla.** `evaluar_respuesta` mezclaba RN-3 y RN-1 en
   58 líneas. Se separó en `_discrepancias_de_correlacion` (RN-3) y `_interpretar_codigo` (RN-1).
   El cuerpo principal queda en cuatro líneas donde **el orden entre ambas reglas es lo único
   visible**, que es justamente la decisión que protege contra falsos positivos.
4. **Configuración repetida.** `PUERTO_POR_DEFECTO` estaba definido con el mismo valor en
   `composicion.py` y en `cli.py`. Cambiar uno y olvidar el otro habría dado un comando de
   demostración apuntando a otro puerto que la web. `cli.py` ahora importa ambos valores.
5. **Import local en `servidor.py`.** `MensajeIso` se importaba dentro de un método sin razón
   —no hay ciclo—; subido al módulo.
6. **Código muerto en pruebas.** `DESTINO_INERTE` se importaba y no se usaba;
   `RepositorioTarjetasSQLite` se importaba dos veces dentro de funciones. Corregidos.

**Lo que se decidió NO refactorizar.** `Orquestador.ejecutar_compra` tiene 71 líneas y se deja
como está. Es la secuencia central del sistema y su valor está en que el orden se lea completo y
seguido: armar, RN-4, codificar, enviar, RN-2, decodificar, RN-3 y RN-1, persistir. Partirla
escondería exactamente lo que hay que poder auditar. El armado del registro ya está extraído en
`_registrar`; lo que queda es el flujo, y el flujo es uno.

Se revisó `pyproject.toml`: se actualizaron dos comentarios que habían quedado obsoletos
—`fastapi` y `uvicorn` seguían marcados "todavía sin usar" cuando la iteración anterior ya los
usa—. No se congelaron dependencias: la estrategia de reproducibilidad exacta se decidirá viendo
lo que reporte el CI, como estaba previsto.

---

## Gobernanza

Controles ya acordados y vigentes.

**Datos de tarjeta.** Nunca registrar el PAN completo en logs, en la bitácora ni en Git; las
ejecuciones referencian la tarjeta por identificador interno; fuera de su pantalla de
mantenimiento se muestra solo `************1234`; el archivo SQLite con tarjetas reales de QA no
se versiona. Antes de cada commit se revisa que no se filtren datos de tarjeta. Verificación
aplicada hasta ahora: se escaneó `CONTEXTO.md` en busca de secuencias de dígitos, credenciales y
secretos antes de versionarlo; el único patrón de tarjeta presente era la representación
enmascarada.

**Historial.** No se usa `--force` ni se reescribe historial sin instrucción expresa. Cada push
realizado hasta ahora fue fast-forward y quedó verificado contra el reflog y contra el remoto.

**Veracidad de las afirmaciones.** No se declara nada implementado, funcionando o corregido sin
verificarlo contra el código y contra Git. `CONTEXTO.md` debe contrastarse siempre contra el
repositorio antes de asumir que algo existe, y Git y el código son la fuente de verdad ante
cualquier contradicción.

**Detección de falsos positivos del simulador.** `PROYECTO.md` §7.6 exige poder detectar si el
simulador afirma que una prueba fue exitosa sin serlo. La obligación está asumida; el mecanismo
concreto se definirá cuando exista el recorrido de extremo a extremo, y se registrará aquí
entonces.

### Caso de afirmación falsa del agente

**2026-08-17 · Afirmación incorrecta sobre los rangos de identificador emisor.**

**Qué afirmó Claude.** Al generar tarjetas sintéticas con relleno `9`, escribió en el código, en
las pruebas y en esta bitácora que ese rango "no se asigna a marcas de pago" y que por lo tanto
un número así generado "no puede coincidir con una tarjeta real".

**Por qué es falso.** El identificador emisor `9` está reservado para asignación **nacional**
según ISO/IEC 7812. No es un rango libre: distintos países lo usan para esquemas domésticos. Que
no lo usen Visa o Mastercard no implica que no exista ninguna tarjeta real con ese prefijo.

**Cómo se detectó.** Lo detectó el usuario al revisar la fundación antes del commit, no una
prueba ni una verificación del agente. Es el modo de detección más caro: de haber pasado la
revisión, el proyecto habría defendido su política de datos con un argumento incorrecto ante el
docente.

**Naturaleza del error.** Es una afirmación técnica presentada con seguridad sin haberse
verificado contra la norma. No fue una alucinación sobre una API o un archivo inexistente —el
código funcionaba— sino sobre una **justificación**, que es más difícil de detectar precisamente
porque nada falla.

**Corrección aplicada.** Se eliminó la afirmación de todo el repositorio y se sustituyó por una
propiedad comprobable: los números generados **no superan la verificación de Luhn**, de modo que
ningún sistema que valide el dígito verificador los aceptaría. La defensa del proyecto no
descansa en el prefijo elegido sino en que ningún PAN completo esté versionado, y esa propiedad
la vigila una prueba automática.

**Control derivado.** Toda justificación que dependa de una norma externa —ISO 7812, ISO 8583,
ISO 4217— debe citar la norma o declararse como decisión propia del proyecto. No se afirma lo
que dice una norma sin haberlo verificado.

---

## Revisión y delegación

Sección que debe mantenerse durante todo el proyecto para dejar explícito qué se revisa siempre
y qué puede delegarse al agente sin revisión detallada.

**Práctica seguida hasta ahora.** Hasta esta iteración, los archivos incorporados al repositorio
fueron presentados para revisión antes de su commit: `CONTEXTO.md` se presentó completo, se pidió
una reducción de tamaño y se aprobó explícitamente antes de registrarse. Ninguna operación sobre
Git se ejecutó sin mostrar antes el estado verificado.

**Pendiente de definir.** Los criterios estables de esta sección —qué categorías de cambio
exigen revisión línea por línea y cuáles admiten revisión por resultado— se irán fijando a
medida que aparezca código y pruebas. No se anticipan aquí.

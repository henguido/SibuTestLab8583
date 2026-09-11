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

## 2026-08-19 · Defecto corregido: el STAN se repetía en cada transacción

Iteración dedicada a un solo problema, detectado en la auditoría del prototipo. No se tocó
ningún otro hallazgo.

**El defecto.** Todas las compras hechas desde la web llevaban el mismo número de trazabilidad,
`000001`. Comprobado ejecutando tres compras de montos distintos: las tres se persistieron con
`STAN=000001`.

**La causa.** El contador nacía dentro de `_contador_de_stan()`, llamado en el constructor del
`Orquestador`; y la composición construye un `Orquestador` **por petición**, porque el destino lo
elige el usuario en el formulario. Cada petición arrancaba su propio contador en 1. El estado que
debía ser compartido y duradero vivía en un objeto efímero.

**Por qué importaba.** El campo 11 es uno de los cinco que RN-3 compara para correlacionar la
respuesta con la solicitud. Con el STAN repetido, RN-3 no podía distinguir *esta* transacción de
otra. Además, un código del catálogo aprobado —`94`, transacción duplicada— existe precisamente
para ese caso.

**La solución.** Un puerto nuevo, `GeneradorStan`, con una operación asíncrona `siguiente()`. Es
un puerto y no una función porque la unicidad exige estado compartido: el dominio declara la
necesidad y no sabe dónde vive ese estado. La composición inyecta la implementación.

**Por qué se descartó `MAX(id)+1`.** Dos peticiones concurrentes leerían el mismo máximo antes de
que ninguna insertara, y entregarían el mismo STAN. Además cuenta filas, no trazas.

**Atomicidad: una sola sentencia.**

```sql
UPDATE secuencias SET valor = (valor % 999999) + 1
 WHERE nombre = 'stan'
RETURNING valor
```

SQLite mantiene el bloqueo de escritura durante toda la sentencia, de modo que leer el valor,
incrementarlo y escribirlo son indivisibles. Una segunda conexión simultánea **espera** al bloqueo
y después vuelve a leer el valor ya incrementado. Lo que se evitó explícitamente es un `SELECT`
seguido de un `UPDATE` en sentencias separadas: ahí ambas conexiones pueden leer el mismo valor
antes de que ninguna escriba.

**Se comprobó que esa diferencia es real, no teórica.** Con 25 solicitudes simultáneas sobre la
misma base: la implementación con `UPDATE … RETURNING` entregó **25 valores distintos de 25**; una
implementación deliberadamente ingenua con `SELECT` + `UPDATE` entregó **1 valor distinto de 25**.
La prueba de concurrencia no es vacía: detecta el enfoque incorrecto.

**Ciclo al llegar al máximo.** El módulo hace que tras `999999` la secuencia vuelva a `000001`.
Seis dígitos no alcanzan para ser únicos indefinidamente: eso es propio del campo 11 de ISO 8583.
Por la misma razón **no** se puso una restricción `UNIQUE` sobre `ejecuciones.stan`.

**Idempotencia.** `sibu-init-db` crea la secuencia con `INSERT OR IGNORE`. Ejecutarlo de nuevo no
reinicia el contador, no duplica filas y no destruye el historial: comprobado tras dos ejecuciones
adicionales sobre una base con cinco ejecuciones ya registradas.

**Una prueba existente pasaba por la razón equivocada.**
`test_rn2_el_timeout_se_persiste_y_se_cuenta_aparte_del_rechazo` fabricaba una respuesta enlatada
con `STAN=000001`. Correlacionaba **solo porque el STAN siempre era 000001**: dependía del
defecto. Al corregirlo, RN-3 detectó correctamente que la respuesta no correspondía y la prueba
falló. Se corrigió el doble de transporte para que construya la respuesta a partir de la solicitud
que recibe, como hace el host real, de modo que no pueda volver a esconder este problema.

## 2026-08-19 · Semántica de comunicación: conectar no es lo mismo que esperar respuesta

Iteración dedicada a dos defectos de la auditoría, tratados juntos porque son la misma materia:
qué ocurrió con el intento y cómo queda registrado. No se tocó isoscopio, historial navegable,
UX ni escenarios de demostración.

### Los defectos

**Intentos que desaparecían del historial.** Un fallo al conectar hacía que el transporte lanzara
`ErrorDeConexion`; la excepción subía, la web la informaba en pantalla, y en `ejecuciones` no
quedaba rastro de haberlo intentado. Lo mismo con un fallo del codec al codificar. Para una
herramienta cuyo valor es la trazabilidad, eso es grave: quien prueba contra un switch caído no
tenía evidencia de haberlo probado.

**Un timeout al conectar se contaba como RN-2.** El mismo `wait_for` envolvía `open_connection` y
la espera de la respuesta, así que agotar el tiempo *conectando* devolvía `TiempoAgotado` y el
orquestador lo registraba como RN-2. Pero RN-2 dice «se envió y no respondieron», y ahí nunca
hubo solicitud en vuelo. Además, en el entorno Windows probado un puerto cerrado agota el tiempo
en lugar de rechazar, de modo que el caso más común —«el host simulado no está levantado»— caía
justamente en esa clasificación equivocada.

### Excepción o resultado: se eligió resultado

El transporte **ya no lanza excepciones por condiciones de red**. Devuelve `bytes`,
`TiempoAgotado` o `FalloDeConexion`.

**Por qué.** Para una herramienta de pruebas, que el destino no esté disponible es una
observación que hay que registrar, no una anomalía que haya que propagar — el mismo razonamiento
que ya había hecho de `TiempoAgotado` un resultado. Mezclar las dos formas obligaba al orquestador
a tener dos caminos para la misma categoría de cosa, y era la causa de que el intento se perdiera.
Como consecuencia, `ErrorDeConexion` y `ErrorDeTransporte` quedaron sin uso y se eliminaron: no
tiene sentido conservar excepciones que nadie lanza.

**Tres fases, tres desenlaces.** El transporte clasifica por fase: si falla al **conectar** o al
**enviar**, `FalloDeConexion`; solo si se agota el tiempo **esperando la respuesta**,
`TiempoAgotado`. Así RN-2 conserva exactamente su significado sin haber cambiado la regla.

### Error de codec: sigue siendo `NO_ENVIADA`

Se evaluó un estado propio y se decidió que no. Lo que define `NO_ENVIADA` es que el mensaje
nunca llegó al transporte, y eso es literalmente cierto para las tres causas que ahora agrupa:
falta un campo obligatorio (RN-4), el codec no pudo codificar, el framing rechazó el payload.
La pregunta operativa que se hace quien prueba es una sola —«salió o no salió»—, y la causa
concreta ya viaja en los motivos de la ejecución. Partirla en un estado por causa multiplicaría
estados sin dar una distinción útil.

### Estados finales: seis

`APROBADA`, `RECHAZADA` e `INVALIDA` presuponen que llegó una respuesta. `TIMEOUT` es RN-2 y solo
RN-2. `ERROR_CONEXION` es que el canal no se pudo usar. `NO_ENVIADA` es que nada salió de la
máquina.

### Cómo se conserva el intento

Todo desenlace pasa por el mismo registro, y por eso todos quedan persistidos con `card_id`,
monto, moneda, STAN, MTI de solicitud, estado, solicitud enmascarada y latencia. El destino se
registra en todo intento que llegó a tocar la red —incluido `ERROR_CONEXION`, porque saber contra
qué se intentó es la mitad del diagnóstico—; solo `NO_ENVIADA` queda sin destino, porque no lo
hubo. Ni `ERROR_CONEXION` ni `TIMEOUT` tienen MTI de respuesta ni campo 39: no se recibió nada
que registrar.

### Una guardia nueva contra un fallo silencioso

`historial.html` busca el estado en el mapa `AVISOS`. Añadir un miembro a `EstadoEjecucion` sin
su entrada correspondiente habría producido un `KeyError` en tiempo de ejecución, al abrir el
historial, y no un fallo en la suite. Ahora una prueba recorre el enum y exige que todos los
estados tengan presentación, y otra que ninguno comparta título con otro.

### Verificación

Los seis recorridos, ejecutados de extremo a extremo contra el host simulado real y persistidos
en la misma base, quedan así:

| estado | c39 | MTI resp. | destino | latencia |
|---|---|---|---|---|
| `no_enviada` | — | — | ninguno | — |
| `error_conexion` | — | — | registrado | sí |
| `timeout` | — | — | registrado | sí |
| `invalida` | `00` | `0110` | registrado | sí |
| `rechazada` | `51` | `0110` | registrado | sí |
| `aprobada` | `00` | `0110` | registrado | sí |

La fila `invalida` con código `00` es la defensa contra falsos positivos siguiendo en pie.

El fallo de conexión se fuerza en las pruebas con un nombre irresoluble bajo `.invalid`,
reservado por RFC 2606: es portable y no depende de cómo cada sistema operativo trate un puerto
cerrado. El timeout usa el host simulado real configurado para aceptar la conexión y callar, y la
prueba comprueba que el host **recibió** el `0100`, que es la premisa de RN-2.

123 pruebas, 12 nuevas.

## 2026-08-19 · Corrección semántica antes del commit: `ERROR_TRANSMISION`

**Esta corrección surgió de una revisión semántica pedida antes de versionar, no de una falla
posterior.** La implementación anterior de P0-2/P0-3 pasaba sus 123 pruebas y aun así clasificaba
mal tres situaciones. El usuario pidió leer el código antes de aprobar el commit, y ahí apareció.

### Lo que estaba mal

`FalloDeConexion` se devolvía en tres momentos distintos, y `ERROR_CONEXION` solo era correcto en
el primero:

- `open_connection` falla o agota tiempo — correcto;
- `write()`/`drain()` falla o agota tiempo — **la sesión TCP ya existía**;
- el canal se rompe *esperando la respuesta* — la sesión existía **y el envío se había completado**.

Y peor que la clasificación: la documentación afirmaba cosas indemostrables. `modelos.py` decía
«no hubo una solicitud en vuelo» y el orquestador decía «nunca salió» para casos donde eso no se
puede saber.

**Por qué no se puede saber.** `StreamWriter.write()` solo encola en el buffer local; `drain()`
habla de ese buffer, no de la aplicación remota; y TCP no le dice al programa cuánto procesó el
par. Si `drain()` falla, pudieron salir cero bytes, algunos o todos, sin forma de distinguirlo.
En pagos eso no es un matiz de redacción: decirle a quien prueba «no se envió» cuando pudo haberse
enviado es el error más caro posible, porque es exactamente el caso que obliga a sospechar un
posible procesamiento y que motiva los reversos —que están fuera de alcance—.

### Lo que se hizo

Un cuarto resultado del transporte, `FalloDeTransmision`, y un séptimo estado,
`ERROR_TRANSMISION`. La clasificación pasó a depender de **la fase**, no de la excepción:

| Fase | Falla | Resultado | Estado |
|---|---|---|---|
| 0. Enmarcar | `preparar()` rechaza | lanza `ErrorDeFraming` | `NO_ENVIADA` |
| 1. Conectar | rechazo, ruta, DNS, tiempo | `FalloDeConexion` | `ERROR_CONEXION` |
| 2. Enviar | `drain()` falla o se agota | `FalloDeTransmision` | `ERROR_TRANSMISION` |
| 3. Esperar | se agota el tiempo | `TiempoAgotado` | `TIMEOUT` (RN-2) |
| 3. Esperar | canal roto o desenmarcado incompleto | `FalloDeTransmision` | `ERROR_TRANSMISION` |

RN-2 quedó reservado para las cuatro premisas observables: se conectó, el drenaje terminó, se
empezó a esperar, no llegó respuesta. **La regla no cambió**; lo que cambió es que dejaron de
entrarle casos que no la cumplen.

### Framing: antes y después de conectar

`preparar()` corre en la fase 0, así que su fallo sí permite afirmar que nada se transmitió →
`NO_ENVIADA`. `leer_mensaje_completo()` corre en la fase 3, así que su fallo es del **mecanismo de
transporte** → `ERROR_TRANSMISION`. Distinto de una **respuesta ISO completa que llega y no se
puede decodificar**, que sigue siendo `INVALIDA` porque sí hubo algo que evaluar. La frontera es
si llegó un mensaje completo, no si el contenido gustó.

### Afirmaciones falsas corregidas

- «no hubo una solicitud en vuelo» en `modelos.py` y `puertos.py` — ahora `FalloDeConexion` se
  restringe a la fase de conexión, donde sí es cierto.
- «nunca salió» en el orquestador después de `write`/`drain` — eliminada.
- «el transporte no lanza excepciones» en el contrato — era falso: `preparar()` puede lanzar
  `ErrorDeFraming`. Ahora el contrato lo declara explícitamente y explica por qué esa sí puede
  salir: no es una condición de red y ocurre antes de tocarla.

Se añadieron dos pruebas que vigilan la prohibición sobre el propio texto: ni el detalle del
resultado ni el aviso que ve el usuario pueden contener «nunca salió», «no se envió», «cero bytes»
ni «nada salió».

### Verificación

18 pruebas nuevas, 141 en total. Los fallos posteriores a conectar se provocan con dobles del
lector y del escritor sustituyendo `asyncio.open_connection`: determinista y portable, sin
depender de que un sistema operativo rechace o descarte una conexión a un puerto cerrado. RN-2
conserva pruebas con TCP real contra el host simulado, que además comprueban que el host
**recibió** el `0100` —la premisa de la regla—.


### Segunda precisión semántica, también antes del commit

Dos afirmaciones más que no resistían el escrutinio, corregidas en la misma revisión previa:

**`TIMEOUT` afirmaba que la solicitud fue transmitida.** El aviso decía «La solicitud fue
transmitida y no se recibió respuesta», y `TiempoAgotado` se documentaba como «se logró enviar la
solicitud». Ninguna de las dos se sostiene: que `drain()` termine sin error dice que el buffer
local se vació, no que la aplicación remota recibiera ni procesara nada. `drain()` habla del
buffer, no del par. La redacción pasó a enunciar solo lo observable **desde este cliente**: se
estableció la conexión, la escritura local terminó sin error, se esperó una respuesta completa
hasta agotar el límite, y no puede afirmarse si el destino recibió o procesó el mensaje.
**RN-2 sigue siendo `TIMEOUT`; no cambió su comportamiento**, solo dejó de prometer más de lo que
observa.

**`NO_ENVIADA` se definía como «no llegó al transporte».** Es incorrecto:
`FramingStrategy.preparar()` se ejecuta *dentro* de `TransporteTcp.enviar()`, así que el mensaje
sí llega al transporte y es el transporte quien lo rechaza. La definición correcta es **«no se
llegó a intentar transmisión por la red»**, que sigue cubriendo los tres casos —RN-4, fallo del
codec y rechazo del framing de salida antes de conectar— sin decir algo falso sobre la frontera
del módulo.

También se corrigió el detalle de `FalloDeTransmision` en la fase 3, que decía «la solicitud se
transmitió»: tampoco eso es demostrable, y ahora dice que el intercambio se interrumpió y no puede
determinarse cuánto recibió o procesó el destino.

**Dónde sí se conservan estas expresiones, y por qué.** «No se envió» sigue apareciendo al
describir `NO_ENVIADA`, y «nada se transmitió» al describir `ERROR_CONEXION`: en esos dos estados
la afirmación **es** demostrable. Y aparecen además citadas dentro de las propias prohibiciones y
en las listas que las pruebas usan para vigilarlas. Ninguna ocurrencia restante es una afirmación
sobre `TIMEOUT` ni sobre `ERROR_TRANSMISION`.

## 2026-08-20 · Rediseño de la interfaz

**Cambio de orden deliberado.** El usuario detuvo las iteraciones funcionales pendientes —los P1
de la auditoría— para mejorar primero el producto ya construido. Queda registrado porque no es
una desviación del plan sino una decisión de prioridad: la herramienta funcionaba y no se veía
como una herramienta.

**Alcance.** Solo la interfaz existente. No se tocó el núcleo transaccional, ni las cuatro
reglas, ni el transporte, ni la persistencia. Sigue siendo la misma aplicación: `0100` → TCP →
`0110`.

### Diagnóstico de partida

La interfaz anterior funcionaba y comunicaba bien los desenlaces, pero tenía cinco defectos de
producto:

1. Ochenta líneas de CSS embebidas en `base.html`, con nombres de una sola letra y sin escala.
2. La navegación era dos enlaces sueltos, sin señal de dónde está el usuario.
3. El estado se mostraba con el valor crudo del enum: `error_conexion`, no «Error de conexión».
4. El desenlace se distinguía **solo por color**. Quien no distingue rojos no podía separar un
   rechazo del autorizador de un fallo de infraestructura, que se investigan de forma distinta.
5. El resumen del resultado no traía moneda ni STAN visible en el historial, dos datos que un
   analista de QA busca primero.

### Concepto visual

Identidad propia, inspirada en el registro de una empresa de tecnología y no copiada de ningún
sitio: cinta oscura con la marca `SibuTestLab8583` y el subtítulo `Laboratorio de pruebas ISO
8583`, lienzo claro, un solo acento —teal corporativo— y numeración tabular monoespaciada para
todo lo que es dato ISO. Sobrio, no un tablero cargado.

**Lo que no se afirma.** No se consultó ningún activo de marca de SibuLabs, así que la paleta es
original y este documento **no** afirma que reproduzca sus colores. Si en algún momento se
quiere alinear con los valores corporativos reales, hacen falta los tokens de marca.

### Decisiones

**La presentación es una capa.** `web/presentacion.py` concentra las dos tablas que gobiernan la
interfaz y las plantillas no duplican ninguna: `AVISOS` (tono, señal, etiqueta, título,
explicación por estado) y `SECCIONES` (navegación). `senal` no se deriva de `tono` porque no son
biyectivos: el tono `error` lo comparten `ERROR_CONEXION` y los errores técnicos.

**Cuatro pistas por desenlace, y el color es la quinta.** Señal gráfica en SVG, rótulo corto,
título y explicación. Las señales son SVG en línea y no glifos tipográficos: así el dibujo no
depende de que la fuente del sistema tenga el carácter. Contraste medido sobre los tokens: el
peor de los siete estados es 5.89:1 y el peor par de texto 5.42:1; el mínimo AA es 4.5:1.

**«Indeterminada», no «Interrumpida».** El rótulo corto de `ERROR_TRANSMISION` dice lo que se
sabe, no lo que se supone. En una tabla, sin la explicación al lado, «interrumpida» se leería
como «no pasó nada», que es justo la lectura prohibida por la iteración anterior.

**Hoja de estilos en un archivo, no en la plantilla.** Creció lo suficiente para merecerlo. Se
sirve en `/estatico`, el navegador la cachea y las plantillas quedan solo con estructura. Todo
color, espacio, radio, sombra y tamaño sale de un token en `:root`.

**Selector de tarjeta como lista de tarjetas, no como `select`.** Un `<select>` solo muestra
texto en una línea; la especificación pedía ver `card_id`, número enmascarado y descripción a la
vez. Se usan radios con el control nativo visible: la selección no depende del fondo ni de
`:has()`, que aquí solo refuerza.

**`data-estado` en cada fila y en el aviso.** El estado exacto queda legible para una herramienta
sin depender del rótulo visible ni de una clase de estilo. Nunca transporta datos de tarjeta, y
una prueba lo comprueba recorriendo todos los atributos `data-*` de las tres pantallas.

### Corrección de una afirmación falsa propia, antes del commit

La cabecera del CSS decía «ningún bloque posterior escribe un color literal». **Era falso:**
quedaban tres —el degradado del sello, el velo del `hover` de navegación y un `#fff` en los
estilos de impresión—. En lugar de suavizar la frase se convirtieron los tres en tokens, y ahora
la afirmación es verdadera y verificable: un barrido de literales de color fuera de `:root`
devuelve ninguno. Mismo criterio que en las dos iteraciones anteriores: primero el hecho, después
la redacción.

### Lo que se corrigió gracias a medir en un navegador real

No se dieron por buenas las medidas de diseño. Con la aplicación levantada contra el host
simulado se midieron los tres anchos, y aparecieron cuatro problemas que la lectura del CSS no
habría revelado:

| Medición | Problema | Corrección |
|---|---|---|
| `.campo__pista` a 4.51:1 | Pasaba AA por dos centésimas | `--tenue` oscurecido a `#56697b` → 5.67:1 |
| Monto de 503 px de ancho | Un campo de importe ocupando media pantalla | Rejilla estrecha acotada a `minmax(150px, 220px)` |
| Navegación de 39 px en móvil | Bajo el objetivo táctil de 44 px | Relleno propio desde el corte de 860 px → 47 px |
| Tres tokens declarados sin uso | Código muerto en un archivo nuevo | Eliminados; 66 tokens, ninguno sin usar |

Evidencia end-to-end desde el navegador: una compra real por HTTP contra `sibu-host-demo`
devolvió `aprobada`, con resumen completo, isoscopio de once campos en la solicitud y siete en la
respuesta, el campo 2 marcado como enmascarado, y desbordamiento horizontal del cuerpo en cero a
375, 768 y 1280 px, con las tablas desplazándose dentro de su contenedor.

### Aserción existente que cambió, y por qué

`test_web.py::test_la_pantalla_de_compra_responde` comprobaba la cadena `"Nueva compra"`. La
pantalla pasó a llamarse `Nueva transaccion` por pedido explícito, así que la aserción se
actualizó. **Es la única de las 141 que se tocó.** Dos pruebas más habrían fallado —comprobaban
el valor crudo del estado en el historial, que ahora muestra el rótulo humano— y en lugar de
reescribirlas se añadió `data-estado`, que da un asidero estable y sirve además al producto.

### Convención de texto: ortografía plena en lo visible, ASCII en el código

Se presentó la interfaz sin tildes, siguiendo la convención previa del proyecto, y se dejó la
ortografía como decisión abierta. **El usuario la resolvió: ortografía española completa en todo
el texto visible.** Aplicada en la misma iteración, antes del commit.

**Dónde se aplicó, y por qué el alcance fue mayor que las plantillas.** El usuario pidió revisar
«todas las plantillas y los textos de `presentacion.py`», pero dos de sus ejemplos —`Número de
tarjeta` y `Código de respuesta`— no viven ahí: son descripciones de campo del perfil genérico. Y
el panel «Por qué» muestra los `motivos`, que nacen en la validación, en el catálogo y en el
transporte. Dejar esas capas en ASCII habría producido una pantalla mitad en español y mitad sin
tildes, peor que cualquiera de los dos extremos. Se siguió el texto hasta su origen:

| Origen | Qué se ve |
|---|---|
| `web/presentacion.py` | Títulos, explicaciones y rótulos de los siete desenlaces; errores de formulario |
| `web/plantillas/*.html` | Todo el texto de las tres pantallas |
| `profiles/generico.py` | Columna «Nombre» del isoscopio |
| `domain/catalogo.py` | Motivo de un rechazo: `14: Tarjeta inválida` |
| `domain/validacion.py` | Motivos de RN-1 y RN-3 |
| `adapters/transporte/tcp.py` | Motivo de un fallo de conexión o de transmisión |
| `adapters/transporte/framing_demo.py` | Motivo de un rechazo de enmarcado |
| `web/app.py` | Errores de entrada del formulario |
| `adapters/persistence/esquema.py` | Descripción de la tarjeta de demostración |

**Lo que NO se tocó, por instrucción expresa:** identificadores, enums, nombres de variables,
clases de estilo, tokens CSS, rutas y valores de `data-estado`. Siguen en ASCII, y una prueba lo
comprueba: recorre `EstadoEjecucion`, los tonos, las señales y todos los atributos `data-*` de las
tres pantallas exigiendo `isascii()`. Los docstrings y comentarios del código también se quedaron
en ASCII: no son texto visible al usuario.

**Tarjeta de demostración.** Su rótulo principal pasó de `Tarjeta sintética de demostración. No es
una tarjeta real.` a `Tarjeta de demostración`, y la aclaración de que los datos son sintéticos
bajó a una segunda línea: `Datos sintéticos para uso exclusivo con el entorno de demostración.`
No se introdujo ningún tipo `QA`: sigue existiendo únicamente la bandera `sintetica` que ya había.

**Efecto secundario que hay que conocer.** Ese rótulo vive en la base de datos y el sembrado usa
`INSERT OR IGNORE`, así que **una base creada antes de este cambio conserva el texto anterior**.
No se convirtió el sembrado en un `UPSERT` porque eso cambia la semántica de la inicialización y
está fuera de esta iteración. Para ver el rótulo nuevo hay que inicializar una base nueva.

**Cómo se ajustaron las pruebas sin debilitarlas.** A cada aserción de texto visible se le añadió
la tilde y nada más: misma cadena, misma especificidad. Las dos listas de frases prohibidas
—las que vigilan que un desenlace indeterminado no se describa como «no se envió»— **se
ampliaron** en lugar de traducirse: si solo se les hubiera puesto la tilde, la forma sin tilde
dejaría de estar vigilada y la guardia se volvería más débil justo donde importa. Ahora cubren
las dos ortografías, en una constante compartida `FRASES_PROHIBIDAS`.

**Guardia contra la regresión.** Se añadieron cinco pruebas que retiran las etiquetas del HTML y
buscan en el texto restante treinta y dos palabras que en español llevan tilde. Deliberadamente
**no** incluye `proceso`, `intento`, `término`, `espero` ni `envío`: las primeras existen sin
tilde como sustantivo o presente —«Código de proceso», «Todo intento queda registrado»— y
prohibirlas daría falsos positivos sobre texto correcto. Se comprobó que la guardia no es vacua:
detecta las cinco redacciones anteriores y no marca ninguno de los cinco casos límite
—sustantivo `proceso`, sustantivo `intento`, `SIBU_TIEMPO_LIMITE`, `data-estado="error_conexion"`
y las clases de estilo—.

### Verificación

182 pruebas en verde: las 141 anteriores más 41 nuevas de interfaz. Las nuevas vigilan contratos
—navegación, los siete desenlaces, campos del formulario, columnas del historial, ausencia de
número completo, tokens de la hoja— y **no** comprueban ningún color, medida ni clase de estilo
concreta: eso rompería en el siguiente ajuste visual sin que nada se hubiera roto de verdad.

La rueda construida desde el árbol de trabajo empaqueta `web/estatico/sibu.css` y
`web/plantillas/_piezas.html`, así que una instalación no editable también sirve la hoja.

## 2026-08-23 · Persistir los mensajes ISO sin pérdida

**Origen.** No salió de una falla en producción ni de una prueba en rojo, sino de una pregunta del
usuario durante un análisis de solo lectura: si el historial va a tener detalle navegable, ¿se
puede reconstruir el ISO de una ejecución pasada? La respuesta obligó a medir en vez de suponer.

### El defecto, medido

`ejecuciones` guardaba cada mensaje en un solo formato de texto:

```
MTI=0100 | 2=************6666 | 3=000000 | 4=<monto en 12 dígitos> | ...
```

Separador `` | ``, **sin escape**. Se comprobó la ida y vuelta con un parser obvio
(`split(" | ")` + `partition("=")`):

| Caso | Resultado |
|---|---|
| Mensaje normal | ida y vuelta **fiel**: los once campos y sus valores idénticos |
| `41 = "A=B \| C"` | recupera `41="A=B"` y **aparece un campo `C` que nunca existió** |
| `41 = "X \| Y"` | recupera `41="X"` y aparece un campo `Y` |

No es una corrupción que falle: **inventa un campo**. El campo 41 son ocho caracteres ASCII
libres, así que el valor hostil cabe de verdad. Y aunque hoy nadie puede escribirlo, la iteración
siguiente aprobada —el modo avanzado ISO 8583— lo haría editable. **Hacer el modo avanzado sobre
esta serialización habría degradado el historial**, y por eso este bloque va primero en el plan de
cinco commits.

### La decisión: no parchear el separador

Escapar el separador habría arreglado el síntoma dejando el vicio: seguir deduciendo dónde termina
un valor a partir de la forma del texto. Se añadió una representación donde **la frontera la
declara el formato**, en columnas aditivas y nullables, sin tocar la semántica de las existentes.

```json
{"version": 1, "mti": "0100", "perfil": "generico",
 "campos": {"2": {"valor": "************6666"}, "3": {"valor": "000000"}}}
```

Cuatro decisiones de forma, consultadas y aprobadas antes de escribir código:

| Decisión | Elegido | Razón |
|---|---|---|
| Clave `version` | **Sí** | Un lector futuro distingue formatos leyendo una declaración, no deduciéndolos por su forma — que es el defecto que se corrige. Y permite marcar como no interpretable una fila escrita por una versión más nueva, en vez de leerla mal |
| `crudo` en la respuesta | **Sí, cuando exista** | Es información real que el formato de texto descartaba: `como_mensaje()` proyecta solo `valor`. Habilitará la columna «Tal como viajó» del detalle histórico sin tocar el codec |
| Descripción por campo | **No persistir** | Se re-deriva del perfil al leer. `perfil` sí se guarda, así que se sabe con qué especificación se armó. Riesgo asumido y declarado: si el perfil cambia, un histórico se re-rotula con la especificación de hoy |
| Ubicación | `application/serializacion.py` | En `adapters` obligaría a la capa de lectura a depender de un adaptador; en `domain` obligaría al dominio a conocer un formato de almacenamiento. Lo necesitan dos piezas de aplicación: el orquestador al escribir y las consultas al leer |

### «Fiel» es una afirmación, y solo se hace cuando se puede demostrar

El resultado de la lectura trae una bandera `fiel`:

- **`True`** solo cuando se leyó un JSON de una versión conocida.
- **`False`** siempre que provenga del texto anterior, **incluso si parece haberse leído bien.**

Esa segunda regla es deliberada y es la misma disciplina de las iteraciones de semántica de
comunicación: `41=A` es indistinguible de un `41=A | B` truncado. No se puede *demostrar*
fidelidad, así que no se afirma. Una prueba lo fija explícitamente: un texto heredado que parsea
sin ningún problema **tampoco** se declara fiel.

Por el mismo criterio, un JSON que declare una versión desconocida **no se interpreta**. Leer una
estructura que el programa no conoce sería inventar significado; se declara y se deja
indisponible.

### Migración sin recrear la base

El proyecto no usa Alembic —para tres tablas sería sobreingeniería— y `CREATE TABLE IF NOT EXISTS`
no altera una tabla que ya existe. `inicializar()` comprueba `PRAGMA table_info` y ejecuta
`ALTER TABLE ... ADD COLUMN` solo para lo que falte.

Verificado sobre la base real que quedó de la revisión manual de la interfaz, escrita con el
código anterior:

```
ANTES :  15 columnas, 2 filas, ninguna columna _json
DESPUES: 17 columnas, 2 filas, agregadas: respuesta_json, solicitud_json
         filas conservadas: True    texto intacto: True
         solicitud_json de las filas históricas: None
TERCERA pasada: 17 columnas, 2 filas
```

**Las filas anteriores conservan `NULL`.** No se reconstruye su JSON, porque reconstruirlo sería
inventarlo: el formato de texto no permite saber si un valor quedó partido.

Se añadió también tolerancia en la lectura de la fila: `_opcional()` devuelve `None` si la columna
no existe todavía. Cubre a quien ejecute el código nuevo contra una base que no pasó por
`inicializar()`, y evita que un historial antiguo se convierta en un error del servidor.

### Límite que queda pendiente, y no se disimula

El JSON de la **solicitud no lleva `crudo` por campo**, y no es un olvido: `Codec.codificar`
devuelve `bytes` y descarta el documento codificado de `pyiso8583` (`codec.py:30`), así que ese
dato **no existe** en el flujo actual. Se decidió no rediseñar el codec para inventarlo. Una
prueba fija el límite: todos los campos de `solicitud_json` tienen `crudo is None`.

**Nunca se persisten los bytes crudos completos de un `0100`**, ni en hexadecimal. Contienen el
PAN completo, y guardarlos pondría una segunda copia del número fuera de `tarjetas_prueba`, que es
el único lugar que la política autoriza.

### Gobernanza de PAN

La barrera que ya existía se movió al módulo nuevo y ahora cubre las dos representaciones y
también el `crudo`. Es `AssertionError` a propósito: no es una condición que el usuario pueda
provocar, es un defecto de programación que debe romper la prueba en lugar de escribir un PAN
completo en la base. Cuatro pruebas lo comprueban, incluida una que recorre **todas las tablas de
la base entera** salvo `tarjetas_prueba` buscando el número completo.

### Correcciones de documentación aplicadas en la misma iteración

Al leer los documentos antes de tocar código aparecieron cinco afirmaciones falsas o
desactualizadas. Se corrigieron las cinco:

| Dónde | Qué decía | Qué dice ahora |
|---|---|---|
| `ARQUITECTURA.md` | «**Nada de lo aquí descrito está implementado.**» | Enumera los once módulos implementados y el único que falta. Contradecía directamente a `CONTEXTO.md` |
| `ARQUITECTURA.md` | `RepositorioEjecuciones` solo declaraba `guardar` | Declara `guardar → id`, `obtener(id)` y `listar(limite)`, que es el puerto real |
| `ARQUITECTURA.md` | «Esquema y columnas» e «Integración continua» seguían como decisiones abiertas | Movidas a decididas, con dónde se resolvieron |
| `CONTEXTO.md` | «Última actualización: 2026-08-19» y «177 pruebas» | Fecha y recuento reales |
| `CONTEXTO.md` | El hito P0-1 aparecía dos veces y el orden del historial estaba roto | Una sola entrada por hito, en orden |

Queda registrado porque es el mismo control que ya aparece en la sección de gobernanza: **un
documento que afirma algo que el código contradice es un defecto**, y se corrige cuando se
detecta, no cuando estorba.

### Verificación y cierre

**254 pruebas en verde**, 72 nuevas: 48 puras del formato en `test_serializacion.py` y 24 contra
SQLite real en `test_persistencia_json.py`. Ninguna prueba existente cambió: esta iteración es
aditiva, no toca RN-1 a RN-4, ni la taxonomía de siete estados, ni el codec, ni el transporte, ni
la web.

**Las pruebas nuevas se revisaron buscando debilidad, y aparecieron dos defectos propios.** El
primero era un `parametrize` que no parametrizaba: dos casos con veinte líneas de montaje distinto
en cada rama, seleccionadas por un `if` sobre una cadena. Eran dos pruebas pegadas con un
interruptor, y se separaron; al hacerlo se añadió una aserción que faltaba, que el fallo del codec
ocurre **antes** de tocar el transporte. El segundo era una parametrización de ocho casos que
replicaba, a través de SQLite, la matriz de contenidos malformados que ya cubre la prueba pura doce
veces más rápido; en esa capa lo único nuevo es el paso por el repositorio, así que quedó en cuatro
casos. Por eso el recuento bajó de 258 a 254: **se quitaron cuatro pruebas redundantes, no se
perdió ninguna comprobación.**

La fortaleza de las nuevas se midió mutando el fuente y comprobando que la suite lo detecta.
Siete mutaciones —quitar la clave `version`, declarar fiel el formato heredado, aceptar cualquier
versión de JSON, desactivar la barrera de enmascarado, dejar de persistir el `crudo`, inventar un
`crudo` de solicitud y no llamar a la migración— fueron **detectadas las siete**. Una prueba que
no falla cuando se borra lo que dice probar no prueba nada, y esta era la forma de saberlo.

**Separación de las dos iteraciones en Git.** El rediseño de la interfaz se publicó primero, por
sí solo, en el commit `ede40c0`; este commit añade únicamente la persistencia estructurada. Los
dos compartían cuatro archivos en el working tree —`esquema.py` y los tres documentos—, y hubo
que separarlos por hunks. En `esquema.py` la separación fue limpia: su cambio del rediseño era una
sola línea de ortografía, aislada en su propio hunk. En `CONTEXTO.md` **no lo fue**: tres hunks
mezclaban las dos iteraciones porque este turno sobrescribió texto que el anterior había escrito,
y el estado intermedio no existía en ningún archivo. Reconstruirlo a mano habría sido inventar un
estado que nunca se guardó, así que **la documentación completa quedó fuera del commit del
rediseño** y describe aquí el estado acumulado de las dos iteraciones. Es la decisión del usuario
entre tres opciones planteadas, y la que no exige escribir nada que no ocurrió.

El recuento de 182 pruebas que aparece más arriba, en la sección del rediseño, **no se corrigió a
254 a propósito**: era el estado real al cerrar esa iteración. Esta bitácora es acumulativa y cada
sección describe su propio momento; reescribir aquel número para que coincida con el de hoy sería
falsear el registro.

## 2026-08-23 · Dos decisiones que dejan de estar abiertas

Iteración exclusivamente documental. **No se tocó código, pruebas, esquema, comportamiento ni
interfaz.** Corrige dos afirmaciones que el propio repositorio había dejado obsoletas.

### Documentación de marca: ya existe, y los perfiles siguen sin implementarse

Hasta ahora la documentación decía que los perfiles de Visa y Mastercard estaban **bloqueados por
falta de documentos autorizados**. Eso dejó de ser cierto: el usuario suministró y aprobó como
fuente para iteraciones posteriores tres documentos de marca.

| Documento | Vigencia declarada |
|---|---|
| VisaNet Authorization-Only Online Messages — Technical Specifications | 20-abr-2026 |
| Mastercard Manual de Autorización | 16-ene-2024 |
| Mastercard MDES Technical Specifications for Dual and Single Message Systems | 4-ago-2026 |

Se registran **solo título y vigencia**, como cita de la fuente. Es lo que exige el control de
gobernanza de este proyecto —toda justificación que dependa de una norma externa debe citar la
norma— y es lo máximo que puede quedar aquí: **los manuales no se versionan y su contenido no se
copia al repositorio.**

**Lo que este registro NO afirma.** No se afirma que esos documentos cubran ningún campo, formato,
obligatorio por MTI ni catálogo concreto: **nada de su contenido se ha verificado todavía.** Lo
único que cambió es el estado del bloqueo. Los perfiles de Visa y de Mastercard **siguen sin
implementarse**, y lo que falta ahora no es documentación sino el análisis de cada documento y la
derivación de la especificación, que no se han hecho.

**Lo que sigue prohibido, sin cambios.** Inventar especificaciones de una marca. Un archivo de
perfil vacío sigue siendo preferible a uno con valores plausibles pero inventados.

**Una tensión que queda declarada a propósito.** `CLAUDE.md` condiciona implementar los perfiles a
que los documentos autorizados existan «en el proyecto». Como los manuales no se versionan, esa
condición no puede cumplirse tal como está redactada. Se reformuló en `CONTEXTO.md` y en
`ARQUITECTURA.md` —la condición pasa a ser que la documentación esté disponible y aprobada como
fuente—, pero `CLAUDE.md` se dejó intacto por decisión expresa del usuario. **Habrá que resolver
esa redacción antes de empezar la iteración de perfiles**, o la instrucción permanente bloqueará
un trabajo que los otros dos documentos declaran desbloqueado.

### DE 14, fecha de vencimiento: decisión tomada

La documentación lo dejaba como decisión abierta: «si el campo 14 debe sumarse a los campos
enmascarados». Queda decidido:

> **El DE 14 permanece visible y se persiste sin enmascarar en esta etapa, asociado a la tarjeta
> de prueba.**

Por lo tanto `CAMPOS_SENSIBLES = {"2", "35"}` es **deliberado**, y el campo 14 **no** se le añade.
El código no cambia: ya se comportaba así. Lo que cambia es que deja de estar descrito como algo
pendiente de resolver y pasa a estar descrito como lo que es, una decisión.

Es dato de tarjeta y no es el PAN. La política de tres ámbitos sigue intacta: el navegador nunca
recibe el PAN completo, las ejecuciones y los logs nunca lo guardan, y el procesamiento
transaccional sí lo usa desde `tarjetas_prueba`. Si una evolución comercial exigiera tratar la
expiración como dato sensible, sería una decisión nueva y explícita, no una corrección de esta.

### Por qué esto es una entrada de bitácora y no solo un `sed`

Las secciones históricas **no se reescribieron**. `BITACORA.md:212` sigue diciendo que el
2026-08-17 los perfiles requerían documentos autorizados, porque entonces era verdad. Esta
bitácora es acumulativa y cada sección describe su propio momento; corregir el pasado para que
coincida con el presente falsearía el registro. Lo que se corrigió fue el **estado actual**, que
vive en `CONTEXTO.md` y en `ARQUITECTURA.md`, y la decisión nueva se registra aquí, fechada.

## 2026-08-24 · Detalle navegable de una ejecución histórica

Segundo bloque del plan de cinco commits. La persistencia estructurada de la iteración
anterior existía precisamente para esto: **ahora se consume**, y el historial deja de ser una
tabla resumen para volverse navegable.

### Qué se añadió

`GET /historial/{id}` muestra una ejecución ya registrada: el desenlace, un resumen de ocho
métricas, la solicitud y la respuesta ISO campo por campo, y la representación de texto
persistida como evidencia. Desde el listado se llega con un enlace `Ver detalle` — un enlace
normal, sin JavaScript, que se puede abrir en otra pestaña con el comportamiento habitual del
navegador.

**El identificador se recibe como cadena, no como entero, y es deliberado.** Declarado `int`,
FastAPI respondería su propio 422 en JSON ante `/historial/abc` y el usuario vería un error
crudo en vez de una página del producto. Es el mismo precedente que ya documenta `web/app.py`
para los campos del formulario. Convirtiéndolo en la ruta, los dos casos —no numérico e
inexistente— caen en la misma respuesta 404 con HTML propio: «Ejecución no encontrada».

### De dónde salen los campos

De `application/serializacion.py`, sin reimplementar nada: JSON estructurado cuando existe,
representación de texto anterior como respaldo, resultado indisponible si no hay nada. **La web
no interpreta y la plantilla tampoco.** El servicio de consultas devuelve un `DetalleEjecucion`
con los dos mensajes ya leídos, y la presentación los convierte en filas.

**La representación histórica no se declara fiel, y eso se ve en pantalla.** Cuando una fila
proviene del formato anterior, la página lo dice una vez, antes de las tablas:

> Esta ejecución fue registrada con el formato anterior. Los campos mostrados se recuperaron de
> la representación textual y no puede garantizarse una reconstrucción exacta.

No se afirma que haya habido corrupción —eso no se sabe— sino únicamente que la fidelidad no se
puede demostrar. Una prueba vigila esa distinción buscando palabras como «corrupto» o «se
perdió». Es la misma disciplina de las iteraciones de semántica de comunicación: no afirmar lo
que no se puede demostrar.

Los nombres de campo se re-derivan del perfil activo. Un número que el perfil de hoy no conozca
sale como `Campo 63`: no se inventa una descripción ni se rompe la página. Ningún detalle de
`pyiso8583` cruza a la plantilla.

### Reutilización: un componente, dos pantallas

El isoscopio vivía dentro de `resultado.html`. Al aparecer el segundo consumidor se movió a
`_piezas.html`, y con él se extrajeron otros dos bloques. La regla que se siguió fue estricta:
**se extrae solo lo que ya tiene dos consumidores reales**, no lo que podría tenerlos.

| Macro | Consumidores | Qué evita duplicar |
|---|---|---|
| `isoscopio` | resultado, detalle | La tabla ISO completa, unas 40 líneas |
| `estado` | resultado, detalle, transacción | El banner de desenlace |
| `resumen` | resultado, detalle | Las ocho métricas |

`resultado.html` bajó de 108 a 47 líneas y **no cambió de aspecto**. Nada más se extrajo: la
cabecera de panel es una línea y envolverla habría sido convertir la plantilla en un framework
de componentes. El bloque de error de entrada de la pantalla de transacción se quedó como
estaba porque su título es fijo y no proviene de un `Aviso`: no es la misma pieza.

El macro `resumen` recibe el destino como texto y nota en vez de derivarlo de la ejecución,
porque el resultado inmediato muestra el destino **solicitado** y el detalle el **persistido**.
Son dos fuentes distintas y las dos son correctas en su pantalla.

### Ejecuciones sin respuesta

`NO_ENVIADA`, `ERROR_CONEXION`, `ERROR_TRANSMISION` y `TIMEOUT` no muestran una tabla vacía que
parezca una respuesta que no existió. Muestran el título y la explicación de `AVISOS`, que ya
están redactados para no afirmar lo indemostrable, más una nota de que **el motivo concreto de
aquella ejecución no se conserva**: no se persiste, y la página no finge conocerlo.

La decisión de si hubo respuesta se toma por el MTI persistido y no por el número de campos
recuperados, para no confundir «no hubo respuesta» con «la representación no se pudo leer».

### Límite que no se disimula

El JSON de la respuesta lleva `crudo` por campo y la columna «Tal como viajó» aparece cuando
existe. El de la solicitud no lo lleva, porque el codec devuelve bytes y descarta el documento
codificado: ese dato **no existe** en el flujo actual. La columna no se finge, y tampoco
aparece en una fila histórica leída del texto. Tres pruebas fijan las tres situaciones.

### Revisión visual humana antes del commit

El bloque **no se dio por terminado con las pruebas en verde**. Se levantaron el host simulado y
la aplicación web, se generaron ejecuciones reales y el usuario revisó la interfaz en el
navegador antes de autorizar el commit. Se revisaron cuatro casos:

| Caso | Qué se comprobó |
|---|---|
| **Ejecución nueva**, con JSON | Sin aviso histórico; la respuesta muestra «Tal como viajó» |
| **Ejecución histórica**, ambas columnas JSON en `NULL` | Un solo aviso histórico; sin «Tal como viajó»; no se finge información |
| **Sin respuesta** (error de conexión) | Sin tabla de respuesta; se explica el desenlace |
| **404** | Página del producto, no el JSON por defecto de FastAPI |

De esa revisión salió una ronda de limpieza visual, también antes del commit: el aviso histórico
pasó de repetirse debajo de cada tabla a aparecer **una sola vez antes de ambas**; la columna de
acciones del historial recibió encabezado; el importe y su código de moneda dejaron de leerse
como un solo número; y la representación persistida pasó a un `<details>` nativo, cerrado por
defecto, que se abre sin JavaScript y sin perder información.

**La interfaz sigue sin ejecutar JavaScript.** Cero guiones en las cinco pantallas.

### Un hallazgo del entorno, no del código

Durante la revisión aparecieron ejecuciones con destino `127.0.0.1:8583` que no correspondían a
ninguna de las creadas para la demostración. La causa resultó ser de entorno y no un defecto:
`8583` es el puerto por defecto del proyecto, y existía una base en la ruta por defecto
—`sibutestlab8583.db`, no versionada— con ejecuciones de un servidor levantado sin
`SIBU_DB_PATH` ni `SIBU_PUERTO_DESTINO`. Esa base todavía tiene el esquema de quince columnas,
anterior a la migración. **Se comprobó que se lee sin error**: `_opcional()` devuelve `None`
para las columnas ausentes y el detalle la presenta como histórica, que es exactamente para lo
que se escribió esa tolerancia. No se modificó esa base ni se cambió ninguna configuración.

### Verificación

**299 pruebas en verde**, 45 nuevas: 43 del detalle en `test_detalle_historial.py` y dos
pantallas más en las guardias existentes. La ruta nueva y la de 404 entraron en `PANTALLAS`, que
pasó a ser la fuente única: agregar una pantalla la mete de golpe en todas las guardias
parametrizadas —ortografía, identidad, ausencia de PAN, ausencia de JavaScript, estructura— y
una aserción impide que las dos listas se desincronicen.

La fortaleza de las nuevas se midió mutando el código: siete mutaciones —declarar el
identificador como entero, usar `HTTPException` en vez de la página propia, mostrar la tabla de
respuesta siempre, inventar un nombre para un campo desconocido, ignorar el JSON, quitar el
aviso histórico y no mostrar nunca la columna transmitida— fueron **detectadas las siete**.

Dos de esas mutaciones destaparon defectos propios que se corrigieron antes de continuar.
**Nada comprobaba que la columna «Tal como viajó» apareciera**, que era justamente para lo que
se persistió `crudo` en la iteración anterior; y la guardia de frases prohibidas para `TIMEOUT`
era demasiado burda y fallaba contra la negación correcta, así que se sustituyó por un contrato
más fuerte: la página debe reutilizar el texto de `AVISOS` tal cual, sin escribir su propia
explicación.

Sin cambios en el esquema, la persistencia, el codec, las cuatro reglas de negocio ni la
taxonomía de siete estados. Comprobado por hash de blob contra el commit anterior.

## 2026-08-24 · D-1: RN-1 pasa a usar el catálogo persistido

Primer sub-bloque de la Fase 1 (módulo de Configuración). Cierra una deuda técnica detectada en
la auditoría previa, sin tocar esquema ni interfaz.

### La causa raíz

`codigos_respuesta` ya existía en el esquema SQLite, con su semilla de seis códigos y su clave
primaria `(catalogo, codigo)` lista para varios catálogos. `RepositorioCatalogosSQLite` ya
existía y ya funcionaba: sabía leer esa tabla y devolver un `CatalogoDeRespuestas`. Pero **nada
en producción lo instanciaba**. `Composicion.__init__` fijaba `self._catalogo =
CATALOGO_GENERICO` — la constante en memoria de `domain/catalogo.py` — una sola vez, al construir
la composición, y `Composicion.orquestador()` era síncrono. El único consumidor real de
`RepositorioCatalogosSQLite` era `tests/test_persistencia.py`. Editar la tabla `codigos_respuesta`
no tenía ningún efecto sobre RN-1: la base y el código en ejecución estaban desconectados.

### Lo que se hizo

- `Composicion` instancia `RepositorioCatalogosSQLite` junto con los demás repositorios.
- `Composicion.orquestador()` pasa a `async def` y **consulta el catálogo en cada llamada**,
  vía `self._catalogos.catalogo_respuestas(self.configuracion.catalogo_activo)`, en vez de
  leerlo una sola vez al construir la composición. Es la condición explícita de esta iteración:
  editar `codigos_respuesta` en SQLite debe reflejarse sin reiniciar la aplicación, y cachear el
  catálogo en `__init__` habría reproducido el mismo defecto en otra forma.
- `Configuracion` (la clase real donde ya viven `host_destino`, `puerto_destino` y
  `tiempo_limite`, en `composicion.py`) gana el campo `catalogo_activo: str`, con valor por
  defecto el catálogo genérico y lectura desde la variable de entorno `SIBU_CATALOGO`.
- `CATALOGO_GENERICO` **queda solo como semilla** de `inicializar()` (`esquema.py`), tal como ya
  era: no se convirtió en fuente activa en ningún punto de este cambio.
- Único punto de llamada en producción actualizado: `web/app.py`, dentro de `ejecutar_compra`,
  pasa de `composicion.orquestador(destino).ejecutar_compra(datos)` a `await
  composicion.orquestador(destino)` seguido de `await orquestador.ejecutar_compra(datos)`.
- El doble de prueba `ComposicionFalsa` en `tests/test_web.py` (reutilizado también por
  `tests/test_web_interfaz.py`) se ajustó a la misma firma asíncrona.
- `tests/conftest.py` **no se tocó**: `construir_orquestador` sigue construyendo el `Orquestador`
  directamente con `CATALOGO_GENERICO`, sin pasar por `Composicion` — es un doble deliberado para
  las pruebas de reglas de negocio, no el camino de producción, y no formaba parte de la deuda.

### Lo que no cambió

RN-3 se sigue evaluando **antes** que RN-1 dentro de `Orquestador.ejecutar_compra`: el orden no
se tocó, porque no era el defecto. `RepositorioCatalogos` (el puerto) y `Orquestador` (el
constructor recibe `catalogo` como antes) tampoco cambiaron: el contrato existente alcanzaba. Sin
cambios de esquema — `codigos_respuesta` ya tenía todo lo necesario — y sin interfaz nueva.

### Prueba crítica

`tests/test_catalogo_persistido.py`, nueva. Construye una base SQLite real y temporal,
la inicializa con `inicializar()`, edita el catálogo persistido con una sentencia `UPDATE`
directa sobre `codigos_respuesta`, y ejecuta la compra completa contra un `HostSimulado` real por
TCP, construyendo el sistema con la `Composicion` real (no con `construir_orquestador`, que
seguiría usando la constante a propósito). Comprueba las dos direcciones:

- `00` marcado como rechazado en la base → el host responde `00` → RN-3 es válida → RN-1 clasifica
  **RECHAZADA**.
- `51` (normalmente rechazado) marcado como aprobado en la base → **APROBADA**.
- Una tercera prueba comprueba que, sin editar nada, la semilla actual se sigue comportando igual
  que antes: `00` aprueba, `05` rechaza.

**No vacuidad, comprobada por mutación.** Con `composicion.py` revertido temporalmente a la
versión anterior a este cambio (vía `git stash`, restaurado de inmediato), las tres pruebas
nuevas fallan con `TypeError: object Orquestador can't be used in 'await' expression` — la firma
síncrona anterior no soporta el `await` que ahora usa el punto de llamada. Confirma que la prueba
mide lo que dice medir y no pasaría contra la implementación anterior.

### Verificación

**302 pruebas en verde**, 3 nuevas (299 + 3). RN-1/RN-3 (`test_reglas_negocio.py`,
`test_catalogo.py`, `test_catalogo_persistido.py`, 37 pruebas) y la guardia de PAN
(`test_datos_sinteticos.py`, 10 pruebas) verificadas aparte. Sin secuencias de 12 a 19 dígitos ni
patrones de secreto en los archivos tocados. El cambio real quedó limitado a cuatro archivos:
`composicion.py`, `web/app.py`, `tests/test_web.py` y el archivo nuevo de la prueba crítica.

## 2026-08-24 · Fase 1, sub-bloque 2: persistencia base para tarjetas y destinos

Segundo sub-bloque de la Fase 1 (módulo de Configuración). Solo persistencia: esquema, dominio,
puerto y adaptador. **Sin esquema propuesto sin implementar, sin interfaz.** No existe todavía
`/configuracion`, ni formularios, ni filtro de tarjetas activas en la compra, ni selector de
destino, ni administración desde la web.

### `tarjetas_prueba.activa`

Columna `activa INTEGER NOT NULL DEFAULT 1` agregada al esquema, y consumida de inmediato en el
dominio y el adaptador — no se dejó como columna huérfana para un sub-bloque posterior, porque el
usuario corrigió explícitamente esa intención a mitad de la iteración. `TarjetaPrueba` gana el
campo `activa: bool = True`, colocado después de `sintetica` para que ningún constructor existente
se rompa: todo el repositorio construye `TarjetaPrueba` por palabra clave, nunca posicional.
`RepositorioTarjetasSQLite.obtener()` y `.listar()` seleccionan la columna nueva; `.guardar()` la
inserta y el `ON CONFLICT ... DO UPDATE` la actualiza, de modo que volver a guardar una tarjeta
existente puede reactivarla o desactivarla. El puerto `RepositorioTarjetas` no ganó ningún método:
`guardar()` ya alcanzaba. **Todavía no se filtra ninguna tarjeta inactiva en ningún flujo**: eso
pertenece a la integración con la compra, fuera de este sub-bloque.

### Tabla `destinos` y `DestinoGuardado`

Tabla nueva, sembrada con un único destino `LOCAL-DEMO` (`127.0.0.1:8583` — mismo valor que
`composicion.PUERTO_POR_DEFECTO`; `esquema.py` no importa `composicion.py` para evitar un ciclo,
así que el valor se repite a propósito, con esa nota en el propio código). `DestinoGuardado` es
la entidad administrada nueva en `domain/modelos.py`: identificador propio, nombre, host, puerto
y estado activo/inactivo, con un método `a_destino_tcp()` que la proyecta al valor mínimo que el
transporte necesita. **`DestinoTcp` no se tocó**: sigue siendo exactamente lo que era, y sigue
siendo lo que efectivamente viaja al transporte.

**Por qué una ejecución no referencia `destinos` por clave foránea.** `Ejecucion.destino_host` y
`destino_puerto` ya eran, desde antes de este sub-bloque, valores propios de la fila y no una
referencia a ninguna tabla de destinos —porque esa tabla no existía—. Al crearla ahora, se
mantuvo la misma decisión a propósito: una ejecución debe conservar contra qué host y puerto
corrió aunque el destino se edite o se desactive después. Acoplarla con una FK habría hecho que
editar `destinos` reescribiera silenciosamente el historial. `RepositorioDestinos` (el puerto,
en `domain/puertos.py`) y `RepositorioDestinosSQLite` (el adaptador, en `sqlite_repos.py`) siguen
el mismo patrón que ya existía para tarjetas: `obtener`, `listar`, `guardar` como upsert.

### Migración generalizada

`_migrar_ejecuciones(conexion)` —de la iteración de persistencia estructurada— se generalizó en
`_migrar(conexion, tabla, columnas)`, capaz de agregar columnas a cualquier tabla existente.
`_migrar_ejecuciones` se conservó como envoltorio delgado sobre la función genérica, porque
`tests/test_persistencia_json.py:62-67` la llama directamente por su nombre: generalizar no debía
obligar a tocar una prueba que no tenía nada que ver con este sub-bloque. Una prueba nueva
comprueba que `_migrar` funciona igual sobre una tercera tabla que no es ni `ejecuciones` ni
`tarjetas_prueba`, para que quede demostrado que ya no está atada a ninguna de las dos.

### La prueba de compatibilidad, completada tras una corrección del usuario

La primera versión de la prueba de migración cubría solo `tarjetas_prueba.activa` de forma
aislada. El usuario pidió el criterio completo: una base anterior real, con tarjeta, ejecución,
secuencia STAN y el esquema anterior de `ejecuciones` **a la vez**, y una comprobación explícita
de cada uno de ocho puntos. `test_compatibilidad_completa_de_una_base_anterior_real`
(`tests/test_migracion_generalizada.py`) reconstruye esa base completa —sin `activa`, sin
`destinos`, sin las columnas JSON de `ejecuciones`— con una tarjeta, una ejecución que la
referencia (monto, moneda, STAN, destino, mensajes enmascarados y latencia reales, no inventados)
y una secuencia `stan` ya avanzada a `123`. Tras `inicializar()`, comprueba explícitamente: que
`activa` existe, que la tarjeta anterior queda `activa = 1`, que aparece `destinos` con
exactamente una semilla `LOCAL-DEMO`, que la ejecución conserva **fila completa por fila
completa** sus valores (comparando el `dict` entero de la fila, no solo algunas columnas), que la
secuencia STAN sigue en `123`, y que las columnas JSON se agregan sin inventar contenido —quedan
en `NULL`, porque reconstruirlas sería inventar datos históricos—. Repite la comprobación después
de una segunda `inicializar()`: ningún valor cambia y `LOCAL-DEMO` no se duplica.

**No vacuidad, comprobada por mutación sin usar `git stash`.** Se comentó temporalmente, con una
edición directa, la línea `await _migrar(conexion, "tarjetas_prueba", COLUMNAS_AGREGADAS_TARJETAS)`
dentro de `inicializar()`; se corrieron las pruebas de migración y **tres fallaron**, incluida la
de compatibilidad completa; se restauró la línea de inmediato. Confirma que las pruebas miden lo
que dicen medir.

### Verificación

**319 pruebas en verde** (302 + 17: 8 de `tests/test_destinos.py`, 5 de
`tests/test_migracion_generalizada.py`, 4 de `activa` en `tests/test_persistencia.py`). RN-1 a
RN-4, STAN y persistencia JSON verificados aparte, sin regresiones. Guardia de PAN en verde. Sin
secuencias de 12 a 19 dígitos ni patrones de secreto en los siete archivos tocados. El cambio real
quedó limitado a `domain/modelos.py`, `domain/puertos.py`,
`adapters/persistence/esquema.py`, `adapters/persistence/sqlite_repos.py`, `tests/test_persistencia.py`,
y los dos archivos nuevos de prueba.

## 2026-08-25 · Fase 1, sub-bloque 3/4: Configuración y administración de tarjetas

Iteración visual combinada: la portada del módulo de Configuración y la administración completa
de tarjetas de prueba (crear, editar, activar/desactivar), sobre la persistencia que ya dejó el
sub-bloque 2.

### Navegación y portada

`Configuración` se agregó como tercera entrada de `presentacion.SECCIONES` (junto a `Nueva
transacción` e `Historial`), la misma fuente única que ya recorre `base.html`: no hay ninguna
lista de navegación duplicada. `GET /configuracion` muestra tres bloques — Tarjetas de prueba,
Códigos de respuesta y Destinos —, pero **solo el primero enlaza a algo real**: Códigos y Destinos
siguen marcados «Próximamente» y no enlazan a ninguna ruta, porque esas rutas no existen todavía.

### Administración de tarjetas

Nuevo servicio de aplicación, `ServicioTarjetas` (`application/tarjetas.py`), construido solo con
el puerto `RepositorioTarjetas` — que no necesitó ningún método nuevo: `guardar()`, ya un upsert
desde el sub-bloque 2, alcanza para crear, editar y cambiar el estado. La web no valida PAN ni
Luhn: delega esa validación en el servicio y solo se ocupa de leer el formulario y renderizar HTML.

Rutas nuevas, todas bajo `/configuracion/tarjetas`: listado, formulario de creación, creación,
formulario de edición, edición, y `POST .../{card_id}/estado` para activar o desactivar.

- **`card_id`** es requerido, y su familia de caracteres (`[A-Za-z0-9_-]`) reutiliza la que ya
  seguían los identificadores existentes del proyecto (`DEMO-0001`, `T-002`, `SIN-VENC`) — no es
  una regla nueva. **Es inmutable tras crear**: en el formulario de edición no es un campo de
  formulario, solo texto de solo lectura; viaja en la ruta, no en el cuerpo del `POST`. Una
  revisión posterior pidió justificar o eliminar un límite de 40 caracteres que se había agregado
  junto con esa regla: no existía ningún precedente de ese número en el proyecto —ni en los
  documentos, ni en el esquema SQLite (`card_id TEXT PRIMARY KEY`, sin longitud), ni en ninguna
  otra constante de largo del código, todas ancladas a un campo ISO real o a una restricción
  técnica— así que **se eliminó** en vez de inventarle una justificación.
- **Activar/desactivar** usa `TarjetaPrueba.activa` (del sub-bloque 2). Desactivar no borra la
  fila, no toca el PAN ni ninguna ejecución que referencie la tarjeta: se comprobó comparando una
  ejecución real, campo por campo, antes y después de desactivar la tarjeta que usó. Activar
  vuelve a dejarla disponible. **`POST .../estado` valida estrictamente su entrada**: solo acepta
  `"0"` o `"1"` (`presentacion.validar_activa`); cualquier otro valor —incluidos intentos de
  manipular el formulario— se rechaza con un error HTML propio (400), en vez de convertirse
  silenciosamente en `False`. Este bloque no filtra tarjetas inactivas en la pantalla de compra:
  esa integración pertenece a un sub-bloque posterior y no se adelantó.

### Política de PAN en la pantalla administrativa

El PAN completo **solo** se recibe en este formulario, y solo por `POST` (nunca en la URL ni en
query string). `TarjetaAdministrada` —lo único que la web puede ver— no tiene ningún campo para
el PAN completo, igual que `TarjetaListada` en `consultas.py`; solo trae `pan_enmascarado`. Un
error de validación nunca repuebla el campo del PAN recibido, ni el que ya existía: se comprobó
explícitamente que ni el HTML de éxito ni el de error contienen el número. El pie de página global
(`base.html`) afirmaba antes que «la interfaz no recibe el número completo en ningún momento»,
lo cual dejó de ser cierto con esta pantalla; se corrigió para decir la excepción exacta que
`CLAUDE.md` ya definía: fuera de la pantalla de mantenimiento, nunca.

- **PAN que falla Luhn** → `sintetica = True`, sin fricción.
- **PAN que pasa Luhn** → exige la casilla de confirmación QA; sin marcarla, se rechaza sin
  repetir el número en el mensaje.
- **Edición con «Nuevo PAN» vacío** → conserva el PAN y el tipo (`sintetica`) actuales.
- **Edición con un PAN nuevo** → aplica la misma validación que crear y recalcula el tipo.

### Flujo y errores

Tras crear, editar o cambiar el estado con éxito: `redirect` HTTP 303 a `/configuracion/tarjetas`
— decisión nueva en este proyecto (el resto de las pantallas renderiza el resultado directamente),
adoptada para evitar reenvíos duplicados de un formulario administrativo; aprobada explícitamente
antes de implementar. Todo error de validación re-renderiza el formulario o el listado con un
banner de error igual al que ya usa `compra.html`: nunca traceback, SQL, ni el 422 en JSON por
defecto de FastAPI. Una tarjeta inexistente en editar o en `/estado` responde 404 con
`no_encontrado.html`, la misma plantilla que ya usaba `/historial/{id}`. Cero JavaScript.

### Verificación

**380 pruebas en verde.** Reconciliado el crecimiento desde las 319 previas: +1 por el crecimiento
de `SECCIONES` (parametrización existente), +1 por una entrada agregada a mano a la prueba de
sección activa, +4 por el crecimiento de `PANTALLAS` de 5 a 9 pantallas, +27 pruebas nuevas de
`test_tarjetas_administracion.py`, +22 de `test_web_configuracion.py`, +6 de la prueba paramétrica
de valores manipulados en `/estado` agregada en la revisión final. RN-1 a RN-4, guardia de PAN y
ausencia de secretos verificados aparte, sin regresiones. El cambio real quedó limitado a trece
archivos: `composicion.py`, `web/app.py`, `web/presentacion.py`, `web/estatico/sibu.css`,
`web/plantillas/base.html`, `tests/test_web.py`, `tests/test_web_interfaz.py` (modificados), y
`application/tarjetas.py`, las tres plantillas de Configuración, y `tests/test_tarjetas_administracion.py`
más `tests/test_web_configuracion.py` (nuevos).

## 2026-08-25 · Fase 1, sub-bloque 5: modelo extendido y persistencia de tarjetas

Precedido por una auditoría técnica de solo lectura del modelo de tarjeta actual (sin cambios de
código), que confirmó que hoy solo existen PAN y expiración como datos transaccionales, que DE35
(Track 2) ya estaba reservado en `CAMPOS_SENSIBLES` sin implementarse nunca, y que Service
Code/Discretionary Data no son DE independientes sino subcampos posicionales de Track1/Track2. La
auditoría se aprobó con una corrección de diseño: no persistir Track1/Track2 completos ni sus
overrides, para no crear una segunda fuente de verdad del PAN.

### Modelo de dominio

`TarjetaPrueba` gana ocho campos de laboratorio, todos `str = ""`: `titular`, `service_code`,
`discretionary_data`, `cvv`, `cvv2`, `icvv`, `card_sequence_number`, `pin_block_laboratorio`.
Ningún constructor existente se rompe: el repositorio entero construye `TarjetaPrueba` por
palabra clave. **`track1`, `track2` y sus overrides no se agregaron**: se derivarán más adelante
desde PAN + titular + expiración + service code + discretionary data, en un sub-bloque posterior,
sin persistirse como estado normal de la tarjeta. **El PIN en claro no se modela en ningún
campo**, ni aquí ni en ningún otro lugar del sistema. `pin_block_laboratorio` es un valor con
forma de PIN Block —para pruebas de laboratorio—, nunca un PIN Block criptográficamente válido:
el proyecto no tiene ninguna clave de cifrado detrás. **El PAN completo sigue teniendo una única
fuente persistente: `tarjetas_prueba.pan`.**

### Esquema y migración

Ocho columnas nuevas en `tarjetas_prueba`, todas `TEXT NOT NULL DEFAULT ''`, agregadas al mismo
`CREATE TABLE` (bases nuevas) y a la misma tupla `COLUMNAS_AGREGADAS_TARJETAS` que ya migraba
`activa` (bases existentes) — sin recrear la tabla, sin copiar filas, sin backfill inventado.
Bases anteriores reciben `''` en las ocho columnas nuevas; ninguna otra columna se toca.
`inicializar()` sigue siendo idempotente.

**Prueba de compatibilidad completa:** `test_compatibilidad_con_esquema_anterior_a_las_columnas_de_laboratorio`
reconstruye el esquema exacto de justo antes de este sub-bloque —tarjeta, ejecución histórica,
secuencia STAN y dos destinos ya sembrados— y comprueba los doce puntos exigidos (columnas
nuevas presentes, valores `''` para la fila anterior, PAN/máscara/expiración/descripción/
sintética/activa idénticos, ejecución idéntica, STAN idéntico, destinos idénticos, sin filas
duplicadas), antes y después de una segunda `inicializar()`. **No vacuidad comprobada por
mutación** (se comentaron las ocho columnas en `COLUMNAS_AGREGADAS_TARJETAS`, la prueba falló, se
restauró el código), sin usar `git stash`. Al escribirla se detectó y corrigió un defecto propio:
la lista de columnas esperadas en la prueba se derivaba inicialmente de la misma constante de
producción que la prueba debía vigilar, así que una mutación de esa constante no se detectaba a
sí misma; se reescribió como una lista independiente, literal, en el archivo de prueba.

### `RepositorioTarjetasSQLite`

`obtener()`, `listar()` y `guardar()` (INSERT y `ON CONFLICT ... DO UPDATE`) leen, listan y
persisten los ocho campos nuevos; `_a_tarjeta()` los construye. **El puerto `RepositorioTarjetas`
no cambió**: `guardar()` ya era un upsert y alcanzaba.

### Explícitamente fuera de este sub-bloque

`application/tarjetas.py`, `ServicioTarjetas` y `TarjetaAdministrada` no se tocaron: la capa de
aplicación y la interfaz todavía no exponen estos campos. `profiles/generico.py` y `armado.py`
no cambiaron: ningún campo nuevo viaja en el mensaje ISO. No se agregó ninguna validación de
negocio para los ocho campos —longitud, formato— ni se tocó la política de tarjeta sintética
frente a QA autorizada: quedan para el bloque que decida cómo exponerlos y validarlos.

### Verificación

**385 pruebas en verde** (380 + 5: 1 en `test_migracion_generalizada.py`, 4 en
`test_persistencia.py`). Una revisión posterior corrigió un error de redacción propio que había
reportado «10 pruebas nuevas» sin que el desglose lo respaldara; se reconcilió contando con
`pytest --collect-only` en ambos archivos, confirmando el 5. RN-1 a RN-4, STAN y persistencia
JSON verificados aparte, sin regresiones. Guardia de PAN en verde. Sin PIN en claro ni patrones
de secreto en los cinco archivos tocados: `domain/modelos.py`, `adapters/persistence/esquema.py`,
`adapters/persistence/sqlite_repos.py`, `tests/test_migracion_generalizada.py`,
`tests/test_persistencia.py`.

## 2026-08-26 · Fase 1, sub-bloque 6: derivación pura de Track 1 y Track 2

Sexto sub-bloque de la Fase 1. Nuevo módulo `domain/tracks.py`: dos funciones puras —sin
I/O, sin persistencia, sin conocer SQLite ni web— que derivan la representación lógica de
Track 1 y Track 2 a partir de PAN, titular, expiración, service code y discretionary data.

**Formato adoptado, propio de SibuTestLab y no un volcado byte a byte de la pista física:**

```
Track 1:  B{PAN}^{TITULAR}^{YYMM}{SERVICE_CODE}{DISCRETIONARY_DATA}
Track 2:  {PAN}={YYMM}{SERVICE_CODE}{DISCRETIONARY_DATA}
```

Ninguna de las dos incluye los sentinels físicos (`%`, `;`, `?`) ni el LRC: son artefactos
de la codificación física de la pista, no contenido lógico. **Los límites de 76 caracteres
para Track 1 y 37 para Track 2 son los límites adoptados por SibuTestLab para su
representación lógica, conforme al diseño aprobado en este sub-bloque. Esta implementación
no pretende reproducir byte a byte una pista física.**

**Explícitamente fuera de este sub-bloque.** Ninguna otra parte del proyecto invoca todavía
estas funciones: `profiles/generico.py` sigue sin DE35 ni DE45, el codec no las codifica, y
no viajan en ningún `0100` real. **Track 1 y Track 2 no son, en este estado, una
funcionalidad de red**: es derivación de dominio, pura y probada, a la espera de que un
sub-bloque futuro decida cómo —y si— se exponen en el mensaje ISO. Tampoco deciden política
de PAN, Luhn ni sintética/QA: eso sigue viviendo, sin cambios, en `application/tarjetas.py`.

**Pruebas:** `tests/test_tracks.py`, 51 pruebas nuevas. **Suite: 385 → 436 pruebas en
verde.**

**Commit:** `725d316`.

## 2026-08-26 · Decisión de congelar el crecimiento funcional

**Qué se decidió.** Se auditó la consigna completa de `PROYECTO.md` y se decidió priorizar
los entregables académicos pendientes sobre seguir añadiendo funcionalidad nueva. El motor
de carga queda fuera de la entrega actual.

**Qué no significa esta decisión.** El motor de carga **no se elimina del horizonte del
proyecto**: se repriorizó como capacidad futura, no se descartó. `PROYECTO.md` no se
modificó por esta decisión: sigue siendo la fuente autoritativa de alcance, y el motor de
carga sigue apareciendo ahí como parte del horizonte del proyecto. Lo que cambió es el orden
de trabajo, no el alcance aprobado.

## 2026-09-03 · Reproducibilidad: `README.md` y `demo.cmd`

Se agregan `README.md` y `demo.cmd` para que un clon limpio del repositorio pueda instalarse
y arrancar en Windows sin depender de instrucciones sueltas ni de memoria operativa.
`demo.cmd` reutiliza exactamente los mismos comandos que documenta `README.md` —no es una
vía de instalación alternativa—: detección pasiva de un intérprete `python` compatible
(`>= 3.13`), creación o validación de `.venv`, instalación idempotente
(`pip install -e ".[dev]"`), inicialización de SQLite (`sibu-init-db`), arranque del host
ISO8583 simulado y de `uvicorn`, espera activa a que la web responda, y apertura del
navegador.

### Hallazgo de gobernanza: `py -3.13 --version` no era de solo lectura

Se asumió inicialmente que consultar la versión de un intérprete con
`py -3.13 --version` era una operación de solo lectura, sin efecto sobre el sistema. En una
instalación nueva de Python en esta misma máquina, esa consulta **disparó la descarga e
instalación de Python 3.13** como efecto lateral de solo preguntar por una versión. El
estudiante detectó el efecto no esperado.

**Corrección aplicada.** Se retiró del camino de arranque de la demostración toda
dependencia operativa del launcher `py`. `demo.cmd` exige en su lugar el comando `python`
disponible en `PATH` y verifica compatibilidad consultando
`sys.version_info` **dentro del propio intérprete**, sin invocar ningún mecanismo capaz de
provocar una instalación.

**Aprendizaje.** No es lo mismo el comportamiento observado de una herramienta externa —el
launcher `py`, con un efecto lateral no anticipado— que una decisión propia del proyecto. La
corrección no es una preferencia de estilo: es la eliminación de una dependencia que puede
modificar el entorno del usuario sin que este lo pida.

### Inconsistencia de validación de `.venv` y Python 3.14

La primera versión de `demo.cmd` trató `3.13` como versión exacta al validar un `.venv`
existente. Al revisar `pyproject.toml` se confirmó que el requisito real, ya declarado, es
`>=3.13`. Se corrigió la validación del `.venv` para aceptar cualquier Python `>= 3.13`
—incluido Python 3.14—, consistente con lo que el propio `pyproject.toml` ya exigía. Se
incluye aquí, en la misma entrada, por ser el mismo aprendizaje de fondo que el hallazgo
anterior: no dar por buena una suposición sobre el entorno sin comprobarla contra la fuente
que ya la declara.

### Bugs menores de `cmd.exe`

Durante la escritura de `demo.cmd` aparecieron dos archivos espurios en el directorio de
trabajo: uno llamado `App`, producido por una reinterpretación de `>` como redirección en
vez de literal, y otro llamado `3.13)`, producido por otro escape incorrecto en un `echo`.
Ambos se detectaron y se corrigieron en el propio archivo. Quedan registrados como defectos
menores de sintaxis de `cmd.exe`, no como incidentes de gobernanza.

### CRLF

Se ajustó `.gitattributes` con `*.cmd text eol=crlf` para preservar en Windows el formato
con el que `demo.cmd` fue validado de forma satisfactoria. Se comprobó el checkout byte a
byte con CRLF. Git puede mantener una representación normalizada internamente; el control
relevante para esta entrega es el archivo resultante en el checkout de Windows.

### Prueba real en una computadora distinta

Un `.venv` copiado directamente desde otro equipo resultó inválido: conservaba una
referencia al Python base de la máquina de origen. Se reconstruyó correctamente en la
máquina nueva, y `demo.cmd` funcionó de punta a punta con Python 3.14.7. Recorrido manual
completo: compra aprobada, historial, detalle de una ejecución, configuración y
administración de tarjetas. Suite: **436 passed**. Guardia de PAN: en verde.

### Prueba definitiva de clon limpio

Sobre un clon separado del repositorio —sin `.venv` previo, sin base SQLite previa, sobre el
`HEAD` ya publicado, con `demo.cmd` llegando en CRLF— se ejecutó la instalación desde cero:
recorrido manual completo, **436 passed** en la suite completa, RN-1 a RN-4 verificadas
aparte con **29 passed**, guardia de PAN en `passed`, working tree limpio al terminar, y los
archivos generados por la ejecución (base SQLite, entorno virtual) correctamente ignorados
por Git. Ningún paso del README resultó ambiguo al seguirlo desde cero.

**Commit:** `633be24`.

## 2026-09-03 · Skill de Claude Code `levantar-demo`

Se crea `.claude/skills/levantar-demo/SKILL.md`: un skill que orquesta el arranque de la
demostración reutilizando `demo.cmd` como única fuente de verdad —no reimplementa `.venv`,
`pip`, `sibu-init-db`, `sibu-host-demo` ni `uvicorn`— y verifica de forma independiente, con
la librería estándar de Python, que la web responda por HTTP y que el host ISO8583 acepte
conexión por TCP antes de dar la demostración por lista.

**Primer intento de descubrimiento, fallido.** En la sesión donde se creó el archivo, el
catálogo de skills de esa misma sesión ya se había cargado antes de que el archivo
existiera, así que el skill no apareció como disponible.

**Descubrimiento confirmado en una sesión nueva.** En una sesión de Claude Code iniciada
después de la creación del archivo, `levantar-demo` apareció en el catálogo de skills
disponibles y se invocó con normalidad, confirmando que el problema anterior era de orden de
carga y no del contenido del archivo.

**Verificación de comportamiento.** El skill ejecutó `demo.cmd` sin envolverlo ni
reimplementar ninguno de sus pasos, y realizó su propia comprobación independiente después:
HTTP 200 en `http://127.0.0.1:8000/` y conexión TCP aceptada en `127.0.0.1:8583`. No
intentó ninguna remediación automática ante los problemas que fueron apareciendo durante las
pruebas.

**Corrección aplicada tras la prueba real.** Ejecutar `demo.cmd` desde una herramienta que
gestiona o redirige la entrada estándar —incluida esta sesión de Claude Code— producía
`ERROR: No es compatible la redirección de entradas` en el paso `timeout /t 1 /nobreak` del
bucle de espera de la web, sin llegar a romper el arranque. Se sustituyó ese `timeout` por
una pausa de un segundo con `".venv\Scripts\python.exe" -c "import time; time.sleep(1)"`,
que no depende de un handle de consola interactivo. Prueba final tras el cambio: el error de
redirección ya no aparece, HTTP 200, conexión TCP a 8583 aceptada, y el host sigue vivo
—`LISTENING`— después de la comprobación.

**Commit:** `ba078538`.

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

**Actualización 2026-09-03 — criterios aplicados en Track 1/Track 2, el congelamiento de
alcance, la reproducibilidad y el skill de demostración.** Siempre revisado por el
estudiante antes de confirmar un commit o un push: las decisiones de alcance —como congelar
el crecimiento funcional—, cualquier cambio funcional, las reglas de negocio, la seguridad
del PAN, los cambios de persistencia, y toda operación de Git con efecto persistente
—staging, commit, push o modificación del historial—. También se revisaron en persona la
reproducibilidad (`README.md`, `demo.cmd`) y el comportamiento real de la demostración
levantada, y el estudiante revisó y aprobó las correcciones que surgieron de hallazgos del
agente antes de incorporarlas, incluido el hallazgo de gobernanza sobre
`py -3.13 --version`.

Delegado principalmente al agente: la inspección inicial de archivos y del estado del
repositorio, la generación de propuestas técnicas, la búsqueda de documentación o
configuración desactualizada, la ejecución mecánica de las suites de pruebas, los borradores
de documentación —incluido este mismo `SKILL.md`— y las auditorías realizadas en paralelo
mediante subagentes. Ningún resultado delegado se aceptó sin presentarse antes para
revisión, en particular antes de cualquier `git add`, `commit` o `push`.

---

## 2026-09-06 · Cuelgue de CI en Python 3.12 y Bloque 7 (exportación de corridas)

**Hallazgo: el job "Suite en Python 3.12" de `tests.yml` se colgaba indefinidamente**, hasta el
timeout de 6 horas de GitHub. Causa raíz: dos pruebas de `tests/test_conexiones_administracion.py`
levantaban un servidor TCP de prueba con `asyncio.start_server(lambda r, w: None, ...)` —un
handler que acepta la conexión y nunca cierra el `writer`—. Bajo Python 3.11,
`asyncio.Server.wait_closed()` no esperaba de verdad a que las conexiones activas terminaran
(casi un no-op), así que dejar el writer abierto nunca se notaba. Python 3.12 corrigió ese
comportamiento (issue documentado en el propio repositorio de CPython, gh-123720, con el mismo
problema real ya parcheado en uvicorn), y una conexión que nadie cierra hace que
`Server.wait_closed()` —y por lo tanto `async with servidor:` al salir del bloque— se cuelgue
para siempre.

**Cómo se aisló.** Se reprodujo el cuelgue real en GitHub Actions, no solo localmente, usando una
rama temporal (`diagnostico/python312-hang`) para no tocar `main`. Se comparó el mismo nodeid
(`test_probar_una_conexion_disponible_da_true`) en Python 3.11.16, 3.12.14 y 3.13.15 antes y
después del cambio, confirmando que el comportamiento distinto entre versiones era la causa, no
una falla intermitente del runner.

**Corrección aplicada.** El handler pasa a ser una función (`_aceptar_y_cerrar`) que cierra el
writer explícitamente (`writer.close(); await writer.wait_closed()`) en vez de depender del
comportamiento permisivo de Python 3.11. Tras el cambio, el mismo nodeid da PASS en las tres
versiones, y el workflow `tests.yml` completo —sin ninguna otra modificación— corrió en verde en
Python 3.12 en la rama de diagnóstico. **Pendiente de commit a `main`.**

**Bloque 7: exportación de una corrida ya persistida.** Nuevo servicio neutral
`application/exportacion_corridas.py` (JSON versión 1 y CSV) y subcomando
`sibu-run-suite export-run CORRIDA_ID --format json|csv [--out ARCHIVO]`, reutilizado por
`cli.py` sin que ninguna interfaz dependa de otra —mismo criterio de desacoplamiento que ya usa
`application/presentacion_evaluacion.py`—. Deliberadamente sin PDF, sin Excel y sin HTML: son
formatos fuera de lo pedido para un reporte portable de CI. El exit code de `export-run` es un
contrato propio, separado del de `run-suite`: solo distingue si el reporte se pudo generar (`0`)
o si la corrida no existe (`1`), nunca codifica el resultado (PASS/FAIL/...) de esa corrida.
Auditado en paralelo por seis perspectivas (arquitectura, seguridad, CSV/JSON, CLI/Windows,
persistencia, calidad de tests), sin hallazgos P0. **Pendiente de commit a `main`.**

---

## 2026-09-07 · Ciclo 6 de cierre: cuatro correcciones sobre Bloque 7 y su cobertura

Auditoría final cruzada sobre el working tree sin commitear (Bloque 7 + fix de Python 3.12).
Cuatro hallazgos puntuales, corregidos en el mismo ciclo:

**1. `export-run --format csv` a stdout imprimía una línea en blanco de más.**
`reporte_a_csv()` ya termina en `"\n"` (usa `csv.writer` con `lineterminator="\n"`), pero la
rama de impresión a stdout de `cli.py` volvía a hacer `print(texto)`, que agrega su propio
salto de línea final —doble salto visible al final de la salida—. Corregido distinguiendo esa
rama: cuando el destino es stdout y el formato es CSV, se usa `print(texto, end="")` en vez de
`print(texto)`, en vez de tocar `reporte_a_csv()` (que ya era correcto y lo sigue usando `--out`
sin cambios).

**2. Mensaje de error genérico y engañoso ante `evaluacion_json` corrupto.** Si la fila
persistida de una corrida tenía `evaluacion_json` con JSON inválido, `export-run` capturaba la
excepción en el `except Exception` genérico de `ejecutar_cli()` e imprimía
`MENSAJE_FALLO_TECNICO`, que sugiere revisar `SIBU_DB_PATH` o la conexión de la suite —ninguna
de las dos cosas es la causa real—. Se agrega un `except json.JSONDecodeError` específico,
antes del genérico, con el nuevo `MENSAJE_EVALUACION_CORRUPTA`, que nombra la causa real (fila
corrupta en la base) y aclara explícitamente que no es un problema de configuración.

**3. Test tautológico en `tests/test_politica_campos.py`.**
`test_la_capa_estructural_gana_aunque_la_validacion_no_existiera` armaba el diccionario de
campos a mano (partiendo de `valores_por_defecto`, aplicando el `update` con los valores
manipulados y luego el `update` con los valores correctos) y afirmaba sobre ESE diccionario
armado a mano —nunca invocaba `armar_compra`—. Pasaba sin importar si `armar_compra` hiciera lo
que el docstring decía. Reescrito para invocar `armar_compra` real con los mismos campos
manipulados; como `validar_campos_manuales` normalmente rechazaría ese `campos_manuales` con
`CampoProtegido` antes de llegar al merge estructural que el test quiere ejercer, se neutraliza
esa validación con `monkeypatch.setattr` para poder llegar al camino real que se quería probar.

**4. `export-run --out archivo` en Windows no respetaba el `"\n"` explícito.**
`Path.write_text()` sin `newline=""` traduce, en modo texto de Windows, cada `"\n"` a
`"\r\n"` -contradiciendo el `lineterminator="\n"` que `reporte_a_csv()` elige a propósito
(ver su propio docstring) para evitar fin de línea mixto. Confirmado con una prueba directa
(`Path.write_text("a,b\n", encoding="utf-8")` produce `b"a,b\r\n"` en esta máquina). Corregido
agregando `newline=""` a esa llamada, tanto para CSV como para JSON con `--out`.

Suite completa: **897 pruebas** (antes 895), cifra verificada con `pytest -q --collect-only`
sobre el working tree, no estimada. El test de `test_politica_campos.py` fue reescrito, no
agregado -no suma a la cuenta-; el incremento neto de +2 viene de dos pruebas nuevas de este
mismo ciclo: `test_export_run_con_evaluacion_json_corrupta_da_mensaje_especifico_no_generico`
(hallazgo 2) y `test_export_run_csv_a_archivo_no_traduce_los_saltos_de_linea_en_windows`
(hallazgo 4), ambas en `tests/test_cli_export_run.py`.
Ninguna de las tres correcciones cambia comportamiento fuera de lo descrito arriba; ninguna
toca RN-1..RN-4 ni el esquema JSON ya publicado de `run-suite` (ese mismo test lo deja como
candado explícito). **Pendiente de commit a `main`**, junto con Bloque 7 y el fix de Python
3.12.

## 2026-09-07 · Decisión de cierre: cifra final de pruebas y corrección de alcance en PROYECTO.md

Revisión final antes de staging. Dos decisiones de gobernanza:

**1. Cifra de pruebas para publicar: 897.** Confirmado que `pytest -q` sobre el working
tree final (Bloque 7 + fix de Python 3.12 + las cuatro correcciones del Ciclo 6) da
`897 passed`. Se decide que esa es la cifra de cierre que se publica -CONTEXTO.md y la
propuesta de presentación se actualizaron para reflejarla como estado final, no como
estimación provisional. Esta entrada no reemplaza las cifras históricas ya registradas
(436, 895) en entradas anteriores de esta bitácora ni en `PRESENTACION.md`: cada una
describe el estado real de un momento distinto del proyecto, y se conservan tal cual.

**2. Corrección de alcance en `PROYECTO.md`.** La nota "Estado de implementación"
agregada el 2026-09-07 (ver entrada anterior de ese mismo día) no bastaba: las secciones
1, 2, 3 (paso 8), 7.2 y 9 (semana 7) seguían redactadas de forma que un lector podía
interpretar el motor de pruebas de carga como parte de la entrega actual. Se agregaron
anotaciones puntuales e inequívocas en cada una de esas menciones -"roadmap posterior a
la entrega", "evolución prevista, no implementada", "planificado; no se llegó a
implementar"-, sin reescribir el documento, sin eliminar el motor de carga del roadmap,
y sin tocar ninguna otra sección. Se revisó además todo el documento buscando menciones
de concurrencia, scheduler, autenticación, productización y perfiles Visa/Mastercard: las
únicas que existían ya estaban correctamente enmarcadas como trabajo futuro (sección 4,
"La decisión difícil", y la nueva sección 0); no hicieron falta más cambios.

Verificación final tras ambas decisiones: `pytest -q` → 897 passed; guardia PAN
(`test_seguridad_auditoria.py`) → 3 passed; `git diff --check` limpio. Sin commit ni push
a `main` todavía -queda para la etapa de staging, fuera de esta revisión.

## 2026-09-07 · Cinco mejoras funcionales posteriores a la entrega

Trabajo pedido explícitamente por el usuario como iteración posterior al cierre académico,
sobre hallazgos de una revisión estática confirmados contra el código antes de implementar
nada. Cinco bloques, en el orden solicitado; cada uno con pruebas nuevas y verificación
manual en navegador (host simulado + web en puertos aislados, base SQLite propia, sin tocar
datos locales existentes).

**1. Diagnóstico histórico de fallos.** `ResultadoCompra.motivos` ya se calculaba y se
mostraba en la pantalla de resultado inmediato, pero nunca se persistía -`detalle.html`
lo declaraba explícitamente: "el motivo concreto no se conserva"-. Se agrega
`Ejecucion.motivo_detalle` (columna nueva, migración aditiva idempotente), poblada en
`Orquestador._registrar` con el mismo texto ya redactado como seguro (nombres de campo,
códigos de catálogo, texto de socket -nunca una excepción cruda ni un mensaje ISO
completo). `APROBADA` nunca lleva motivo; una fila anterior a este campo se distingue de
una `APROBADA` y se explica como "no disponible", nunca como "sin problema".

**2. Filtros y paginación del historial.** `ejecuciones_recientes(limite=20)` no tenía
filtros ni páginas. Se agrega `FiltroHistorial` (dominio, compartido por el puerto y su
adaptador SQLite) y `RepositorioEjecuciones.buscar(filtro, pagina, tam_pagina)` con
`WHERE` parametrizado (nunca interpolado) y `COUNT(*)` aparte del `LIMIT/OFFSET`, para
distinguir historial vacío de búsqueda sin resultados. Filtros: fecha, estado
transaccional, PASS/FAIL/sin expectativas, tarjeta, destino, STAN. La paginación
preserva los filtros en la propia URL, sin sesión ni cookie.

**3. Conservar datos del formulario.** Diagnóstico confirmado: el bloque "Cambiar
conexión" vivía FUERA del `<form>` del constructor -un simple `<a href>`-, así que
cambiar de conexión perdía tarjeta, monto, campos editables, expectativas y nombre de
escenario. Se movió dentro del formulario como botones `formmethod="get"` con nombre
propio (`ir_a_conexion`, para no chocar con el campo oculto `conexion_id`); al someter,
el navegador arma la querystring con todo el formulario, y `pantalla_compra` la lee
igual que ya leía un reintento tras error de validación (`_leer_enviado`, factorizada
para que compra/escenarios/conexión-nueva compartan una sola implementación). Se
corrigió también que un error al guardar una suite perdiera los escenarios ya marcados
y su orden -`_formulario_suite` ahora reconstruye la selección desde el formulario
rechazado, no desde la `Suite` (que puede no existir todavía).

**4. Reutilizar una transacción desde su resultado.** "Editar y volver a ejecutar" y
"Guardar como escenario" en `resultado.html`, resueltos por `GET /?ejecucion_id={id}`.
Recupera `card_id` (nunca el PAN), monto, campos editables (leídos de la solicitud ya
persistida) y expectativas (reconstruidas de `evaluacion_json`). La conexión usada se
resuelve por `destino_host:puerto` contra las conexiones administradas activas; si no
hay match único, se explica y se deja sin preseleccionar -nunca se sustituye en
silencio, mismo principio que ya aplicaba a escenarios-. Cada reejecución es un POST
normal a `/compra`: STAN e id nuevos siempre, sin mecanismo de reenvío.

**5. Exportación desde la web.** Dos rutas nuevas (`/suites/corridas/{id}/exportar.json`
y `.csv`) y sus botones en `corrida_detalle.html`, reutilizando literalmente
`application/exportacion_corridas.py` -el mismo módulo que ya usa `sibu-run-suite
export-run`-. Nunca vuelve a ejecutar la suite: lee únicamente el snapshot ya
persistido (`CorridaSuite` + `ItemCorridaSuite`).

Verificado en navegador de punta a punta contra host simulado y web reales, en puertos y
base SQLite aislados (no los del entorno habitual del usuario): construir → ejecutar
(NO_ENVIADA por un campo mal armado, causa visible en "Por qué") → ejecutar de nuevo con
datos válidos (APROBADA) → cambiar de conexión sin perder lo escrito → "Editar y volver
a ejecutar" recupera tarjeta/monto/campo/conexión exactos → historial filtrado por
estado → guardar escenario → correr suite → exportar JSON y CSV desde el detalle de la
corrida, verificando que el JSON coincide byte a byte con `reporte_a_json()`.

Suite completa: 921 passed, 2 skipped (antes 897 passed) -24 pruebas nuevas en
`tests/test_web.py`, `tests/test_detalle_historial.py` (una reescrita, dos agregadas),
`tests/test_web_suites.py`, `tests/test_historial_filtros.py` (nuevo) y
`tests/test_reutilizar_ejecucion.py` (nuevo). Ningún archivo de prueba nuevo ni
modificado contiene un PAN de 12 a 19 dígitos; la guardia de secretos sigue en verde.
Sin commit ni push -pendiente de que el usuario lo pida.

## 2026-09-07 · Revisión crítica de las cinco mejoras, antes de darlas por cerradas

A pedido explícito del usuario: revisar el diff completo contra cinco puntos concretos,
con pruebas de comportamiento donde corresponda, sin ampliar alcance. Se encontraron y
corrigieron tres defectos reales; se investigó y se documentó (sin corregir, por ser un
rediseño desproporcionado al hallazgo) una exposición de datos no sensibles en URLs.
Detalle completo en el informe entregado al usuario en esa misma conversación; aquí solo
el registro de gobernanza.

**Hallazgos corregidos:**
1. **Reutilizar una ejecución no explicaba por qué no se podía ejecutar.** Si la tarjeta
   de una ejecución pasada ya estaba desactivada o eliminada, `_reconstruir_desde_ejecucion`
   dejaba `conexion_id`/tarjeta sin resolver -correcto- pero nunca lo decía: la persona veía
   el botón "Ejecutar transacción" deshabilitado sin ninguna explicación. Corregido para que
   la tarjeta no disponible y la conexión no resoluble se expliquen juntas, sin sustitución
   silenciosa. Además, una ejecución del formato de texto heredado (anterior a la
   persistencia estructurada, `MensajeSerializado.fiel=False`) no avisaba que sus campos
   editables recuperados no son demostrablemente exactos; ahora sí.
2. **Los botones de "Cambiar conexión" no llevaban `formnovalidate` verificado con un clic
   real.** Ya se había agregado el atributo, pero solo se había probado disparando el envío
   por JavaScript (`.click()` sin passar por la validación nativa real). Se verificó con
   clics reales de mouse en navegador, con `monto` vacío y con `monto` inválido: el cambio
   de conexión no se bloquea y no se pierde lo escrito. Se agregó un test que verifica que
   el atributo siga presente en el marcado (`TestClient` no ejecuta validación HTML5, así
   que solo un test de marcado -o el navegador real- puede detectar una regresión aquí).
3. **Faltaba la prueba de migración para `motivo_detalle`.** Todas las demás columnas
   agregadas en la historia del proyecto tienen su propia prueba en
   `test_migracion_generalizada.py` contra una base anterior real; esta, agregada en la
   iteración anterior, no la tenía. Se agregó siguiendo el mismo patrón (fila preexistente
   conservada, migración idempotente, sin inventar un motivo para una fila que nunca lo tuvo).

**Hallazgo documentado en esta entrada -- RESUELTO en la revisión del mismo día, ver la
entrada siguiente ("Cierre del hallazgo de datos del formulario en la URL"):** cambiar de
conexión sometía el formulario completo por GET, así que `monto`, los campos editables y
el nombre del escenario viajaban en la URL, visibles en el historial del navegador y en
los logs de acceso por defecto del servidor. La corrección finalmente adoptada -POST en
vez de GET, sin sessionStorage ni borrador alguno- se explica en esa entrada.

**Pruebas nuevas de esta revisión:** 16 (`test_reutilizar_ejecucion.py` +4,
`test_reglas_negocio.py` +4 y refuerzo de 1 existente, `test_migracion_generalizada.py` +3,
`test_web.py` +2, `test_web_suites.py` +2, `test_historial_filtros.py` +1). Suite completa
tras la revisión: **937 passed, 2 skipped** (antes 921). Verificado también en navegador
real (no solo `pytest`): clic real en "Cambiar conexión" con monto vacío/inválido: la
conexión cambia y nada se pierde; confirmado en un log de acceso real (descartado al
cerrar) que la URL completa, incluida cualquier referencia libre escrita por la persona,
quedaba en el log de acceso -este es precisamente el hallazgo que la entrada siguiente
resuelve-. Guardia de PAN (`test_seguridad_auditoria.py` y equivalentes) sigue en verde.
Sin commit ni push.

## 2026-09-07 · Cierre del hallazgo de datos del formulario en la URL, y refuerzo de `motivo_detalle`

A pedido explícito del usuario, tras la revisión anterior: no dejar el hallazgo de la URL
solo documentado, sino resolverlo dentro del propio alcance de "conservar datos al cambiar
de conexión". Además, revisar si `motivo_detalle` persiste alguna vez texto crudo de una
excepción de terceros, en vez de solo confiar en haber leído el código de la versión
instalada de `pyiso8583`.

**1. Cambiar de conexión pasa de GET a POST.** Solución más simple compatible con la
arquitectura existente, evaluada y preferida sobre `sessionStorage`: el botón "Cambiar"
ya vivía dentro del mismo `<form>` (`method="post" action="/compra"`); le bastaba con NO
llevar `formmethod="get"` -sin ese atributo, el botón hereda el método POST del propio
formulario- y con seguir llevando `formnovalidate` (para que un `monto` vacío o inválido,
campo `required`, no bloquee el cambio). Se agregó la ruta `POST /`
(`cambiar_conexion` en `web/app.py`), que lee el mismo `request.form()` que ya sabía leer
`_leer_enviado`, resuelve la conexión destino desde `ir_a_conexion` y vuelve a renderizar
`compra.html` con `_formulario` -sin invocar el orquestador ni `ServicioEscenarios` en
ningún caso-. No hizo falta `sessionStorage` ni ningún borrador persistido: el propio
cuerpo del POST, mas la re-renderización del lado del servidor, alcanzan. `GET /` se
simplificó de vuelta: ya no necesita distinguir "vino de un resubmit" leyendo si `monto`
aparece en la querystring, porque esa querystring ya no existe.

Verificado con clics reales de mouse en un navegador (no simulados por JavaScript), con
`monto` vacío y con `monto` inválido, en un servidor y una base SQLite aislados
(`SIBU_DB_PATH` propio, puertos propios, host simulado propio): la conexión cambia, nada
de lo escrito se pierde, la URL del navegador permanece exactamente en `/` sin querystring,
y la línea del log de acceso del servidor queda como `"POST / HTTP/1.1" 200 OK` -sin
ningún valor del formulario-. Se confirmó además, leyendo la base SQLite aislada
directamente, que ningún cambio de conexión creó una fila en `ejecuciones` ni en
`escenarios`.

**2. Las expectativas se recuperan de la ejecución, nunca del escenario editado después.**
Ya estaba implementado así (`_expectativas_de_ejecucion` lee `evaluacion_json`, el
snapshot propio de la ejecución), pero no había ninguna prueba que lo demostrara con datos
reales -solo el docstring lo afirmaba-. Se agregó
`test_las_expectativas_se_recuperan_de_la_ejecucion_no_del_escenario_editado`: un
escenario que HOY espera "rechazada" (edición posterior), pero cuya ejecución reutilizada
evaluó "aprobada" + campo 39 igual a "00" en su momento, muestra "aprobada" al recuperarse
-nunca "rechazada"-. Se agregó también el caso complementario: una ejecución sin
expectativas no debe heredar las del escenario actual aunque exista.

**3. `motivo_detalle` sí persistía texto crudo de una excepción de terceros.**
Confirmado: `CodecIso8583.codificar()`/`decodificar()` envolvían `iso8583.EncodeError`/
`DecodeError` con `f"...: {error}"`, incrustando el mensaje LIBRE que redacta la librería
`pyiso8583` -no un contrato que este proyecto controle ni pueda auditar hacia adelante-.
La revisión anterior había dado esto por seguro leyendo el código fuente de la versión
instalada (`EncodeError.__init__`/`DecodeError.__init__` solo concatenan `msg` y el
número de campo, nunca el valor), pero eso es una observación puntual sobre una versión,
no una garantía. Corregido para no depender en absoluto del texto de la librería: ambos
métodos ahora usan únicamente `error.field` (el número de campo ISO, un atributo
estructural que la librería expone en su `__init__`) para redactar un mensaje **propio**
de este proyecto -`"no se pudo codificar el campo {N} para el MTI {mti} con el perfil
{perfil!r}"`-, sin ninguna palabra de la librería. Verificado con una prueba que compara
el mensaje persistido contra el texto exacto esperado y confirma que ninguna palabra de la
redacción original de `pyiso8583` para ese caso ("expecting", "bytes") sobrevive. Revisados
también los demás orígenes de `motivo_detalle` (`FalloDeConexion`/`FalloDeTransmision` en
`adapters/transporte/tcp.py`, `ErrorDeFraming` en `framing_demo.py`): son texto propio de
este proyecto, o -para las excepciones `OSError`/`TimeoutError` de socket que sí se
interpolan- errores que por su propia naturaleza describen solo el fallo de la conexión
(actor "Connection refused", "Broken pipe", agotamiento de tiempo), nunca el contenido de
la aplicación que se estaba transmitiendo; no se cambiaron.

**Pruebas nuevas de este cierre:** 6 (`test_reutilizar_ejecucion.py` +2 sobre
expectativas, `test_web.py` +1, `test_web_escenarios.py` +1, y `test_reglas_negocio.py`
reescribe -no agrega- la prueba de `motivo_detalle` de codec para que verifique el texto
exacto en vez de un fragmento heredado de la librería). Suite completa: **941 passed, 2
skipped** (antes 937). Guardia de PAN sigue en verde. Verificado en navegador real (host
simulado + web en puertos y base SQLite aislados, descartados al cerrar; la base local
real del usuario no se tocó). Sin commit ni push.

## 2026-09-09 · Gestión avanzada de corridas: comparación histórica y reintento selectivo

Segunda evolución funcional posterior a la entrega, priorizada por el usuario tras una
investigación de mercado (herramientas comparables de simulación/certificación ISO 8583:
jPOS, isosim, neaPay, Iliad t3; VTS/VCMS del lado Visa, MTF/M-TIP del lado Mastercard,
ninguno un competidor exacto de este alcance académico). Dos capacidades tratadas como un
solo bloque: **comparar dos corridas históricas de la misma suite** y **reintentar
selectivamente los ítems en FAIL/ERROR de una corrida**. Explícitamente fuera de esta
iteración: variantes parametrizadas, carga, perfiles de marca reales, multiusuario, flujos
encadenados, condiciones negativas configurables.

**Diseño previo a implementar (pedido explícito del usuario: proponer antes de tocar
código).** Tres decisiones no obvias, documentadas antes de escribir una línea:

1. **Matriz SIN_CAMBIO/MEJORÓ/EMPEORÓ/CAMBIÓ**, `domain/comparacion_corridas.py`. Ranking
   de severidad **solo** entre PASS/FAIL/ERROR (2/1/0): `SIN_EXPECTATIVAS`/`NO_EJECUTADO`
   quedan deliberadamente fuera -no hay expectativa que ganar o perder-, así que cualquier
   transición que involucre alguno de los dos es CAMBIO, nunca MEJORÓ/EMPEORÓ. El único par
   que el pedido no fijaba de antemano, FAIL↔ERROR, se resolvió así: **FAIL → ERROR es
   EMPEORÓ** (se pierde la capacidad de diagnóstico: FAIL todavía dice qué discrepancia
   hubo, ERROR no dice nada evaluable) y **ERROR → FAIL es MEJORÓ** (se recupera esa
   capacidad, aunque la expectativa siga sin cumplirse). Mismo resultado en ambos lados con
   contenido distinto (discrepancias para FAIL, `detalle` para ERROR) es CAMBIO, no
   SIN_CAMBIO -ej. FAIL→FAIL pero cambió qué campo no cumplió-.
2. **Emparejamiento por `escenario_id`**, nunca por `orden` (un reintento renumera 1..N) ni
   por `escenario_nombre` (mutable). Es una clave estable ya persistida en
   `ItemCorridaSuite`, y por construcción de `web.app._leer_escenarios_de_suite` (que arma
   la selección recorriendo el catálogo real) un mismo escenario nunca se repite dentro de
   los items de una misma corrida: el emparejamiento nunca es ambiguo.
3. **`corrida_origen_id`: NO se agregó.** La comparación ya funciona genéricamente entre
   cualquier par de corridas de la misma suite, elegido a mano en el selector "Comparar
   contra" -no depende de que una sea "hija" de la otra-. Agregar la columna habría sido
   solo una conveniencia de UX (auto-sugerir el origen del reintento), no una capacidad
   nueva, a cambio de una migración + repositorio + modelo + pruebas. Se documenta como
   mejora futura de bajo costo si se pide, no como algo pendiente de esta entrega.
4. **Reintento: selección histórica, ejecución vigente.** Aceptada tal cual la preferencia
   conceptual del usuario: `reintentar_fallidos` toma la lista de `escenario_id` de los
   **items históricos** de la corrida origen (nunca de la membresía actual de la suite -un
   escenario agregado después no entra-), pero cada uno se ejecuta con la configuración
   **actual** del escenario (tarjeta/monto/conexión/expectativa vigentes) -exactamente lo
   mismo que ya hacía `ejecutar()` para toda la suite-. Un escenario desactivado o borrado
   (esto último solo posible manipulando la base por fuera de la aplicación: los servicios
   nunca borran, solo desactivan) cae en ERROR con el mismo motivo controlado que ya usa
   una corrida normal (`EscenarioNoEjecutable`/`EscenarioNoEncontrado` de
   `EjecutorDeEscenarios`), sin abortar el reintento de los demás ítems -cero comportamiento
   nuevo que inventar, cero runner paralelo.

**Arquitectura.** `domain/comparacion_corridas.py` (nuevo, puro: `CambioItem`,
`clasificar_cambio`, `ComparacionItem`). `application/comparacion_corridas.py` (nuevo:
`ServicioComparacionCorridas.comparar(corrida_a_id, corrida_b_id)`, empareja items leyendo
solo `RepositorioCorridasSuite.obtener`/`obtener_items` de ambas corridas -nunca el
escenario, la suite ni la expectativa vigentes-, con errores controlados
`CorridaNoEncontrada`/`CorridasDeSuitesDistintas`). `application/corredor_suites.py`:
refactorizado para compartir un núcleo `_correr()` entre `ejecutar()` (existente) y
`reintentar_fallidos()` (nuevo, con `CorridaOrigenNoEncontrada`/`SinItemsReintentables`) -
ningún segundo runner. `adapters/persistence/sqlite_repos.py`: un único método nuevo de
solo lectura, `listar_por_suite(suite_id, limite)`, para poblar el selector "Comparar
contra" sin que el límite global de `listar()` esconda una corrida antigua de esta suite
-**sin migración**: `suite_id` ya existía en `corridas_suite`-. `web/app.py`: rutas
`GET /suites/corridas/{id}/comparar` (con y sin `?contra=`) y
`POST /suites/corridas/{id}/reintentar`. `web/presentacion.py`: traducción a filas de
tabla, incluida la fusión de discrepancias de A y B por criterio (CRITERIO/recibido en
A/recibido en B) en una sola fila en vez de dos tablas separadas.

**Verificación.** 46 pruebas nuevas, reconciliadas archivo por archivo contra
`pytest --collect-only` (no una suma estimada): `tests/test_comparacion_corridas.py` +24
(archivo nuevo; 13 funciones, 3 de ellas parametrizadas -7+2+5 casos- más 10 simples; cubre
la matriz completa incluida la estabilidad histórica frente a edición posterior de
escenario y suite); `test_corredor_suites.py` +9 (18→27 funciones, sin parametrizar,
incluida la prueba explícita de escenario eliminado por fuera de la aplicación);
`test_web_suites.py` **+13** (34→47 funciones, sin parametrizar; rutas de comparar/
reintentar y "0 fallidos no crea nada"); `test_web.py` +0 (solo se agregó el atributo
`comparador_corridas` a `ComposicionFalsa`, ningún test nuevo). 24+9+13+0 = 46.
Suite completa: **991 passed** (antes 945, confirmado en un worktree aislado en el commit
`f318ffa`). Verificado además con clics reales en
navegador, en una base y puertos completamente aislados de la base real del usuario:
suite de 3 escenarios, dos corridas con una edición de expectativa y una desactivación de
por medio, comparación mostrando 1 SIN_CAMBIO + 1 MEJORÓ + 1 EMPEORÓ con la discrepancia de
Expected vs Actual correcta, y "Reintentar fallidos" creando una corrida nueva con
únicamente el ítem en ERROR, sin alterar la corrida de origen. Sin commit ni push.

**Cierre posterior a la reconciliación: defensa contra duplicado de `escenario_id` y
cobertura web de SOLO_EN_A/SOLO_EN_B.** El usuario aprobó la reconciliación anterior pero
señaló, antes de aprobar un commit, un riesgo objetivo no cubierto: `corrida_suite_items`
tiene `PRIMARY KEY (corrida_id, orden)`, no una restricción `UNIQUE` sobre `escenario_id`
-ver `adapters/persistence/esquema.py`-. El `{escenario_id: item for item in items}` que
arma el emparejamiento en `_comparar_items` (`application/comparacion_corridas.py`) se
quedaba en silencio con "el último que gana" si alguna vez apareciera un duplicado: nunca
ocurre por los caminos actuales de la aplicación (`ServicioSuites._validar_escenarios`
rechaza un escenario repetido al crear o editar una suite), pero el esquema no lo impide
por sí solo -un dato corrupto insertado por fuera de la aplicación, o un bug futuro, sí
podría producirlo-. **No se agregó una migración ni una restricción `UNIQUE` en SQLite**
-decisión explícita del usuario, defensa a nivel de servicio en vez de esquema-. Se agregó
`_indice_por_escenario(corrida_id, items)`, que arma el mismo diccionario pero levanta la
excepción nueva `ItemsHistoricosDuplicados(corrida_id, escenario_id)` en cuanto encuentra
una clave repetida, en vez de sobrescribir en silencio; lleva solo identificadores técnicos
(`corrida_id`, `escenario_id`), nunca datos de tarjeta. `web/app.py` la traduce a una
respuesta controlada (HTTP 409, mismo patrón que `CorridasDeSuitesDistintas`) en la ruta
`GET /suites/corridas/{id}/comparar`, sin traceback expuesto. Dos pruebas nuevas en
`test_comparacion_corridas.py` construyen el estado corrupto a mano -`CorridaSuite`/
`ItemCorridaSuite` instanciados directamente, sin pasar por el repositorio ni por el flujo
normal, que ya lo impide- y llaman a `_comparar_items()` para confirmar el error controlado
tanto con el duplicado en la corrida A como en la B.

Aparte, la cobertura de SOLO_EN_A/SOLO_EN_B existía solo a nivel dominio/aplicación; se
agregó una prueba web dedicada en `test_web_suites.py` que compara dos corridas de una
misma suite a la que se le agregó un escenario entre una corrida y otra, verificando en la
misma prueba -comparando en ambas direcciones- HTTP 200, el nombre del escenario correcto,
el lado ausente renderizado como celda vacía controlada (`class="vacio">—<`), la etiqueta
de clasificación SOLO_EN_A y SOLO_EN_B presentes, ningún "Traceback" en la respuesta y
ningún PAN completo. Ninguna semántica de la matriz MEJORÓ/EMPEORÓ/CAMBIÓ ni del reintento
se tocó. Pruebas nuevas de este cierre: **3** (2 en `test_comparacion_corridas.py`, 24→26;
1 en `test_web_suites.py`, 47→48). Suite completa: **994 passed** (antes 991, confirmado
con `pytest --collect-only -q`). Guardia de PAN en verde. `git diff --check` sin
conflictos de merge marker (solo advertencias cosméticas de CRLF). Sin commit ni push.

## 2026-09-09 · Sesión autónoma de auditoría: hallazgo y corrección en `campos_de_correlacion` (RN-3)

Sesión autónoma posterior al cierre anterior: seis agentes de auditoría en modo solo lectura
(funcional, seguridad, arquitectura, tests/mutación, documentación, UX) más uno de
investigación de mercado, todos verificando contra el código real antes de aceptar cualquier
hallazgo -no se acepta ningún hallazgo de un agente sin releer el archivo citado-. La mayoría
de lo reportado son hallazgos P1/P2 de UX y documentación (ver reporte de cierre de sesión
para el detalle completo); uno solo ameritó una corrección de código inmediata por su
naturaleza de seguridad, siguiendo el mismo criterio de "arreglo mínimo y autocontenido" ya
usado en el cierre anterior.

**Hallazgo confirmado: `campos_de_correlacion` (RN-3) no excluía `CAMPOS_SENSIBLES`.**
`campos_de_correlacion(perfil, mti_respuesta)` (`domain/validacion.py`) restaba
`CAMPO_CODIGO_RESPUESTA` pero no `CAMPOS_SENSIBLES` ({"2","35"}), a diferencia de
`domain/expectativas.py::campos_permitidos_expectativa`, que sí los excluye siempre.
`_discrepancias_de_correlacion` arma el texto del motivo interpolando el valor tal cual
(`f"...se envió {esperado!r} y volvió {recibido!r}"`), y ese texto (`motivo_detalle`) se
persiste en `Ejecucion` y se muestra en el historial **sin pasar por `.enmascarado()`** -ese
enmascarado solo se aplica a `solicitud`/`respuesta` en `Orquestador._registrar`, nunca a los
`motivos`-. Verificado leyendo ambos archivos línea por línea antes de aceptar el hallazgo del
agente. Con el único perfil vigente (`PERFIL_GENERICO`) esto era inofensivo hoy:
`OBLIGATORIOS_0110` no incluye `"2"` ni `"35"`, así que ningún campo sensible entraba a
`campos_de_correlacion` en la práctica. Pero es exactamente el tipo de mecanismo que cambiaría
si un futuro perfil de marca real declarara el PAN obligatorio en la respuesta 0110 (con
precedente real en ISO 8583) -y `CLAUDE.md` anticipa que los perfiles reales sí se
implementarán cuando existan documentos autorizados-, momento en el que el PAN completo
quedaría embebido en `motivo_detalle`, en SQLite y en pantalla.

Corregido restando también `CAMPOS_SENSIBLES` en `campos_de_correlacion`
(`src/sibutestlab8583/domain/validacion.py`), mismo criterio ya usado en `expectativas.py`.
Un test nuevo, `test_campos_de_correlacion_excluye_siempre_los_campos_sensibles`
(`tests/test_reglas_negocio.py`), construye un `PerfilDeMarca` de prueba que sí declara
`"2"`/`"35"` obligatorios en la respuesta -el perfil genérico vigente no lo hace- y confirma
que quedan excluidos de la correlación de todas formas. Ningún cambio de comportamiento
observable con el perfil actual: los mismos campos que antes se correlacionaban lo siguen
haciendo, porque ninguno era sensible. Suite completa: **995 passed** (antes 994, confirmado
con `pytest --collect-only -q`). Guardia de PAN en verde. `git diff --check` sin conflictos.
Sin commit ni push.


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
(Python 3.13.3). Los mínimos declarados en `pyproject.toml` son exactamente lo resuelto:
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

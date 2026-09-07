# Propuesta de cierre — presentación 2026-09-08

Documento de PROPUESTA, no aplicado. No modifica `PRESENTACION.md` ni el `.pptx`.
Se preparó durante el cierre técnico del proyecto (Bloque 7 + fix de Python 3.12,
ambos todavía sin commitear) para que el estudiante decida qué incorporar antes
de la entrega. Nada de esto reemplaza el guion ya aprobado sin su revisión.

Motivo del documento aparte: el guion actual (`PRESENTACION.md`) suma 10:50 y
quedó redactado antes de Bloque 5/6/7 y antes del hallazgo/fix de Python 3.12.
Todo lo que sigue son **adiciones e integraciones**, no una reescritura — el
90% del texto ya aprobado (El problema, La oportunidad, Arquitectura,
Supervisión de Claude Code -incluido el caso de la alucinación, verificado
intacto y correcto-, Adopción y riesgos, Retorno y recomendación) se conserva
tal cual.

---

## 1. Qué cambia y qué no

**Se mantiene sin tocar** (ya correcto, verificado contra el código real):
- "El problema" (0:50)
- "La oportunidad" (0:50)
- "Arquitectura" (1:20)
- "Supervisión de Claude Code" (1:15) — el caso del prefijo PAN 9 sigue
  atribuyendo la detección al estudiante, nunca a un test automatizado. **No
  tocar esta sección bajo ninguna circunstancia.**
- "Adopción y riesgos" (1:00)
- "Retorno y recomendación" (0:55)

**Se propone ampliar** (mismo slide, texto adicional):
- "Qué construí" — agregar una línea que mencione Bloque 5/6/7 sin entrar en
  detalle (el detalle vive en la demo).
- "Resultados verificados" — agregar la cifra real de tests actual y la
  mención del CI verificado en GitHub Actions.

**Se propone reemplazar entero:**
- "Demo en vivo" — de 3:00 a ~4:00, con el recorrido ampliado que pediste.

**No se agrega ningún slide nuevo.** Todo el contenido de Bloque 5/6/7 entra
por la demo ampliada, tal como pediste ("la demo debe tener prioridad").

Total propuesto: **11:35** (dentro de 10-12 minutos), con margen de ~25s.

---

## 2. Texto propuesto — "Qué construí" (reemplaza el cuerpo del slide, mismo título)

```
# Qué construí

**0100 → TCP → host simulado propio → 0110 → validación → persistencia/historial**
**+ escenarios reutilizables, suites de regresión, CLI y CI real, reporte exportable**

No implementado hoy: motor de carga · perfiles reales de marca · DE35/DE45 · autenticación
```

Nota hablada propuesta (agregar una frase al final del comentario ya existente,
sin tocar el resto):

> "...ninguna de esas cuatro está resuelta hoy. Sobre esa base agregué después
> escenarios reutilizables con validación automática, suites de regresión, una
> CLI para correrlas sin navegador, integración con GitHub Actions ya
> verificada en un run real, y un exportador que convierte cualquiera de esas
> corridas en un reporte JSON o CSV, pensado para que alguien de afuera del
> proyecto lo reciba sin depender de que la aplicación siga corriendo — lo van
> a ver en la demo, no se los voy a contar en una diapositiva."

Tiempo: 0:50 → 0:58 (+8s; la frase agregada es real, no relleno — ver
sección 9 sobre por qué hizo falta ampliar en vez de solo pausar).

---

## 3. Texto propuesto — "Resultados verificados"

```
# Resultados verificados

<div class="stats">
<div><p class="num">897</p><p class="label">pruebas en verde</p></div>
<div><p class="num">33</p><p class="label">de RN-1 a RN-4 y seguridad PAN</p></div>
<div><p class="num">3</p><p class="label">versiones de Python en CI</p></div>
<div><p class="num">1</p><p class="label">run real de GitHub Actions, exitoso</p></div>
</div>
```

Guion hablado propuesto (reemplaza el párrafo actual):

> "897 pruebas en verde, incluidas las cuatro reglas de negocio y la guardia
> que impide que un PAN completo llegue a versionarse. El pipeline de
> integración continua ya corrió de verdad en GitHub Actions —no es una
> promesa, es un run con resultado exitoso que les puedo mostrar ahora mismo
> si la conexión lo permite, y tengo la captura si no. Y no corre en una sola
> versión de Python: la misma suite se ejecuta en tres versiones distintas en
> cada push —3.11, 3.12 y 3.13— porque investigando a fondo un cuelgue real
> en el pipeline encontré que un cambio de comportamiento entre versiones de
> Python puede exponer un defecto que antes pasaba desapercibido. Preferí
> reproducirlo con evidencia real en GitHub Actions antes de dar el problema
> por resuelto, en vez de confiar en una explicación sin probarla."

Tiempo: 0:50 → 1:05 (+15s; la ampliación es la única mención hablada del
hallazgo de Python 3.12 en todo el guion — ver sección 9).

**Decisión final de cierre (revisión final, 2026-09-07):** la cifra que se publica es
**897 pruebas** — el estado final del working tree, incluyendo el fix de Python 3.12,
Bloque 7 completo, y las cuatro correcciones puntuales del Ciclo 6 (detalladas en
`BITACORA.md`, entradas del 2026-09-07: el doble salto de línea de `export-run --format
csv` a stdout, el mensaje genérico y engañoso ante `evaluacion_json` corrupto, un test
tautológico en `tests/test_politica_campos.py` que no invocaba `armar_compra`, y `--out`
en Windows traduciendo `\n` a `\r\n` pese al `lineterminator` explícito). Esto YA NO es
una decisión pendiente: se congela como la cifra de cierre, y el bloque de estadísticas
de arriba y el guion hablado ya la usan. Queda pendiente solo el paso mecánico de
`git add` + `commit` + `push` a `main` (fuera del alcance de esta revisión), no una
decisión de contenido.

---

## 4. Demo ampliada (~4:00) — reemplaza el slide "Demo en vivo" completo

### 4.1 Guion exacto de clics (orden fijo, sin desvíos)

Preparación previa (ANTES de empezar a hablar, ver checklist en la sección 6):
navegador abierto en `http://127.0.0.1:8000/`, `sibu-host-demo` corriendo,
suite demo ya creada con un escenario PASS y uno FAIL, terminal con
`sibu-run-suite` probado una vez en seco, pestaña de GitHub Actions abierta
en el run verde, ambas ventanas visibles para alternar sin buscarlas en vivo.

```
0:00 — Pantalla "Nueva transacción". Tarjeta DEMO-0001, destino LOCAL-DEMO.
       "Esto arma un 0100 y lo manda por TCP a un host simulado que ya está
       corriendo aparte."
       ⚠️ ANTES DE HACER CLIC EN "EJECUTAR": hacer clic en el campo "Monto" y
       escribir `150.00` a mano. El "150.00" que se ve ahí es solo un
       placeholder (texto de ejemplo), NO un valor cargado -si se hace clic
       en "Ejecutar transacción" sin escribir el monto, el navegador bloquea
       el envío con un aviso nativo pequeño ("Completa este campo") que es
       muy fácil de no notar en un proyector, y la demo se queda "trabada"
       sin ningún error visible de la aplicación. Confirmado de forma
       reproducible en dos ensayos independientes (Ciclo 2, 2026-09-07).
       Recién ENTONCES, clic en "Ejecutar transacción".

0:20 — Resultado APROBADA, isoscopio abierto un instante (PAN enmascarado).
       "El PAN nunca sale completo de acá, ni en la vista técnica. Este
       isoscopio muestra el mensaje ISO completo, campo por campo, con el
       mismo detalle que usaría alguien certificando una integración real —
       la única diferencia es que el número de tarjeta se enmascara incluso
       acá, en la vista más técnica de toda la aplicación."

0:35 — Clic en "Historial". "Cada intento queda acá, por id de tarjeta,
       nunca por el número."

0:50 — Ir a "Escenarios". Abrir el escenario demo que YA tiene una
       expectativa configurada (preparado de antemano, NO crearlo en vivo).
       "Esto es un caso reutilizable: mismo monto, misma tarjeta, misma
       conexión, y además una expectativa — qué tiene que pasar para que
       cuente como correcto, no solo que el mensaje haya viajado."

1:10 — Ir a "Suites". Abrir la suite demo (ya armada con 2 escenarios: uno
       que da PASS, uno que da FAIL a propósito). Clic en "Ejecutar".
       "Esto corre varios escenarios en secuencia y compara cada resultado
       contra lo que declaré esperar, no solo si el servidor respondió. Y si
       uno de los escenarios fallara por un error real de conexión, en vez
       de una discrepancia de expectativa, el corredor aísla ese fallo y
       sigue con los demás — un problema en un escenario no tira abajo toda
       la corrida, que es justo el comportamiento que uno espera de una
       suite de regresión real."

1:40 — Pantalla de la corrida: un ítem en PASS, uno en FAIL con su
       discrepancia visible. "Acá está la diferencia entre 'la transacción
       funcionó' y 'la transacción hizo lo que yo esperaba' — son preguntas
       distintas, y el sistema las separa a propósito. Esta separación es la
       que hace que una suite sirva como regresión real: si mañana cambio el
       catálogo de códigos de respuesta y algo dejó de comportarse como se
       esperaba, esta suite lo va a marcar en rojo aunque el mensaje siga
       viajando sin ningún error de red."

2:00 — Cambiar a la terminal (ya abierta). Correr:
       `sibu-run-suite run-suite SUI-xxxxxxxx --format json`
       "La misma suite, ahora sin navegador — para que un pipeline de
       integración continua la pueda correr sola."
       Señalar brevemente el código de salida (`echo $?` si ya está en el
       prompt) — "el código de salida ya le dice a un pipeline si esto pasó
       o no, sin que nadie tenga que leer el JSON."

2:30 — Cambiar a la pestaña de GitHub Actions (ya abierta, run verde visible
       de antemano). "Y esto ya corrió de verdad: cada push ejecuta esta
       misma suite en un runner de GitHub, con este resultado."

2:55 — Volver a la terminal. Correr:
       `sibu-run-suite export-run <corrida_id> --format csv`
       "Y esta corrida, una vez que ya pasó, se puede exportar como reporte
       portable — JSON o CSV — sin volver a ejecutar nada ni depender de que
       el navegador siga abierto. Es un snapshot histórico: si después edito
       el escenario o la suite, esta exportación no cambia — es evidencia de
       lo que pasó en este momento exacto, no un cálculo que se pueda mover
       con el tiempo."

3:20 — Cierre de la demo. "Todo lo que acaban de ver corrió en vivo, contra
       un host real, con persistencia real. Nada de esto es una maqueta."

3:20–4:00 — margen de colchón (preguntas cortas del público durante la demo,
       o simplemente terminar antes; no forzar a llenar los 4:00 completos).
```

NO MOSTRAR: Track 1/Track 2, motor de carga, formulario de alta/edición de
tarjetas, creación en vivo de un escenario o una suite (siempre precargados),
consola/código fuente, `--help` de la CLI, ningún subcomando de la CLI que no
sea el exacto de arriba.

### 4.2 Datos demo exactos a preparar (checklist de contenido, no solo de proceso)

- Tarjeta: `DEMO-0001` (ya sembrada por `sibu-init-db`).
- Conexión: `LOCAL-DEMO` (127.0.0.1:8583, ya sembrada).
- Escenario 1 (PASS): monto 10.00, tarjeta `DEMO-0001`, conexión `LOCAL-DEMO`,
  expectativa `estado = APROBADA`. Nombre sugerido: **"Compra aprobada — demo"**.
- Escenario 2 (FAIL a propósito): mismo monto/tarjeta/conexión, expectativa
  sobre el campo 39 con un valor que el host demo NO va a devolver (por
  ejemplo `igual "05"` mientras el host responde "00"). Nombre sugerido:
  **"Código esperado distinto — demo"**. Este es el que da la discrepancia
  visible en el minuto 1:40.
- Suite: **"Suite de regresión — demo"**, con ambos escenarios, en ese orden.
- Comando CLI exacto a tener ya tipeado (o en el historial de la terminal,
  flecha arriba): `sibu-run-suite run-suite SUI-xxxxxxxx --format json`
  (reemplazar `SUI-xxxxxxxx` por el id real de la suite demo, anotado antes).
- `corrida_id` real de exportación: se obtiene de la salida JSON del paso
  anterior (`"corrida_id": N`) — anotarlo o copiarlo, no adivinarlo en vivo.

---

## 5. Guion completo con tiempos (propuesta, ~11:35 total)

**Nota:** los tiempos de esta tabla son ESTIMACIONES por diapositiva, hechas
antes de medir. La sección 9.1 (al final de este documento) las reconcilia
con un conteo real de palabras — la cifra final vigente es **9:30 a 11:06**
según el ritmo, no el "11:35" de esta tabla. Se deja la tabla igual por
referencia del orden y de qué cambia en cada slide.

| # | Slide | Tiempo | Cambio |
|---|---|---|---|
| 1 | El problema | 0:50 | sin cambio |
| 2 | La oportunidad | 0:50 | sin cambio |
| 3 | Qué construí | 0:50 | +1 línea (sección 2) |
| 4 | Arquitectura | 1:20 | sin cambio |
| 5 | Supervisión de Claude Code | 1:15 | sin cambio (incluye alucinación) |
| 6 | Demo en vivo | 4:00 | reemplazo completo (sección 4) |
| 7 | Resultados verificados | 0:55 | ampliado (sección 3) |
| 8 | Adopción y riesgos | 1:00 | sin cambio |
| 9 | Retorno y recomendación | 0:55 | sin cambio |
| | **Total** | **11:35** | dentro de 10-12 min |

---

## 6. Checklist de demo (Fase 9)

### Antes de presentar
- [ ] Working tree en el estado que se va a presentar: DECIDIDO publicar con
      Bloque 7 + fix de Python 3.12 + las correcciones del Ciclo 6 incluidas
      (897 pruebas). Confirmar antes de la clase que el commit/push a `main`
      ya se hizo, para que ese número coincida con lo que un profesor vería
      clonando el repositorio (ver sección 3).
- [ ] `demo.cmd` corrido una vez completo, sin errores, ANTES de la clase —
      **en la máquina/red exactas donde se va a presentar, no solo en la
      máquina de desarrollo.** Hallazgo real (Ciclo 6, 2026-09-07): en la
      máquina de desarrollo, `demo.cmd` fue bloqueado por una directiva de
      Device Guard/AppLocker de la organización específicamente en
      `sibu-init-db.exe` (no en `sibu-run-suite.exe`, que sí corrió sin
      problema) — un bloqueo selectivo por ejecutable, no general. Si la
      política de la máquina/aula de presentación es la misma, la demo se
      cae ANTES de empezar. Mitigación de respaldo si se repite el bloqueo:
      `python -c "from sibutestlab8583.adapters.persistence.esquema import
      main; main()"` en vez de `sibu-init-db.exe` (y el equivalente
      `python -m` para `sibu-host-demo`/`uvicorn` si también estuvieran
      bloqueados) — practicar este comando de respaldo ANTES, no en vivo.
- [ ] `sibu-host-demo` corriendo (ventana visible, minimizada).
- [ ] Web (`uvicorn`) corriendo, `http://127.0.0.1:8000/` responde.
- [ ] Conexión `LOCAL-DEMO` activa.
- [ ] Tarjeta `DEMO-0001` activa.
- [ ] Escenario PASS creado (ver datos exactos en 4.2).
- [ ] Escenario FAIL creado (ver datos exactos en 4.2).
- [ ] Suite demo creada con ambos, en orden.
- [ ] Historial con al menos una ejecución previa (para que no se vea vacío
      al entrar por primera vez, antes de correr la demo en vivo).
- [ ] Terminal abierta, con el comando `run-suite` ya en el historial
      (flecha arriba lo trae, no hace falta tipearlo entero en vivo).
- [ ] Al menos una corrida ya ejecutada de antemano, para tener un
      `corrida_id` de respaldo por si el `export-run` en vivo falla.
- [ ] Pestaña de GitHub Actions abierta en el run verde específico (no en el
      listado general — directo al run, para no navegar en vivo).
- [ ] Terminal "limpia" (sin historial de comandos ajenos a la demo visible
      con flecha arriba, sin ventanas de otras cosas al alternar con Alt+Tab).

### Demo offline (si GitHub Actions no carga)
- Tener una captura de pantalla del run verde (`ci-suite-demo.yml`,
  14/14 steps verdes) guardada localmente, para mostrar en vez de navegar.
- Decir: "Esto ya corrió en GitHub Actions con éxito, tengo la captura acá
  por si la red no coopera hoy" — sin perder tiempo reintentando la carga.

### Demo offline (si internet falla del todo)
- La demo CENTRAL (pasos 0:00 a 3:20, salvo el paso de GitHub Actions a
  2:30) es 100% local — no depende de internet en ningún punto. Confirmar
  esto ANTES: `sibu-host-demo`, la web, y la CLI corren sin red externa.
- Si falla la red, saltar directo el paso 2:30 ("GitHub Actions") y decir la
  frase de la sección 4.1 igual, mostrando la captura de pantalla en vez de
  la pestaña en vivo.

### Plan B completo (si la app web falla en vivo)
Se mantiene el plan B ya existente en `PRESENTACION.md` (screenshots
pregrabados de 60s) — no se propone cambiarlo, solo ampliarlo con una
captura adicional de: Suites (corrida con PASS/FAIL visible) y terminal con
`export-run` ya ejecutado. Grabar ambas capturas ANTES de la clase, junto
con las 4 que ya existen.

---

## 6.1 Arranque de la demo sin depender de `demo.cmd` (Revisión final, 2026-09-07)

Distinto del "Plan B" de arriba (que cubre que la app web falle DURANTE la
demo en vivo): esto cubre que la demo **no pueda ni arrancar**, por el
hallazgo real de Ciclo 6 -Device Guard/AppLocker de la organización bloqueó
específicamente `sibu-init-db.exe` en la máquina de desarrollo (no
`sibu-run-suite.exe`, que sí corrió bien). Probado y confirmado real en esta
revisión: los mismos tres pasos funcionan sin tocar ningún `.exe`, usando
`python -m` sobre los módulos que esos `.exe` ya envuelven (`pyproject.toml`,
sección `[project.scripts]`).

**Recomendación de la revisión final: PLAN C como principal (llevar los
servicios ya levantados a la presentación), PLAN B como respaldo si hay que
reiniciar algo en vivo, y PLAN A (`demo.cmd`) solo como conveniencia -útil
para el ensayo previo o si la política de la máquina del aula lo permite,
nunca como el único plan probado.**

**PLAN A — arranque normal por conveniencia (solo si la política de la
máquina lo permite):**
```
demo.cmd
```
Desde la raíz del repositorio. Si Device Guard no bloquea nada en la
máquina/red de presentación, este es el paso más rápido para el ensayo
previo -pero no reemplaza probar el Plan C con anticipación real.

**PLAN B — arranque manual sin `demo.cmd`, respaldo si hay que reiniciar en
vivo o si Device Guard bloquea algún `.exe`:**
```
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m sibutestlab8583.adapters.persistence.esquema
```
En una terminal aparte (queda abierta durante la demo):
```
.venv\Scripts\python.exe -m sibutestlab8583.adapters.host_simulado.cli
```
En otra terminal aparte (queda abierta durante la demo):
```
.venv\Scripts\python.exe -m uvicorn sibutestlab8583.web.app:app
```
Abrir manualmente `http://127.0.0.1:8000/` en el navegador. Probado de
verdad en esta revisión (2026-09-07): los tres comandos funcionan, el host
queda escuchando en `127.0.0.1:8583`, la web responde `200` en `/`, y no
tocan ningún archivo `.exe` -si `sibu-run-suite.exe` también estuviera
bloqueado el día de la demo, su equivalente es
`.venv\Scripts\python.exe -m sibutestlab8583.cli run-suite ...` /
`export-run ...`, con los mismos subcomandos y argumentos ya documentados.

**PLAN C — demo ya levantada antes de entrar a presentar (PRINCIPAL):**
Ejecutar el Plan A (o el B, si el A falla) con suficiente anticipación -en
la máquina y la red exactas del aula, no solo en la máquina de desarrollo-,
dejar ambos procesos corriendo, verificar `http://127.0.0.1:8000/` y la
conexión TCP a `127.0.0.1:8583` ANTES de que empiece la clase, y entrar a
presentar con todo ya arriba. Así ningún problema de arranque (Device Guard
u otro) se descubre en vivo, frente al profesor. Plan B queda como
respaldo si hay que reiniciar algo a mitad de la exposición.

---

## 7. Preguntas difíciles y respuestas preparadas

**¿Por qué SQLite?**
> "Es un prototipo de un solo operador, sin necesidad de un servidor de base
> de datos aparte. `aiosqlite` me da persistencia asíncrona real sin sumar
> infraestructura. Si esto pasara a multiusuario, sería el primer cambio —
> ya lo tengo identificado como P0 para producción, no es un punto ciego."

**¿Por qué no Visa/Mastercard real?**
> "Porque no tengo documentación autorizada de sus especificaciones, y
> `CLAUDE.md` prohíbe explícitamente inventarlas — un perfil falso es peor
> que no tener perfil. Hoy trabajo con un perfil ISO 8583 genérico, y la
> arquitectura ya separa perfil de catálogo de respuestas para que agregar
> un perfil real, el día que tenga el documento, no toque el resto del
> sistema."

**¿Por qué se guarda el PAN?**
> "Solo en un lugar: el catálogo de tarjetas de prueba, porque sin el PAN
> completo no hay transacción que enviar al host. Nunca sale de ahí — el
> navegador, los logs, el historial y cualquier reporte exportado solo ven
> la versión enmascarada. Es una distinción deliberada entre 'dónde vive el
> dato' y 'quién lo puede ver'."

**¿Por qué CLI además de web?**
> "Porque un pipeline de integración continua no tiene navegador. La CLI
> reutiliza exactamente el mismo motor de ejecución que la web — no hay una
> segunda implementación de 'correr una suite', solo una segunda forma de
> invocarla."

**¿Por qué no concurrencia en las suites?**
> "Porque el alcance aprobado es un recorrido único de compra, y la
> concurrencia agrega una clase entera de bugs (condiciones de carrera,
> aislamiento de fallas) que no necesito para demostrar el valor central.
> Está identificado como el siguiente bloque posible, no como un olvido."

**¿Qué hizo Claude y qué supervisó usted?**
> "Claude escribió código bajo instrucciones mías, en bloques chicos y
> revisables. Yo definí el alcance, revisé cada diff antes de aceptarlo, y
> until ejecuté yo mismo las pruebas — no confié en que 'Claude dijo que
> pasó'. El caso de la alucinación del prefijo PAN es el ejemplo concreto:
> lo until encontré yo, no un test."

**¿Cómo detectó alucinaciones?**
> "Leyendo el código con la misma desconfianza con la que leería el de un
> compañero junior: toda afirmación sobre una norma externa (ISO, un
> estándar de tarjetas) la contrasté contra la fuente, no la di por buena
> porque sonara razonable."

**¿Qué parte vendería?**
> "El corredor de suites con Expected vs Actual y la integración de CI — es
> lo que un equipo de QA de pagos usa todos los días para regresión, y ya
> está probado de punta a punta, incluido un run real en GitHub Actions."

**¿Qué falta para producción?**
> "Autenticación y control de acceso, cifrado en tránsito del lado TCP,
> atribución de quién hizo qué, y perfiles reales de marca cuando exista la
> documentación autorizada. Los tengo priorizados, ninguno implementado
> todavía — se puede ver en la sección de riesgos."

**¿Qué tan reproducible es?**
> "Clon limpio, sin ningún estado local: `pip install`, inicializar la base,
> y ya. Lo probé en una segunda máquina, y además hay un pipeline de GitHub
> Actions que lo prueba en cada push, en tres versiones distintas de
> Python."

**¿Por qué Python?**
> "Por la librería `pyiso8583` ya existente para el codec, y porque
> `asyncio` me da concurrencia real para el transporte TCP sin la
> complejidad de hilos manuales."

**¿Qué aporta CI acá específicamente?**
> "Que 'funciona en mi máquina' deje de ser la única evidencia. Cada push
> corre la suite completa y, además, una suite de regresión de negocio de
> punta a punta -host simulado incluido- en un entorno limpio que no es el
> mío."

**¿Cómo garantiza que no expone PAN?**
> "Con una prueba automatizada que falla el build si aparece, en cualquier
> archivo versionado, una secuencia de 12 a 19 dígitos -el largo típico de
> un número de tarjeta-, más una guardia adicional específica sobre
> cualquier artefacto que se publique desde CI. No es una promesa, es una
> verificación que corre en cada cambio."

**¿Por qué la exportación usa snapshots y no vuelve a consultar el escenario
o la suite?**
> "Porque una corrida es evidencia histórica: si edito el escenario después,
> el reporte de una corrida pasada no debe cambiar retroactivamente. Guardo
> una copia literal del resultado en el momento en que ocurrió, no un
> puntero a datos que pueden moverse."

---

## 8. Riesgos de esta propuesta que el estudiante debe decidir

1. **La cifra "897 pruebas" ya está decidida** (ver sección 3) — sigue
   pendiente, eso sí, el paso mecánico de commitear Bloque 7 + fix de 3.12 +
   las correcciones del Ciclo 6 a `main` antes de presentar, para que el
   número que se muestra en la diapositiva coincida con lo que un profesor
   vería si clona el repositorio.
2. **4:00 de demo en vivo es más riesgo que 3:00** — más pasos, más
   superficie de fallo. El plan B ampliado (sección 6) mitiga esto, pero es
   una decisión real: demo más rica vs. demo más corta y más segura.
3. **Mostrar GitHub Actions en vivo depende de la red del aula** — el plan
   de captura de pantalla ya lo contempla, pero confirmar CON ANTICIPACIÓN
   que el wifi del lugar de la exposición no esté detrás de un portal
   cautivo que bloquee GitHub.

---

## 9. Ensayo cronometrado del guion completo (Ciclo 3 del cierre, 2026-09-07)

Metodología: se transcribió el guion COMPLETO tal como se hablaría (las 9
diapositivas, con el texto de "Qué construí"/"Demo en vivo"/"Resultados
verificados" ya corregidos según las secciones 2-4 de este documento), se
contó automáticamente la cantidad de palabras (`wc -w`), y se calculó la
duración a distintos ritmos de habla en español (100-140 palabras/minuto),
en vez de sumar estimaciones subjetivas por diapositiva como se había hecho
en la sección 5.

**Resultado (palabras reales, no estimado):**
- Guion completo: **1045 palabras** (669 de diapositivas + 341 palabras de
  narración de demo, sobre 376 palabras totales del bloque de demo contando
  también los 2 comandos de terminal literales).
- A 110 ppm (ritmo deliberado, típico de una defensa académica con pausas):
  **9:30** de habla pura.
- A 130 ppm (ritmo conversacional más rápido): **8:02**.

**Hallazgo real (no obvio, contradice la suma de la sección 5):** la suma de
tiempos estimados por diapositiva en la sección 5 da 11:35, pero un cálculo
basado en el conteo real de palabras da entre 8:00 y 9:30 de HABLA pura —
1:35 a 3:35 MENOS que lo estimado. La diferencia no es un error del guion:
son los silencios reales que un conteo de palabras no captura (pausas entre
diapositivas, tiempo de espera de clics/carga de página durante la demo,
pausas de énfasis). Aplicando un 15% de sobrecarga por pausas reales (cifra
conservadora, no inventada: es el rango típico citado para presentaciones
con transiciones y pausas deliberadas) sobre el cálculo a 110 ppm: **9:30 ×
1.15 ≈ 10:56** — SÍ entra en la ventana 10:00-12:00, pero con menos margen
del que sugería la sección 5, y con riesgo real de terminar por DEBAJO de
los 10:00 si el expositor habla rápido o no hace las pausas.

### Ensayo 1 (guion tal cual, sin marcar pausas)
Duración estimada: **~9:30 hablado + demo real** (ver Ciclo 2: la demo real,
sin narración, tomó ~2 min de navegación de punta a punta en la segunda
corrida limpia) ≈ **9:30-10:56** según cuánto se pause. Riesgo detectado:
sin pausas explícitas, el guion completo puede terminar en menos de 9:30,
por debajo del piso de 10:00 exigido.

### Ensayo 2 (guion corregido: mismas palabras, pausas explícitas marcadas)
Corrección aplicada: NO se agrega contenido nuevo (viola la regla de "no
reescribir"), se agregan 8 marcas de pausa deliberada de 2-3s en cada
transición entre diapositivas (8 × ~2.5s ≈ 20s) más una pausa deliberada
más larga (4-5s) después de la frase final de "Supervisión de Claude Code"
(sección con mayor peso diferenciador, se beneficia de que respire el
público). Estimado: 9:30 + ~1:00 de pausas reales ≈ **10:30**, dentro de la
ventana con margen razonable a ambos lados (1:30 hasta el piso, 1:30 hasta
el techo). **Mejor resultado de los tres ensayos.**

### Ensayo 3 (versión "más ejecutiva": recortar frases redundantes)
Se identificaron ~90-100 palabras recortables sin perder contenido (frases
como "Sonaba razonable, porque Visa y Mastercard efectivamente no lo usan"
→ "Sonaba razonable, pero era una generalización"). Resultado: ~950
palabras, **8:38 a 110 ppm**, empeora el problema del Ensayo 1 en vez de
resolverlo — menos palabras significa MÁS riesgo de terminar bajo los
10:00, no menos. **Se descarta este camino**: la corrección correcta es
ritmo/pausas (Ensayo 2), no recorte de texto.

**Conclusión Ciclo 3 — decisión recomendada:** adoptar el guion tal como
está (sin recortar), con el mapa de pausas del Ensayo 2. No se necesita
agregar ni quitar contenido. El riesgo real no es "demasiado largo" (como
sugería la estimación original de la sección 5) sino "demasiado corto si se
habla rápido sin pausar" — es la corrección exactamente inversa a la que se
habría hecho si solo se hubiera confiado en el "11:35" original sin medirlo.

---

## 9.1 Reconciliación final del guion (Revisión final, 2026-09-07)

En la revisión final se pidió explícitamente no confiar solo en el mapa de
pausas del Ensayo 2 y, si el guion queda por debajo de los 10 minutos a
velocidad normal, **ajustar el guion con contenido real, no rellenar con
texto vacío.** Se aplicó ese criterio: se agregaron 4 pasajes reales dentro
de las ÚNICAS tres secciones que esta propuesta puede tocar ("Qué
construí", "Resultados verificados" y la demo) —nunca en "El problema",
"La oportunidad", "Arquitectura", "Supervisión de Claude Code", "Adopción y
riesgos" ni "Retorno y recomendación", que siguen intactas sin excepción—:

1. "Qué construí": una cláusula real sobre qué produce `export-run` y para
   quién (+~30 palabras).
2. "Resultados verificados": la mención hablada del hallazgo de Python 3.12
   y de que se verificó en 3 versiones con evidencia real de CI en vez de
   confiar en una explicación (+~75 palabras) — es la única mención hablada
   de ese hallazgo en todo el guion.
3. Demo, paso 0:20: una frase real sobre qué muestra el isoscopio y por qué
   sigue enmascarando el PAN ahí (+~50 palabras).
4. Demo, paso 1:10: una frase real sobre aislamiento de fallas por
   escenario en el corredor de suites (+~55 palabras).
5. Demo, pasos 1:40 y 2:55 (ya agregados en el Ciclo 3 original, se
   mantienen): por qué Expected-vs-Actual importa para regresión real, y
   por qué el reporte exportado es un snapshot histórico inmutable.

**Resultado recontado (`wc -w` sobre el guion completo con estas 4
ampliaciones aplicadas): 1331 palabras** (antes 1045).

| Ritmo | Duración |
|---|---|
| 120 ppm (deliberado) | **11:06** |
| 130 ppm (normal) | **10:14** |
| 140 ppm (rápido) | **9:30** |

**Conclusión:** a ritmo normal a deliberado (120-130 ppm), el guion cae
sólidamente dentro de la ventana de 10 a 12 minutos, sin necesidad de
pausas adicionales artificiales. Solo a un ritmo rápido (140 ppm) queda
9:30, un poco corto — pero 140 ppm es una velocidad de habla rápida para
una defensa técnica con transiciones de diapositiva y clics de demo
intercalados; con las pausas naturales de esas transiciones (ver Ensayo 2:
~8 pausas de transición + demo real) el tiempo total real, incluso a ese
ritmo, se acerca a los 10:30-11:00. No se agregó ningún relleno: las 4
ampliaciones son afirmaciones verificadas contra el código real, no texto
decorativo.

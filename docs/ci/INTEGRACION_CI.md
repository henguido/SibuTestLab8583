# Integración CI genérica para suites de regresión

Bloque 6. Meta: una suite guardada puede ejecutarse automáticamente dentro de un
pipeline de CI usando la CLI ya existente (`sibu-run-suite`), fallando el pipeline según
el resultado real de la suite y dejando una salida útil para revisión.

Este documento describe el flujo **genérico** (portable a cualquier CI) y cómo
GitHub Actions lo implementa como referencia. No hay una segunda implementación de la
ejecución: el pipeline corre exactamente los mismos comandos que se documentan en
[`README.md`](../../README.md#ejecutar-una-suite-de-regresión-por-línea-de-comandos-ci).

## Lógica portable vs. adaptador de GitHub

**Lógica portable** — vive en comandos de línea de comandos ya versionados, sin
depender de ningún proveedor de CI:

| Paso | Comando |
|---|---|
| Inicializar la base de datos | `sibu-init-db` |
| Sembrar (o reutilizar) datos de demo | `python scripts/sembrar_suite_demo.py` |
| Levantar el host ISO 8583 simulado | `sibu-host-demo` |
| Esperar a que el host esté listo | `python scripts/ci_esperar_host.py --host 127.0.0.1 --puerto 8583 --timeout 15` |
| Ejecutar la suite | `sibu-run-suite run-suite "$SUITE_ID" --format json > corrida.json` |
| Verificar el artefacto antes de publicarlo | `python scripts/verificar_artefacto_seguro.py corrida.json` |

**Adaptador de GitHub** — únicamente sintaxis de orquestación, sin lógica de negocio:

- [`.github/workflows/ci-suite-demo.yml`](../../.github/workflows/ci-suite-demo.yml)
- `actions/upload-artifact` (publicar `corrida.json`)
- `if: always()` (que limpieza y artefacto corran aunque la suite falle)

Migrar este flujo a Jenkins, Azure DevOps o GitLab CI significa reescribir **solo** la
lista de arriba (columna "adaptador"): la columna "lógica portable" se copia literal,
comando por comando, sin traducir nada. Ningún paso de la tabla portable conoce el
concepto de "step", "job" ni "artifact" de ningún proveedor.

### Ejemplo de adaptación (ilustrativo, no ejecutado por este repositorio)

```yaml
# GitLab CI (.gitlab-ci.yml) — mismos comandos, sintaxis distinta.
suite-demo:
  stage: test
  script:
    - pip install -e ".[dev]"
    - sibu-init-db
    - SUITE_ID=$(python scripts/sembrar_suite_demo.py | sed 's/SUITE_ID=//')
    - sibu-host-demo &
    - python scripts/ci_esperar_host.py --host 127.0.0.1 --puerto 8583 --timeout 15
    - sibu-run-suite run-suite "$SUITE_ID" --format json > corrida.json || CODIGO=$?
    - python scripts/verificar_artefacto_seguro.py corrida.json
    - kill %1 || true
    - exit ${CODIGO:-0}
  artifacts:
    when: always
    paths: [corrida.json]
```

```groovy
// Jenkinsfile (declarative) — mismo principio: capturar el exit code real,
// nunca dejar que un pipe se lo coma.
stage('Suite demo') {
    steps {
        sh 'pip install -e ".[dev]"'
        sh 'sibu-init-db'
        script {
            env.SUITE_ID = sh(script: 'python scripts/sembrar_suite_demo.py | sed "s/SUITE_ID=//"', returnStdout: true).trim()
        }
        sh 'sibu-host-demo & echo $! > host.pid'
        sh 'python scripts/ci_esperar_host.py --host 127.0.0.1 --puerto 8583 --timeout 15'
        script {
            env.CODIGO = sh(script: "sibu-run-suite run-suite ${env.SUITE_ID} --format json > corrida.json; echo \$?", returnStdout: true).trim()
        }
        sh 'python scripts/verificar_artefacto_seguro.py corrida.json'
    }
    post {
        always {
            sh 'kill $(cat host.pid) 2>/dev/null || true'
            archiveArtifacts artifacts: 'corrida.json'
        }
    }
}
```

## Política de exit codes

Fuente de verdad única: el exit code real de `sibu-run-suite` (ver la tabla completa en
[`README.md`](../../README.md)). Política de este pipeline:

| Resultado | Código | ¿Éxito de pipeline? |
|---|---|---|
| PASS | 0 | Sí |
| Cualquier otro (FAIL, ERROR, INCOMPLETA, SIN_EXPECTATIVAS, suite no ejecutable, fallo de CLI, interrumpido) | 1/2/3/4/5/6/130 | No |

**Solo PASS es éxito.** SIN_EXPECTATIVAS (código 4) se trata como fallo a propósito: una
suite sin ninguna expectativa declarada no está verificando nada, y un pipeline verde ahí
sería falsa confianza.

## Preservar el exit code en shell (pipes, `set -e`, redirecciones)

Los steps de bash en GitHub Actions corren con `set -e` (y `-o pipefail`) por defecto: un
comando que falla aborta el step de inmediato. Esto es exactamente lo que se quiere para
un step normal, pero complica capturar el código real cuando además hace falta limpieza y
publicación de artefacto **después** de una suite fallida. El diseño de este pipeline:

1. **Nunca usar `| tee`** para el JSON: se usa `>` (redirección), no un pipe, así el `$?`
   inmediatamente después es siempre el de `sibu-run-suite`, sin intermediarios que
   puedan sustituirlo.
2. El step que ejecuta la suite envuelve la llamada en `set +e` / `set -e`, captura
   `codigo=$?` explícitamente, lo escribe a `$GITHUB_OUTPUT`, y termina con `exit 0` — así
   los steps siguientes (mostrar el JSON, verificar el artefacto, detener el host, subir
   el artefacto) corren siempre, sin depender de encadenar `if: always()` sobre un step
   ya marcado como fallido.
3. Un último step, también `if: always()`, lee ese código guardado y hace
   `exit "$codigo"` — es la única fuente de verdad del resultado del job.

## Manejo del host demo

- Se levanta explícitamente (`sibu-host-demo &`) solo en este pipeline de demo/CI —
  nunca lo levanta `sibu-run-suite` por su cuenta (ver su docstring en
  [`cli.py`](../../src/sibutestlab8583/cli.py)).
- `scripts/ci_esperar_host.py` sondea `host:puerto` con `socket.create_connection`
  (solo librería estándar) hasta que responde o se agota un timeout configurable —evita
  la carrera de arrancar la suite antes de que el host esté realmente escuchando.
- Se detiene siempre (`if: always()`), incluso si la suite falla: un host que sigue vivo
  no debe sobrevivir al job.
- No se modificó `sibu-host-demo`: no maneja `SIGTERM` de forma especial (solo
  `KeyboardInterrupt`/`SIGINT`), pero para un proceso descartable de CI esto es
  irrelevante — el puerto se libera igual al matar el proceso.

## Datos de prueba (siembra)

`sibu-init-db` ya siembra tarjeta y destino de demostración
(`CARD_ID_DEMO`/`DESTINO_ID_DEMO`), pero ningún escenario ni suite — eso solo existía
antes desde la interfaz web. `scripts/sembrar_suite_demo.py` cierra ese hueco:

- Crea (o reutiliza) **un** escenario y **una** suite con nombres fijos reservados
  (`[CI] Escenario demo` / `[CI] Suite demo`).
- **Idempotente**: busca primero por nombre exacto; si ya existe exactamente uno, lo
  reutiliza; si encuentra más de una coincidencia con el nombre reservado, se detiene con
  un mensaje claro en vez de elegir una al azar (evidencia de que algo ajeno ya usa ese
  nombre).
- Imprime **exactamente una línea** a stdout: `SUITE_ID=<id>` — cualquier otro mensaje va
  a stderr, para que un pipeline la capture con una asignación simple, sin parsing.
- En CI se corre siempre contra una base de datos **efímera** (una ruta temporal del
  runner, vía `SIBU_DB_PATH`), así que la idempotencia es una garantía de robustez del
  script versionado, no algo de lo que este pipeline dependa en la práctica.

## Artefactos

- **`corrida.json`** — el único artefacto oficial, siempre publicado (`if: always()`),
  incluso cuando la suite falla: es exactamente la evidencia que alguien necesita para
  revisar qué pasó.
- **`host-demo.log`** — el host redirige su stdout/stderr a este archivo para
  diagnóstico local, pero **no se publica por defecto**: menor superficie de datos,
  contrato de CI más chico. Quien necesite verlo puede correr el mismo pipeline
  localmente (ver más abajo) o ajustar el workflow para subirlo también.

## Seguridad y PAN

Nunca se publica: el archivo `.db` de CI (se descarta con el runner), ningún PAN, ni
mensajes ISO crudos. La CLI ya lo garantiza por diseño (Bloque 3/4): `evaluacion_json`
nunca contiene PAN. Además, `scripts/verificar_artefacto_seguro.py` corre como guardia
específica sobre el artefacto ya generado, antes de publicarlo, y falla el step si
encuentra:

- una secuencia de 12 a 19 dígitos (mismo criterio que la guardia PAN de la suite de
  pruebas, `tests/test_datos_sinteticos.py`);
- cualquiera de estas claves/textos: `solicitud_json`, `respuesta_json`,
  `solicitud_enmascarada`, `respuesta_enmascarada`, `pan_completo`, `track1`, `track2`.

Esto **no** es una garantía nueva ni reemplaza nada: es una segunda comprobación barata
sobre el archivo que efectivamente se sube, complementaria a que el sistema ya no extrae
ni copia PAN desde tarjetas/mensajes hacia ningún snapshot persistido. No se escanean
nombres libres de escenario buscando "parecer un PAN" — eso no sería una prueba válida.

## Ejemplo de corrida local equivalente al workflow

```bash
export SIBU_DB_PATH=/tmp/ci-suite-demo.db
sibu-init-db
SUITE_ID=$(python scripts/sembrar_suite_demo.py | sed 's/SUITE_ID=//')
sibu-host-demo > /tmp/host-demo.log 2>&1 &
HOST_PID=$!
python scripts/ci_esperar_host.py --host 127.0.0.1 --puerto 8583 --timeout 15
sibu-run-suite run-suite "$SUITE_ID" --format json > corrida.json
CODIGO=$?
cat corrida.json
python scripts/verificar_artefacto_seguro.py corrida.json
kill "$HOST_PID" 2>/dev/null || true
exit "$CODIGO"
```

## Limitaciones

- No hay ejecución paralela, scheduler, API pública, autenticación, reportes
  PDF/Excel, integración profunda con un proveedor específico, secretos reales ni
  despliegue productivo — deliberadamente fuera de alcance de este bloque.
- El workflow de referencia está pensado para terminar en PASS: la CLI ya tiene
  pruebas automatizadas exhaustivas para los demás exit codes
  (`tests/test_cli.py`), así que no se mantiene una segunda variante del workflow
  que fuerce FAIL solo para "demostrarlo" en Actions.
- `sibu-host-demo` no maneja `SIGTERM` explícitamente — ver "Manejo del host demo".

# SibuTestLab8583

Simulador de transacciones ISO 8583: construye una compra (`0100`), la transmite por TCP a
un host receptor, interpreta y valida la respuesta (`0110`), y persiste la ejecución en
SQLite. Alcance y reglas de negocio completos en [`PROYECTO.md`](PROYECTO.md).

## Requisitos

- **Python 3.13 o superior**, disponible en el `PATH` como `python`.
- Git.
- Windows, Linux o macOS. `demo.cmd` (arranque de un clic) está validado en Windows; el
  procedimiento manual de abajo incluye instrucciones para los tres sistemas, pero no se
  ha probado de punta a punta en Linux/macOS todavía.

## Camino rápido (recomendado para Windows)

```bash
git clone https://github.com/henguido/SibuTestLab8583.git
cd SibuTestLab8583
demo.cmd
```

`demo.cmd` automatiza todo el arranque:

1. Comprueba que el comando `python` esté disponible y sea `>= 3.13`. Si no lo encuentra,
   se detiene con instrucciones — nunca instala Python por su cuenta.
2. Crea `.venv` si no existe, o lo reutiliza si ya es válido. Si existe pero está roto o
   corresponde a una versión incompatible, explica lo encontrado y pide confirmación antes
   de reconstruirlo.
3. Instala/confirma las dependencias (`pip install -e ".[dev]"`).
4. Inicializa la base de datos y los datos de demostración (`sibu-init-db`).
5. Comprueba que los puertos 8583 y 8000 estén libres. Si alguno está ocupado, se detiene
   e indica cuál — no cambia de puerto automáticamente.
6. Levanta el host ISO 8583 simulado y la aplicación web, cada uno en su propia ventana.
7. Espera a que la web responda de verdad (no un tiempo fijo) y abre
   `http://127.0.0.1:8000/` en el navegador predeterminado.

Para detener la demostración: cierre las ventanas del host y de la aplicación web, o
presione Ctrl+C en cada una.

`demo.cmd` es un facilitador, no una vía de instalación alternativa: cada paso invoca
exactamente los mismos comandos que el procedimiento manual de abajo. Si algo falla ahí,
falla igual el paso manual equivalente.

## Camino manual (Windows, Linux/macOS)

```bash
git clone https://github.com/henguido/SibuTestLab8583.git
cd SibuTestLab8583
python -m venv .venv
```

Activar el entorno:

- Windows (PowerShell): `.venv\Scripts\Activate.ps1`
- Windows (cmd): `.venv\Scripts\activate.bat`
- Linux/macOS: `source .venv/bin/activate`

Instalar e inicializar:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
sibu-init-db
```

Levantar el prototipo — **el host simulado y la aplicación web corren en dos terminales
separadas**, ambas abiertas desde la raíz del repositorio (la base de datos se resuelve
por ruta relativa al directorio de trabajo). Una terminal nueva no hereda el `.venv`
activado en la anterior: cada una debe activarlo de nuevo antes de su comando.

**Windows (PowerShell):**
```powershell
# Terminal 1
.venv\Scripts\Activate.ps1
sibu-host-demo

# Terminal 2
.venv\Scripts\Activate.ps1
uvicorn sibutestlab8583.web.app:app
```

**Linux/macOS:**
```bash
# Terminal 1
source .venv/bin/activate
sibu-host-demo

# Terminal 2
source .venv/bin/activate
uvicorn sibutestlab8583.web.app:app
```

Abrir en el navegador: **http://127.0.0.1:8000/**

## Recorrido de demostración

1. Abrir **Nueva transacción** (pantalla inicial).
2. Elegir la tarjeta **`DEMO-0001`**.
3. Escribir un monto en el campo **Monto** (el valor que se ve ahí, ej. `150.00`,
   es solo un placeholder de ejemplo, no un valor precargado — el formulario no
   se envía si se deja vacío) y ejecutar la compra.
4. Revisar el resultado: estado, código de respuesta e isoscopio con los campos ISO 8583
   (el número de tarjeta siempre enmascarado, `************6666`).
5. Ir a **Historial** — la ejecución queda listada.
6. Abrir su **detalle** desde el historial.
7. Ir a **Escenarios** — guardar la transacción recién ejecutada como caso reutilizable.
8. Ir a **Suites** — agrupar escenarios y ejecutar una suite completa desde el navegador
   (misma ejecución que expone `sibu-run-suite`, ver más abajo); revisar la corrida resultante.
9. Entrar a **Configuración**.
10. Revisar **Tarjetas de prueba** — administración del catálogo (crear, editar,
    activar/desactivar).

## Ejecutar una suite de regresión por línea de comandos (CI)

Una suite guardada (ver "Suites" en la interfaz web) se puede correr sin navegador, con un
código de salida apto para un pipeline de CI. Usa la misma composición y el mismo
`CorredorDeSuites` que la web — no hay una segunda implementación de la ejecución.

Requiere la instalación editable ya hecha (`pip install -e ".[dev]"`, ver arriba) y la base
de datos inicializada (`sibu-init-db`).

Listar las suites guardadas, para obtener su `suite_id`:

```bash
sibu-run-suite list-suites
```

Ejecutar una suite por id (forma primaria, sin ambigüedad):

```bash
sibu-run-suite run-suite SUI-xxxxxxxx
```

Ejecutar por nombre exacto (conveniencia; falla si el nombre no es único):

```bash
sibu-run-suite run-suite --nombre "Regresión nocturna"
```

`suite_id` y `--nombre` son mutuamente excluyentes: indique exactamente uno.

Salida para consumo automático, en vez de texto para lectura humana:

```bash
sibu-run-suite run-suite SUI-xxxxxxxx --format json
```

También invocable como módulo, sin depender del script instalado:

```bash
python -m sibutestlab8583.cli run-suite SUI-xxxxxxxx
```

**Códigos de salida:**

| Código | Significado |
|---|---|
| `0` | Resultado de la corrida: PASS |
| `1` | Resultado de la corrida: FAIL |
| `2` | Resultado de la corrida: ERROR (algún escenario no se pudo ejecutar) |
| `3` | Resultado de la corrida: INCOMPLETA (mezcla de PASS y escenarios sin expectativas) |
| `4` | Resultado de la corrida: SIN EXPECTATIVAS (ningún escenario definía qué esperaba) |
| `5` | La suite no se pudo ejecutar: no existe, está inactiva, está vacía, o `--nombre` no resolvió a una única suite |
| `6` | Fallo técnico o de uso de la propia CLI (argumentos inválidos, base de datos inaccesible) |
| `130` | Interrumpido con Ctrl+C — la corrida puede haber quedado registrada como en curso |

La CLI nunca levanta `sibu-host-demo` por su cuenta: si la conexión configurada para un
escenario no responde, eso se registra como el `ERROR` de ese escenario dentro de la
corrida, igual que en la interfaz web.

Este mismo comando es lo que ejecuta automáticamente el pipeline de CI de referencia
(`.github/workflows/ci-suite-demo.yml`) en cada push — ver
[`docs/ci/INTEGRACION_CI.md`](docs/ci/INTEGRACION_CI.md) para el flujo completo (siembra de
datos, host demo, exit codes, artefacto) y cómo adaptarlo a Jenkins/Azure DevOps/GitLab.

## Exportar el reporte de una corrida ya persistida

`export-run` arma un reporte portable y autosuficiente (JSON o CSV) de una corrida **ya
registrada**, a partir de su propio snapshot histórico — nunca vuelve a ejecutar la suite, ni
relee el escenario/suite/expectativas tal como están hoy (que pueden haber cambiado desde
entonces). Es distinto de `run-suite`: su código de salida solo dice si el reporte se pudo
generar (`0`) o si la corrida no existe (`1`), nunca codifica PASS/FAIL/etc. de esa corrida.

```bash
sibu-run-suite export-run 42 --format json
sibu-run-suite export-run 42 --format csv --out reporte.csv
```

El CSV tiene una fila por escenario de la corrida, con columnas estables (incluidos los datos
de la corrida repetidos en cada fila, para que el archivo sea autosuficiente). Ni el JSON ni el
CSV contienen PAN, PIN, Track1/Track2 ni mensajes ISO crudos — solo lo que el snapshot de la
corrida ya tenía persistido.

## Ejecutar las pruebas

```bash
python -m pytest -q
```

Solo las reglas de negocio (RN-1 a RN-4, ver [`PROYECTO.md`](PROYECTO.md) §4):

```bash
python -m pytest tests/test_reglas_negocio.py -v
```

> Nota de estado, no un requisito fijo: al momento de escribir esto la suite completa
> pasa en verde. El número exacto de pruebas crece con cada iteración — no se documenta
> aquí como cifra a mantener.

## Limitaciones actuales

Este es el estado real del prototipo, no una lista de fallos:

- **Motor de pruebas de carga:** no implementado. Fase posterior, ver el
  [documento de arquitectura](docs/arquitectura/ARQUITECTURA.md).
- **Perfiles reales de Visa/Mastercard:** no implementados. Se trabaja con un único
  perfil ISO 8583 genérico.
- **DE35/DE45 (Track 1/Track 2):** Track 1 y Track 2 ya tienen derivación lógica pura en
  el dominio, pero todavía no se transmiten en el mensaje ISO.
- **PIN e infraestructura de llaves:** no hay PIN criptográficamente válido ni
  infraestructura de cifrado — los valores de laboratorio son solo de forma, no de
  seguridad real.

## Documentación adicional

- [PROYECTO.md](PROYECTO.md) — alcance aprobado, recorrido principal y reglas de negocio.
- [CLAUDE.md](CLAUDE.md) — convenciones, arquitectura y políticas del repositorio.
- [BITACORA.md](BITACORA.md) — decisiones, correcciones de rumbo y gobernanza del proceso.
- [Documento de arquitectura](docs/arquitectura/ARQUITECTURA.md) — diseño detallado y
  diagramas.
- [Integración CI](docs/ci/INTEGRACION_CI.md) — cómo correr una suite de regresión en un
  pipeline, política de exit codes y adaptación a otros proveedores de CI.

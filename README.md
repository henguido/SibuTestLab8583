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
3. Ejecutar la compra.
4. Revisar el resultado: estado, código de respuesta e isoscopio con los campos ISO 8583
   (el número de tarjeta siempre enmascarado, `************6666`).
5. Ir a **Historial** — la ejecución queda listada.
6. Abrir su **detalle** desde el historial.
7. Entrar a **Configuración**.
8. Revisar **Tarjetas de prueba** — administración del catálogo (crear, editar,
   activar/desactivar).

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

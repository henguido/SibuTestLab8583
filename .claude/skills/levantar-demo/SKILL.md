---
name: levantar-demo
description: Prepara y verifica la demostración de SibuTestLab8583 reutilizando demo.cmd. Usar cuando el usuario pida preparar, levantar, iniciar o dejar lista la demo del proyecto.
---

# Levantar demo de SibuTestLab8583

Orquesta el arranque de la demostración reutilizando `demo.cmd`, que es la única fuente de
verdad para instalación y arranque. Este skill no reimplementa nada de lo que hace
`demo.cmd`: no ejecuta `python -m venv`, `pip`, `sibu-init-db`, `sibu-host-demo` ni
`uvicorn` por su cuenta. Su trabajo es ejecutar `demo.cmd`, interpretar su resultado, y
verificar el resultado de forma independiente antes de decir que la demo está lista.

## Paso 1 — Confirmar el repositorio

Comprobar que existe `demo.cmd` en la raíz del directorio de trabajo actual.

- Si no existe: detenerse. Informar que el directorio actual no parece ser la raíz de
  SibuTestLab8583 y pedir la ruta correcta, o pedir que se posicione en ella. No buscar
  `demo.cmd` en otras carpetas ni adivinar rutas.
- Si existe: continuar.

## Paso 2 — Ejecutar demo.cmd

Ejecutar `demo.cmd` desde la raíz del repositorio, sin argumentos, sin modificarlo y sin
envolverlo en lógica adicional propia. No redirigir su salida a la nada ni encadenarlo con
otros comandos: se necesita ver lo que imprime para poder relayarlo si algo falla o si pide
una confirmación.

No duplicar dentro de este skill ningún comando de creación de `.venv`, `pip`,
`sibu-init-db`, `sibu-host-demo` ni `uvicorn`. Toda esa lógica tiene una sola fuente:
`demo.cmd`.

### Si demo.cmd pide una confirmación destructiva

`demo.cmd` puede preguntar interactivamente `Eliminarlo y crear uno nuevo? [s/N]` cuando
encuentra un `.venv` roto o de una versión de Python incompatible. Si aparece esa pregunta
(o cualquier otra confirmación de `demo.cmd`):

- Detenerse ahí. Mostrar al usuario el diagnóstico que `demo.cmd` haya impreso (versión
  detectada, motivo) y la pregunta tal cual.
- No responder "s" ni "N" por cuenta propia. No borrar `.venv` como atajo. No decidir en
  nombre del usuario.
- Continuar solo cuando el usuario haya dado su respuesta explícita.

### Si demo.cmd falla

`demo.cmd` puede terminar con código de salida distinto de cero por varias razones: Python
`>= 3.13` no disponible como `python`, falla `pip install -e ".[dev]"`, falla
`sibu-init-db`, o el puerto 8583 y/o 8000 ya está ocupado. En cualquiera de estos casos:

- Reportar el mensaje real que imprimió `demo.cmd`, sin resumirlo ni reinterpretarlo.
- Detenerse ahí. No continuar al Paso 3.
- No matar procesos, no cambiar de puerto, no instalar ni reinstalar Python, no reintentar
  con otra versión ni con otro intérprete, no editar `pyproject.toml` ni ningún otro
  archivo. Ninguna remediación automática.

## Paso 3 — Verificación independiente

Si `demo.cmd` terminó con código de salida 0, no dar la demo por lista solo porque
`demo.cmd` haya impreso su mensaje de éxito. Verificarlo de forma independiente usando el
Python del entorno ya preparado por `demo.cmd`, `.venv\Scripts\python.exe`, y únicamente
librería estándar (no agregar dependencias nuevas, no requerir PowerShell):

- **Web:** comprobar que `http://127.0.0.1:8000/` responde, con `urllib.request`.
- **Host ISO8583:** comprobar que `127.0.0.1:8583` acepta conexión, con
  `socket.create_connection(("127.0.0.1", 8583), timeout=...)`.

Ejemplo del tipo de verificación a ejecutar con `.venv\Scripts\python.exe`:

```python
import socket
import urllib.request

def web_responde(url="http://127.0.0.1:8000/", timeout=3):
    try:
        urllib.request.urlopen(url, timeout=timeout)
        return True
    except Exception:
        return False

def puerto_acepta_conexion(host="127.0.0.1", puerto=8583, timeout=3):
    try:
        with socket.create_connection((host, puerto), timeout=timeout):
            return True
    except OSError:
        return False
```

- Si **ambas** comprobaciones tienen éxito: continuar al Paso 4.
- Si **alguna falla**, incluso si `demo.cmd` había reportado éxito: no confirmar la demo
  como lista. Informar al usuario exactamente cuál de las dos verificaciones falló, aclarar
  que `demo.cmd` no cerró ninguna ventana (el host y la web pueden seguir corriendo en sus
  propias consolas), y sugerir revisarlas manualmente. No matar procesos, no reintentar en
  otro puerto, no volver a lanzar `demo.cmd` automáticamente.
- Un reintento breve de la propia verificación (unos pocos segundos adicionales) es
  razonable si `demo.cmd` ya había avisado que la web no respondió dentro de sus 20
  segundos, antes de darse por vencido. Si sigue sin responder, reportarlo igual que
  cualquier otro fallo de verificación: no ocultarlo.

## Paso 4 — Confirmar al usuario

Solo si ambas verificaciones del Paso 3 tuvieron éxito, informar algo equivalente a:

```
SibuTestLab listo para demostración.

Web:
http://127.0.0.1:8000/

Host ISO8583:
127.0.0.1:8583

Tarjeta sugerida:
DEMO-0001
```

Recordar cómo detener la demostración cuando termine: cerrar las ventanas de consola "Host
ISO8583" y "Aplicación web" que `demo.cmd` abrió, o presionar Ctrl+C dentro de cada una —
exactamente como ya indica el propio `demo.cmd` al finalizar. Este skill no ofrece ni
necesita un mecanismo separado para detener la demostración.

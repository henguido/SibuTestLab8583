@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

rem =============================================================================
rem  demo.cmd - Arranque rapido de SibuTestLab8583 para la demostracion.
rem
rem  Facilitador de demostracion, no una via de instalacion alternativa: cada
rem  paso invoca exactamente los mismos comandos que documenta README.md
rem  (pip install -e ".[dev]", sibu-init-db, sibu-host-demo, uvicorn). Si algo
rem  falla aqui, el mismo paso manual del README fallaria igual.
rem
rem  Supuesto conocido: esta version asume que la ruta del repositorio no
rem  contiene espacios (los comandos "start ... .venv\Scripts\..." no citan
rem  la ruta). La ruta de desarrollo actual no los tiene.
rem =============================================================================

echo ============================================
echo  SibuTestLab8583 - Arranque rapido (demo.cmd)
echo ============================================
echo.

rem --- 1. Comprobar que "python" este disponible y sea >= 3.13 -----------------
rem Se exige el comando "python" especificamente: nada de "py" ni "py -3.13".
rem El launcher "py" de las instalaciones nuevas de Windows puede descargar e
rem instalar un runtime como efecto lateral de solo consultar una version
rem (comprobado en esta misma maquina), asi que se elimina esa dependencia por
rem completo del camino de arranque de la demostracion.
set "PYCMD="

python -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 13) else 1)" >nul 2>&1
if not errorlevel 1 (
    set "PYCMD=python"
    goto :python_encontrado
)

echo [ERROR] Se requiere Python 3.13 o superior disponible como "python".
echo.
echo No se encontro un interprete "python" compatible ^(^>= 3.13^) en esta
echo maquina. Instale Python 3.13 o superior desde
echo https://www.python.org/downloads/, confirme que "python" quede
echo disponible, y vuelva a ejecutar demo.cmd.
goto :fin_con_error

:python_encontrado
echo Python compatible ^(^>= 3.13^) localizado con: !PYCMD!
echo.

rem --- 2. Comprobar o crear el entorno virtual ---------------------------------
set "VENV_OK=0"
set "VENV_VER=(no existe)"

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" --version >nul 2>&1
    if errorlevel 1 (
        set "VENV_VER=(no se pudo ejecutar: interprete ausente o entorno de otra maquina)"
    ) else (
        for /f "delims=" %%v in ('".venv\Scripts\python.exe" --version 2^>^&1') do set "VENV_VER=%%v"
        rem La compatibilidad se decide igual que en la seccion 1: por
        rem sys.version_info dentro del propio interprete, nunca por texto.
        rem VENV_VER solo se conserva para el mensaje informativo si hace
        rem falta reconstruir el entorno.
        ".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 13) else 1)" >nul 2>&1
        if not errorlevel 1 set "VENV_OK=1"
    )
)

if exist ".venv\Scripts\python.exe" if "!VENV_OK!"=="0" (
    echo El entorno .venv existente no funciona o no es Python 3.13.
    echo Version detectada: !VENV_VER!
    echo.
    set /p "CONFIRMAR=Eliminarlo y crear uno nuevo? [s/N]: "
    if /i not "!CONFIRMAR!"=="s" (
        echo.
        echo Operacion cancelada. Resuelva el entorno .venv existente ^(o elimine la
        echo carpeta manualmente^) y vuelva a ejecutar demo.cmd.
        goto :fin_con_error
    )
    echo Eliminando .venv anterior...
    rmdir /s /q ".venv"
    if exist ".venv" (
        echo [ERROR] No se pudo eliminar la carpeta .venv existente.
        goto :fin_con_error
    )
)

if not exist ".venv\Scripts\python.exe" (
    echo Creando entorno virtual en .venv con Python 3.13...
    !PYCMD! -m venv .venv
    if errorlevel 1 (
        echo [ERROR] No se pudo crear el entorno virtual.
        goto :fin_con_error
    )
    echo Entorno virtual creado.
    echo.
)

rem --- 3. Instalar o confirmar dependencias -------------------------------------
echo Instalando/confirmando dependencias ^(pip resuelve si ya estan al dia^)...
".venv\Scripts\python.exe" -m pip install -e ".[dev]"
if errorlevel 1 (
    echo [ERROR] Fallo la instalacion de dependencias.
    goto :fin_con_error
)
echo.

rem --- 4. Inicializar datos de demostracion -------------------------------------
echo Inicializando base de datos y datos de demostracion...
".venv\Scripts\sibu-init-db.exe"
if errorlevel 1 (
    echo [ERROR] Fallo la inicializacion de la base de datos.
    goto :fin_con_error
)
echo.

rem --- 5. Comprobar que los puertos 8583 y 8000 esten libres --------------------
echo Comprobando puertos 8583 y 8000...
set "PUERTO_OCUPADO="

netstat -ano | findstr /C:":8583 " >nul
if not errorlevel 1 set "PUERTO_OCUPADO=8583"

netstat -ano | findstr /C:":8000 " >nul
if not errorlevel 1 (
    if defined PUERTO_OCUPADO (
        set "PUERTO_OCUPADO=!PUERTO_OCUPADO! y 8000"
    ) else (
        set "PUERTO_OCUPADO=8000"
    )
)

if defined PUERTO_OCUPADO (
    echo [ERROR] El puerto !PUERTO_OCUPADO! ya esta en uso.
    echo Cierre el proceso que lo esta usando y vuelva a ejecutar demo.cmd.
    echo Esta version no cambia de puerto automaticamente: la URL y el destino
    echo del host simulado deben quedar predecibles para la demostracion.
    goto :fin_con_error
)
echo Puertos libres.
echo.

rem --- 6. Levantar el host simulado y la aplicacion web, cada uno en su ventana -
echo Levantando el host ISO8583 simulado ^(127.0.0.1:8583^)...
start "SibuTestLab - Host ISO8583 (127.0.0.1:8583)" cmd /k .venv\Scripts\sibu-host-demo.exe

echo Levantando la aplicacion web ^(127.0.0.1:8000^)...
start "SibuTestLab - Aplicacion web (127.0.0.1:8000)" cmd /k .venv\Scripts\uvicorn.exe sibutestlab8583.web.app:app
echo.

rem --- 7. Esperar a que la web responda de verdad antes de abrir el navegador --
echo Esperando a que la aplicacion web responda ^(hasta 20 segundos^)...
set "WEB_LISTO=0"
for /l %%i in (1,1,20) do (
    if "!WEB_LISTO!"=="0" (
        ".venv\Scripts\python.exe" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/', timeout=1)" >nul 2>&1
        if not errorlevel 1 (
            set "WEB_LISTO=1"
        ) else (
            ".venv\Scripts\python.exe" -c "import time; time.sleep(1)" >nul 2>&1
        )
    )
)
echo.

if "!WEB_LISTO!"=="1" (
    start "" "http://127.0.0.1:8000/"
    echo ============================================
    echo  SibuTestLab listo para demostracion
    echo ============================================
    echo.
    echo Web:
    echo   http://127.0.0.1:8000/
    echo.
    echo Host ISO8583:
    echo   127.0.0.1:8583
    echo.
    echo Datos demo: inicializados
    echo.
    echo Para detener la demostracion:
    echo   cierre las ventanas "Host ISO8583" y "Aplicacion web", o presione
    echo   Ctrl+C dentro de cada una.
    echo.
) else (
    echo [AVISO] La aplicacion web no respondio dentro del tiempo esperado
    echo ^(20 segundos^).
    echo.
    echo No se cerro ninguna ventana: revise las consolas "Host ISO8583" y
    echo "Aplicacion web" para ver si hay un error real o si solo hace falta
    echo mas tiempo, y abra manualmente http://127.0.0.1:8000/ cuando responda.
    echo.
)

goto :fin

:fin_con_error
echo.
echo demo.cmd se detuvo por el problema indicado arriba.
endlocal
exit /b 1

:fin
endlocal
exit /b 0

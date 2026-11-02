@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title MediFlow AI - arranque de la demo

echo ============================================
echo  MediFlow AI - arranque de la demo
echo ============================================
echo.

rem ---- [1/5] Configuracion: .env ----
echo [1/5] Configuracion (.env)...
if exist ".env" goto env_listo
if not exist ".env.example" goto error_env
copy /y ".env.example" ".env" >nul
echo      creado .env desde .env.example
:env_listo
findstr /C:"DEEPSEEK_API_KEY=coloca_tu_api_key_aqui" ".env" >nul 2>&1
if errorlevel 1 goto sin_aviso_clave
echo      AVISO: DEEPSEEK_API_KEY tiene el valor de ejemplo.
echo             El chat no va a responder hasta que pongas tu clave en .env
echo.
:sin_aviso_clave
findstr /C:"CAMBIA_ESTA_CONTRASENA" ".env" >nul 2>&1
if errorlevel 1 goto env_ok
echo      AVISO: la contrasena de la base sigue siendo CAMBIA_ESTA_CONTRASENA.
echo             Sirve para la demo local; cambiala si vas a abrir el tunel.
echo.
:env_ok
echo      configuracion lista.
echo.

rem ---- [2/5] Python y dependencias ----
echo [2/5] Python y dependencias...
set "PYEXE=.venv\Scripts\python.exe"
if exist "%PYEXE%" goto deps_check
echo      no hay entorno virtual: creandolo (solo la primera vez)...
set "BASEPY="
py -3.12 --version >nul 2>&1
if not errorlevel 1 set "BASEPY=py -3.12"
if defined BASEPY goto crear_venv
python --version >nul 2>&1
if not errorlevel 1 set "BASEPY=python"
:crear_venv
if not defined BASEPY goto error_python
%BASEPY% -m venv .venv
if errorlevel 1 goto error_python
echo      entorno virtual creado.
:deps_check
"%PYEXE%" -c "import fastapi, uvicorn, langgraph" >nul 2>&1
if not errorlevel 1 goto deps_ok
echo      instalando dependencias (1-2 minutos la primera vez)...
"%PYEXE%" -m pip install --upgrade pip >nul 2>&1
"%PYEXE%" -m pip install -r requirements.txt
if errorlevel 1 goto error_deps
:deps_ok
echo      dependencias listas.
echo.

rem ---- Node/npm: no siempre estan en el PATH de un doble clic ----
set "NPM="
if exist "C:\Program Files\nodejs\npm.cmd" set "NPM=C:\Program Files\nodejs\npm.cmd"
if not defined NPM if exist "%LOCALAPPDATA%\hermes\tools\node-26.7.0-win32-x64\npm.cmd" set "NPM=%LOCALAPPDATA%\hermes\tools\node-26.7.0-win32-x64\npm.cmd"

rem ---- [3/5] Docker y base de datos ----
echo [3/5] Docker y PostgreSQL...
docker info >nul 2>&1
if not errorlevel 1 goto docker_ok
echo      Docker apagado. Abriendo Docker Desktop, espera 40-60 segundos...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
set /a intentos=0
:docker_loop
timeout /t 3 /nobreak >nul
docker info >nul 2>&1
if not errorlevel 1 goto docker_ok
set /a intentos+=1
if %intentos% GEQ 40 goto error_docker
goto docker_loop
:docker_ok
echo      Docker listo.
docker compose up -d
if errorlevel 1 goto error_docker
set /a intentos=0
:espera_base
docker exec mediflow-postgres pg_isready -U mediflow -d mediflow_db >nul 2>&1
if not errorlevel 1 goto base_lista
set /a intentos+=1
if %intentos% GEQ 40 goto error_base
timeout /t 2 /nobreak >nul
goto espera_base
:base_lista
echo      base de datos lista.
echo.

rem ---- [4/5] Frontend ----
echo [4/5] Simulador de WhatsApp...
if not defined NPM goto sin_node
if exist "frontend\dist\index.html" goto front_ok
call "%NPM%" --prefix frontend run build
:front_ok
if exist "frontend\dist\index.html" echo      frontend compilado.
goto api
:sin_node
if exist "frontend\dist\index.html" echo      se usa el frontend ya compilado.
if not exist "frontend\dist\index.html" echo      aviso: sin Node no se compila; la demo sigue en /demo.

rem ---- [5/5] API ----
:api
echo.
echo [5/5] Arrancando la API (ventana aparte)...
start "MediFlow API" cmd /k "%PYEXE% -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"
set /a intentos=0
:espera_api
curl -s -m 2 http://127.0.0.1:8000/api/health >nul 2>&1
if not errorlevel 1 goto api_lista
set /a intentos+=1
if %intentos% GEQ 60 goto error_api
timeout /t 2 /nobreak >nul
goto espera_api
:api_lista
echo      API en linea: http://127.0.0.1:8000
echo.
echo Abriendo las dos ventanas...
start "" http://127.0.0.1:8000/crm
timeout /t 1 /nobreak >nul
start "" http://127.0.0.1:8000/app
echo.
echo Listo.
echo   WhatsApp del paciente : http://127.0.0.1:8000/app
echo   CRM de la secretaria  : http://127.0.0.1:8000/crm
echo.
echo Para mostrarlo desde otros computadores, ejecuta tunel.cmd
echo Para apagar todo, ejecuta detener.cmd
timeout /t 10 /nobreak >nul
exit /b 0

:error_env
echo ERROR: no existe .env ni .env.example. Descarga el repositorio completo.
pause
exit /b 1

:error_python
echo.
echo ERROR: no se encontro Python 3.12.
echo        Instalalo desde python.org y marca "Add python.exe to PATH".
echo        Despues vuelve a ejecutar demo.cmd.
pause
exit /b 1

:error_deps
echo.
echo ERROR: fallo la instalacion de las dependencias.
echo        Revisa la conexion a internet y vuelve a ejecutar demo.cmd.
pause
exit /b 1

:error_docker
echo ERROR: Docker no responde. Abre Docker Desktop y vuelve a intentar.
pause
exit /b 1

:error_base
echo ERROR: la base de datos no respondio a tiempo.
pause
exit /b 1

:error_api
echo ERROR: la API no respondio. Revisa la ventana "MediFlow API".
pause
exit /b 1

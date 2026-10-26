@echo off
setlocal
cd /d "%~dp0"
title MediFlow AI - arranque de la demo

echo ============================================
echo  MediFlow AI - arranque de la demo
echo ============================================
echo.

rem ---- Node/npm: no siempre estan en el PATH de un doble clic ----
set "NPM="
if exist "C:\Program Files\nodejs\npm.cmd" set "NPM=C:\Program Files\nodejs\npm.cmd"
if not defined NPM if exist "%LOCALAPPDATA%\hermes\tools\node-26.7.0-win32-x64\npm.cmd" set "NPM=%LOCALAPPDATA%\hermes\tools\node-26.7.0-win32-x64\npm.cmd"

echo [1/4] Comprobando Docker...
docker info >nul 2>&1
if not errorlevel 1 goto docker_ok
echo      Docker apagado. Abriendo Docker Desktop, espera 40-60 segundos...
start "" "C:\Program Files\Docker\Docker\Docker Desktop.exe"
set /a intentos=0
:dock_loop
timeout /t 3 /nobreak >nul
docker info >nul 2>&1
if not errorlevel 1 goto docker_ok
set /a intentos+=1
if %intentos% GEQ 40 goto error_docker
goto dock_loop
:docker_ok
echo      Docker listo.
echo.

echo [2/4] Levantando PostgreSQL...
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

echo [3/4] Compilando el simulador de WhatsApp...
if not defined NPM goto sin_node
if not exist "frontend\dist\index.html" call "%NPM%" --prefix frontend run build
if exist "frontend\dist\index.html" echo      frontend compilado.
goto api

:sin_node
if exist "frontend\dist\index.html" echo      se usa el frontend ya compilado.
if not exist "frontend\dist\index.html" echo      aviso: sin Node no se puede compilar el frontend.

:api
echo.
echo [4/4] Arrancando la API (ventana aparte)...
start "MediFlow API" cmd /k ".venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000"
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

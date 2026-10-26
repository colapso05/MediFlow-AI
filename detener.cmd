@echo off
setlocal
cd /d "%~dp0"
title MediFlow AI - detener

echo Deteniendo la API (ventanas de uvicorn)...
taskkill /FI "WINDOWTITLE eq MediFlow API*" /T /F >nul 2>&1
echo Deteniendo PostgreSQL...
docker compose stop
echo.
echo Listo. Los datos quedan guardados en el volumen de Docker.
timeout /t 3 /nobreak >nul
exit /b 0

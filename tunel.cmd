@echo off
setlocal
cd /d "%~dp0"
title MediFlow - tunel publico (solo para la demo)

echo ============================================
echo  MediFlow - abrir la demo a internet
echo ============================================
echo.

curl -s -m 3 http://127.0.0.1:8000/api/health >nul 2>&1
if not errorlevel 1 goto api_ok
echo ERROR: la API no esta respondiendo. Ejecuta demo.cmd primero y deja
echo        la ventana "MediFlow API" abierta.
pause
exit /b 1

:api_ok
if exist "_interno\tools\cloudflared.exe" goto tunel
echo ERROR: falta _interno\tools\cloudflared.exe
pause
exit /b 1

:tunel
echo Copia la direccion https://....trycloudflare.com que aparece abajo.
echo Esa direccion abre la demo desde cualquier computador con internet.
echo.
echo   WhatsApp del paciente :  https://.../app
echo   CRM de la secretaria  :  https://.../crm
echo.
echo Para cortar el acceso, cierra esta ventana o pulsa Ctrl+C.
echo.
_interno\tools\cloudflared.exe tunnel --url http://127.0.0.1:8000 --no-autoupdate
pause

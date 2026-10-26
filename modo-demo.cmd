@echo off
setlocal
cd /d "%~dp0"
title MediFlow - modo demo (equipo despierto)

echo ============================================
echo  MediFlow - modo demo
echo ============================================
echo.
echo Este modo impide que el equipo se suspenda o apague la pantalla
echo mientras la ventana siga abierta. Necesario si vas a mostrar la
echo demo con tunel.cmd y el notebook se queda solo.
echo.
echo Si quieres ademas desactivar la suspension en el plan de energia
echo de forma permanente, abre PowerShell como administrador y ejecuta:
echo    powercfg /change standby-timeout-ac 0
echo    powercfg /change monitor-timeout-ac 0
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0_interno\mantener-despierto.ps1"

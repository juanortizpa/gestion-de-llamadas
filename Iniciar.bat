@echo off
rem Doble clic en Windows. Solo busca Python y delega todo en iniciar.py (el mismo archivo que usan macOS y Linux).
chcp 65001 >nul
title Auditoria de Llamadas
cd /d "%~dp0"

where py >nul 2>nul
if not errorlevel 1 (
  py -3 iniciar.py %*
  goto :fin
)
where python >nul 2>nul
if not errorlevel 1 (
  python iniciar.py %*
  goto :fin
)
echo Python 3.12 o superior no esta instalado.
echo Instalelo con:  winget install --id Python.Python.3.12 -e
echo o desde https://www.python.org/downloads/ (marque "Add python.exe to PATH") y vuelva a abrir este archivo.

:fin
pause

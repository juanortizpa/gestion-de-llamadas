@echo off
chcp 65001 >nul
title Instalacion - Auditoria de Llamadas
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creando el entorno de Python 3.12 e instalando dependencias...
  py -3.12 -m venv .venv || goto :error
  ".venv\Scripts\python.exe" -m pip install --upgrade pip || goto :error
  ".venv\Scripts\python.exe" -m pip install -e ".[dev]" || goto :error
)

".venv\Scripts\python.exe" scripts\instalar.py
pause
exit /b 0

:error
echo.
echo No se pudo preparar el entorno. Verifique que Python 3.12 este instalado (vea README.md, paso 1).
pause
exit /b 1

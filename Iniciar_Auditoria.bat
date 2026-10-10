@echo off
chcp 65001 >nul
title Auditoria de Llamadas
cd /d "%~dp0"
echo Iniciando Auditoria de Llamadas... (se abrira en su navegador)
echo No cierre esta ventana mientras use el programa.
".venv\Scripts\python.exe" -m llamadas gui
pause

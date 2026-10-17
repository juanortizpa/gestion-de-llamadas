@echo off
rem Se conserva el nombre de siempre; ahora delega en Iniciar.bat (que usa iniciar.py, igual en todos los sistemas).
call "%~dp0Iniciar.bat" %*

@echo off
REM Revisa que esta computadora tenga todo para correr Logix.
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
python verificar_instalacion.py
pause

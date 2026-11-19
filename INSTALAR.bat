@echo off
REM Instala las librerias de Python que usa Logix.
cd /d "%~dp0"
python -m pip install -r requirements.txt
pause

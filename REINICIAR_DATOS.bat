@echo off
REM Borra logix_db y la vuelve a crear con datos simulados.
cd /d "%~dp0"
python generar_datos.py
pause

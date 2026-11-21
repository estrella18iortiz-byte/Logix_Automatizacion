@echo off
REM Genera la factura XML de prueba de una orden (para mandarla por Telegram como proveedor).
cd /d "%~dp0"
set /p FOLIO=Folio de la orden (ej. OC-2026-0012):
python generar_factura_prueba.py %FOLIO%
start "" "%~dp0datos_prueba\facturas_telegram"
pause

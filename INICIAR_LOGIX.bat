@echo off
REM Logix: abre el robot (ventana aparte) y el panel.
cd /d "%~dp0"
start "Robot Logix" cmd /k python robot.py
python panel.py

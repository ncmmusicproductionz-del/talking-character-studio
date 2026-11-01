@echo off
cd /d "%~dp0"
set "VENV=%~dp0.venv"
if not exist "%VENV%\Scripts\python.exe" (
  echo First time here: running setup...
  call "Setup (run once).bat"
)
"%VENV%\Scripts\python.exe" app.py
pause

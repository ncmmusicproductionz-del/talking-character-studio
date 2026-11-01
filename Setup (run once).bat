@echo off
setlocal
cd /d "%~dp0"
set "VENV=%~dp0.venv"
echo ============================================
echo  Talking Character Studio - one-time setup
echo ============================================
where py >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install Python 3 from https://www.python.org/downloads/ and tick "Add Python to PATH", then run this again.
  pause
  exit /b 1
)
if not exist "%VENV%\Scripts\python.exe" (
  echo Creating a private Python environment in %VENV% ...
  py -m venv "%VENV%"
  if errorlevel 1 ( echo Could not create the environment. & pause & exit /b 1 )
)
echo Installing Pillow, a bundled video encoder and the AI voice library...
"%VENV%\Scripts\python.exe" -m pip install --upgrade pip >nul
"%VENV%\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 ( echo Install failed. Check your internet connection and try again. & pause & exit /b 1 )
echo.
echo Setup finished. Now double-click "Start Talking Character Studio.bat".
pause

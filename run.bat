@echo off
rem Video Trimmer launcher for Windows: installs missing tools and starts the app.
setlocal
cd /d "%~dp0"

py -3 -c "import sys" >nul 2>nul
if errorlevel 1 (
  echo Python 3 was not found. Installing Python 3.12 with winget...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  echo.
  echo Python installed. Close this window and double-click run.bat again.
  pause
  exit /b 1
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo ffmpeg was not found. Installing ffmpeg with winget...
  winget install -e --id Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
  echo.
  echo ffmpeg installed. Close this window and double-click run.bat again.
  pause
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  py -3 -m venv .venv
)

echo Checking dependencies...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 (
  echo Failed to install dependencies.
  pause
  exit /b 1
)

set "PYTHONPATH=%~dp0src"
".venv\Scripts\python.exe" -m video_trimmer
if errorlevel 1 pause

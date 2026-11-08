@echo off
rem Video Trimmer launcher for Windows: prepares tools and starts the app.
setlocal
cd /d "%~dp0"

rem --- Python 3 (required; winget is optional) ---
py -3 -c "import sys" >nul 2>nul
if errorlevel 1 (
  echo Python 3 was not found.
  where winget >nul 2>nul
  if errorlevel 1 (
    echo Install Python 3.10 or newer from https://www.python.org/downloads/
    echo During setup tick "Add python.exe to PATH", then run run.bat again.
    pause
    exit /b 1
  )
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  echo.
  echo Python installed. Close this window and double-click run.bat again.
  pause
  exit /b 1
)

rem --- ffmpeg: use system one, or download a local copy into tools\ffmpeg ---
where ffmpeg >nul 2>nul
if errorlevel 1 (
  if not exist "tools\ffmpeg\bin\ffmpeg.exe" (
    echo ffmpeg was not found. Downloading a local copy, about 100 MB, please wait...
    if not exist "tools" mkdir "tools"
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile 'tools\ffmpeg.zip'; if (Test-Path 'tools\ffmpeg_tmp') { Remove-Item -Recurse -Force 'tools\ffmpeg_tmp' }; Expand-Archive -Force 'tools\ffmpeg.zip' 'tools\ffmpeg_tmp'; $d = Get-ChildItem 'tools\ffmpeg_tmp' -Directory | Select-Object -First 1; Move-Item $d.FullName 'tools\ffmpeg'; Remove-Item -Recurse -Force 'tools\ffmpeg_tmp','tools\ffmpeg.zip'"
  )
  if not exist "tools\ffmpeg\bin\ffmpeg.exe" (
    echo Could not download ffmpeg automatically.
    echo Download "ffmpeg-release-essentials.zip" from https://www.gyan.dev/ffmpeg/builds/
    echo Unpack it so that this file exists: %~dp0tools\ffmpeg\bin\ffmpeg.exe
    echo Then run run.bat again.
    pause
    exit /b 1
  )
  set "PATH=%~dp0tools\ffmpeg\bin;%PATH%"
)

rem --- virtual environment and dependencies ---
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

@echo off
rem Video Trimmer launcher for Windows.
rem Written without parenthesised blocks on purpose: a ")" inside a folder name
rem (for example "Video_trimmer-main (1)") or inside PATH breaks such blocks.
setlocal EnableExtensions
cd /d "%~dp0"

rem Keep the window open on errors: re-run ourselves inside "cmd /k".
if /i "%~1"=="--inner" goto main
start "Video Trimmer" cmd /k ""%~f0" --inner"
exit /b 0

:main
echo ==== Video Trimmer launcher ====
echo Folder: %CD%
echo.

if exist "requirements.txt" goto folder_ok
echo requirements.txt was not found next to run.bat.
echo Extract the whole ZIP archive first (right click, Extract All), then run run.bat from the extracted folder.
goto fail
:folder_ok

rem ---- Python 3.10+ ----
set "PY="
py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if defined PY goto python_found
python -c "import sys" >nul 2>nul && set "PY=python"
if defined PY goto python_found
echo Python was not found.
echo Install Python 3.10 or newer from https://www.python.org/downloads/
echo During setup tick "Add python.exe to PATH", then run run.bat again.
goto fail
:python_found
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>nul
if not errorlevel 1 goto python_ok
echo Python is too old. Install Python 3.10 or newer from https://www.python.org/downloads/
goto fail
:python_ok
echo Python: OK

rem ---- ffmpeg: system one, or a local copy in tools\ffmpeg ----
where ffmpeg >nul 2>nul
if not errorlevel 1 goto ffmpeg_ok
if exist "tools\ffmpeg\bin\ffmpeg.exe" goto ffmpeg_local
echo ffmpeg was not found. Downloading a local copy, about 100 MB, please wait...
if not exist "tools" mkdir "tools"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; $ProgressPreference='SilentlyContinue'; Invoke-WebRequest -Uri 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip' -OutFile 'tools\ffmpeg.zip'; if (Test-Path 'tools\ffmpeg_tmp') { Remove-Item -Recurse -Force 'tools\ffmpeg_tmp' }; Expand-Archive -Force 'tools\ffmpeg.zip' 'tools\ffmpeg_tmp'; $d = Get-ChildItem 'tools\ffmpeg_tmp' -Directory | Select-Object -First 1; Move-Item $d.FullName 'tools\ffmpeg'; Remove-Item -Recurse -Force 'tools\ffmpeg_tmp','tools\ffmpeg.zip'"
if exist "tools\ffmpeg\bin\ffmpeg.exe" goto ffmpeg_local
echo Could not download ffmpeg automatically.
echo Download "ffmpeg-release-essentials.zip" from https://www.gyan.dev/ffmpeg/builds/
echo Unpack it so that this file exists: %~dp0tools\ffmpeg\bin\ffmpeg.exe
echo Then run run.bat again.
goto fail
:ffmpeg_local
set "PATH=%~dp0tools\ffmpeg\bin;%PATH%"
:ffmpeg_ok
ffmpeg -version >nul 2>nul
if not errorlevel 1 goto ffmpeg_works
echo ffmpeg was found but does not start.
goto fail
:ffmpeg_works
echo ffmpeg: OK

rem ---- virtual environment and dependencies ----
if exist ".venv\Scripts\python.exe" goto venv_ok
echo Creating virtual environment...
%PY% -m venv .venv
if errorlevel 1 goto fail
:venv_ok
echo Checking dependencies. The first time this can take several minutes...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 goto fail
echo Dependencies: OK

rem ---- start the app ----
set "PYTHONPATH=%~dp0src"
echo Starting Video Trimmer...
".venv\Scripts\python.exe" -m video_trimmer
if errorlevel 1 goto fail
exit

:fail
echo.
echo Something went wrong. Please send a screenshot of this window.
exit /b 1

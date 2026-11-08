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
echo ffmpeg was not found. Downloading a local copy, about 150 MB.
echo A progress line is shown below. If a source is too slow, the next one is tried.
if not exist "tools" mkdir "tools"
if exist "tools\ffmpeg.zip" del "tools\ffmpeg.zip"
if exist "tools\ffmpeg_tmp" rmdir /s /q "tools\ffmpeg_tmp"
if exist "tools\ffmpeg" rmdir /s /q "tools\ffmpeg"
where curl.exe >nul 2>nul
if errorlevel 1 goto ff_powershell
echo Source 1 of 2: GitHub
curl.exe -L --fail --retry 3 --connect-timeout 20 --speed-limit 100000 --speed-time 60 -o "tools\ffmpeg.zip" "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
if not errorlevel 1 goto ff_unpack
echo Source 1 failed or was too slow. Source 2 of 2: gyan.dev
if exist "tools\ffmpeg.zip" del "tools\ffmpeg.zip"
curl.exe -L --fail --retry 3 --connect-timeout 20 --speed-limit 100000 --speed-time 120 -o "tools\ffmpeg.zip" "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
if not errorlevel 1 goto ff_unpack
goto ff_manual
:ff_powershell
echo curl.exe is not available, using PowerShell (no progress is shown, please wait)...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip' -OutFile 'tools\ffmpeg.zip' -TimeoutSec 600"
if errorlevel 1 goto ff_manual
:ff_unpack
echo Unpacking ffmpeg...
mkdir "tools\ffmpeg_tmp"
tar -xf "tools\ffmpeg.zip" -C "tools\ffmpeg_tmp"
if errorlevel 1 powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Force 'tools\ffmpeg.zip' 'tools\ffmpeg_tmp'"
for /d %%D in ("tools\ffmpeg_tmp\*") do move "%%D" "tools\ffmpeg" >nul
if exist "tools\ffmpeg_tmp" rmdir /s /q "tools\ffmpeg_tmp"
if exist "tools\ffmpeg.zip" del "tools\ffmpeg.zip"
if exist "tools\ffmpeg\bin\ffmpeg.exe" goto ffmpeg_local
:ff_manual
echo.
echo Automatic ffmpeg download failed.
echo Download this file in your browser:
echo   https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip
echo Unpack it and copy its folder "bin" into: %~dp0tools\ffmpeg
echo so that this file exists: %~dp0tools\ffmpeg\bin\ffmpeg.exe
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

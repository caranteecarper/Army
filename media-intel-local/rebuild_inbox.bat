@echo off
setlocal
cd /d "%~dp0"
set PY=..\envs\media-crawlers\python.exe

if not exist "%PY%" (
  echo Python environment not found: %PY%
  echo Please keep envs, external-tools, and media-intel-local in the same package folder.
  pause
  exit /b 1
)

if "%~1"=="" (
  for /f %%i in ('"%PY%" -c "from datetime import datetime,timedelta,timezone; print((datetime.now(timezone(timedelta(hours=8))).date()-timedelta(days=1)).isoformat())"') do set TARGET_DATE=%%i
) else (
  set TARGET_DATE=%~1
)

echo Rebuilding trend/hotspot inbox for %TARGET_DATE%...
"%PY%" tools\channel_intake_from_output.py --date %TARGET_DATE%
pause

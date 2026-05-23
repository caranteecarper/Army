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

echo Running daily media collection for yesterday...
"%PY%" main.py --date yesterday
echo.
echo Done. Outputs are under media-intel-local\output and media-intel-local\data\inbox.
pause

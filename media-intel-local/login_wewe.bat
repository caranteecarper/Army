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

echo Starting WeWe RSS login. Scan the opened QR/login page when it appears.
"%PY%" tools\wewe_login.py
pause

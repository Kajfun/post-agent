@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0.."

where py >nul 2>&1
if %errorlevel%==0 (set PY=py) else (set PY=python)

%PY% --version >nul 2>&1
if errorlevel 1 (
  echo.
  echo Nie znalazlem Pythona.
  echo Zainstaluj go z https://www.python.org/downloads/
  echo i zaznacz "Add Python to PATH".
  echo.
  pause
  exit /b 1
)

%PY% narzedzia\uruchom.py %*

echo.
echo Gotowe. Mozesz zamknac to okno.
pause

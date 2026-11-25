@echo off
title Third Moon Audiobook Studio
cd /d "%~dp0"
set PYTHONUTF8=1

rem Use Chatterbox's own Python (it already has torch + Chatterbox Turbo). The studio itself needs nothing else.
set "PY=C:\Users\Glen\ChatterboxTurbo\venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Chatterbox's Python wasn't found at %PY%
  echo Trying the normal Python instead - voices won't work until Chatterbox is found.
  echo You can change the Chatterbox folder in Settings.
  set "PY=python"
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo.
  echo  WARNING: ffmpeg isn't on the PATH. The studio needs it to build audio.
  echo.
)

"%PY%" -m app
echo.
echo The studio has stopped.
pause

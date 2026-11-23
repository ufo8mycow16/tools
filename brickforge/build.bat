@echo off
title Building BrickForge
cd /d "%~dp0"
echo.
echo  ===== Building BrickForge =====
echo.

if not exist complete.zip (
    echo  Can't find complete.zip - put the LDraw complete.zip in this folder and run me again.
    pause
    exit /b 1
)

set PY=python
%PY% --version >nul 2>&1 || set PY=py -3
%PY% --version >nul 2>&1 || (
    echo  Can't find Python. Install it from python.org and tick "Add python.exe to PATH".
    pause
    exit /b 1
)

tasklist /fi "imagename eq BrickForge.exe" 2>nul | find /i "BrickForge.exe" >nul && (
    echo  BrickForge is still open - close it first, otherwise the new version
    echo  can't replace the old one. Then press a key to carry on.
    pause
)

echo  [1/3] Getting the build tools (numpy, pyinstaller)...
%PY% -m pip install --quiet --upgrade numpy pyinstaller || goto :fail

echo  [2/3] Packing the LDraw parts library...
%PY% make_library.py complete.zip ldraw_lib.zip || goto :fail

echo  [3/3] Making BrickForge.exe (takes a minute or two)...
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed --name BrickForge ^
    --add-data "ldraw_lib.zip;." brickforge.py || goto :fail

copy /y dist\BrickForge.exe BrickForge.exe >nul || (
    echo.
    echo  Couldn't replace BrickForge.exe - is it still open? Close it and run build.bat again.
    pause
    exit /b 1
)
rmdir /s /q build >nul 2>&1
rmdir /s /q dist >nul 2>&1
del /q BrickForge.spec >nul 2>&1
del /q ldraw_lib.zip >nul 2>&1

echo.
echo  All done! BrickForge.exe is in this folder - it has the whole library inside,
echo  so you can copy it anywhere on its own.
echo.
pause
exit /b 0

:fail
echo.
echo  Something went wrong - copy the messages above and send them to Claude.
pause
exit /b 1

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

echo  [1/3] Getting the build tools (numpy, scipy, pyinstaller, Windows repair)...
%PY% -m pip install --quiet --upgrade numpy scipy pillow pyinstaller || goto :fail
%PY% -m pip install --quiet --upgrade winrt-runtime winrt-Windows.Foundation winrt-Windows.Foundation.Collections winrt-Windows.Graphics.Printing3D winrt-Windows.Storage.Streams || echo  (Windows repair add-on didn't install - BrickForge will still work without it)

echo  [2/3] Packing the LDraw parts library...
%PY% make_library.py complete.zip ldraw_lib.zip || goto :fail

set SETSDATA=
set CAT=
for %%F in (*downloads*.zip rebrickable*.zip) do if not defined CAT set CAT=%%F
if defined CAT (
    echo  [2b] Building the sets catalogue from %CAT%...
    %PY% make_sets.py "%CAT%" ldraw_lib.zip sets.db || goto :fail
    set SETSDATA=--add-data "sets.db;."
) else (
    echo  [2b] No Rebrickable catalogue zip here - building without the Sets tab.
)

echo  [3/3] Making BrickForge.exe (takes a minute or two)...
%PY% -m PyInstaller --noconfirm --clean --onefile --windowed --name BrickForge ^
    --add-data "ldraw_lib.zip;." --add-data "art\*.png;art" %SETSDATA% --hidden-import ldraw_seal --hidden-import winrepair --hidden-import sets_core --hidden-import PIL.ImageTk ^
    --collect-submodules winrt --hidden-import scipy.spatial ^
    brickforge.py || goto :fail

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
del /q sets.db >nul 2>&1

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

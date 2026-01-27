@echo off
title Build CrossTrans EXE
cd /d "%~dp0"

:: Get version from Python code
for /f "delims=" %%i in ('python -c "from src.constants import VERSION; print(VERSION)"') do set APP_VERSION=%%i

echo ========================================================
echo Building CrossTrans v%APP_VERSION%...
echo ========================================================
echo.

:: Clean previous builds
echo [1/4] Cleaning previous builds...
if exist "build" rmdir /s /q "build" 2>nul
if exist "dist" rmdir /s /q "dist" 2>nul

:: Ensure ICO file exists
echo [2/4] Checking icon file...
if not exist "CrossTrans.ico" (
    echo Creating CrossTrans.ico from PNG...
    python -c "from PIL import Image; img = Image.open('CrossTrans.png'); img.save('CrossTrans.ico', format='ICO', sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)])"
)

:: Build EXE
echo [3/4] Building EXE with PyInstaller...
python -m PyInstaller CrossTrans.spec --clean --noconfirm

:: Check build result and rename
echo [4/4] Finalizing...
if exist "dist\CrossTrans.exe" (
    :: Rename with version
    if exist "dist\CrossTrans_v%APP_VERSION%.exe" del "dist\CrossTrans_v%APP_VERSION%.exe"
    ren "dist\CrossTrans.exe" "CrossTrans_v%APP_VERSION%.exe"

    :: Show file info
    echo.
    echo ========================================================
    echo SUCCESS! Created: dist\CrossTrans_v%APP_VERSION%.exe
    echo ========================================================
    for %%A in ("dist\CrossTrans_v%APP_VERSION%.exe") do echo File size: %%~zA bytes
    echo.

    :: Cleanup build folder
    echo Cleaning up build folder...
    rmdir /s /q "build" 2>nul
) else (
    echo.
    echo ========================================================
    echo ERROR: Build failed! Check the output above for errors.
    echo ========================================================
)

pause

@echo off
title Build AI Translator EXE
cd /d "%~dp0"

:: Get version from Python code
for /f "delims=" %%i in ('python -c "from src.constants import VERSION; print(VERSION)"') do set APP_VERSION=%%i

echo ========================================================
echo Building AI Translator v%APP_VERSION%...
echo Please wait, this process takes approximately 1-2 minutes.
echo ========================================================
echo.

python -m PyInstaller AITranslator.spec --clean --noconfirm

:: Rename output file with version
if exist "dist\AITranslator.exe" (
    if exist "dist\AITranslator_v%APP_VERSION%.exe" del "dist\AITranslator_v%APP_VERSION%.exe"
    ren "dist\AITranslator.exe" "AITranslator_v%APP_VERSION%.exe"
)

echo.
echo ========================================================
echo DONE! Created: dist\AITranslator_v%APP_VERSION%.exe
pause
@echo off
@chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"

echo =====================================================================
echo Building CorridorKeyer 2.0 Lightweight Distribution Package (Option A)...
echo =====================================================================

if exist "%~dp0venv\Scripts\python.exe" (
    "%~dp0venv\Scripts\python.exe" "%~dp0scripts\create_distribution_zip.py"
) else if exist "%~dp0python_embed\python.exe" (
    "%~dp0python_embed\python.exe" "%~dp0scripts\create_distribution_zip.py"
) else (
    python "%~dp0scripts\create_distribution_zip.py"
)

if errorlevel 1 (
    echo [ERROR] Packaging failed.
    pause
    exit /b 1
)

echo.
echo Packaging complete! Check the 'dist' folder for your release ZIP.
pause
exit /b 0

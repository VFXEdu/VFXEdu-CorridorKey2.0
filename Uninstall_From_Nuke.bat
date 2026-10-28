@echo off
@chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"

echo =====================================================================
echo   VFXEdu CorridorKey 2.0 - Uninstall from Foundry Nuke
echo =====================================================================
echo.

set "CURRENT_DIR=%~dp0"
if "%CURRENT_DIR:~-1%"=="\" set "CURRENT_DIR=%CURRENT_DIR:~0,-1%"

set "PY_EXE="
if exist "%CURRENT_DIR%\python_embed\python.exe" (
    set "PY_EXE=%CURRENT_DIR%\python_embed\python.exe"
) else if exist "%CURRENT_DIR%\venv\Scripts\python.exe" (
    set "PY_EXE=%CURRENT_DIR%\venv\Scripts\python.exe"
) else (
    set "PY_EXE=python"
)

"%PY_EXE%" "%CURRENT_DIR%\scripts\install_nuke.py" --uninstall

if errorlevel 1 (
    echo.
    echo [ERROR] Uninstall failed.
    pause
    exit /b 1
)

echo.
pause
exit /b 0

@echo off
@chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"

echo =====================================================================
echo   VFXEdu CorridorKey 2.0 - DaVinci Resolve 1-Click Installer
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

"%PY_EXE%" "%CURRENT_DIR%\scripts\install_resolve.py" --install "%CURRENT_DIR%"

if errorlevel 1 (
    echo.
    echo [ERROR] Installation failed.
    pause
    exit /b 1
)

echo.
echo =====================================================================
echo   [Next Steps]
echo   1. Launch or switch to DaVinci Resolve (Edit or Color page).
echo   2. Position the playhead over any video clip on the timeline.
echo   3. Click top menu: 'Workspace' -^> 'Scripts' -^> 'CorridorKeyer'.
echo =====================================================================
echo.
pause
exit /b 0

@echo off
@chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PATH=%~dp0bin;%~dp0python_embed;%~dp0python_embed\Scripts;%PATH%"

echo =====================================================================
echo    VFXEdu CorridorKey 2.0 - Fast Auto-Update Utility
echo =====================================================================
echo.

set "PY_EXE="
if exist "%~dp0python_embed\python.exe" set "PY_EXE=%~dp0python_embed\python.exe"
if not defined PY_EXE if exist "%~dp0venv\Scripts\python.exe" set "PY_EXE=%~dp0venv\Scripts\python.exe"
if not defined PY_EXE set "PY_EXE=python"

"%PY_EXE%" "%~dp0scripts\updater.py" --apply
if errorlevel 1 (
    echo.
    echo [-] Update encountered an issue. Please check the logs above.
    pause
    exit /b 1
)

echo.
echo =====================================================================
echo [SUCCESS] CorridorKey 2.0 has been updated to the latest version!
echo =====================================================================
echo.
set /p LAUNCH_CHOICE="Launch CorridorKey 2.0 now? (Y/N) [default: Y]: "
if /i "%LAUNCH_CHOICE%"=="N" goto finish
call "%~dp0Launch_GUI.bat"

:finish
exit /b 0

@echo off
@chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"

echo =====================================================================
echo  VFXEdu CorridorKey 2.0 - GitHub Release Publisher
echo =====================================================================
echo.

if exist "%~dp0venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0venv\Scripts\python.exe"
) else if exist "%~dp0python_embed\python.exe" (
    set "PY_EXE=%~dp0python_embed\python.exe"
) else (
    set "PY_EXE=python"
)

"%PY_EXE%" "%~dp0scripts\publish_release.py"

echo.
pause

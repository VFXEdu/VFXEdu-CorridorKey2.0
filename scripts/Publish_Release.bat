@echo off
@chcp 65001 >nul
cd /d "%~dp0.."
set "PYTHONUTF8=1"

echo =====================================================================
echo  VFXEdu CorridorKey 2.0 - GitHub Release Publisher
echo =====================================================================
echo.

if exist "%~dp0..\venv\Scripts\python.exe" (
    set "PY_EXE=%~dp0..\venv\Scripts\python.exe"
) else if exist "%~dp0..\python_embed\python.exe" (
    set "PY_EXE=%~dp0..\python_embed\python.exe"
) else (
    set "PY_EXE=python"
)

"%PY_EXE%" "%~dp0publish_release.py"

echo.
pause

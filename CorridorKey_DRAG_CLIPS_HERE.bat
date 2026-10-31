@echo off
@chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PYTORCH_ALLOC_CONF=max_split_size_mb:512"
set "PATH=%~dp0bin;%~dp0python_embed;%~dp0python_embed\Scripts;%PATH%"

if exist "%~dp0python_embed\python.exe" (
    set "PYTHON=%~dp0python_embed\python.exe"
) else if exist "%~dp0venv\Scripts\python.exe" (
    set "PYTHON=%~dp0venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

if "%~1"=="" (
    "%PYTHON%" "%~dp0run_interactive.py"
) else (
    "%PYTHON%" "%~dp0run_interactive.py" "%~1"
)

echo.
pause

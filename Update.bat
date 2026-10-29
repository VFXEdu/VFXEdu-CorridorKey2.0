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

rem 1. If scripts\updater.py does not exist yet (e.g. older v0.1.1 folder), download it automatically
if not exist "%~dp0scripts\updater.py" (
    echo [*] Fetching updater engine from GitHub...
    if not exist "%~dp0scripts" mkdir "%~dp0scripts"
    "%PY_EXE%" -c "import urllib.request; urllib.request.urlretrieve('https://raw.githubusercontent.com/VFXEdu/VFXEdu-CorridorKey2.0/master/scripts/updater.py', r'%~dp0scripts\updater.py')" 2>nul
    if not exist "%~dp0scripts\updater.py" (
        powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object Net.WebClient).DownloadFile('https://raw.githubusercontent.com/VFXEdu/VFXEdu-CorridorKey2.0/master/scripts/updater.py', '%~dp0scripts\updater.py')" 2>nul
    )
)

rem 2. Apply update
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
set "LAUNCH_CHOICE="
set /p LAUNCH_CHOICE="Launch CorridorKey 2.0 now? (Y/N) [default: Y]: "
if "%LAUNCH_CHOICE%"=="" set "LAUNCH_CHOICE=Y"
if /i "%LAUNCH_CHOICE%"=="Y" (
    start "" "%~dp0Launch_GUI.bat"
)

exit /b 0

@echo off
@chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PATH=%~dp0bin;%~dp0python_embed;%~dp0python_embed\Scripts;%PATH%"

rem Check if extracted
if not exist "%~dp0gui.py" goto err_not_extracted

rem 1. Prioritize existing ready virtual environment (developer machine)
if exist "%~dp0venv\Scripts\pythonw.exe" (
    if exist "%~dp0venv\Lib\site-packages\PySide6" goto launch_venv
)

rem 2. Check portable embedded Python (target distribution machine)
if exist "%~dp0python_embed\pythonw.exe" (
    if exist "%~dp0python_embed\Lib\site-packages\PySide6" goto launch_embed
)

rem 3. If neither is ready, notify user to run Setup_GUI.bat
goto err_not_setup

:launch_venv
start "" "%~dp0venv\Scripts\pythonw.exe" "%~dp0gui.py"
exit /b 0

:launch_embed
start "" "%~dp0python_embed\pythonw.exe" "%~dp0gui.py"
exit /b 0

:err_not_extracted
echo =====================================================================
echo [ERROR] Please EXTRACT the ZIP file completely before running!
echo.
echo 압축 파일(ZIP) 내부에서 바로 실행하지 마시고, 반드시 [압축 풀기]를
echo 완료한 폴더에서 실행해 주세요.
echo =====================================================================
pause
exit /b 1

:err_not_setup
echo =====================================================================
echo [ERROR] Environment not initialized yet!
echo.
echo GUI 의존성 라이브러리가 아직 설치되지 않았습니다.
echo Setup_GUI.bat 를 먼저 더블클릭하여 환경 설치를 완료해 주세요.
echo =====================================================================
pause
exit /b 1

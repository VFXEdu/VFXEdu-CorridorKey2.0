@echo off
@chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "PATH=%~dp0bin;%~dp0python_embed;%~dp0python_embed\Scripts;%PATH%"

if not exist "%~dp0gui.py" goto err_not_extracted

rem 1. Check virtual environment (developer PC)
if exist "%~dp0venv\Scripts\pythonw.exe" goto launch_venv_w
if exist "%~dp0venv\Scripts\python.exe" goto launch_venv

rem 2. Check portable embedded Python (standalone portable user)
if exist "%~dp0python_embed\pythonw.exe" goto launch_embed_w
if exist "%~dp0python_embed\python.exe" goto launch_embed

rem 3. Check system Python
where python >nul 2>nul
if %errorlevel% equ 0 goto launch_system

goto err_not_setup

:launch_venv_w
start "" "%~dp0venv\Scripts\pythonw.exe" "%~dp0gui.py"
exit /b 0

:launch_venv
start "" "%~dp0venv\Scripts\python.exe" "%~dp0gui.py"
exit /b 0

:launch_embed_w
start "" "%~dp0python_embed\pythonw.exe" "%~dp0gui.py"
exit /b 0

:launch_embed
start "" "%~dp0python_embed\python.exe" "%~dp0gui.py"
exit /b 0

:launch_system
start "" python "%~dp0gui.py"
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

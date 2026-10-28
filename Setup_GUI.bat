@echo off
@chcp 65001 >nul
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "HF_HOME=%~dp0tmp\huggingface"
set "PATH=%~dp0bin;%~dp0python_embed;%~dp0python_embed\Scripts;%PATH%"

echo =====================================================================
echo  CorridorKey 2.0 - Portable Environment Setup (Option A)
echo =====================================================================
echo.

rem Check if user ran directly inside ZIP without extracting
if not exist "%~dp0requirements-gui.txt" goto err_not_extracted
if not exist "%~dp0gui.py" goto err_not_extracted

rem 1. Detect Python Runtime (prioritize venv if present, otherwise python_embed)
if exist "%~dp0venv\Scripts\python.exe" goto use_venv
if exist "%~dp0python_embed\python.exe" goto use_embed

echo [*] Bundled Python not found. Creating local Python virtual environment...
python -m venv venv
if errorlevel 1 goto fail_venv
set "PY_EXE=%~dp0venv\Scripts\python.exe"
goto check_python

:use_venv
echo [*] Using existing virtual environment: venv
set "PY_EXE=%~dp0venv\Scripts\python.exe"
goto check_python

:use_embed
echo [*] Found bundled Embedded Python runtime: Zero-install Portable Mode.
set "PY_EXE=%~dp0python_embed\python.exe"
goto check_python

:check_python
echo [*] Python executable: %PY_EXE%
echo.

rem Test Python execution
"%PY_EXE%" --version
if errorlevel 1 goto fail_python

rem 2. Verify FFmpeg binary
if exist "%~dp0bin\ffmpeg.exe" (
    echo [*] Found bundled FFmpeg binary: bin\ffmpeg.exe
) else (
    echo [!] Bundled bin\ffmpeg.exe not found. Checking system PATH...
)

rem 3. Install PyTorch with CUDA 12.8 support
echo.
echo =====================================================================
echo [*] Installing PyTorch 2.9.1 with CUDA 12.8 support...
echo     (This may take a few minutes depending on network speed)
echo =====================================================================
"%PY_EXE%" -m pip install torch==2.9.1 torchvision==0.24.1 --index-url https://download.pytorch.org/whl/cu128
if errorlevel 1 goto fail_pip

rem 4. Install GUI and Computer Vision dependencies
echo.
echo =====================================================================
echo [*] Installing GUI and VFX pipeline dependencies...
echo =====================================================================
"%PY_EXE%" -m pip install -r "%~dp0requirements-gui.txt"
if errorlevel 1 goto fail_pip

echo.
echo =====================================================================
echo [SUCCESS] CorridorKeyer 2.0 runtime and dependencies installed!
echo.
echo AI Foundation Model weights (~4.8 GB) are required for keying.
echo You can download them now, or download them later via the GUI Model Manager.
echo =====================================================================
set /p "DL_CHOICE=Download required model weights now? [Y/N] (default: Y): "
if /i "%DL_CHOICE%"=="N" goto finish

"%PY_EXE%" "%~dp0scripts\download_weights.py" --model required
if errorlevel 1 goto fail_model

:finish
echo.
echo =====================================================================
echo CorridorKey 2.0 is ready to use! Double-click Launch_GUI.bat to start.
echo =====================================================================
pause
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

:fail_venv
echo.
echo =====================================================================
echo [ERROR] Failed to create Python virtual environment.
echo Please ensure Python 3.10-3.12 is installed or python_embed is present.
echo =====================================================================
pause
exit /b 1

:fail_python
echo.
echo =====================================================================
echo [ERROR] Failed to run Python executable: %PY_EXE%
echo Please check if Windows Defender or antivirus blocked python.exe.
echo =====================================================================
pause
exit /b 1

:fail_pip
echo.
echo =====================================================================
echo [ERROR] Package installation failed. Please check your internet connection.
echo =====================================================================
pause
exit /b 1

:fail_model
echo.
echo =====================================================================
echo [WARNING] Model weights download interrupted.
echo You can download them later anytime inside the GUI (Model Manager).
echo =====================================================================
pause
exit /b 0

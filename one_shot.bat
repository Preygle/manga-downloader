@echo off
setlocal enabledelayedexpansion

echo ==========================================
echo  Starting Manga Downloader Pipeline
echo ==========================================

echo ^>^> Running Downloader...
powershell -ExecutionPolicy Bypass -NoProfile -File "%~dp0url_down.ps1"

if not exist "download_dir.txt" (
    echo Error: Could not determine download directory from url_down.ps1.
    echo Make sure the download finished successfully.
    exit /b 1
)

set /p CAPTURED_DIR=<download_dir.txt
del download_dir.txt

echo ^>^> Detected Download Directory: '!CAPTURED_DIR!'

echo ^>^> Checking Environment...
set VENV_DIR=venv
set PYTHON_CMD=python

if not exist "%VENV_DIR%" (
    echo Creating virtual environment...
    %PYTHON_CMD% -m venv "%VENV_DIR%" || (
        echo Failed to create venv
        exit /b 1
    )
)

if exist "%VENV_DIR%\Scripts\python.exe" (
    set PYTHON_EXEC="%VENV_DIR%\Scripts\python.exe"
) else (
    set PYTHON_EXEC=python
)

echo ^>^> Installing Requirements...
%PYTHON_EXEC% -m pip install -r requirements.txt

echo ^>^> Running PDF Converter...
%PYTHON_EXEC% img_pdf.py --input_folder "!CAPTURED_DIR!"

echo ==========================================
echo  Pipeline Finished Successfully
echo ==========================================
pause

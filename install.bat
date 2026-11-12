@echo off
setlocal
cd /d "%~dp0"

echo [1/3] Checking Python...
where python >nul 2>nul
if errorlevel 1 (
    echo Python not found. Download Python 3.11+ from https://www.python.org/downloads/
    echo IMPORTANT: tick "Add Python to PATH" during installation, then re-run this file.
    pause
    exit /b 1
)
python --version

echo [2/3] Installing dependencies...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo Dependency installation failed. Check internet connection and try again.
    pause
    exit /b 1
)

echo [3/3] Checking FFmpeg (needed for WAV output and merging)...
where ffmpeg >nul 2>nul
if errorlevel 1 (
    if exist "C:\ffmpeg\bin\ffmpeg.exe" (
        setx PATH "%PATH%;C:\ffmpeg\bin" >nul
        echo FFmpeg found at C:\ffmpeg\bin and added to PATH.
    ) else (
        echo FFmpeg not found. Download from https://www.gyan.dev/ffmpeg/builds/
        echo Extract to C:\ffmpeg, or set FFMPEG_PATH to your ffmpeg.exe.
        echo MP3 output works without FFmpeg.
    )
) else (
    echo FFmpeg found in PATH.
)

echo.
echo Installation complete! Double-click run.bat to start AI Audio Studio Pro.
pause

@echo off
REM Quick Launcher for QenBel Smart Formatter
cd /d "%~dp0"

if exist "dist\QenBelSmartFormatter\QenBelSmartFormatter.exe" (
    start "" "dist\QenBelSmartFormatter\QenBelSmartFormatter.exe"
) else (
    echo Launching via Python...
    python -m app.main
)

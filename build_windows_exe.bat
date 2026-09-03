@echo off
REM =====================================================================
REM  QenBel Smart Formatter — Windows Build Script
REM  Builds a production desktop .exe package using PyInstaller
REM =====================================================================

echo [QenBel Formatter] Starting build process...

REM Check Python
python --version
if %errorlevel% neq 0 (
    echo [ERROR] Python not found in PATH!
    exit /b %errorlevel%
)

REM Install / verify dependencies
echo [QenBel Formatter] Verifying dependencies...
pip install -r requirements.txt

REM Clean previous builds
echo [QenBel Formatter] Cleaning previous build artifacts...
taskkill /F /IM QenBelSmartFormatter.exe >nul 2>&1
ping 127.0.0.1 -n 2 >nul
if exist "build" rd /s /q "build"
if exist "dist\QenBelSmartFormatter" rd /s /q "dist\QenBelSmartFormatter"

REM Run PyInstaller
echo [QenBel Formatter] Packaging application with PyInstaller...
python -m PyInstaller --clean -y qenbel_formatter.spec

if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller packaging failed!
    exit /b %errorlevel%
)

echo.
echo =====================================================================
echo  BUILD SUCCESSFUL!
echo  Executable location: dist\QenBelSmartFormatter\QenBelSmartFormatter.exe
echo =====================================================================

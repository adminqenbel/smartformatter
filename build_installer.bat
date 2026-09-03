@echo off
setlocal enabledelayedexpansion

REM =====================================================================
REM  QenBel Smart Formatter — Professional Windows Installer Build Script
REM =====================================================================

echo =====================================================================
echo  QenBel Smart Formatter - Production Installer Build
echo =====================================================================

REM Locate ISCC (Inno Setup Compiler)
set "ISCC="
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if "%ISCC%"=="" if exist "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if "%ISCC%"=="" if exist "C:\Program Files\Inno Setup 6\ISCC.exe" set "ISCC=C:\Program Files\Inno Setup 6\ISCC.exe"

if "%ISCC%"=="" (
    echo [ERROR] Inno Setup compiler ^(ISCC.exe^) not found!
    echo Please install Inno Setup 6 using: winget install JRSoftware.InnoSetup
    exit /b 1
)

echo [1/3] Inno Setup compiler detected: "%ISCC%"

REM Step 2: Build PyInstaller distribution
if "%1"=="--skip-pyinstaller" goto SKIP_PYINSTALLER

echo [2/3] Packaging application with PyInstaller...
taskkill /F /IM QenBelSmartFormatter.exe >nul 2>&1
ping 127.0.0.1 -n 2 >nul
if exist "dist\QenBelSmartFormatter" rmdir /s /q "dist\QenBelSmartFormatter"
python -m PyInstaller --clean -y qenbel_formatter.spec
if errorlevel 1 (
    echo [ERROR] PyInstaller packaging failed!
    exit /b 1
)
goto DO_INNO

:SKIP_PYINSTALLER
echo [2/3] Skipping PyInstaller build (--skip-pyinstaller flag passed)...

:DO_INNO
if not exist "dist\QenBelSmartFormatter\QenBelSmartFormatter.exe" (
    echo [ERROR] dist\QenBelSmartFormatter\QenBelSmartFormatter.exe does not exist!
    exit /b 1
)

REM Step 3: Compile Inno Setup package
echo [3/3] Compiling Windows installer with Inno Setup...
if not exist "dist\installer" mkdir "dist\installer"

"%ISCC%" "installer\qenbel_installer.iss"
if errorlevel 1 (
    echo [ERROR] Inno Setup compilation failed!
    exit /b 1
)

echo.
echo =====================================================================
echo  INSTALLER BUILD SUCCESSFUL!
echo  Installer location: dist\installer\QenBel-Smart-Formatter-Setup.exe
echo =====================================================================
endlocal

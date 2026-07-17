@echo off
title Build All - AI Trading Radar v3.0.0
cd /d "%~dp0"

echo ========================================
echo  AI Trading Radar - Full Build (EXE + Installer)
echo ========================================
echo.

echo [1/2] Running build_exe.bat...
call build_exe.bat
if %errorlevel% neq 0 (
    echo [ERROR] Build EXE gagal.
    pause
    exit /b %errorlevel%
)

echo.
echo [2/2] Compiling Installer via Inno Setup...

set "ISCC_PATH=C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

if not exist "%ISCC_PATH%" (
    where ISCC.exe >nul 2>&1
    if %errorlevel% equ 0 (
        set "ISCC_PATH=ISCC.exe"
    ) else (
        echo [ERROR] Inno Setup Compiler (ISCC.exe) tidak ditemukan.
        echo Install Inno Setup 6 di lokasi default:
        echo C:\Program Files (x86)\Inno Setup 6\
        pause
        exit /b 1
    )
)

echo Running: "%ISCC_PATH%" installer.iss
"%ISCC_PATH%" installer.iss
if %errorlevel% neq 0 (
    echo [ERROR] Kompilasi installer gagal.
    pause
    exit /b %errorlevel%
)

echo.
echo ========================================
echo  SUCCESS!
echo  Installer: installer_output\AITradingRadar_Setup_v3.0.0.exe
echo ========================================
pause

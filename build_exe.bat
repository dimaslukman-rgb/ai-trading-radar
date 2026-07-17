@echo off
title Building AI Trading Radar v3.0.0
cd /d "%~dp0"

echo ========================================
echo  AI Trading Radar v3.0.0 - Build EXE
echo ========================================
echo.

:: Auto-detect Python and Pip
set "PYTHON_EXE=python"
set "PIP_CMD=pip"

:: 1. Cek apakah python global 3.14 yang punya pyinstaller & pip bisa diakses langsung
"C:\Users\ASUS\AppData\Local\Python\pythoncore-3.14-64\python.exe" -c "import PyInstaller, pip" >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXE="C:\Users\ASUS\AppData\Local\Python\pythoncore-3.14-64\python.exe""
    set "PIP_CMD="C:\Users\ASUS\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m pip"
    echo [INFO] Menggunakan Python global: %PYTHON_EXE%
    goto :python_detected
)

:: 2. Cek apakah launcher 'py' ada dan memiliki pip/pyinstaller
py -c "import PyInstaller, pip" >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXE=py"
    set "PIP_CMD=py -m pip"
    echo [INFO] Menggunakan Python Launcher: py
    goto :python_detected
)

:: 3. Fallback check 'python'
python -c "import PyInstaller, pip" >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXE=python"
    set "PIP_CMD=python -m pip"
    echo [INFO] Menggunakan default python
    goto :python_detected
)

:: 4. Jika python aktif (venv) tidak memiliki pip/pyinstaller, tapi pip global ada
pip --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_EXE=python"
    set "PIP_CMD=pip"
    echo [WARN] Menggunakan pip global secara langsung.
    goto :python_detected
)

echo [ERROR] Python / Pip / PyInstaller tidak terkonfigurasi dengan benar.
echo Pastikan Python terinstall secara global dengan pip dan pyinstaller.
pause
exit /b 1

:python_detected
echo [1/4] Installing dependencies...
%PIP_CMD% install -e ".[all]"
if %errorlevel% neq 0 (
    echo [WARN] pip install error, melanjutkan...
)

echo [2/4] Installing PyInstaller 6.21.0...
%PIP_CMD% install pyinstaller==6.21.0
if %errorlevel% neq 0 (
    echo [WARN] Gagal menginstall PyInstaller via %PIP_CMD%, mencoba menggunakan versi terinstall...
)

if not exist "icon.ico" (
    echo [3/4] icon.ico tidak ditemukan, lanjut tanpa regenerate.
)

echo [4/4] Building AITradingRadar.exe...
if exist "build" rmdir /s /q "build" 2>nul
if exist "dist\AITradingRadar.exe" del "dist\AITradingRadar.exe" 2>nul
if exist "AITradingBot.spec" del "AITradingBot.spec" 2>nul
if exist "AITradingRadar.spec" del "AITradingRadar.spec" 2>nul

%PYTHON_EXE% -m PyInstaller --onefile ^
    --name "AITradingRadar" ^
    --icon "icon.ico" ^
    --version-file "file_version_info.txt" ^
    --noconsole ^
    --hidden-import "MetaTrader5._core" ^
    --hidden-import "pystray._win32" ^
    --hidden-import "PIL._tkinter_finder" ^
    --hidden-import "PyQt6.QtCore" ^
    --hidden-import "PyQt6.QtGui" ^
    --hidden-import "PyQt6.QtWidgets" ^
    --hidden-import "aitrader_bot.licensing" ^
    --hidden-import "aitrader_bot.app.license_dialog" ^
    --add-data "config.example.json;." ^
    --add-data "config_finex_ultra_m1.json;." ^
    --add-data "data;data" ^
    --collect-all "aitrader_bot" ^
    --clean ^
    --noconfirm ^
    run_scalping.py

echo.
if exist "dist\AITradingRadar.exe" (
    echo ========================================
    echo  BUILD SUCCESS!
    echo  File: dist\AITradingRadar.exe
    for %%I in ("dist\AITradingRadar.exe") do echo  Size: %%~zI bytes
    echo ========================================
    copy "config.example.json" "dist\config.example.json" >nul 2>&1
    copy "config_finex_ultra_m1.json" "dist\config_finex_ultra_m1.json" >nul 2>&1
    if not exist "dist\data" mkdir "dist\data"
    copy "data\sample_prices.csv" "dist\data\" >nul 2>&1
    dir /b "dist\"
) else (
    echo ========================================
    echo  BUILD FAILED!
    echo  Check errors above.
    echo ========================================
)

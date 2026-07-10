@echo off
title Building AI Trading Radar .exe
cd /d "%~dp0"

echo ========================================
echo  AI Trading Radar â€” Build .exe
echo ========================================
echo.

REM ── Read version from version.py ─────────────────────────────────
for /f "tokens=2 delims==" %%a in ('python -c "import sys; sys.path.insert(0,'.'); from aitrader_bot.version import __version__; print(__version__)"') do set APP_VERSION=%%a
if "%APP_VERSION%"=="" (
    echo [ERROR] Cannot read version from aitrader_bot/version.py
    pause
    exit /b 1
)
set APP_VERSION=%APP_VERSION: =%
echo Building version: %APP_VERSION%
echo.

REM Check Python
python --version >nul 2>&1 || (
    echo [ERROR] Python tidak ditemukan. Install Python 3.10+.
    pause
    exit /b 1
)

REM Install dependencies
echo [1/5] Installing dependencies...
pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [WARN] pip install error, melanjutkan...
)

REM Install packaging tools
echo [2/5] Installing PyInstaller...
pip install pyinstaller
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller gagal diinstall.
    pause
    exit /b 1
)

REM Generate icon (if not exists)
if not exist "icon.ico" (
    echo [3/5] Generating icon.ico...
    python -c "
from PIL import Image, ImageDraw
img = Image.new('RGBA', (64, 64), (0,0,0,0))
d = ImageDraw.Draw(img)
d.ellipse([2,2,62,62], fill=(34,197,94,255))
d.ellipse([12,20,24,32], fill=(255,255,255,255))
d.ellipse([40,20,52,32], fill=(255,255,255,255))
d.arc([16,30,48,50], 0, 180, fill=(255,255,255,255), width=3)
img.save('icon.ico', format='ICO', sizes=[(64,64)])
" 2>nul
)
if not exist "icon.ico" (
    echo [WARN] icon.ico tidak bisa dibuat, lanjut tanpa icon.
)

REM Clean old build
echo [4/5] Cleaning old build artifacts...
if exist "dist\AITradingRadar.exe" del "dist\AITradingRadar.exe" 2>nul
if exist "build" rmdir /s /q "build" 2>nul
if exist "AITradingRadar.spec" del "AITradingRadar.spec" 2>nul

REM Build with PyInstaller
echo [5/5] Building AITradingRadar.exe v%APP_VERSION% (this may take several minutes)...

pyinstaller --onefile ^
    --name "AITradingRadar" ^
    --icon "icon.ico" ^
    --version-file "file_version_info.txt" ^
    --hidden-import="MetaTrader5._core" ^
    --hidden-import="pystray._win32" ^
    --hidden-import="PIL._tkinter_finder" ^
    --hidden-import="queue" ^
    --hidden-import="threading" ^
    --add-data "config.example.json;." ^
    --add-data "data;data" ^
    --collect-all "aitrader_bot" ^
    --clean ^
    --noconfirm ^
    run_scalping.py

echo.
if exist "dist\AITradingRadar.exe" (
    echo ========================================
    echo  BUILD SUCCESS!
    echo  Version: %APP_VERSION%
    echo  File: dist\AITradingRadar.exe
    for %%I in ("dist\AITradingRadar.exe") do echo  Size: %%~zI bytes
    echo ========================================
    
    REM Copy config and data
    copy "config.example.json" "dist\config.example.json" >nul 2>&1
    if not exist "dist\data" mkdir "dist\data"
    copy "data\sample_prices.csv" "dist\data\" >nul 2>&1
    
    echo.
    echo Files in dist\:
    dir /b "dist\"
) else (
    echo ========================================
    echo  BUILD FAILED!
    echo  Check errors above.
    echo ========================================
)

pause


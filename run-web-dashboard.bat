@echo off
title AI Trading Radar â€” Web Dashboard
cd /d "%~dp0"

echo ============================================
echo   AI Trading Radar â€” Web Dashboard Launcher
echo ============================================
echo.
echo [1/3] Starting bot in background...
start "AI Bot Engine" "%USERPROFILE%\AppData\Local\Python\pythoncore-3.14-64\python.exe" run_scalping.py --no-gui --auto-start
if %ERRORLEVEL% NEQ 0 (
    echo [FAIL] Gagal start bot. Coba jalankan manual:
    echo   python run_scalping.py --no-gui --auto-start
    pause
    exit /b 1
)

echo [2/3] Waiting for web server to start...
timeout /t 5 /nobreak >nul

echo [3/3] Opening browser...
start "" http://127.0.0.1:9190

echo.
echo ============================================
echo   Web Dashboard: http://127.0.0.1:9190
echo   System Tray:   Icon hijau di taskbar
echo   Telegram:      Notifikasi buy/sell ke HP
echo ============================================
echo.
echo Tekan CTRL+C untuk stop, atau klik Exit di tray.
echo.


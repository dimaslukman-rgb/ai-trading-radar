@echo off
cd /d "%~dp0"
"%~dp0AITradingRadar.exe" --config "%~dp0config.json" --broker default --auto-start --no-gui --no-tray


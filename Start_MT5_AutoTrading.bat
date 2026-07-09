@echo off
cd /d "%~dp0"
start "" "%~dp0AITradingRadar.exe" --config "%~dp0config.json" --broker mt5 --auto-start


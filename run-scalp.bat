@echo off
cd /d "%~dp0"
python -m aitrader_bot.cli scalp --config config_finex.json --broker mt5 --iterations 20 --interval 300
pause

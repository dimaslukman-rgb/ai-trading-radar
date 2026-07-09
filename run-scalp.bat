@echo off
cd /d "%~dp0"
python -m aitrader_bot.cli scalp --config config.example.json --broker default --iterations 20 --interval 300
pause

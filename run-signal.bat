@echo off
cd /d "%~dp0"
python -m aitrader_bot.cli signal --config config.example.json --data data\sample_prices.csv
pause

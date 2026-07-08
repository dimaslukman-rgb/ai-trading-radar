Set-Location -LiteralPath $PSScriptRoot
python -m aitrader_bot.cli signal --config config.example.json --data data\sample_prices.csv

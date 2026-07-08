Set-Location -LiteralPath $PSScriptRoot
python -m aitrader_bot.cli scalp --config config.example.json --broker default --iterations 20 --interval 300

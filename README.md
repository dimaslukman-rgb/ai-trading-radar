# AI Trading Radar

[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![MetaTrader 5](https://img.shields.io/badge/MetaTrader%205-Execution-0052CC?style=for-the-badge)](https://www.metatrader5.com/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg?style=for-the-badge)](LICENSE)
[![Status](https://img.shields.io/badge/Status-Research%20%2B%20Live%20Execution-orange?style=for-the-badge)](#disclaimer)

**AI Trading Radar** is a Python-based algorithmic trading system for XAUUSD scalping research, signal generation, broker execution, and real-time browser monitoring.

Built for operators who need a compact trading stack: strategy logic, risk controls, MT5 execution, Telegram alerts, historical backtests, and a live dashboard in one repository.

> Quantitative Researcher | Algorithmic Trader | Trading Systems Architect

## About

This project focuses on short-horizon XAUUSD trading workflows:

- Research strategy behavior on historical OHLCV data.
- Generate structured `BUY`, `SELL`, and `HOLD` signals.
- Execute through MetaTrader 5 when a live broker profile is configured.
- Track account equity, open positions, entries, current price, floating P&L, and radar confidence through a local web dashboard.
- Keep sensitive broker credentials out of Git by using local-only config files.

The bot includes two primary execution styles:

- **Normal Finex profile**: slower 5-minute scalping settings with session and news filters.
- **Ultra M1 profile**: aggressive 1-minute scalping settings for faster signal rotation and tighter TP/SL logic.

Safe config templates are included. Real broker credentials are intentionally ignored by Git.

## Features

- Multi-broker abstraction with Paper, MT5, CCXT/Binance, and Alpaca adapters.
- XAUUSD scalping strategy with EMA, MACD, Bollinger Bands, Stochastic, RSI, and momentum velocity.
- Broker-authoritative long/short position state with independent multi-ticket tracking, pending/partial close states, and configurable scale-in or hedging policy.
- Risk manager for dynamic position sizing, stop loss, take profit, lock profit, and timeout exits.
- Real-time browser dashboard at `http://127.0.0.1:9190`.
- Open position table with ticket, side, entry, current price, pips, and P&L.
- Telegram notification support for signals, lifecycle events, and errors.
- CSV backtesting and signal generation CLI. Scalping simulations reuse the
  live decision service and position state machine, including long/short risk
  exits, entry gates, higher-timeframe confirmation, sizing, and SL/TP prices.
- TradingView chart dashboard helper.
- Windows-friendly launcher scripts and executable build tooling.

## Technical Stack

- **Language**: Python
- **Execution**: MetaTrader 5 Python API, paper broker simulation
- **Market Connectors**: MT5, CCXT, Alpaca
- **Strategy Layer**: EMA, MACD, RSI, Bollinger Bands, Stochastic, volatility and momentum scoring
- **Dashboard**: Python `http.server`, Server-Sent Events, HTML/CSS/JavaScript, TradingView widget
- **Notifications**: Telegram Bot API
- **Packaging**: PyInstaller, Inno Setup
- **Testing**: Python `unittest`
- **Operating Target**: Windows desktop/VPS with MetaTrader 5 installed

## Requirements

Minimum:

- Python 3.10 or newer
- Git
- MetaTrader 5 terminal, required only for MT5 live execution
- A broker account configured inside MT5, required only for live execution

Install Python dependencies:

```powershell
pip install -r requirements.txt
```

Core CLI/backtest functionality can run with the Python standard library. MT5, GUI, Telegram, and exchange connectors require the optional packages listed in `requirements.txt`.

## Quick Start

Clone the repository:

```powershell
git clone https://github.com/dimaslukman-rgb/ai-trading-radar.git
cd ai-trading-radar
```

Run the test suite:

```powershell
python -m unittest discover -s tests -v
```

Run a sample backtest:

```powershell
python -m aitrader_bot.cli backtest --config config.example.json --data data/sample_prices.csv
```

Generate a signal from local CSV data:

```powershell
python -m aitrader_bot.cli signal --config config.example.json --data data/sample_prices.csv
```

## MT5 Live Setup

Copy an example config and fill in local credentials:

```powershell
copy config_xauusd_m1_ultra.example.json config_xauusd_m1_ultra.json
```

Edit only the local config file:

```json
"telegram": {
  "enabled": true,
  "bot_token": "YOUR_TELEGRAM_BOT_TOKEN",
  "chat_id": "YOUR_CHAT_ID"
},
"brokers": {
  "mt5": {
    "backend": "mt5",
    "server": "YOUR_MT5_SERVER",
    "login": 12345678,
    "password": "YOUR_MT5_PASSWORD"
  }
}
```

`config_xauusd_m1_ultra.json`, `config_finex.json`, and other live config files are ignored by Git.

## Run Live Bot

Start the M1 MT5 live engine in the background:

```powershell
Start-Process -FilePath "C:\Users\ASUS\AppData\Local\Python\pythoncore-3.14-64\python.exe" -ArgumentList @('run_scalping.py','--config','config_xauusd_m1_ultra.json','--broker','mt5','--no-gui','--no-tray','--auto-start') -WorkingDirectory "." -WindowStyle Hidden
```

Open the dashboard:

```text
http://127.0.0.1:9190
```

Check bot process ID:

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*run_scalping.py*' } | Select-Object ProcessId,CommandLine
```

Stop the bot:

```powershell
Stop-Process -Id YOUR_PROCESS_ID
```

Or stop every running bot process:

```powershell
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like '*run_scalping.py*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId }
```

## Project Structure

```text
aitrader_bot/
  app/             Web dashboard, GUI, tray, logging, Telegram notifier
  broker/          Paper, MT5, CCXT, Alpaca broker adapters
  backtest.py      Historical simulation engine
  decision.py      Shared live, CLI, and backtest trading decisions
  position_state.py Long/short and multi-ticket position state machine
  scalping.py      XAUUSD scalping strategy and risk manager
  strategy.py      Momentum signal model
  config.py        Typed config loader
data/              Sample and XAUUSD research datasets
tests/             Unit tests
run_scalping.py    Windows app/live engine launcher
```

## Configuration Profiles

- `config.example.json`: safe default paper config.
- `config_finex.example.json`: sanitized 5-minute XAUUSD profile.
- `config_xauusd_m1_ultra.example.json`: sanitized aggressive M1 profile.

Position behavior is explicit in every safe template. Defaults preserve one position at a time:

```json
{
  "scalping": {
    "allow_long_entries": true,
    "allow_short_entries": true,
    "max_open_positions": 1,
    "max_positions_per_side": 1,
    "allow_scale_in": false,
    "hedging_enabled": false,
    "close_on_opposite_signal": true,
    "opposite_exit_only_in_profit": true
  }
}
```

Set both position limits above `1` and enable `allow_scale_in` only after verifying that the connected broker account supports independent hedged tickets. MT5 netting accounts remain limited to one net position.

Local live profiles are excluded from Git:

- `config_finex.json`
- `config_finex_aggressive_1m.json`
- `config_xauusd_m1_ultra.json`

## Safety Model

Live execution uses fail-closed entry controls:

- Session, news, and spread filters block new entries but never suppress management of an existing position.
- Spread thresholds are compared in broker points using each quote's point size.
- Live, CLI, and scalping backtest paths use the same decision service for
  risk exits, signal actions, entry sizing, and position-policy enforcement.
- Paper backtests execute buys at ask, sells at bid, and apply historical
  session/news/spread gates rather than assuming cost-free fills.
- MT5 and Paper entries attach stop-loss and take-profit prices to the order. Generic CCXT and Alpaca entries are blocked until their adapters implement atomic protective orders.
- MT5 position timestamps and protective prices are recovered after restart; missing SL/TP is repaired through the broker when possible.
- A position is recorded as closed only after the broker reports a full fill. Pending, partial, rejected, and missing close results keep local position state open.

The repository also avoids accidental credential leakage:

- Live configs are ignored by `.gitignore`.
- Build artifacts, logs, cache files, and executable output are ignored.
- Public examples contain blank tokens, blank passwords, and `null` login values.
- The dashboard is local-only by default at `127.0.0.1`.

Before pushing changes, scan staged files:

```powershell
git diff --cached --name-only
git grep -n --cached -I -E "password|bot_token|api_key|secret|login"
```

## Roadmap

- Strategy performance reports by market session.
- Risk dashboard with daily loss limits and max drawdown controls.
- Walk-forward strategy validation with session and transaction-cost reports.
- Docker or Windows Task Scheduler deployment recipes.

## Contributing

Contributions, issues, and feature requests are welcome.

Before opening a pull request:

- Keep credentials, logs, and live broker configs out of commits.
- Run `python -m unittest discover -s tests -v`.
- Keep changes scoped and explain trading-behavior changes clearly.
- Include sample data or tests when changing strategy/risk logic.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the full contribution guide.

## License

This project is licensed under the **GNU General Public License v3.0**.

See [LICENSE](LICENSE) for the full license text.

## Disclaimer

This software is provided for research, education, and engineering experimentation.

It is **not financial advice**, investment advice, tax advice, legal advice, or a recommendation to buy or sell any instrument. Trading forex, CFDs, commodities, crypto, stocks, futures, or leveraged products involves substantial risk and may result in partial or total loss of capital.

You are solely responsible for:

- Reviewing the source code before use.
- Testing in paper/demo environments.
- Verifying broker settings, lot sizes, leverage, margin, symbols, spreads, and execution behavior.
- Monitoring the bot while it is running.
- Complying with local laws, broker rules, and exchange rules.

The authors and contributors are not responsible for losses, damages, missed profits, account restrictions, broker errors, API outages, execution slippage, or any other consequence of using this software.

## Contact

- GitHub: [@dimaslukman-rgb](https://github.com/dimaslukman-rgb)
- Repository: [dimaslukman-rgb/ai-trading-radar](https://github.com/dimaslukman-rgb/ai-trading-radar)

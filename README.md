<div align="center">

# AI Trading Radar

**Professional Multi-Factor Analysis Engine -- XAUUSD Scalping for MT5/Finex**

[![Version](https://img.shields.io/badge/version-1.2.0-00ff88?style=for-the-badge&labelColor=0a0e17)](https://github.com/dimaslukman-rgb/ai-trading-radar/releases/tag/v1.2.0)
[![Python](https://img.shields.io/badge/Python-3.10+-00d4ff?style=for-the-badge&labelColor=0a0e17&logo=python&logoColor=00d4ff)](https://python.org)
[![License](https://img.shields.io/badge/License-Proprietary-a855f7?style=for-the-badge&labelColor=0a0e17)]()
[![Platform](https://img.shields.io/badge/Platform-Windows-ffaa00?style=for-the-badge&labelColor=0a0e17&logo=windows&logoColor=ffaa00)]()

Live AI-powered scalping signals, real-time dashboard, and automated MT5 execution -- all in one Windows desktop application.

[Download Latest Installer](https://github.com/dimaslukman-rgb/ai-trading-radar/releases/tag/v1.2.0)  |  [Report Bug](https://github.com/dimaslukman-rgb/ai-trading-radar/issues)

</div>

---

## What's New in v1.2.0

### Auto-Update System

The app now automatically checks for new versions via GitHub Releases! No more manual downloads.

- **Background check** -- Checks every 24 hours automatically
- **One-click update** -- Download & install directly from the web dashboard
- **Progress bar** -- See download progress in real-time
- **Smart installer** -- Inno Setup detects existing install and upgrades seamlessly
- **CLI support** -- `--check-update` and `--version` flags

> **How it works:** The app checks GitHub Releases in the background. When a new version is found, a banner appears in the dashboard -- just click **Download** then **Install**.

[Check out v1.2.0 Release](https://github.com/dimaslukman-rgb/ai-trading-radar/releases/tag/v1.2.0)

---

## Features

| Real-Time Analysis | Live Dashboard | Smart Execution |
|:---|:---|:---|
| Trend, EMA, BOS, Order Block | TradingView XAUUSD M1 chart | MT5/Finex auto-trading |
| Liquidity Sweep, Volume, RSI, MACD, FVG | Confidence score breakdown | Entry / SL / TP management |
| Session detection (Sydney/Tokyo/London/NY) | Sentiment & volatility index | Risk:Reward optimization |
| High-impact news filter | Signal history & live log | Aggressive mode for M1 scalping |

---

## Quick Start

### Prerequisites

- **Windows 10/11**
- **Python 3.10+**
- **MetaTrader 5** (for live trading with Finex/MT5)

### Installation

```powershell
# 1. Clone the repository
git clone https://github.com/dimaslukman-rgb/ai-trading-radar.git
cd ai-trading-radar

# 2. Install dependencies
python -m pip install -r requirements.txt

# 3. Copy config
copy config.example.json config.json

# 4. Edit config.json with your MT5 credentials:
#    brokers.mt5.login, brokers.mt5.password, brokers.mt5.server

# 5. Run the bot
python run_scalping.py --config config.json --broker mt5 --auto-start

# 6. Open dashboard
#    -> http://127.0.0.1:9190
```

### Check Version & Updates

```powershell
# Show version info
python run_scalping.py --version

# Check for updates
python run_scalping.py --check-update
```

---

## Usage Modes

| Command | Description |
|:--------|:------------|
| `python run_scalping.py` | Full mode: Tray icon + Web Dashboard |
| `python run_scalping.py --no-gui` | Background mode: Tray only (recommended) |
| `python run_scalping.py --no-tray` | Web Dashboard only, no tray |
| `python run_scalping.py --no-gui --no-tray` | Pure CLI mode |
| `python run_scalping.py --version` | Show current version |
| `python run_scalping.py --check-update` | Check for newer version on GitHub |
| `python run_scalping.py --auto-start` | Auto-start the trading engine on launch |
| `python run_scalping.py --reset-license` | Reset stored license key |

---

## Architecture

```
+------------------------------------------------------------------+
|                      AI TRADING RADAR                             |
+----------+---------+-------------+----------+--------------------+
|  Engine  | Broker  |  Dashboard  | License  |    Auto-Update     |
|          |         |             |          |                    |
| Strategy | MT5     | Web HTTP    | Serial   | Background Checker |
| Risk     | Finex   | Server 9190 | Key      | Downloader         |
| Signal   | Paper   | SSE Updates | Valid.   | Installer Launcher |
+----------+---------+-------------+----------+--------------------+
|        Shared State (Thread-Safe) -- dashboard_data.py            |
+------------------------------------------------------------------+
```

---

## Build from Source

### Windows Executable

```powershell
# Auto-build script (recommended)
build_exe.bat

# Or manually:
pyinstaller --onefile --name "AITradingRadar" --icon "icon.ico" ^
    --version-file "file_version_info.txt" ^
    --hidden-import="MetaTrader5._core" ^
    --hidden-import="pystray._win32" ^
    --hidden-import="PIL._tkinter_finder" ^
    --hidden-import="queue" ^
    --hidden-import="threading" ^
    --add-data="config.example.json;." ^
    --add-data="data;data" ^
    --collect-all=aitrader_bot ^
    run_scalping.py
```

### Windows Installer (Inno Setup)

1. Build the EXE first (see above)
2. Open `installer.iss` in **Inno Setup Compiler**
3. Click **Build** -> **Compile**
4. Output: `installer_output\AITradingRadar_Setup.exe`

### Automated Release

```powershell
# Preview release steps
python tools\release.py --dry-run

# Full release (build + upload to GitHub)
python tools\release.py --publish --token ghp_xxxx
```

---

## Project Structure

```
ai-trading-radar/
  aitrader_bot/           Core package
    version.py            Single source of truth for version
    updater.py            Auto-update system (NEW in v1.2.0)
    config.py             Configuration loader
    data.py               Market data handlers
    indicators.py         Technical indicators
    strategy.py           Trading strategy logic
    scalping.py           Scalping-specific logic
    risk.py               Risk management
    portfolio.py          Portfolio tracking
    licensing.py          Serial key licensing
    models.py             Data models
    backtest.py           Backtesting engine
    cli.py                Command-line interface
    broker/               Broker integrations
      mt5_broker.py       MetaTrader 5
      paper_broker.py     Paper/demo trading
      ccxt_broker.py      CCXT exchange support
      alpaca_broker.py    Alpaca trading
    app/                  Desktop application
      dashboard_template.html  Web dashboard UI
      web_dashboard.py         HTTP server + SSE
      dashboard_data.py        Shared state store
      engine.py                Trading engine
      gui.py                   PyQt6 dashboard
      tray.py                  System tray icon
      logger.py                Logging system
      news_filter.py           News impact filter
  tools/                  Development tools
    release.py            Release automation (NEW in v1.2.0)
    make_serial.py        License key generator
  data/                   Sample market data (CSV)
  tests/                  Test suite
  run_scalping.py         Entry point
  config.example.json     Example configuration
  installer.iss           Inno Setup installer script
  build_exe.bat           Windows build script
  file_version_info.txt   Windows EXE metadata
  requirements.txt        Python dependencies
```

---

## Security

- Never commit real MT5 credentials, Telegram tokens, API keys, or license files
- All secrets are stored in `config.json` (gitignored)
- License keys are stored in `%APPDATA%\AITradingRadar\license.json`
- The `.gitignore` covers sensitive files by default

---

## License

**Proprietary** -- Private distribution with serial-key activation.

This software is not open-source. A valid license key is required to use the application.

---

<div align="center">

**Made for XAUUSD scalping**

[Download v1.2.0](https://github.com/dimaslukman-rgb/ai-trading-radar/releases/tag/v1.2.0)  |  [Report Bug](https://github.com/dimaslukman-rgb/ai-trading-radar/issues)

</div>

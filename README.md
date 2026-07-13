<div align="center">

# AI Trading Radar

**Professional Multi-Factor Analysis Engine — XAUUSD Scalping for MT5/Finex**

[![Version](https://img.shields.io/badge/version-2.0.1-00ff88?style=for-the-badge&labelColor=0a0e17)](https://github.com/dimaslukman-rgb/ai-trading-radar/releases/tag/v2.0.1)
[![Python](https://img.shields.io/badge/Python-3.10+-00d4ff?style=for-the-badge&labelColor=0a0e17&logo=python&logoColor=00d4ff)](https://python.org)
[![License](https://img.shields.io/badge/License-Proprietary-a855f7?style=for-the-badge&labelColor=0a0e17)]()
[![Platform](https://img.shields.io/badge/Platform-Windows-ffaa00?style=for-the-badge&labelColor=0a0e17&logo=windows&logoColor=ffaa00)]()

Live AI-powered scalping signals, real-time dashboard, and automated MT5 execution — all in one Windows desktop application.

[Download v2.0.1 Installer](https://github.com/dimaslukman-rgb/ai-trading-radar/releases/tag/v2.0.1)  |  [Report Bug](https://github.com/dimaslukman-rgb/ai-trading-radar/issues)  |  [View Dashboard Demo](https://github.com/dimaslukman-rgb/ai-trading-radar)

</div>

---

## What's New in v2.0.1

- Fixed Windows startup when loading version metadata (`VERSION_TUPLE`)
- Fixed dashboard state snapshot syntax so the packaged app starts correctly
- Corrected the default GitHub update repository and excluded local `tools` from builds

## What's New in v2.0.0

### 🔐 MT5 Login Dialog (New!)
Every time the bot runs, a **popup login dialog** (PyQt6) appears asking for MT5 credentials:
- **Server** — e.g. `FinexBisnisSolusi-Demo`
- **Login** — MT5 account number
- **Password** — MT5 account password

After successful login, the bot **auto-starts** and runs in the **Windows system tray**.

> **Why?** So you never have to store real credentials in config files. Login securely every session.

### 🤖 Multi-Agent AI System (New!)
A team of **20+ specialized AI agents** analyze the market before every trade:
- **Chief Trader** — Final decision maker, aggregates all agent reports
- **Trend Analyst** — Identifies trend direction and strength
- **Price Action** — Candlestick patterns and market structure
- **Market Structure** — BOS, CHOCH, order blocks
- **Liquidity** — Liquidity sweeps and stop hunts
- **Volatility** — ATR, Bollinger Band width, volatility regime
- **Volume Profile** — High volume nodes, value area
- **Smart Money** — Institutional order flow concepts
- **Session Analyst** — London/NY/Tokyo/Sydney session influence
- **Correlation** — XAUUSD correlations with DXY, yields
- **Risk Manager** — Position sizing based on account risk
- **Exit Strategy** — Optimal take-profit and stop-loss placement
- **Journal** — Trade journal and performance tracking
- And more...

Each agent votes with a confidence score. The **Chief Trader** compiles the analysis and either confirms or rejects signals.

### 📊 MT5 Account Management (New!)
- View **balance, equity, margin, free margin, leverage** in real-time
- Account info displayed in both GUI dashboard and web dashboard
- Connection status indicator (CONNECTED / DISCONNECTED)
- Server and UserLogin information visible at all times

### 🌐 Enhanced Web Dashboard
- MT5 account info (login number & server) in the header
- Real-time account balance & equity display
- Agent analysis summary with confidence scores
- Improved signal breakdown with factor indicators
- Better news catalyst integration

### 🔧 Other Improvements
- Refactored engine into dedicated services (`services/` folder)
- New `position_state.py` for robust position management
- New `decision.py` for unified trading decisions
- New `research.py` and `walk_forward.py` for advanced backtesting
- Cost-aware walk-forward optimization research
- Integration tests and CI pipeline

---

## Auto-Update System

The app automatically checks for new versions via GitHub Releases!

- **Background check** — Checks every 24 hours automatically
- **One-click update** — Download & install directly from the web dashboard
- **Progress bar** — See download progress in real-time
- **Smart installer** — Inno Setup detects existing install and upgrades seamlessly
- **CLI support** — `--check-update` and `--version` flags

> **How it works:** The app checks GitHub Releases in the background. When a new version is found, a banner appears in the dashboard — just click **Download** then **Install**.

---

## Features

| Real-Time Analysis | Live Dashboard | Smart Execution |
|:---|:---|:---|
| Trend, EMA, BOS, Order Block | TradingView XAUUSD M1 chart | MT5/Finex auto-trading |
| Liquidity Sweep, Volume, RSI, MACD, FVG | Confidence score breakdown | Entry / SL / TP management |
| Session detection (Sydney/Tokyo/London/NY) | Sentiment & volatility index | Risk:Reward optimization |
| High-impact news filter | Signal history & live log | Aggressive mode for M1 scalping |
| **20+ AI Agents** (NEW in v2.0.0) | **MT5 Account Info** (NEW) | **Login Dialog** (NEW) |

---

## Quick Start

### Prerequisites

- **Windows 10/11**
- **Python 3.10+** (for source installation)
- **MetaTrader 5** (for live trading with Finex/MT5)
- **PyQt6** (for login dialog and GUI dashboard)

### Installation

```powershell
# 1. Clone the repository
git clone https://github.com/dimaslukman-rgb/ai-trading-radar.git
cd ai-trading-radar

# 2. Install all dependencies
python -m pip install -r requirements.txt

# 3. Install optional desktop dependencies
python -m pip install PyQt6 pystray Pillow win10toast

# 4. Copy config
copy config.example.json config.json

# 5. Run the bot (login dialog will appear)
python run_scalping.py --config config.json --broker mt5
```

> **Note:** In v2.0.0, you no longer need to edit `config.json` with MT5 credentials. The **login dialog** will prompt you for server, login, and password every time you run the bot.

### Login Flow

1. Run `python run_scalping.py`
2. A **PyQt6 popup dialog** appears asking for:
   - **Server** — e.g. `FinexBisnisSolusi-Demo`
   - **Login** — e.g. `60779778`
   - **Password** — your MT5 password
3. Click **Connect**
4. Bot auto-starts and connects to MT5
5. Dashboard opens at `http://127.0.0.1:9190/`
6. System tray icon appears for stop/start controls

> **Skip login** for development: `python run_scalping.py --skip-login` (uses credentials from config file)

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
| `python run_scalping.py` | Full mode: Login Dialog → Tray + Web Dashboard |
| `python run_scalping.py --no-gui` | Background mode: Tray only (recommended) |
| `python run_scalping.py --no-tray` | Web Dashboard only, no tray |
| `python run_scalping.py --no-gui --no-tray` | Pure CLI mode (console login fallback) |
| `python run_scalping.py --skip-login` | Skip login popup, use config file credentials |
| `python run_scalping.py --auto-start` | Auto-start the trading engine on launch |
| `python run_scalping.py --version` | Show current version |
| `python run_scalping.py --check-update` | Check for newer version on GitHub |
| `python run_scalping.py --reset-license` | Reset stored license key |

### Run as Windows Executable

```powershell
# Just double-click AITradingRadar.exe
# Or run from command line:
AITradingRadar.exe [--skip-login] [--no-gui] [--auto-start]
```

---

## Architecture

```
+---------------------------------------------------------------------+
|                      AI TRADING RADAR v2.0.0                        |
+----------+---------+-------------+----------+----------+-----------+
|  Engine  | Broker  |  Dashboard  | Agents   | License  | Auto-     |
|          |         |             |          |          | Update    |
| Strategy | MT5     | Web HTTP    | Chief    | Serial   | Background|
| Risk     | Finex   | Server 9190 | Trader   | Key      | Checker   |
| Signal   | Paper   | SSE Updates | 20+ AI   | Valid.   | Download  |
| Services | CCXT    | GUI (PyQt6) | Agents   |          | Installer |
+----------+---------+-------------+----------+----------+-----------+
|  Services Layer: execution, market_data, position_state, risk, signal |
+----------------------------------------------------------------------+
|        Shared State (Thread-Safe) -- dashboard_data.py                |
+----------------------------------------------------------------------+
```

### Multi-Agent AI Pipeline

```
Market Data → 20+ Specialized Agents → Chief Trader → Decision
                                                        ↓
                                              Signal Validation
                                              Confidence Boost/Reduce
                                              Entry Block Veto
```

---

## Build from Source

### Windows Executable

```powershell
# Auto-build script (recommended)
build_exe.bat

# Or manually with PyInstaller:
pip install pyinstaller

pyinstaller --onefile --name "AITradingRadar" --icon "icon.ico" ^
    --version-file "file_version_info.txt" ^
    --hidden-import="MetaTrader5._core" ^
    --hidden-import="pystray._win32" ^
    --hidden-import="PIL._tkinter_finder" ^
    --hidden-import="queue" ^
    --hidden-import="threading" ^
    --hidden-import="PyQt6" ^
    --hidden-import="PyQt6.QtCore" ^
    --hidden-import="PyQt6.QtGui" ^
    --hidden-import="PyQt6.QtWidgets" ^
    --add-data="config.example.json;." ^
    --add-data="data;data" ^
    --collect-all=aitrader_bot ^
    run_scalping.py
```

### Windows Installer (Inno Setup)

1. **Build the EXE first** (see above)
2. **Download and install** [Inno Setup](https://jrsoftware.org/isdl.php)
3. Open `installer.iss` in **Inno Setup Compiler**
4. Click **Build** → **Compile**
5. Output: `installer_output\AITradingRadar_Setup_v2.0.1.exe`

> The installer supports **auto-upgrade** — it detects existing installations and preserves user config.

---

## Project Structure

```
ai-trading-radar/
  aitrader_bot/              Core package
    version.py               Single source of truth for version
    updater.py               Auto-update system
    config.py                Configuration loader
    data.py                  Market data handlers
    indicators.py            Technical indicators
    strategy.py              Trading strategy logic
    scalping.py              Scalping-specific logic
    risk.py                  Risk management
    portfolio.py             Portfolio tracking
    licensing.py             Serial key licensing
    models.py                Data models
    backtest.py              Backtesting engine
    decision.py              Unified trading decisions (NEW in v2.0.0)
    position_state.py        Position state machine (NEW in v2.0.0)
    research.py              Research tools (NEW in v2.0.0)
    walk_forward.py          Walk-forward analysis (NEW in v2.0.0)
    cli.py                   Command-line interface
    agents/                  Multi-Agent AI System (NEW in v2.0.0)
      chief_trader.py        Chief Trader - final decision maker
      integration.py         Agent integration with trading engine
      trend_analyst.py       Trend analysis agent
      price_action.py        Price action patterns agent
      market_structure.py    Market structure agent
      liquidity.py           Liquidity analysis agent
      volatility.py          Volatility regime agent
      volume_profile.py      Volume profile agent
      smart_money.py         Smart money concepts agent
      session.py             Session analysis agent
      correlation.py         Correlation analysis agent
      risk_manager.py        Risk management agent
      position_sizing.py     Position sizing agent
      entry_strategy.py      Entry strategy agent
      exit_strategy.py       Exit strategy agent
      trade_management.py    Trade management agent
      trade_execution.py     Execution agent
      indicator_confirmation.py  Indicator confirmation agent
      news_macro.py          News & macro analysis agent
      performance_analyst.py Performance analysis agent
      journal.py             Trading journal agent
      order_flow.py          Order flow agent
      base.py                Base agent class
    services/                Service Layer (NEW in v2.0.0)
      execution.py           Order execution service
      market_data.py         Market data service
      position_state.py      Position state service
      risk.py                Risk service
      signal.py              Signal generation service
    broker/                  Broker integrations
      mt5_broker.py          MetaTrader 5
      paper_broker.py        Paper/demo trading
      ccxt_broker.py         CCXT exchange support
      alpaca_broker.py       Alpaca trading
    app/                     Desktop application
      login_dialog.py        MT5 Login popup (NEW in v2.0.0)
      dashboard_template.html  Web dashboard UI
      web_dashboard.py       HTTP server + SSE + MT5 account mgmt
      dashboard_data.py      Shared state store
      engine.py              Trading engine + multi-agent integration
      gui.py                 PyQt6 dashboard with login info bar
      tray.py                System tray icon
      logger.py              Logging system
      news_filter.py         News impact filter
      notifier.py            Telegram notification
  data/                      Sample market data (CSV)
  tests/                     Test suite
  run_scalping.py            Entry point with login dialog
  config.example.json        Example configuration
  installer.iss              Inno Setup installer script
  build_exe.bat              Windows build script
  file_version_info.txt      Windows EXE metadata
  requirements.txt           Python dependencies
  pyproject.toml             Project metadata
```

---

## Security

- **MT5 Credentials** — Entered via login dialog every session (not stored in config)
- Never commit real MT5 credentials, Telegram tokens, API keys, or license files
- All secrets are stored in `config.json` (gitignored)
- License keys are stored in `%APPDATA%\AITradingRadar\license.json`
- The `.gitignore` covers sensitive files by default
- Password field uses `QLineEdit.EchoMode.Password` (masked input)
- Password is never logged — only server and login are logged for debugging

---

## License

**Proprietary** — Private distribution with serial-key activation.

This software is not open-source. A valid license key is required to use the application.

---

<div align="center">

**Made for XAUUSD scalping — v2.0.1 with Multi-Agent AI**

[Download v2.0.1](https://github.com/dimaslukman-rgb/ai-trading-radar/releases/tag/v2.0.1)  |  [Report Bug](https://github.com/dimaslukman-rgb/ai-trading-radar/issues)  |  [View Dashboard](http://127.0.0.1:9190)

</div>

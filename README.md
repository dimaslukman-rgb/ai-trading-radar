# AI Trading Radar

Windows desktop trading radar for XAUUSD/MT5 with a live web dashboard, serial-key licensing, and MT5 auto-start mode.

Version: `1.1.0`

## Features

- Live AI Trading Radar dashboard at `http://127.0.0.1:9190`.
- MetaTrader 5 broker integration for Finex/MT5 accounts.
- XAUUSD dual-state scalping strategy: momentum and mean reversion.
- Equity, balance, price, confidence, signal status, news catalyst, and signal history panels.
- Offline serial-key licensing with `tools/make_serial.py`.
- Windows packaging support through PyInstaller and IExpress package scripts.

## Quick Start

1. Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

2. Create local config:

```powershell
copy config.example.json config.json
```

3. Edit `config.json` and fill:

```text
brokers.mt5.login
brokers.mt5.password
brokers.mt5.server
```

4. Run MT5 auto-start mode:

```powershell
python run_scalping.py --config config.json --broker mt5 --auto-start
```

5. Open dashboard:

```text
http://127.0.0.1:9190
```

## Serial Keys

Generate a customer serial:

```powershell
python tools\make_serial.py --plan 1m --customer "Customer Name"
```

Supported plans: `1m`, `3m`, `6m`, `1y`, `lifetime`.

Generated serials are appended to `generated_serial_keys.txt`, which is intentionally ignored by Git.

## Windows Build

Build executable:

```powershell
python -m PyInstaller AITradingRadar-Windows.spec --clean --noconfirm
```

The spec now produces:

```text
dist\AITradingRadar.exe
```

## Security

Do not commit:

- real MT5 credentials
- customer serial keys
- local `config.json`
- logs
- generated installers or release ZIP files

These are covered by `.gitignore`.


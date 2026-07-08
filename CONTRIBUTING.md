# Contributing

Thank you for considering a contribution to AI Trading Radar.

This repository touches trading logic, live broker execution, and account-risk workflows. Changes should be clear, testable, and conservative.

## Ground Rules

- Do not commit real broker credentials, Telegram tokens, API keys, account numbers, or private logs.
- Do not commit `config_finex.json`, `config_xauusd_m1_ultra.json`, `.env`, `build/`, `dist/`, or runtime logs.
- Keep live-execution behavior explicit. If a change can open, close, resize, or reverse a position, describe it clearly.
- Prefer small pull requests with one clear purpose.
- Add or update tests when changing strategy, risk, broker, or dashboard data contracts.

## Development Setup

Clone the repository:

```powershell
git clone https://github.com/dimaslukman-rgb/ai-trading-radar.git
cd ai-trading-radar
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Run tests:

```powershell
python -m unittest discover -s tests -v
```

Run a sample backtest:

```powershell
python -m aitrader_bot.cli backtest --config config.example.json --data data/sample_prices.csv
```

## Secret Hygiene

Before committing:

```powershell
git status --short
git diff --cached --name-only
git grep -n --cached -I -E "password|bot_token|api_key|secret|login"
```

If the scan finds an example placeholder, verify it is not a real value. If it finds a real secret, remove it before committing and rotate the exposed credential.

## Pull Request Checklist

- Tests pass locally.
- README or docs are updated when behavior changes.
- Live trading implications are documented.
- No credentials, account IDs, personal tokens, logs, or build artifacts are included.
- Broker-specific changes are tested with paper/demo mode before live use.

## Strategy Changes

For strategy or risk changes, include:

- What market condition the change targets.
- Which indicators, thresholds, or exits changed.
- Expected effect on trade frequency, drawdown, position size, or holding time.
- Backtest or demo-test notes when available.

## Disclaimer

Contributions are reviewed as software changes, not as financial advice. Every user is responsible for testing, monitoring, and accepting the risk of running any trading system.


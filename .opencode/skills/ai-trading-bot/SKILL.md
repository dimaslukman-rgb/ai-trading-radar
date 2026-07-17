---
name: ai-trading-bot
description: >
  Use when working on AI Trading Bot — XAUUSD scalping strategy, MT5 execution,
  web dashboard, backtesting, risk management, Telegram alerts, or any file
  under aitrader_bot/, run_scalping.py, config_*.json, or tests/.
---

# AI Trading Bot — Developer Skill

## Project Identity

AI Trading Bot (AI Trading Radar) is a Python-based algorithmic trading system for XAUUSD scalping. It uses a **dual-state strategy** (momentum vs mean reversion detection), **pip-based risk management**, and supports **MT5, Binance, Alpaca, and Paper brokers**.

## Architecture

```
run_scalping.py  ← primary entry point (desktop app)
└─ TradingEngine (daemon thread)
   ├─ Config loader → frozen dataclasses
   ├─ Broker factory → paper/mt5/ccxt/alpaca
   ├─ ScalpingStrategy → dual-state signal
   ├─ PositionStateMachine → broker-authoritative state
   ├─ TradingDecisionService → risk + execution planning
   ├─ ExecutionService → order placement + reconciliation
   └─ DashboardDataStore → thread-safe shared state
       ├─ Web Dashboard (HTTP + SSE, port 9190)
       ├─ PyQt6 GUI window (optional)
       └─ System Tray icon (optional)
```

### Key Modules & Responsibilities

| Module | File | Purpose |
|--------|------|---------|
| **Engine** | `app/engine.py` | Main scalping loop, broker lifecycle, signal→execute→notify cycle |
| **Strategy** | `scalping.py` | Dual-state scalping (State A: EMA+MACD momentum, State B: BB+Stochastic mean reversion) |
| **Decision** | `decision.py` | Entry gates (sessions, news, spread), HTF confirmation, pip→price conversion |
| **Position** | `position_state.py` | State machine: multi-ticket, scale-in, hedging, partial close, broker sync |
| **Execution** | `services/execution.py` | Order dispatch, reconciliation, P&L calc, SL/TP repair |
| **Signal** | `services/signal.py` | Signal generation + radar analysis (trend, BOS, order block, FVG, etc.) |
| **Market** | `services/market_data.py` | Quote + candles + bars snapshot |
| **Risk** | `services/risk.py` | Safety gates facade |
| **Dashboard** | `app/web_dashboard.py` | Zero-dep HTTP server, SSE streaming |
| **GUI** | `app/gui.py` | PyQt6 desktop window |
| **Tray** | `app/tray.py` | System tray (pystray) |
| **Notifier** | `app/notifier.py` | Telegram bot |
| **News** | `app/news_filter.py` | 2026 macro news schedule |
| **Config** | `config.py` | Frozen dataclasses: BotConfig, ScalpingConfig, RiskConfig |
| **Broker** | `broker/` | Abstract base → paper, MT5, CCXT, Alpaca adapters |

## Conventions

### Code Style
- `from __future__ import annotations` at top of every module
- Full type hints: Python 3.10+ `X | None` syntax, return types always specified
- `@dataclass(frozen=True)` for immutable data objects
- Abstract methods use `...` (Ellipsis), not `pass`
- CamelCase classes, snake_case functions/variables, UPPER_SNAKE_CASE constants
- Deep relative imports: `from ..broker.base import Quote`
- Indonesian/Bahasa Indonesia in CLI messages, logs, comments

### Error Handling
- Broker returns `OrderResult` with `OrderStatus.REJECTED` + message, not exceptions
- Engine wraps each iteration in try/except; errors logged, notified, loop continues
- Lazy imports with try/except ImportError + install instructions
- Non-blocking queue.put() with bare except fallback

### Testing
- Framework: Python `unittest` (no pytest)
- Run all: `python -m unittest discover tests -v`
- Test files: `test_core.py`, `test_decision.py`, `test_position_state.py`, `test_live_safety.py`
- Contract tests ensure live & backtest decisions match (test_decision.py)

## Key Design Decisions

1. **Dual-state strategy**: Automatically detects trending (EMA+MACD) vs sideways (BB+Stochastic) markets
2. **Broker-authoritative positions**: State machine syncs from broker at every cycle
3. **Pip-based risk**: SL/TP in pips (XAU=0.1, JPY=0.01, forex=0.0001), not percentages
4. **Zero-dep core**: Strategy, backtest, CLI, web dashboard use Python stdlib only
5. **MT5 hardening**: `order_check()` before `order_send()`, filling mode detection, volume normalization
6. **Port allocation**: Dashboard tries 9190-9200, then 9090-9100

## Configuration

Config files are JSON loaded into frozen dataclasses with full defaults. Active files: `config_finex.json`, `config_xauusd_m1_ultra.json`, `config_finex_aggressive_1m.json`.

Key config sections:
- `scalping.*` — All strategy parameters (EMA, MACD, BB, Stoch, filters, risk, position policy)
- `telegram.*` — Bot token + chat ID
- `brokers.*` — Multi-broker connection profiles (mt5, binance, alpaca, default)

## Commands Reference

```powershell
# Run desktop app (web dashboard + auto-start)
python run_scalping.py --auto-start

# CLI scalping loop
python -m aitrader_bot.cli scalp --config config_finex.json --broker mt5 --iterations 20

# Backtest
python -m aitrader_bot.cli backtest --config config_finex.json --data data/xauusd_5m_2000.csv

# Generate signal
python -m aitrader_bot.cli signal --config config_finex.json --data data/xauusd_5m_2000.csv

# Run tests
python -m unittest discover tests -v

# Background launcher
python start_bot_hybrid.py
```

## Dashboard

- URL: `http://127.0.0.1:9190`
- API: `/api/status` (JSON), `/api/events` (SSE)
- TradingView widget embedded in dashboard HTML
- Auto-kills port zombies on startup (netstat + taskkill)

## When Helping

When asked to develop, debug, or modify this project:
1. Always verify configuration files and their structure before making changes
2. Run tests before and after changes: `python -m unittest discover tests -v`
3. For broker-related changes, test with `--broker paper` first
4. Follow existing conventions (imports, typing, error handling patterns)
5. Check both `config_finex.json` and `config_xauusd_m1_ultra.json` if relevant
6. Ensure thread safety when modifying shared state (DashboardDataStore, engine queue)
7. Test backtest equivalence when changing strategy or decision logic

---
name: institutional-trading-ai
description: >
  Use when working on institutional-grade trading features — multi-asset portfolio
  management, prime broker connectivity, FIX protocol, OMS/EMS integration,
  compliance/regulatory reporting, risk analytics, and large-scale backtesting
  infrastructure.
---

# Institutional Trading AI — Developer Skill

## Project Identity

Institutional Trading AI extends the AI Trading Radar ecosystem with features required for **prop trading desks, hedge funds, and asset managers**. It focuses on multi-asset support (equities, FX, commodities, crypto, fixed income), prime broker connectivity, FIX engine integration, real-time portfolio risk (VaR, Greeks, stress testing), and regulatory compliance (MiFID II, SEC, MAS).

## Architecture

```
institutional_trading/
├── portfolio/           # Multi-asset portfolio management
│   ├── manager.py       # Portfolio allocation, rebalancing, P&L aggregation
│   ├── hedging.py       # Delta-neutral, beta-hedged, tail-risk strategies
│   └── reporting.py     # Daily/ weekly/ monthly performance reports
├── fix/                 # FIX protocol engine
│   ├── engine.py        # FIX session management, logon/heartbeat/resend
│   ├── messages.py      # Order types: NewOrderSingle, OrderCancelRequest, etc.
│   └── tags.py          # FIX tag definitions (custom + standard)
├── oms/                 # Order Management System
│   ├── router.py        # Smart order routing (price, venue, algo selection)
│   ├── lifecycle.py     # Order state machine (New→PartiallyFilled→Filled→DoneForDay)
│   └── allocation.py    # Pre/post-trade allocation models
├── compliance/          # Regulatory compliance engine
│   ├── aml.py           # Anti-Money Laundering screening
│   ├── mifid.py         # MiFID II transaction reporting, best execution
│   └── limits.py        # Position limits, concentration limits, circuit breakers
├── risk/                # Institutional risk analytics
│   ├── var.py           # Historical, parametric, Monte Carlo VaR
│   ├── greeks.py        # Options Greeks (delta, gamma, vega, theta, rho)
│   ├── stress.py        # Scenario analysis + stress testing
│   └── collateral.py    # Margin calculation, collateral management
├── data/                # Market data infrastructure
│   ├── feed.py          # Real-time market data feed adapter (Bloomberg, Reuters, etc.)
│   ├── historical.py    # Historical data warehouse interface
│   └── corporate.py     # Corporate actions (dividends, splits, M&A)
├── backtest/            # Large-scale backtesting
│   ├── engine.py        # Event-driven backtest engine with multi-asset support
│   ├── metrics.py       # Sharpe, Sortino, Calmar, Max DD, Win rate, Profit factor
│   └── optimizer.py     # Walk-forward optimization, parameter sweeps
├── reporting/           # Client & regulatory reporting
│   ├── templates/       # PDF/HTML report templates
│   └── export.py        # Data export (CSV, Excel, PDF, email)
└── api/                 # REST/WebSocket API for external integration
    ├── rest.py          # RESTful endpoints for order placement, portfolio view
    └── websocket.py     # Real-time streaming of positions, P&L, risk metrics
```

## Multi-Agent Trading System

The system uses **20 specialized agents**, each with a narrow responsibility, structured JSON output, and zero overlap. Agents run independently and results are aggregated by the **Chief Trader**.

### Agent Pipeline

```
Market Data
  │
  ├─ Market Structure Agent     → structure, phase, BOS/CHoCH
  ├─ Trend Analyst Agent        → trend alignment per timeframe
  ├─ Smart Money Agent          → order block, FVG, discount zone
  ├─ Liquidity Agent            → BSL/SSL, sweep, inducement
  ├─ Order Flow Agent           → buying/selling pressure, delta
  ├─ Volume Profile Agent       → POC, VAH/VAL, HVN/LVN
  ├─ Price Action Agent         → candle patterns, confirmation
  ├─ Indicator Confirmation Agent → EMA, RSI, MACD, ADX
  ├─ Volatility Agent           → ATR, spread, slippage
  ├─ Session Agent              → session, kill zone, liquidity
  ├─ News & Macro Agent         → high-impact news, risk level
  └─ Correlation Agent          → DXY, US10Y, SP500, Oil, BTC
       │
       ▼
  ┌─ Entry Strategy Agent       → entry price + type (Limit/Stop/Market)
  │
  ├─ Risk Manager Agent         → 0.5% max risk, daily/weekly limits
  ├─ Position Sizing Agent      → lot size based on balance × risk ÷ SL
  │
  ▼
  ┌─ Trade Execution Agent      → spread/latency/slippage/duplicate check
  │
  ├─ Trade Management Agent     → BE, trailing, partial close, scale out
  ├─ Exit Strategy Agent        → TP, SL, reversal, news, time exit
  │
  ▼
  ┌─ Performance Analyst Agent  → win rate, PF, drawdown, grade
  └─ Journal Agent              → record, analyze, report, improve
```

### Agent Definitions

All agent definitions are stored as JSON in `agents/`:

| # | Agent | File | Output |
|---|-------|------|--------|
| 1 | Market Structure | `agents/market_structure_agent.json` | `structure, trend, bos, choch, phase, strength` |
| 2 | Trend Analyst | `agents/trend_analyst_agent.json` | `weekly/daily/h4/h1/m15 trend, alignment` |
| 3 | Smart Money | `agents/smart_money_agent.json` | `order_block, fvg, discount_zone, bias, score` |
| 4 | Liquidity | `agents/liquidity_agent.json` | `liquidity, sweep, inducement, next_target` |
| 5 | Order Flow | `agents/order_flow_agent.json` | `flow, buyers, sellers, strength` |
| 6 | Volume Profile | `agents/volume_profile_agent.json` | `bias, location, volume_acceptance` |
| 7 | Price Action | `agents/price_action_agent.json` | `pattern, confirmation` |
| 8 | Indicator Confirmation | `agents/indicator_confirmation_agent.json` | `ema, rsi, adx, macd, confirmation` |
| 9 | Volatility | `agents/volatility_agent.json` | `volatility, spread_ok, trade_allowed` |
| 10 | Session | `agents/session_agent.json` | `session, liquidity, quality` |
| 11 | News & Macro | `agents/news_macro_agent.json` | `high_impact_news, risk, trade_allowed` |
| 12 | Correlation | `agents/correlation_agent.json` | `dxy, gold_bias, correlation_score` |
| 13 | Entry Strategy | `agents/entry_strategy_agent.json` | `entry, entry_type, quality` |
| 14 | Risk Manager | `agents/risk_manager_agent.json` | `risk_percent, daily_limit_ok, approved` |
| 15 | Position Sizing | `agents/position_sizing_agent.json` | `lot, risk_amount, margin_ok` |
| 16 | Trade Execution | `agents/trade_execution_agent.json` | `status, ticket` |
| 17 | Trade Management | `agents/trade_management_agent.json` | `action, new_sl` |
| 18 | Exit Strategy | `agents/exit_strategy_agent.json` | `exit, reason` |
| 19 | Performance Analyst | `agents/performance_analyst_agent.json` | `winrate, profit_factor, drawdown, grade` |
| 20 | Journal | `agents/journal_agent.json` | `journal_id, grade, discipline, mistakes` |
| — | **Login Dialog** | `agents/login_dialog_agent.json` | `server, login, password, confirmed` (UI popup) |

### Chief Trader Orchestration

Chief Trader mengumpulkan output dari semua agent, melakukan weighted aggregation, dan menghasilkan keputusan akhir:

```json
{
  "decision": "BUY",
  "confidence": 87,
  "entry": 3358.10,
  "sl": 3345.50,
  "tp": 3378.00,
  "lot": 0.35,
  "agents_used": 20,
  "rejected_by": []
}
```

## Key Modules & Responsibilities

| Module | Purpose |
|--------|---------|
| **portfolio/manager.py** | Multi-currency P&L aggregation, rebalancing triggers |
| **fix/engine.py** | FIX 4.4 session lifecycle, encrypted connections |
| **oms/router.py** | Smart routing: venue selection, algo scheduling, cost analysis |
| **compliance/mifid.py** | Transaction reporting XML generation, EMIR reporting |
| **risk/var.py** | 95/99% VaR, expected shortfall, incremental/component VaR |
| **risk/greeks.py** | First/second-order Greeks, implied/realized vol surface |
| **risk/stress.py** | Historical scenario replay, hypothetical shock simulation |
| **backtest/engine.py** | Multi-threaded event loop, fill simulation, slippage models |

## Conventions

### Code Style
- `from __future__ import annotations` at top of every module
- Full type hints: Python 3.10+ `X | None` syntax
- `@dataclass(frozen=True)` for immutable config/data objects
- Decimal types (`Decimal`) for monetary values; `float` for ratios/percentages
- ISO 8601 datetimes everywhere; tz-aware `datetime` with UTC
- CamelCase classes, snake_case functions/variables, UPPER_SNAKE_CASE constants
- Deep relative imports: `from ..risk.var import calculate_var`

### Error Handling
- All external connections (FIX, market data feeds) implement retry + circuit breaker
- Order rejection returns `RejectionReason` enum, not exceptions
- Portfolio validation runs pre-trade; rejects with detailed reason
- Risk limit breaches trigger configurable actions (warn, block, auto-hedge, notify)
- All errors logged with correlation IDs for audit trail

### Data & Persistence
- Timeseries stored in Parquet format for efficient I/O
- Order/trade audit log in PostgreSQL (or SQLite for dev)
- Portfolio snapshots every hour to enable point-in-time reconstruction
- All monetary values stored in minor units (cents, pips) to avoid floating point

### Testing
- Framework: `pytest` with `pytest-xdist` for parallel execution
- Run all: `pytest tests/ -v --cov=institutional_trading`
- FIX session tests use a mock FIX acceptor
- Compliance tests verify generated XML against regulatory XSD schemas
- Backtest metrics must reproduce within 0.01% for deterministic scenarios

## Key Design Decisions

1. **Multi-asset portfolio engine**: Unified P&L across equities, FX, commodities, crypto with currency conversion
2. **FIX 4.4 as primary protocol**: Industry standard for institutional connectivity; custom tags for proprietary data
3. **Pre-trade risk gating**: Every order passes through risk/compliance before reaching OMS
4. **Event-driven backtesting**: Tick-by-tick simulation with configurable slippage, latency, and fill models
5. **Decimal precision for money**: All monetary values use Python `Decimal` (28-digit precision)
6. **Audit-first compliance**: Every decision, override, and trade tagged with immutable correlation ID

## Configuration

Config files in `config/institutional/` as YAML:

```yaml
# config/institutional/prime_broker.yaml
prime_broker:
  name: "Goldman Sachs"
  fix_version: "FIX.4.4"
  sender_comp_id: "AITRADER"
  target_comp_id: "GS"
  connection:
    host: "fix.gs.com"
    port: 4198
    ssl: true

# config/institutional/risk_limits.yaml
risk_limits:
  max_position_size_usd: 5000000
  max_concentration_pct: 15
  var_limit_pct: 2.0
  leverage_limit: 4.0
```

## Regulatory Support

| Regulation | Coverage |
|------------|----------|
| MiFID II / MiFIR | Transaction reporting (RTS 22), best execution (RTS 28) |
| EMIR | Trade reporting to trade repositories |
| SEC Rule 15c3-1 | Net capital calculation |
| MAS SFA | Singapore financial advisor reporting |
| FATCA/CRS | Tax reporting, common reporting standard |

### Login Dialog — Runtime Credential Entry

Pada startup, bot menampilkan **popup login MT5** (PyQt6 QDialog) yang meminta:

| Field | Contoh |
|-------|--------|
| Server | `FinexAsia-Demo` |
| Login | `12345` |
| Password | `********` |

- User klik **Connect** → kredensial dikirim ke engine, override config file
- User klik **Cancel** → bot tidak jalan
- `--skip-login` flag untuk bypass (pakai kredensial dari config langsung)
- File: `aitrader_bot/app/login_dialog.py`
- Terintegrasi di `run_scalping.py` dan `TradingEngine.__init__`

## Commands Reference

```powershell
# Run portfolio rebalancer (daily)
python -m institutional_trading.portfolio.manager --rebalance

# Start FIX engine
python -m institutional_trading.fix.engine --config config/institutional/prime_broker.yaml

# Run backtest with multi-asset data
python -m institutional_trading.backtest.engine --data data/institutional/ --symbols AAPL,MSFT,GC=F,USDJPY

# Generate MiFID II transaction report
python -m institutional_trading.compliance.mifid --action report --date 2026-07-11

# Run VaR calculation
python -m institutional_trading.risk.var --method monte_carlo --confidence 0.99

# Run full test suite
pytest tests/ -v --cov=institutional_trading
```

## When Helping

1. Always verify config YAML structure before making changes
2. Run full test suite before/after: `pytest tests/ -v`
3. For FIX-related changes, test against the mock acceptor first
4. Use `Decimal` for all monetary calculations; never `float`
5. Follow ISO 8601 for all datetime handling; always tz-aware
6. Check both `prime_broker.yaml` and `risk_limits.yaml` if relevant
7. Ensure thread safety in OMS and portfolio manager (shared position state)
8. Backtest equivalence: deterministic scenarios must produce identical results across runs

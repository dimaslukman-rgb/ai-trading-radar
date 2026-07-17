"""Thread-safe shared data store for the web dashboard.

Engine writes real-time data here; the web HTTP server reads from here.
Expanded for AI Trading Radar v3.0.0 with multi-pair support and equity tracking.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

# Default symbol for backward compatibility
DEFAULT_SYMBOL = "XAUUSD"

def _create_symbol_data(symbol: str) -> dict[str, Any]:
    """Create a new data structure for a specific symbol."""
    return {
        "symbol": symbol,
        "last_signal": "",
        "last_price": 0.0,
        "last_confidence": 0.0,
        "trades": [],
        "open_positions": [],
        # ── Aggressive Mode ─────────────────────────────────────────────
        "aggressive_mode": False,
        "entry_time": None,
        "timeout_minutes": 0,
        # ── AI Trading Radar fields ────────────────────────────────────
        "confidence_pct": 0,
        "confidence_category": "NO TRADE",
        "signal_action": "HOLD",
        "entry": 0.0,
        "sl": 0.0,
        "tp": 0.0,
        "rr": 0.0,
        "signal_status": "Waiting",
        "current_session": "—",
        "sessions": {
            "sydney": False,
            "tokyo": False,
            "london": False,
            "new_york": False,
        },
        "sentiment": {"bullish": 0, "bearish": 0, "neutral": 100},
        "volatility": "NORMAL",
        "news_events": [],
        "macro_sentiment": {
            "bias": "NEUTRAL",
            "risk_score": 25,
            "summary": "Waiting for macro catalyst scan...",
            "updated_at": "",
            "drivers": [],
        },
        "processor_status": "stopped",
        "adaptive_risk": {"enabled": False, "atr": 0.0},
        "chief_decision": {},
        "agent_reasoning": [],
        "agent_scores": {},
        "analysis": {
            "trend": False,
            "ema": False,
            "bos": False,
            "order_block": False,
            "liquidity_sweep": False,
            "volume": False,
            "rsi": False,
            "macd": False,
            "fvg": False,
            "news_clear": True,
        },
    }

# Internal state
_dashboard_data: dict[str, Any] = {
    "account": {
        "status": "stopped",
        "equity": 0.0,
        "initial_equity": 0.0,
        "peak_equity": 0.0,
        "pl_pct": 0.0,
        "drawdown_pct": 0.0,
        "balance": 0.0,
        "broker": "mt5",
        "telegram": False,
        "started_at": None,
        "mt5_connected": False,
        "mt5_login": None,
        "mt5_server": "",
        "mt5_trade_allowed": None,
        "mt5_account_info": None,
        "mt5_last_error": "",
        "equity_history": [],
        "active_symbols": [],
    },
    "symbols": {
        DEFAULT_SYMBOL: _create_symbol_data(DEFAULT_SYMBOL)
    },
    "logs": [],
    "global_trades": [],
}

_lock = threading.Lock()
_log_id = 0

# Fields that belong to account section
ACCOUNT_FIELDS = {
    "status", "equity", "initial_equity", "peak_equity", "pl_pct", "drawdown_pct",
    "balance", "broker", "telegram", "started_at", "mt5_connected", "mt5_login",
    "mt5_server", "mt5_trade_allowed", "mt5_account_info", "mt5_last_error", "equity_history",
    "active_symbols",
}

def update(symbol: str | None = None, **kwargs: Any) -> None:
    """Update one or more fields atomically.
    If 'symbol' is provided or in kwargs, updates symbol-specific data.
    """
    with _lock:
        # Determine target symbol
        target_symbol = symbol or kwargs.get("symbol")

        # Legacy callers can still replace the shared stream collections.
        # Keep these out of the symbol dictionary so an API test/reset does
        # not silently create fields that the snapshot never reads.
        if "logs" in kwargs:
            _dashboard_data["logs"] = list(kwargs["logs"])
        if "trades" in kwargs:
            _dashboard_data["global_trades"] = list(kwargs["trades"])

        # 1. Update Account Fields
        acc_updates = {k: v for k, v in kwargs.items() if k in ACCOUNT_FIELDS}
        if acc_updates:
            _dashboard_data["account"].update(acc_updates)
            if "equity" in acc_updates:
                _recompute_equity_metrics()

        # 2. Update Symbol Fields
        sym_updates = {
            k: v for k, v in kwargs.items()
            if k not in ACCOUNT_FIELDS and k not in {"logs", "trades"}
        }
        if sym_updates:
            # If no symbol specified, use DEFAULT_SYMBOL for backward compatibility
            if not target_symbol:
                target_symbol = DEFAULT_SYMBOL

            if target_symbol not in _dashboard_data["symbols"]:
                _dashboard_data["symbols"][target_symbol] = _create_symbol_data(target_symbol)

            _dashboard_data["symbols"][target_symbol].update(sym_updates)


def reset_account_metrics(equity: float, balance: float) -> None:
    """Reset account baseline for a fresh bot run."""
    with _lock:
        acc = _dashboard_data["account"]
        acc["equity"] = equity
        acc["initial_equity"] = equity
        acc["peak_equity"] = equity
        acc["pl_pct"] = 0.0
        acc["drawdown_pct"] = 0.0
        acc["balance"] = balance
        acc["equity_history"] = [{"time": datetime.now().isoformat(), "equity": equity}]


def _recompute_equity_metrics() -> None:
    """Recompute peak_equity, pl_pct and drawdown_pct from current equity."""
    acc = _dashboard_data["account"]
    equity = acc["equity"]
    if equity <= 0:
        return

    if acc["initial_equity"] <= 0:
        acc["initial_equity"] = equity
    if acc["peak_equity"] <= 0:
        acc["peak_equity"] = equity
    else:
        acc["peak_equity"] = max(acc["peak_equity"], equity)

    init = acc["initial_equity"]
    peak = acc["peak_equity"]
    acc["pl_pct"] = ((equity - init) / init * 100.0) if init else 0.0
    acc["drawdown_pct"] = (((peak - equity) / peak * 100.0) if peak else 0.0)

    # Auto-record equity history if changed
    if not acc["equity_history"] or acc["equity_history"][-1]["equity"] != equity:
        acc["equity_history"].append({
            "time": datetime.now().isoformat(),
            "equity": round(equity, 2)
        })
        # Keep last 500 points
        if len(acc["equity_history"]) > 500:
            acc["equity_history"] = acc["equity_history"][-500:]


def add_log(msg: str) -> None:
    """Append a log entry (in-memory ring buffer, max 200)."""
    global _log_id
    with _lock:
        _log_id += 1
        entry = {"id": _log_id, "time": datetime.now().isoformat(), "msg": msg}
        _dashboard_data["logs"].append(entry)
        if len(_dashboard_data["logs"]) > 200:
            _dashboard_data["logs"] = _dashboard_data["logs"][-200:]


def add_trade(action: str, symbol: str, price: float, qty: float,
              reason: str, pnl: float | None = None) -> None:
    """Record a trade event."""
    with _lock:
        trade = {
            "time": datetime.now().strftime("%H:%M:%S"),
            "action": action,
            "symbol": symbol,
            "price": round(price, 2),
            "qty": round(qty, 4),
            "reason": reason[:60],
            "pnl": round(pnl, 2) if pnl is not None else None,
        }
        # Add to global trades
        _dashboard_data["global_trades"].append(trade)
        if len(_dashboard_data["global_trades"]) > 100:
            _dashboard_data["global_trades"] = _dashboard_data["global_trades"][-100:]

        # Add to symbol-specific trades
        if symbol not in _dashboard_data["symbols"]:
            _dashboard_data["symbols"][symbol] = _create_symbol_data(symbol)

        sym_trades = _dashboard_data["symbols"][symbol]["trades"]
        sym_trades.append(trade)
        if len(sym_trades) > 50:
            _dashboard_data["symbols"][symbol]["trades"] = sym_trades[-50:]


def update_mt5_status(connected: bool, login: int | None = None, server: str = "",
                    trade_allowed: bool | None = None, account_info: dict | None = None,
                    last_error: str = "") -> None:
    """Update MT5 connection status and account information."""
    update(
        mt5_connected=connected,
        mt5_login=login,
        mt5_server=server,
        mt5_trade_allowed=trade_allowed,
        mt5_account_info=account_info,
        mt5_last_error=last_error
    )


def snapshot() -> dict[str, Any]:
    """Return a thread-safe copy of all current data.
    Maintains backward compatibility by flattening account + first symbol.
    """
    with _lock:
        # Get primary symbol (XAUUSD or first available)
        primary = DEFAULT_SYMBOL
        if primary not in _dashboard_data["symbols"] and _dashboard_data["symbols"]:
            primary = next(iter(_dashboard_data["symbols"]))

        sym_data = _dashboard_data["symbols"].get(primary, _create_symbol_data(primary))

        # 1. Base snapshot from account
        snap = dict(_dashboard_data["account"])

        # 2. Mix in primary symbol data for backward compat
        for k, v in sym_data.items():
            if k == "trades": continue # Trades are handled via global_trades below
            snap[k] = v

        # 3. Add shared collections
        snap["logs"] = list(_dashboard_data["logs"])
        snap["trades"] = list(_dashboard_data["global_trades"])

        # 4. Add v3.0.0 multi-pair data
        snap["v3"] = True
        snap["all_symbols"] = {s: dict(d) for s, d in _dashboard_data["symbols"].items()}

        return snap

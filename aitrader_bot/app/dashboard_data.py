"""Thread-safe shared data store for the web dashboard.

Engine writes real-time data here; the web HTTP server reads from here.
Expanded for AI Trading Radar with multi-factor confidence analysis.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

_dashboard_data: dict[str, Any] = {
    "status": "stopped",
    "equity": 0.0,
    "initial_equity": 0.0,
    "peak_equity": 0.0,
    "pl_pct": 0.0,
    "drawdown_pct": 0.0,
    "balance": 0.0,
    "last_signal": "",
    "last_price": 0.0,
    "last_confidence": 0.0,
    "symbol": "XAUUSD",
    "broker": "mt5",
    "telegram": False,
    "trades": [],
    "open_positions": [],
    "logs": [],
    "started_at": None,
    # ── Aggressive Mode ─────────────────────────────────────────────
    "aggressive_mode": False,
    "entry_time": None,
    "timeout_minutes": 0,
    # ── MT5 Account Management ─────────────────────────────────────
    "mt5_connected": False,
    "mt5_login": None,
    "mt5_server": "",
    "mt5_account_info": None,
    "mt5_last_error": "",
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

_lock = threading.Lock()
_log_id = 0


def update(**kwargs: Any) -> None:
    """Update one or more fields atomically.

    When ``equity`` is provided, the running peak, percentage P/L, and
    drawdown (relative to the peak) are recomputed automatically.
    """
    with _lock:
        _dashboard_data.update(kwargs)
        if "equity" in kwargs:
            _recompute_equity_metrics()


def reset_account_metrics(equity: float, balance: float) -> None:
    """Reset account baseline for a fresh bot run.

    This makes dashboard % P/L start from 0.00% whenever the trading engine
    connects after a process restart or manual start.
    """
    with _lock:
        _dashboard_data["equity"] = equity
        _dashboard_data["initial_equity"] = equity
        _dashboard_data["peak_equity"] = equity
        _dashboard_data["pl_pct"] = 0.0
        _dashboard_data["drawdown_pct"] = 0.0
        _dashboard_data["balance"] = balance


def _recompute_equity_metrics() -> None:
    """Recompute peak_equity, pl_pct and drawdown_pct from current equity."""
    equity = _dashboard_data["equity"]
    if equity <= 0:
        return
    # Seed initial_equity/peak from the first non-zero equity reading if unset.
    if _dashboard_data["initial_equity"] <= 0:
        _dashboard_data["initial_equity"] = equity
    if _dashboard_data["peak_equity"] <= 0:
        _dashboard_data["peak_equity"] = equity
    else:
        _dashboard_data["peak_equity"] = max(_dashboard_data["peak_equity"], equity)

    init = _dashboard_data["initial_equity"]
    peak = _dashboard_data["peak_equity"]
    _dashboard_data["pl_pct"] = ((equity - init) / init * 100.0) if init else 0.0
    _dashboard_data["drawdown_pct"] = (
        ((peak - equity) / peak * 100.0) if peak else 0.0
    )


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
        _dashboard_data["trades"].append(trade)
        if len(_dashboard_data["trades"]) > 100:
            _dashboard_data["trades"] = _dashboard_data["trades"][-100:]

def update_mt5_status(connected: bool, login: int | None = None, server: str = "",
                    account_info: dict | None = None, last_error: str = "") -> None:
    """Update MT5 connection status and account information."""
    with _lock:
        _dashboard_data["mt5_connected"] = connected
        if login is not None:
            _dashboard_data["mt5_login"] = login
        if server:
            _dashboard_data["mt5_server"] = server
        if account_info is not None:
            _dashboard_data["mt5_account_info"] = account_info
        if last_error:
            _dashboard_data["mt5_last_error"] = last_error


def snapshot() -> dict[str, Any]:
    """Return a thread-safe copy of all current data."""
    with _lock:
        return {
            "status": _dashboard_data["status"],
            "equity": _dashboard_data["equity"],
            "initial_equity": _dashboard_data["initial_equity"],
            "peak_equity": _dashboard_data["peak_equity"],
            "pl_pct": _dashboard_data["pl_pct"],
            "drawdown_pct": _dashboard_data["drawdown_pct"],
            "balance": _dashboard_data["balance"],
            "last_signal": _dashboard_data["last_signal"],
            "last_price": _dashboard_data["last_price"],
            "last_confidence": _dashboard_data["last_confidence"],
            "symbol": _dashboard_data["symbol"],
            "broker": _dashboard_data["broker"],
            "telegram": _dashboard_data["telegram"],
            "trades": list(_dashboard_data["trades"]),
            "open_positions": list(_dashboard_data["open_positions"]),
            "logs": list(_dashboard_data["logs"]),
            "started_at": _dashboard_data["started_at"],
            # ── Aggressive Mode ───────────────────────────────────
            "aggressive_mode": _dashboard_data["aggressive_mode"],
            "entry_time": _dashboard_data["entry_time"],
            "timeout_minutes": _dashboard_data["timeout_minutes"],
            # ── MT5 Account Management ────────────────────────────
            "mt5_connected": _dashboard_data["mt5_connected"],
            "mt5_login": _dashboard_data["mt5_login"],
            "mt5_server": _dashboard_data["mt5_server"],
            "mt5_account_info": _dashboard_data["mt5_account_info"],
            "mt5_last_error": _dashboard_data["mt5_last_error"],
            # ── AI Trading Radar ───────────────────────────────────
            "confidence_pct": _dashboard_data["confidence_pct"],
            "confidence_category": _dashboard_data["confidence_category"],
            "signal_action": _dashboard_data["signal_action"],
            "entry": _dashboard_data["entry"],
            "sl": _dashboard_data["sl"],
            "tp": _dashboard_data["tp"],
            "rr": _dashboard_data["rr"],
            "signal_status": _dashboard_data["signal_status"],
            "current_session": _dashboard_data["current_session"],
            "sessions": dict(_dashboard_data["sessions"]),
            "sentiment": dict(_dashboard_data["sentiment"]),
            "volatility": _dashboard_data["volatility"],
            "news_events": list(_dashboard_data["news_events"]),
            "macro_sentiment": dict(_dashboard_data["macro_sentiment"]),
            "analysis": dict(_dashboard_data["analysis"]),
        }

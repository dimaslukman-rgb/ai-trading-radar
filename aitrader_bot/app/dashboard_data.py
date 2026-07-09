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
    "logs": [],
    "started_at": None,
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
              reason: str, pnl: float | None = None,
              status: str | None = None) -> None:
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
            "status": status or ("OPEN" if "BUY" in action else "CLOSED"),
        }
        _dashboard_data["trades"].append(trade)
        if len(_dashboard_data["trades"]) > 100:
            _dashboard_data["trades"] = _dashboard_data["trades"][-100:]


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
            "logs": list(_dashboard_data["logs"]),
            "started_at": _dashboard_data["started_at"],
            # ── Aggressive Mode ───────────────────────────────────
            "aggressive_mode": _dashboard_data["aggressive_mode"],
            "entry_time": _dashboard_data["entry_time"],
            "timeout_minutes": _dashboard_data["timeout_minutes"],
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
            "analysis": dict(_dashboard_data["analysis"]),
        }

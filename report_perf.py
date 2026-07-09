"""Performance Report â€” parse trading log + backtest scalping.

Usage:
    python report_perf.py                    # report from log + backtest
    python report_perf.py --no-backtest      # log only
    python report_perf.py --no-log           # backtest only
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  Log parser
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

LOG_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+\|\s+\w+\s+\|\s+\w+\s+\|\s+(?P<msg>.*)"
)


@dataclass
class LogSession:
    start: datetime
    end: datetime | None = None
    trades: list[dict] = field(default_factory=list)
    equity_updates: list[tuple[datetime, float]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    hold_signals: int = 0


def parse_log(path: str) -> tuple[list[LogSession], str]:
    """Parse trading log -> list of sessions + raw lines for display."""
    if not os.path.exists(path):
        return [], f"[WARN] Log tidak ditemukan: {path}"

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    sessions: list[LogSession] = []
    current: LogSession | None = None
    raw_display: list[str] = []

    for line in lines:
        m = LOG_RE.match(line.strip())
        if not m:
            continue
        ts_str = m.group("ts")
        msg = m.group("msg")
        try:
            ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

        raw_display.append(line.rstrip())

        if "=== AI Trading Radar Starting ===" in msg:
            current = LogSession(start=ts)
            sessions.append(current)
        elif current is None:
            continue
        elif "Auto-start enabled - starting engine" in msg or "System tray initialized" in msg or "Dashboard" in msg:
            continue
        elif msg.startswith("signal:BOUGHT") or msg.startswith("signal:SOLD"):
            parts = msg.split(":", 1)
            current.trades.append({"ts": ts, "event": parts[1]})
        elif msg.startswith("signal:HODL") or msg.startswith("signal:hold") or msg.startswith("signal:HOLD"):
            current.hold_signals += 1
        elif msg.startswith("account:"):
            try:
                eq = float(msg.split(":", 1)[1])
                current.equity_updates.append((ts, eq))
            except ValueError:
                pass
        elif msg.startswith("error:"):
            current.errors.append(msg)
        elif msg == "Koneksi broker diputus." or msg.startswith("[DONE]"):
            current.end = ts

    # Close open sessions
    now = datetime.now()
    for s in sessions:
        if s.end is None:
            s.end = now

    return sessions, "\n".join(raw_display[-30:])  # last 30 lines


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  Backtest runner with trade details
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def run_detailed_backtest(config_path: str, data_path: str) -> dict:
    """Run scalping backtest and return detailed results including individual trades."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    from aitrader_bot.backtest import run_backtest
    from aitrader_bot.config import load_config
    from aitrader_bot.data import read_csv_prices
    from aitrader_bot.portfolio import Portfolio
    from aitrader_bot.risk import RiskManager
    from aitrader_bot.scalping import ScalpingRiskManager, ScalpingStrategy
    from aitrader_bot.broker.base import ExchangeType, Quote as BrokerQuote
    from aitrader_bot.models import Signal

    config = load_config(config_path)
    bars = read_csv_prices(data_path)

    # Re-run scalping backtest with full trade tracking
    strategy = ScalpingStrategy(config.scalping)
    risk = ScalpingRiskManager(config.scalping)
    portfolio = Portfolio(config.risk.initial_cash)
    start_equity = config.risk.initial_cash
    peak_equity = start_equity
    max_drawdown = 0.0

    trades_detail: list[dict] = []
    entry_price: float | None = None
    entry_bar_index: int | None = None
    buy_signal = Signal(config.symbol, "hold", 0.0, bars[0].close, "", bars[0].date)
    signals: dict[str, int] = {"buy": 0, "sell": 0, "hold": 0}

    def _record_trade(bar_idx: int, bar: any, action: str, qty: float, price: float,
                      reason: str, pnl: float = 0.0):
        trades_detail.append({
            "bar": bar_idx,
            "date": bar.date.strftime("%m/%d %H:%M"),
            "action": action,
            "qty": round(qty, 4),
            "price": round(price, 2),
            "reason": reason,
            "pnl": round(pnl, 2),
        })

    for index in range(1, len(bars) + 1):
        window = bars[:index]
        latest = window[-1]
        prices = {config.symbol: latest.close}

        quote = BrokerQuote(
            symbol=config.symbol,
            exchange=ExchangeType.PAPER,
            bid=latest.close * 0.9995,
            ask=latest.close * 1.0005,
            last=latest.close,
            volume=latest.volume,
            timestamp=latest.date,
        )
        signal = strategy.generate(config.symbol, window, quote)
        signals[signal.action] = signals.get(signal.action, 0) + 1

        position = portfolio.position(config.symbol)

        # Check forced exit (SL/TP)
        if entry_price is not None and position:
            forced_exit = risk.forced_exit_reason(entry_price, latest.close)
            if forced_exit:
                pnl = (latest.close - entry_price) * position.quantity
                portfolio.sell(signal, position.quantity, forced_exit)
                _record_trade(index, latest, "SELL (SL/TP)", position.quantity,
                              latest.close, forced_exit, pnl)
                entry_price = None
                entry_bar_index = None

                equity = portfolio.equity(prices)
                peak_equity = max(peak_equity, equity)
                drawdown = (peak_equity - equity) / peak_equity if peak_equity else 0.0
                max_drawdown = max(max_drawdown, drawdown)
                continue

        # Signal-driven action
        if signal.action == "buy" and not position:
            quantity = risk.buy_quantity(portfolio.cash, portfolio.equity(prices), latest.close)
            bought = portfolio.buy(signal, quantity, signal.reason)
            if bought:
                entry_price = latest.close
                entry_bar_index = index
                buy_signal = signal
                _record_trade(index, latest, "BUY", quantity, latest.close, signal.reason)
        elif signal.action == "sell" and position:
            pnl = (latest.close - entry_price) * position.quantity if entry_price else 0.0
            portfolio.sell(signal, position.quantity, signal.reason)
            _record_trade(index, latest, "SELL (signal)", position.quantity,
                          latest.close, signal.reason, pnl)
            entry_price = None
            entry_bar_index = None

        equity = portfolio.equity(prices)
        peak_equity = max(peak_equity, equity)
        drawdown = (peak_equity - equity) / peak_equity if peak_equity else 0.0
        max_drawdown = max(max_drawdown, drawdown)

    end_equity = portfolio.equity({config.symbol: bars[-1].close})

    # Compute win rate
    win_count = sum(1 for t in trades_detail if t["action"].startswith("SELL") and t["pnl"] > 0)
    loss_count = sum(1 for t in trades_detail if t["action"].startswith("SELL") and t["pnl"] <= 0)
    total_closed = win_count + loss_count
    win_rate = (win_count / total_closed * 100) if total_closed > 0 else 0.0

    gross_profit = sum(t["pnl"] for t in trades_detail if t["pnl"] > 0)
    gross_loss = sum(t["pnl"] for t in trades_detail if t["pnl"] < 0)
    profit_factor = (
        round(abs(gross_profit / gross_loss), 2) if gross_loss != 0
        else 999.99 if gross_profit > 0 else 0.0
    )

    return {
        "mode": "scalping",
        "symbol": config.symbol,
        "bars": len(bars),
        "start_equity": round(start_equity, 2),
        "end_equity": round(end_equity, 2),
        "return_pct": round((end_equity - start_equity) / start_equity * 100, 2),
        "profit_loss": round(end_equity - start_equity, 2),
        "max_drawdown_pct": round(max_drawdown * 100, 2),
        "trade_count": len(portfolio.trades),
        "buy_trades": len([t for t in trades_detail if t["action"] == "BUY"]),
        "sell_trades": len([t for t in trades_detail if "SELL" in t["action"]]),
        "win_rate_pct": round(win_rate, 1),
        "win_count": win_count,
        "loss_count": loss_count,
        "profit_factor": round(profit_factor, 2),
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "total_signals": signals,
        "trades": trades_detail,
        "config": {
            "ema_fast": config.scalping.ema_fast,
            "ema_slow": config.scalping.ema_slow,
            "rsi_window": config.scalping.rsi_window,
            "rsi_oversold": config.scalping.rsi_oversold,
            "rsi_overbought": config.scalping.rsi_overbought,
            "stop_loss_pct": config.scalping.stop_loss_pct,
            "take_profit_pct": config.scalping.take_profit_pct,
            "min_buy_score": config.scalping.min_buy_score,
            "max_trade_pct": config.scalping.max_trade_pct,
        },
    }


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  Report formatter
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def format_report(bt: dict, sessions: list[LogSession], raw_log: str) -> str:
    lines: list[str] = []
    sep = "=" * 60

    # â”€â”€ Header â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    lines.append("")
    lines.append(sep)
    lines.append("  AI Trading Radar â€” PERFORMANCE REPORT")
    lines.append(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(sep)

    # â”€â”€ Section 1: Live Session Summary â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    lines.append("")
    lines.append("  [1] LIVE SESSIONS (from trading_bot.log)")
    lines.append("  " + "-" * 56)

    if not sessions:
        lines.append("    No live trading sessions found.")
    else:
        all_trades = []
        all_errors = []
        total_duration = timedelta()
        for s in sessions:
            all_trades.extend(s.trades)
            all_errors.extend(s.errors)
            if s.end:
                total_duration += (s.end - s.start)

        lines.append(f"    Total sessions     : {len(sessions)}")
        lines.append(f"    Total runtime      : {_fmt_duration(total_duration)}")
        lines.append(f"    Trade signals      : {len(all_trades)}")
        lines.append(f"    Hold signals       : {sum(s.hold_signals for s in sessions)}")
        lines.append(f"    Errors             : {len(all_errors)}")

        last_equity_sessions = [s for s in sessions if s.equity_updates]
        if last_equity_sessions:
            latest = last_equity_sessions[-1]
            last_eq = latest.equity_updates[-1]
            first_eq = latest.equity_updates[0] if len(latest.equity_updates) > 1 else None
            lines.append(f"    Latest equity      : ${last_eq[1]:,.2f}")
            if first_eq and first_eq[1] != last_eq[1]:
                delta = last_eq[1] - first_eq[1]
                sign = "+" if delta >= 0 else ""
                lines.append(f"    Equity change      : {sign}${delta:,.2f}")

        if all_trades:
            lines.append("")
            lines.append("    Recent trades (from log):")
            for t in all_trades[-5:]:
                lines.append(f"      {t['ts'].strftime('%H:%M:%S')} | {t['event'][:70]}")

        if all_errors:
            lines.append("")
            lines.append(f"    Errors ({len(all_errors)}):")
            for e in all_errors[-3:]:
                lines.append(f"      {e[:80]}")

    # â”€â”€ Section 2: Backtest Performance â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    lines.append("")
    lines.append("  [2] BACKTEST PERFORMANCE (scalping â€” data 5m)")
    lines.append("  " + "-" * 56)

    lines.append(f"    Symbol             : {bt['symbol']}")
    lines.append(f"    Bars               : {bt['bars']} ({bt['bars'] // 288}d of 5m data)")
    lines.append(f"    Start equity       : ${bt['start_equity']:,.2f}")
    lines.append(f"    End equity         : ${bt['end_equity']:,.2f}")

    ret = bt["return_pct"]
    pnl = bt["profit_loss"]
    ret_str = f"+{ret}%" if ret >= 0 else f"{ret}%"
    pnl_str = f"+${pnl:,.2f}" if pnl >= 0 else f"-${abs(pnl):,.2f}"
    lines.append(f"    Return             : {ret_str} ({pnl_str})")
    lines.append(f"    Max drawdown       : {bt['max_drawdown_pct']}%")
    lines.append(f"    Total trades       : {bt['trade_count']}")
    lines.append(f"    Win rate           : {bt['win_rate_pct']}% ({bt['win_count']}W / {bt['loss_count']}L)")
    lines.append(f"    Profit factor      : {bt['profit_factor']}")
    lines.append(f"    Gross profit       : ${bt['gross_profit']:,.2f}")
    lines.append(f"    Gross loss         : ${bt['gross_loss']:,.2f}")

    # Signal distribution
    sig = bt["total_signals"]
    total_sig = sum(sig.values())
    lines.append(f"    Signal events      : Buy {sig.get('buy', 0)} / Sell {sig.get('sell', 0)} / Hold {sig.get('hold', 0)}")
    lines.append(f"                         ({total_sig} total signals across {bt['bars']} bars)")

    # â”€â”€ Section 3: Strategy Config â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    lines.append("")
    lines.append("  [3] STRATEGY PARAMETERS")
    lines.append("  " + "-" * 56)

    cfg = bt["config"]
    lines.append(f"    EMA                 : {cfg['ema_fast']}/{cfg['ema_slow']}")
    lines.append(f"    RSI                 : {cfg['rsi_window']} ({cfg['rsi_oversold']}/{cfg['rsi_overbought']})")
    lines.append(f"    Stop Loss           : {cfg['stop_loss_pct']*100:.1f}%")
    lines.append(f"    Take Profit         : {cfg['take_profit_pct']*100:.1f}%")
    lines.append(f"    Min Buy Score       : {cfg['min_buy_score']}")
    lines.append(f"    Max Trade/Equity    : {cfg['max_trade_pct']*100:.0f}%")

    # â”€â”€ Section 4: Recent Trades Detail â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    trades = bt.get("trades", [])
    if trades:
        lines.append("")
        lines.append("  [4] RECENT TRADES (last 10)")
        lines.append("  " + "-" * 56)
        lines.append(f"    {'Date':>12} {'Action':<16} {'Price':>8} {'Qty':>8} {'P&L':>8}  Reason")
        lines.append(f"    {'-'*12} {'-'*16} {'-'*8} {'-'*8} {'-'*8}  {'-'*20}")
        for t in trades[-10:]:
            action = t["action"]
            price = f"${t['price']:,.2f}"
            qty = f"{t['qty']:.4f}"
            pnl_str = f"{t['pnl']:+.2f}" if t["pnl"] != 0 else "-"
            reason = t["reason"][:25]
            lines.append(f"    {t['date']:>12} {action:<16} {price:>8} {qty:>8} {pnl_str:>8}  {reason}")

    # â”€â”€ Section 5: Log tail (last 10 lines) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
    lines.append("")
    lines.append("  [5] LOG TAIL (last 10 lines)")
    lines.append("  " + "-" * 56)
    log_lines = raw_log.split("\n")
    for ll in log_lines[-10:]:
        if ll.strip():
            lines.append(f"    {ll.strip()[:90]}")

    lines.append("")
    lines.append(sep)
    lines.append("")

    return "\n".join(lines)


def _fmt_duration(d: timedelta) -> str:
    total_minutes = int(d.total_seconds() // 60)
    hours = total_minutes // 60
    minutes = total_minutes % 60
    if hours > 0:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
#  Main
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def main():
    import argparse

    parser = argparse.ArgumentParser(prog="report_perf")
    parser.add_argument("--config", default="config_finex.json",
                        help="Config file (default: config_finex.json)")
    parser.add_argument("--data", default="data/sample_prices_5m.csv",
                        help="Price data for backtest (default: data/sample_prices_5m.csv)")
    parser.add_argument("--log", default=None,
                        help="Path to trading log (default: %%APPDATA%%/AITradingRadar/logs/trading_bot.log)")
    parser.add_argument("--no-backtest", action="store_true",
                        help="Skip backtest, log only")
    parser.add_argument("--no-log", action="store_true",
                        help="Skip log parsing, backtest only")

    args = parser.parse_args()

    # Determine log path
    log_path = args.log
    if log_path is None:
        log_path = str(
            Path(os.environ.get("APPDATA", ""))
            / "AITradingRadar" / "logs" / "trading_bot.log"
        )

    # Parse log
    sessions = []
    raw_log = ""
    if not args.no_log:
        sessions, raw_log = parse_log(log_path)

    # Run backtest
    bt = {}
    if not args.no_backtest:
        data_file = args.data
        if not os.path.exists(data_file):
            # Fall back to daily data
            data_file = "data/sample_prices.csv"
        if os.path.exists(data_file):
            print(f"[REPORT] Running backtest with {data_file}...", file=sys.stderr)
            bt = run_detailed_backtest(args.config, data_file)
            print(f"[REPORT] Backtest complete: {bt['trade_count']} trades", file=sys.stderr)
        else:
            print(f"[WARN] Data file not found: {args.data}", file=sys.stderr)
            bt = {
                "symbol": "N/A",
                "bars": 0,
                "start_equity": 0,
                "end_equity": 0,
                "return_pct": 0,
                "profit_loss": 0,
                "max_drawdown_pct": 0,
                "trade_count": 0,
                "buy_trades": 0,
                "sell_trades": 0,
                "win_rate_pct": 0,
                "win_count": 0,
                "loss_count": 0,
                "profit_factor": 0,
                "gross_profit": 0,
                "gross_loss": 0,
                "total_signals": {"buy": 0, "sell": 0, "hold": 0},
                "trades": [],
                "config": {},
            }

    # Create report
    report = format_report(bt, sessions, raw_log)
    print(report)

    # Save to file
    report_path = "perf_report_latest.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"[REPORT] Saved to: {report_path}", file=sys.stderr)


if __name__ == "__main__":
    main()


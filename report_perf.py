"""Human-readable live-log and cost-aware backtest performance report."""

from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from aitrader_bot.config import load_config
from aitrader_bot.data import read_csv_prices
from aitrader_bot.research import (
    TransactionCostModel,
    analyze_dataset,
    simulate_scalping,
)


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
    if not os.path.exists(path):
        return [], f"[WARN] Log tidak ditemukan: {path}"
    lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    sessions: list[LogSession] = []
    current: LogSession | None = None
    parsed_lines: list[str] = []
    for line in lines:
        match = LOG_RE.match(line.strip())
        if not match:
            continue
        try:
            timestamp = datetime.strptime(match.group("ts"), "%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
        message = match.group("msg")
        parsed_lines.append(line)
        if "=== AI Trading Bot Starting ===" in message:
            current = LogSession(timestamp)
            sessions.append(current)
        elif current is None:
            continue
        elif message.startswith("signal:OPENED") or message.startswith("signal:CLOSED"):
            current.trades.append({"timestamp": timestamp, "event": message})
        elif message.startswith("signal:HOLD"):
            current.hold_signals += 1
        elif message.startswith("account:"):
            try:
                current.equity_updates.append((timestamp, float(message.split(":", 1)[1])))
            except ValueError:
                pass
        elif "ERROR" in message or message.startswith("error:"):
            current.errors.append(message)
        elif "engine stopped" in message.lower():
            current.end = timestamp
    now = datetime.now()
    for session in sessions:
        session.end = session.end or now
    return sessions, "\n".join(parsed_lines[-20:])


def run_detailed_backtest(
    config_path: str,
    data_path: str,
    costs: TransactionCostModel | None = None,
) -> dict:
    config = load_config(config_path)
    bars = read_csv_prices(data_path)
    simulation = simulate_scalping(
        config,
        bars,
        cost_model=costs or TransactionCostModel(20, 2),
        warmup_bars=min(50, len(bars) - 1),
        liquidate_at_end=True,
    )
    return {
        "symbol": config.symbol,
        "bars": len(bars),
        "diagnostics": analyze_dataset(bars),
        "simulation": simulation,
    }


def format_report(backtest: dict, sessions: list[LogSession], raw_log: str) -> str:
    simulation = backtest["simulation"]
    metrics = simulation.metrics
    diagnostics = backtest["diagnostics"]
    lines = [
        "",
        "=" * 72,
        "  AI TRADING RADAR - COST-AWARE PERFORMANCE REPORT",
        f"  Generated: {datetime.now():%Y-%m-%d %H:%M:%S}",
        "=" * 72,
        "",
        "  [1] LIVE SESSION SUMMARY",
        "  " + "-" * 68,
    ]
    if not sessions:
        lines.append("    No parsed live sessions.")
    else:
        duration = sum(
            (session.end - session.start for session in sessions if session.end),
            timedelta(),
        )
        lines.extend([
            f"    Sessions           : {len(sessions)}",
            f"    Runtime            : {_format_duration(duration)}",
            f"    Trade events       : {sum(len(s.trades) for s in sessions)}",
            f"    Hold signals       : {sum(s.hold_signals for s in sessions)}",
            f"    Errors             : {sum(len(s.errors) for s in sessions)}",
        ])

    lines.extend([
        "",
        "  [2] BACKTEST PERFORMANCE",
        "  " + "-" * 68,
        f"    Symbol / bars      : {backtest['symbol']} / {backtest['bars']}",
        f"    Period             : {diagnostics.start.isoformat()} - {diagnostics.end.isoformat()}",
        f"    Median interval    : {diagnostics.median_interval_minutes:.1f} minutes",
        f"    Duplicate / gaps   : {diagnostics.duplicate_timestamps} / {diagnostics.large_gap_count}",
        f"    Start / end equity : ${metrics.start_equity:,.2f} / ${metrics.end_equity:,.2f}",
        f"    Net return         : {metrics.return_pct:+.4f}% (${metrics.net_profit:+,.2f})",
        f"    Completed trades   : {metrics.completed_trades}",
        f"    Win rate           : {metrics.win_rate_pct:.2f}%",
        f"    Profit factor      : {_format_optional(metrics.profit_factor)}",
        "",
        "  [3] TRANSACTION COSTS",
        "  " + "-" * 68,
        f"    Spread             : ${metrics.total_spread_cost:,.4f}",
        f"    Slippage           : ${metrics.total_slippage_cost:,.4f}",
        f"    Commission         : ${metrics.total_commission:,.4f}",
        f"    Total              : ${metrics.total_transaction_cost:,.4f}",
        "",
        "  [4] DRAWDOWN",
        "  " + "-" * 68,
        f"    Maximum            : {metrics.drawdown.max_drawdown_pct:.4f}%",
        f"    Peak               : {_format_time(metrics.drawdown.peak_time)}",
        f"    Trough             : {_format_time(metrics.drawdown.trough_time)}",
        f"    Recovery           : {_format_time(metrics.drawdown.recovery_time)}",
        f"    Longest underwater : {metrics.drawdown.max_underwater_bars} bars / "
        f"{metrics.drawdown.max_underwater_minutes:.0f} minutes",
        "",
        "  [5] SESSION PERFORMANCE (WIB entry session)",
        "  " + "-" * 68,
    ])
    for session in metrics.sessions:
        lines.append(
            f"    {session.session:<12} trades={session.trades:<4} "
            f"win={session.win_rate_pct:>6.2f}% pnl=${session.net_pnl:+8.2f} "
            f"PF={_format_optional(session.profit_factor)} cost=${session.total_cost:.2f}"
        )
    lines.extend([
        "",
        "  [6] RECENT COMPLETED TRADES",
        "  " + "-" * 68,
    ])
    for trade in simulation.trades[-10:]:
        lines.append(
            f"    {trade.closed_at:%m-%d %H:%M} {trade.side:<5} "
            f"net=${trade.net_pnl:+7.2f} cost=${trade.total_cost:.2f} "
            f"{trade.exit_reason[:30]}"
        )
    if raw_log:
        lines.extend(["", "  [7] LOG TAIL", "  " + "-" * 68])
        lines.extend(f"    {line[:100]}" for line in raw_log.splitlines()[-10:])
    lines.extend(["", "=" * 72, ""])
    return "\n".join(lines)


def _format_optional(value: float | None) -> str:
    return "N/A" if value is None else f"{value:.3f}"


def _format_time(value: datetime | None) -> str:
    return "not recovered" if value is None else value.isoformat()


def _format_duration(value: timedelta) -> str:
    minutes = int(value.total_seconds() // 60)
    return f"{minutes // 60}h {minutes % 60}m"


def main() -> None:
    parser = argparse.ArgumentParser(prog="report_perf")
    parser.add_argument("--config", default="config_finex.example.json")
    parser.add_argument("--data", default="data/xauusd_5m_merged.csv")
    parser.add_argument("--log", default=None)
    parser.add_argument("--no-log", action="store_true")
    parser.add_argument("--spread-points", type=float, default=20.0)
    parser.add_argument("--slippage-points", type=float, default=2.0)
    parser.add_argument("--commission-per-order", type=float, default=0.0)
    parser.add_argument("--commission-per-unit", type=float, default=0.0)
    parser.add_argument("--output", default="perf_report_latest.txt")
    args = parser.parse_args()
    log_path = args.log or str(
        Path(os.environ.get("APPDATA", "")) / "AITradingBot" / "logs" / "trading_bot.log"
    )
    sessions, raw_log = ([], "") if args.no_log else parse_log(log_path)
    backtest = run_detailed_backtest(
        args.config,
        args.data,
        TransactionCostModel(
            args.spread_points,
            args.slippage_points,
            args.commission_per_order,
            args.commission_per_unit,
        ),
    )
    report = format_report(backtest, sessions, raw_log)
    print(report)
    Path(args.output).write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()

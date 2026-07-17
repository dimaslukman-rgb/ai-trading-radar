"""Bounded grid-search optimizer for periodic AI Trading Radar research.

The script never changes a live configuration.  It writes ranked candidates to
JSON, where an operator can review the result before copying parameters into a
paper-trading or live configuration.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, replace
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

from aitrader_bot.backtest import run_backtest
from aitrader_bot.config import load_config
from aitrader_bot.data import read_csv_prices


def _csv_numbers(value: str, cast) -> list:
    return [cast(item.strip()) for item in value.split(",") if item.strip()]


def _score(result) -> float:
    """Reward return, penalize drawdown, and reject zero-trade candidates."""
    if result.trade_count == 0:
        return -10_000.0
    return round(result.return_pct - result.max_drawdown_pct * 0.75, 4)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run bounded scalping parameter optimization")
    parser.add_argument("--config", required=True, help="Base JSON config; it is never modified")
    parser.add_argument("--data", required=True, help="OHLCV CSV with date/open/high/low/close/volume")
    parser.add_argument("--output", default="optimizer_report.json")
    parser.add_argument("--ema-fast", default="5,8,9")
    parser.add_argument("--ema-slow", default="13,21")
    parser.add_argument("--stop-loss-pips", default="15,20,30")
    parser.add_argument("--take-profit-pips", default="15,20,30")
    parser.add_argument("--top", type=int, default=10)
    args = parser.parse_args()

    config = load_config(args.config)
    bars = read_csv_prices(args.data)
    if len(bars) < 60:
        raise SystemExit("Dataset terlalu pendek; gunakan minimal 60 candle.")

    candidates = []
    for fast, slow, stop_loss, take_profit in product(
        _csv_numbers(args.ema_fast, int),
        _csv_numbers(args.ema_slow, int),
        _csv_numbers(args.stop_loss_pips, float),
        _csv_numbers(args.take_profit_pips, float),
    ):
        if fast >= slow or stop_loss <= 0 or take_profit <= 0:
            continue
        scalping = replace(
            config.scalping,
            ema_fast=fast,
            ema_slow=slow,
            stop_loss_pips=stop_loss,
            take_profit_pips=take_profit,
        )
        result = run_backtest(replace(config, scalping=scalping), bars, mode="scalping")
        candidates.append({
            "score": _score(result),
            "parameters": {
                "ema_fast": fast, "ema_slow": slow,
                "stop_loss_pips": stop_loss, "take_profit_pips": take_profit,
            },
            "metrics": {
                "return_pct": result.return_pct,
                "max_drawdown_pct": result.max_drawdown_pct,
                "trade_count": result.trade_count,
                "end_equity": result.end_equity,
            },
        })

    candidates.sort(key=lambda item: item["score"], reverse=True)
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": str(Path(args.data)),
        "symbol": config.symbol,
        "mode": "scalping",
        "objective": "return_pct - 0.75 * max_drawdown_pct; zero-trade candidates are rejected",
        "tested": len(candidates),
        "top_candidates": candidates[:max(1, args.top)],
    }
    Path(args.output).write_text(json.dumps(report, indent=2), encoding="utf-8")
    if candidates:
        best = candidates[0]
        print(f"Best score {best['score']:.2f}: {best['parameters']}")
    print(f"Report written: {args.output}")


if __name__ == "__main__":
    main()

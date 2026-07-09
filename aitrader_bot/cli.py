"""CLI — multi-broker scalping bot interface.

Commands:
  backtest       Run backtest (momentum or scalping mode)
  signal         Generate signal (momentum or scalping mode)
  scalp          Live scalping loop via any broker (paper/mt5/binance/alpaca)
  broker         Test broker connection and get info/quote/positions
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime
from pathlib import Path

from .ai_trader_client import AiTraderClient
from .backtest import run_backtest
from .broker import ExchangeType, OrderSide, create_broker
from .config import load_config
from .data import fetch_yahoo_chart, read_csv_prices
from .models import PriceBar
from .scalping import ScalpingStrategy
from .strategy import AiMomentumStrategy


def main() -> None:
    parser = argparse.ArgumentParser(prog="ai-trading-bot")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── backtest ────────────────────────────────────────────────────────
    bt = subparsers.add_parser("backtest", help="Jalankan backtest")
    bt.add_argument("--config", default="config.example.json")
    bt.add_argument("--data", default="data/sample_prices.csv")
    bt.add_argument("--mode", choices=["momentum", "scalping"], default="momentum")

    # ── signal ──────────────────────────────────────────────────────────
    sig = subparsers.add_parser("signal", help="Generate trading signal")
    sig.add_argument("--config", default="config.example.json")
    sig.add_argument("--data")
    sig.add_argument("--range", default="6mo")
    sig.add_argument("--interval", default="1d")
    sig.add_argument("--mode", choices=["momentum", "scalping"], default="momentum")
    sig.add_argument("--publish", action="store_true")

    # ── scalp (live loop) ───────────────────────────────────────────────
    sc = subparsers.add_parser("scalp", help="Live scalping via broker")
    sc.add_argument("--config", default="config.example.json")
    sc.add_argument("--broker", default="default",
                    help="Nama broker config (default / paper / mt5 / binance / alpaca)")
    sc.add_argument("--iterations", type=int, default=10)
    sc.add_argument("--interval", type=int, default=300,
                    help="detik antar sinyal (default 300 = 5m)")
    sc.add_argument("--symbol", default=None,
                    help="Override symbol (default: dari config)")

    # ── broker info ─────────────────────────────────────────────────────
    br = subparsers.add_parser("broker", help="Test broker connection")
    br.add_argument("--config", default="config.example.json")
    br.add_argument("--broker", default="default",
                    help="Nama broker config (default / paper / mt5 / binance / alpaca)")
    br.add_argument("--action", choices=["info", "quote", "positions", "candles"],
                    default="info")
    br.add_argument("--symbol", default=None)

    args = parser.parse_args()

    if args.command == "backtest":
        _cmd_backtest(args)
    elif args.command == "signal":
        _cmd_signal(args)
    elif args.command == "scalp":
        _cmd_scalp(args)
    elif args.command == "broker":
        _cmd_broker(args)


# ══════════════════════════════════════════════════════════════════════════
#  Backtest
# ══════════════════════════════════════════════════════════════════════════

def _cmd_backtest(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    bars = read_csv_prices(args.data)
    result = run_backtest(config, bars, mode=args.mode)
    print(json.dumps({
        "mode": args.mode,
        "start_equity": round(result.start_equity, 2),
        "end_equity": round(result.end_equity, 2),
        "return_pct": round(result.return_pct, 2),
        "max_drawdown_pct": round(result.max_drawdown_pct, 2),
        "trade_count": result.trade_count,
        "last_signal": {
            "symbol": result.last_signal.symbol,
            "action": result.last_signal.action,
            "confidence": round(result.last_signal.confidence, 3),
            "price": round(result.last_signal.price, 4),
            "reason": result.last_signal.reason,
        },
    }, indent=2))


# ══════════════════════════════════════════════════════════════════════════
#  Signal
# ══════════════════════════════════════════════════════════════════════════

def _cmd_signal(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    if args.data:
        bars = read_csv_prices(args.data)
    else:
        bars = fetch_yahoo_chart(config.symbol, args.range, args.interval)

    if args.mode == "scalping":
        signal = ScalpingStrategy(config.scalping).generate(config.symbol, bars)
    else:
        signal = AiMomentumStrategy(config.strategy).generate(config.symbol, bars)

    payload = {
        "mode": args.mode,
        "symbol": signal.symbol,
        "action": signal.action,
        "confidence": round(signal.confidence, 3),
        "price": round(signal.price, 4),
        "reason": signal.reason,
        "created_at": signal.created_at.isoformat(),
    }

    if args.publish:
        token = os.getenv("AI_TRADER_TOKEN")
        if not token:
            raise SystemExit("set AI_TRADER_TOKEN dulu untuk publish")
        payload["ai_trader_response"] = AiTraderClient(token).publish_strategy(config.market, signal)

    print(json.dumps(payload, indent=2))


# ══════════════════════════════════════════════════════════════════════════
#  Scalp — live loop
# ══════════════════════════════════════════════════════════════════════════

def _cmd_scalp(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    strategy = ScalpingStrategy(config.scalping)

    # Resolve broker
    broker_cfg = config.brokers.get(args.broker) or config.brokers.get("default")
    if not broker_cfg:
        available = ", ".join(config.brokers.keys())
        print(f"Broker '{args.broker}' tidak ditemukan. Tersedia: {available}")
        return

    symbol = args.symbol or config.symbol
    broker = create_broker(
        broker_cfg.backend,
        api_key=broker_cfg.api_key,
        secret=broker_cfg.secret,
        server=broker_cfg.server,
        login=broker_cfg.login,
        password=broker_cfg.password,
        paper=broker_cfg.paper,
        sandbox=broker_cfg.sandbox,
        initial_cash=config.risk.initial_cash,
    )

    mapped_symbol = broker.get_symbol_map(symbol)

    print(f"[SCALP] {broker_cfg.backend}  symbol={mapped_symbol}")
    print(f"        interval={args.interval}s  iterations={'INF' if args.iterations == 0 else args.iterations}")
    print()

    try:
        broker.connect()
        acct = broker.get_account()
        print(f"[OK] Connected — {acct.equity} {acct.currency}")
    except Exception as e:
        print(f"[FAIL] Connection failed: {e}")
        return

    iteration = 0
    bars: list[PriceBar] = []
    candle_history: list = []

    try:
        while True:
            if args.iterations > 0 and iteration >= args.iterations:
                break
            iteration += 1

            # Fetch latest quote
            quote = broker.get_quote(mapped_symbol)

            if quote is None:
                print(f"[{iteration}] [...waiting...] No quote yet")
            else:
                # Try to fetch candles from broker
                try:
                    candle_history = broker.fetch_candles(mapped_symbol, "5m", 50)
                except Exception:
                    pass

                if candle_history:
                    # Use broker candles
                    bars = [PriceBar(
                        date=c.timestamp,
                        open=c.open, high=c.high, low=c.low,
                        close=c.close, volume=c.volume,
                    ) for c in candle_history]
                else:
                    # Build from ticks
                    now = datetime.now()
                    bars.append(PriceBar(
                        date=now, open=quote.last, high=quote.last,
                        low=quote.last, close=quote.last, volume=quote.volume,
                    ))
                    if len(bars) > 50:
                        bars = bars[-50:]

                # Generate signal
                signal = strategy.generate(symbol, bars, quote)
                positions = broker.get_positions(mapped_symbol)
                has_pos = len(positions) > 0

                # Execute
                qty = 0.01
                if signal.action == "buy" and not has_pos:
                    result = broker.place_order(mapped_symbol, OrderSide.BUY, qty)
                    msg = f"[BUY]  {mapped_symbol} @ {quote.last:.2f} | {result.message}"
                elif signal.action == "sell" and has_pos:
                    result = broker.close_position(positions[0].ticket)
                    msg = f"[SELL] {mapped_symbol} @ {quote.last:.2f} | {result.message}"
                else:
                    status = "HODL" if has_pos else "HOLD"
                    msg = f"[{status}] {mapped_symbol} @ {quote.last:.2f}  sc={signal.confidence:.3f}  [{signal.reason}]"

                print(f"[{iteration}] {msg}")

            time.sleep(args.interval)

    except KeyboardInterrupt:
        print("\n[STOP] Stopped by user.")
    finally:
        broker.disconnect()
        print(f"[DONE] Disconnected. Iterations: {iteration}")


# ══════════════════════════════════════════════════════════════════════════
#  Broker info
# ══════════════════════════════════════════════════════════════════════════

def _cmd_broker(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    broker_cfg = config.brokers.get(args.broker) or config.brokers.get("default")
    if not broker_cfg:
        available = ", ".join(config.brokers.keys())
        print(f"Broker '{args.broker}' tidak ditemukan. Tersedia: {available}")
        return

    symbol = args.symbol or config.symbol

    broker = create_broker(
        broker_cfg.backend,
        api_key=broker_cfg.api_key,
        secret=broker_cfg.secret,
        server=broker_cfg.server,
        login=broker_cfg.login,
        password=broker_cfg.password,
        paper=broker_cfg.paper,
        sandbox=broker_cfg.sandbox,
        initial_cash=config.risk.initial_cash,
    )

    try:
        broker.connect()
    except Exception as e:
        print(json.dumps({"error": str(e)}, indent=2))
        return

    try:
        if args.action == "info":
            acct = broker.get_account()
            print(json.dumps({
                "exchange": acct.exchange.value,
                "balance": acct.balance,
                "equity": acct.equity,
                "margin": acct.margin,
                "margin_free": acct.margin_free,
                "leverage": acct.leverage,
                "currency": acct.currency,
                "buying_power": acct.buying_power,
            }, indent=2))

        elif args.action == "quote":
            mapped = broker.get_symbol_map(symbol)
            quote = broker.get_quote(mapped)
            if quote:
                print(json.dumps({
                    "symbol": quote.symbol,
                    "exchange": quote.exchange.value,
                    "bid": quote.bid,
                    "ask": quote.ask,
                    "last": quote.last,
                    "spread": round(quote.spread, 4),
                    "spread_pct": round(quote.spread_pct * 100, 4),
                    "volume": quote.volume,
                    "timestamp": quote.timestamp.isoformat(),
                }, indent=2))
            else:
                print(json.dumps({"error": f"no quote for {mapped}"}, indent=2))

        elif args.action == "positions":
            positions = broker.get_positions()
            if positions:
                data = []
                for p in positions:
                    data.append({
                        "ticket": p.ticket,
                        "symbol": p.symbol,
                        "exchange": p.exchange.value,
                        "qty": p.quantity,
                        "avg_price": p.avg_price,
                        "current": p.current_price,
                        "unrealized_pnl": round(p.unrealized_pnl, 2),
                    })
                print(json.dumps(data, indent=2))
            else:
                print(json.dumps({"message": "no open positions"}, indent=2))

        elif args.action == "candles":
            mapped = broker.get_symbol_map(symbol)
            candles = broker.fetch_candles(mapped, "5m", 10)
            if candles:
                data = []
                for c in candles:
                    data.append({
                        "time": c.timestamp.isoformat(),
                        "o": c.open, "h": c.high, "l": c.low,
                        "c": c.close, "v": c.volume,
                    })
                print(json.dumps(data, indent=2))
            else:
                print(json.dumps({"error": "no candles"}, indent=2))

    finally:
        broker.disconnect()


if __name__ == "__main__":
    main()

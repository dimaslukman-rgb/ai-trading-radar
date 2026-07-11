"""CLI — multi-broker scalping bot interface.

Commands:
  backtest       Run backtest (momentum or scalping mode)
  research       Cost-aware walk-forward strategy research
  signal         Generate signal (momentum or scalping mode)
  scalp          Live scalping loop via any broker (paper/mt5/binance/alpaca)
  broker         Test broker connection and get info/quote/positions
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from .ai_trader_client import AiTraderClient
from .backtest import run_backtest
from .broker import ExchangeType, OrderSide, OrderStatus, create_broker
from .config import load_config
from .data import fetch_yahoo_chart, read_csv_prices
from .decision import (
    TradingDecisionService,
    compute_protective_prices as _compute_sl_tp,
    entry_safety_blocks as _entry_safety_blocks,
    higher_timeframe_confirmation,
)
from .models import PriceBar
from .position_state import PositionActionType, PositionPhase, PositionSide, PositionStateMachine
from .scalping import ScalpingStrategy
from .services.execution import order_result_detail as _order_result_detail
from .strategy import AiMomentumStrategy


def main() -> None:
    parser = argparse.ArgumentParser(prog="ai-trading-bot")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ── backtest ────────────────────────────────────────────────────────
    bt = subparsers.add_parser("backtest", help="Jalankan backtest")
    bt.add_argument("--config", default="config.example.json")
    bt.add_argument("--data", default="data/sample_prices.csv")
    bt.add_argument("--mode", choices=["momentum", "scalping"], default="momentum")

    # ── research ────────────────────────────────────────────────────────
    research = subparsers.add_parser(
        "research",
        help="Walk-forward optimization dan analisis biaya/sesi/drawdown",
    )
    research.add_argument("--config", default="config_finex.example.json")
    research.add_argument("--data", default="data/xauusd_5m_merged.csv")
    research.add_argument("--train-bars", type=int, default=3000)
    research.add_argument("--test-bars", type=int, default=1000)
    research.add_argument("--step-bars", type=int, default=None)
    research.add_argument("--warmup-bars", type=int, default=50)
    research.add_argument("--max-candidates", type=int, default=12)
    research.add_argument("--minimum-trades", type=int, default=5)
    research.add_argument("--spread-points", type=float, default=20.0)
    research.add_argument("--slippage-points", type=float, default=2.0)
    research.add_argument("--commission-per-order", type=float, default=0.0)
    research.add_argument("--commission-per-unit", type=float, default=0.0)
    research.add_argument("--output", default=None)
    research.add_argument("--quiet", action="store_true")

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
    elif args.command == "research":
        _cmd_research(args)
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


def _cmd_research(args: argparse.Namespace) -> None:
    """Run cost sensitivity plus train-only selection / unseen test folds."""
    from .research import TransactionCostModel, analyze_dataset, simulate_scalping
    from .walk_forward import default_candidate_grid, walk_forward_optimize

    config = load_config(args.config)
    bars = read_csv_prices(args.data)
    candidates = default_candidate_grid()[:max(1, args.max_candidates)]
    costs = TransactionCostModel(
        spread_points=args.spread_points,
        slippage_points=args.slippage_points,
        commission_per_order=args.commission_per_order,
        commission_per_unit=args.commission_per_unit,
    )
    baseline = simulate_scalping(
        config,
        bars,
        cost_model=costs,
        warmup_bars=min(args.warmup_bars, len(bars) - 1),
        liquidate_at_end=True,
    )
    zero_cost = TransactionCostModel(spread_points=0.0)
    stress_cost = TransactionCostModel(
        spread_points=min(
            config.scalping.max_spread_points,
            max(args.spread_points, args.spread_points * 1.25),
        ),
        slippage_points=args.slippage_points * 2,
        commission_per_order=args.commission_per_order * 1.5,
        commission_per_unit=args.commission_per_unit * 1.5,
    )
    sensitivity = {
        "zero_cost": simulate_scalping(
            config,
            bars,
            cost_model=zero_cost,
            warmup_bars=min(args.warmup_bars, len(bars) - 1),
            liquidate_at_end=True,
        ).to_dict(),
        "configured": baseline.to_dict(),
        "stress": simulate_scalping(
            config,
            bars,
            cost_model=stress_cost,
            warmup_bars=min(args.warmup_bars, len(bars) - 1),
            liquidate_at_end=True,
        ).to_dict(),
    }
    walk_forward = walk_forward_optimize(
        config,
        bars,
        candidates=candidates,
        train_bars=args.train_bars,
        test_bars=args.test_bars,
        step_bars=args.step_bars,
        warmup_bars=args.warmup_bars,
        cost_model=costs,
        minimum_train_trades=args.minimum_trades,
    )
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dataset": {
            "path": args.data,
            "symbol": config.symbol,
            "bars": len(bars),
            "start": bars[0].date.isoformat(),
            "end": bars[-1].date.isoformat(),
            "timestamp_policy": "naive CSV timestamps normalized as UTC; sessions reported in WIB",
        },
        "methodology": {
            "selection": "train windows only",
            "evaluation": "unseen test windows with pre-entry warmup",
            "liquidation": "positions closed at each evaluation boundary",
            "candidate_count": len(candidates),
        },
        "baseline": baseline.to_dict(),
        "cost_sensitivity": sensitivity,
        "walk_forward": walk_forward.to_dict(),
    }
    payload["dataset"]["diagnostics"] = {
        key: (value.isoformat() if isinstance(value, datetime) else value)
        for key, value in vars(analyze_dataset(bars)).items()
    }
    rendered = json.dumps(payload, indent=2, allow_nan=False)
    if not args.quiet:
        print(rendered)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")


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
    from .app.news_filter import get_upcoming_event

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
        symbol=symbol,
        market=config.market,
    )

    mapped_symbol = broker.get_symbol_map(symbol)

    print(f"[SCALP] {broker_cfg.backend}  symbol={mapped_symbol}")
    print(f"        interval={args.interval}s  iterations={'INF' if args.iterations == 0 else args.iterations}")
    print()

    try:
        broker.connect()
        acct = broker.get_account()
        position_machine = PositionStateMachine.from_config(
            config.scalping,
            broker_supports_short=broker.supports_short_positions,
            broker_supports_multiple=broker.supports_multiple_positions,
        )
        decision_service = TradingDecisionService(config.scalping, position_machine)
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
                news_event = None
                if config.scalping.news_filter_enabled:
                    news_event = get_upcoming_event(
                        buffer_minutes=config.scalping.news_filter_minutes,
                    )
                entry_blocks = _entry_safety_blocks(
                    config.scalping,
                    quote,
                    supports_attached_protection=broker.supports_attached_protection,
                    news_event=news_event,
                )

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
                position_machine.sync(positions)
                managed_positions = position_machine.active_positions(mapped_symbol)

                if managed_positions and broker.supports_attached_protection:
                    for pos in positions:
                        side = (getattr(pos, "side", "") or "buy").lower()
                        side = "sell" if side in {"sell", "short"} else "buy"
                        needs_sl = config.scalping.stop_loss_pips > 0 and pos.stop_loss is None
                        needs_tp = config.scalping.take_profit_pips > 0 and pos.take_profit is None
                        if not (needs_sl or needs_tp):
                            continue
                        desired = _compute_sl_tp(
                            pos.avg_price,
                            side,
                            config.scalping,
                            symbol=symbol,
                            point_size=quote.point_size,
                        )
                        repair = broker.set_position_protection(
                            pos.ticket,
                            desired["sl"] if needs_sl else pos.stop_loss,
                            desired["tp"] if needs_tp else pos.take_profit,
                        )
                        if repair.status != OrderStatus.FILLED:
                            print(f"[{iteration}] [SAFETY] {_order_result_detail(repair, pos.quantity)}")

                messages: list[str] = []
                close_attempted = False

                def close_position(pos, reason: str) -> None:
                    nonlocal close_attempted
                    close_attempted = True
                    position_machine.mark_closing(pos.ticket)
                    result = broker.close_position(pos.ticket)
                    phase = position_machine.apply_close_result(pos.ticket, result)
                    if phase == PositionPhase.CLOSED:
                        messages.append(f"[CLOSED {pos.side.name}] {pos.ticket} | {reason}")
                    else:
                        messages.append(
                            f"[CLOSE {phase.value.upper()}] {pos.ticket} | "
                            f"{_order_result_detail(result, pos.quantity)}"
                        )

                tf_confirmed, tf_reason = higher_timeframe_confirmation(
                    [bar.close for bar in bars[-25:]], signal.action,
                )
                decision_plan = decision_service.decide(
                    signal.action,
                    mapped_symbol,
                    point_size=quote.point_size,
                    now=datetime.now(timezone.utc),
                    entry_block_reasons=entry_blocks,
                    higher_timeframe_confirmed=tf_confirmed,
                    higher_timeframe_reason=tf_reason,
                )

                if not close_attempted:
                    actions = decision_plan.actions
                    for action in actions:
                        if action.action == PositionActionType.HOLD:
                            messages.append(f"[HOLD] {action.reason}")
                            continue
                        if action.action == PositionActionType.CLOSE:
                            pos = position_machine.get(action.ticket)
                            if pos is not None:
                                close_position(pos, action.reason)
                            continue

                        side = (
                            PositionSide.LONG
                            if action.action == PositionActionType.OPEN_LONG
                            else PositionSide.SHORT
                        )
                        order_side = OrderSide.BUY if side == PositionSide.LONG else OrderSide.SELL
                        entry_price = quote.ask if side == PositionSide.LONG else quote.bid
                        account = broker.get_account()
                        quantity = decision_service.entry_quantity(
                            account.balance, account.equity, entry_price,
                        )
                        protection = _compute_sl_tp(
                            entry_price,
                            side.value,
                            config.scalping,
                            symbol=symbol,
                            point_size=quote.point_size,
                        )
                        result = broker.place_order(
                            mapped_symbol,
                            order_side,
                            quantity,
                            stop_loss=protection["sl"] if config.scalping.stop_loss_pips > 0 else None,
                            take_profit=protection["tp"] if config.scalping.take_profit_pips > 0 else None,
                        )
                        position_machine.record_entry_result(mapped_symbol, side, result)
                        if result.status in {OrderStatus.FILLED, OrderStatus.PARTIAL} and result.filled_qty > 0:
                            messages.append(f"[OPEN {side.name}] {mapped_symbol} | {result.message}")
                        elif result.status == OrderStatus.PENDING:
                            messages.append(f"[ENTRY PENDING {side.name}] {result.message}")
                        else:
                            messages.append(
                                f"[ENTRY REJECTED {side.name}] "
                                f"{_order_result_detail(result, quantity)}"
                            )

                print(f"[{iteration}] {' || '.join(messages)}")

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
        symbol=symbol,
        market=config.market,
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

from __future__ import annotations

from dataclasses import dataclass

from .broker import OrderSide, OrderStatus, PaperBroker
from .config import BotConfig
from .decision import (
    TradingDecisionService,
    as_wib,
    compute_protective_prices,
    entry_safety_blocks,
    higher_timeframe_confirmation,
)
from .models import PriceBar, Signal
from .portfolio import Portfolio
from .position_state import PositionActionType, PositionSide, PositionStateMachine
from .risk import RiskManager
from .scalping import ScalpingStrategy
from .strategy import AiMomentumStrategy


@dataclass(frozen=True)
class BacktestResult:
    start_equity: float
    end_equity: float
    return_pct: float
    max_drawdown_pct: float
    trade_count: int
    last_signal: Signal


def run_backtest(config: BotConfig, bars: list[PriceBar], mode: str = "momentum") -> BacktestResult:
    """Run a backtest with either 'momentum' or 'scalping' strategy mode."""
    if len(bars) < 2:
        raise ValueError("butuh minimal 2 bar harga")

    if mode == "scalping":
        return _run_scalping_backtest(config, bars)
    return _run_momentum_backtest(config, bars)


def _run_momentum_backtest(config: BotConfig, bars: list[PriceBar]) -> BacktestResult:
    strategy = AiMomentumStrategy(config.strategy)
    risk = RiskManager(config.risk)
    portfolio = Portfolio(config.risk.initial_cash)
    start_equity = config.risk.initial_cash
    peak_equity = start_equity
    max_drawdown = 0.0
    last_signal = Signal(config.symbol, "hold", 0.0, bars[0].close, "awal backtest", bars[0].date)

    for index in range(1, len(bars) + 1):
        window = bars[:index]
        latest = window[-1]
        prices = {config.symbol: latest.close}
        last_signal = strategy.generate(config.symbol, window)
        position = portfolio.position(config.symbol)
        forced_exit = risk.forced_exit_reason(position, latest.close)

        if forced_exit and position:
            portfolio.sell(last_signal, position.quantity, forced_exit)
        elif last_signal.action == "buy":
            quantity = risk.buy_quantity(portfolio, last_signal, prices)
            portfolio.buy(last_signal, quantity, last_signal.reason)
        elif last_signal.action == "sell" and position:
            quantity = risk.sell_quantity(position, last_signal)
            portfolio.sell(last_signal, quantity, last_signal.reason)

        equity = portfolio.equity(prices)
        peak_equity = max(peak_equity, equity)
        drawdown = (peak_equity - equity) / peak_equity if peak_equity else 0.0
        max_drawdown = max(max_drawdown, drawdown)

    end_equity = portfolio.equity({config.symbol: bars[-1].close})
    return BacktestResult(
        start_equity=start_equity,
        end_equity=end_equity,
        return_pct=((end_equity - start_equity) / start_equity) * 100.0,
        max_drawdown_pct=max_drawdown * 100.0,
        trade_count=len(portfolio.trades),
        last_signal=last_signal,
    )


def _run_scalping_backtest(config: BotConfig, bars: list[PriceBar]) -> BacktestResult:
    """Run scalping through the same state machine and decisions as live mode."""
    from .app.news_filter import get_upcoming_event

    upper_symbol = config.symbol.upper()
    if "XAU" in upper_symbol or "GOLD" in upper_symbol:
        point_size = 0.01
    elif "JPY" in upper_symbol:
        point_size = 0.001
    elif config.market.lower() == "forex":
        point_size = 0.00001
    else:
        point_size = 0.01

    broker = PaperBroker(
        initial_cash=config.risk.initial_cash,
        point_size=point_size,
        spread_points=min(10.0, max(0.0, config.scalping.max_spread_points)),
    )
    broker.connect()
    strategy = ScalpingStrategy(config.scalping)
    position_machine = PositionStateMachine.from_config(
        config.scalping,
        broker_supports_short=broker.supports_short_positions,
        broker_supports_multiple=broker.supports_multiple_positions,
    )
    decision_service = TradingDecisionService(config.scalping, position_machine)
    start_equity = config.risk.initial_cash
    peak_equity = start_equity
    max_drawdown = 0.0
    last_signal = Signal(config.symbol, "hold", 0.0, bars[0].close, "awal scalping backtest", bars[0].date)

    for index in range(1, len(bars) + 1):
        window = bars[:index]
        latest = window[-1]
        broker.update_price(
            config.symbol,
            latest.close,
            latest.volume,
            timestamp=latest.date,
        )
        quote = broker.get_quote(config.symbol)
        if quote is None:
            continue
        last_signal = strategy.generate(config.symbol, window, quote)
        position_machine.sync(broker.get_positions(config.symbol))

        news_event = None
        if config.scalping.news_filter_enabled:
            news_time = as_wib(latest.date).replace(tzinfo=None)
            news_event = get_upcoming_event(
                news_time,
                buffer_minutes=config.scalping.news_filter_minutes,
            )
        blockers = entry_safety_blocks(
            config.scalping,
            quote,
            supports_attached_protection=broker.supports_attached_protection,
            now=latest.date,
            news_event=news_event,
        )
        tf_confirmed, tf_reason = higher_timeframe_confirmation(
            [bar.close for bar in window[-25:]], last_signal.action,
        )
        decision = decision_service.decide(
            last_signal.action,
            config.symbol,
            point_size=quote.point_size,
            now=latest.date,
            entry_block_reasons=blockers,
            higher_timeframe_confirmed=tf_confirmed,
            higher_timeframe_reason=tf_reason,
        )

        for action in decision.actions:
            if action.action == PositionActionType.HOLD:
                continue
            if action.action == PositionActionType.CLOSE:
                result = broker.close_position(action.ticket)
                position_machine.apply_close_result(action.ticket, result)
                if result.status == OrderStatus.FILLED:
                    closed_side = action.side or PositionSide.LONG
                    last_signal = Signal(
                        config.symbol,
                        "sell" if closed_side == PositionSide.LONG else "buy",
                        last_signal.confidence,
                        result.avg_fill_price or latest.close,
                        action.reason,
                        latest.date,
                    )
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
            protection = compute_protective_prices(
                entry_price,
                side.value,
                config.scalping,
                symbol=config.symbol,
                point_size=quote.point_size,
            )
            result = broker.place_order(
                config.symbol,
                order_side,
                quantity,
                stop_loss=protection["sl"] if config.scalping.stop_loss_pips > 0 else None,
                take_profit=protection["tp"] if config.scalping.take_profit_pips > 0 else None,
            )
            position_machine.record_entry_result(config.symbol, side, result)

        position_machine.sync(broker.get_positions(config.symbol))
        equity = broker.get_account().equity
        peak_equity = max(peak_equity, equity)
        drawdown = (peak_equity - equity) / peak_equity if peak_equity else 0.0
        max_drawdown = max(max_drawdown, drawdown)

    end_equity = broker.get_account().equity
    trade_count = len(broker.trade_log)
    broker.disconnect()
    return BacktestResult(
        start_equity=start_equity,
        end_equity=end_equity,
        return_pct=((end_equity - start_equity) / start_equity) * 100.0,
        max_drawdown_pct=max_drawdown * 100.0,
        trade_count=trade_count,
        last_signal=last_signal,
    )

"""Detailed, cost-aware scalping simulation and performance analytics."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from .app.news_filter import get_upcoming_event
from .broker import OrderSide, OrderStatus, PaperBroker
from .broker.paper_broker import infer_contract_size, infer_leverage
from .config import BotConfig
from .decision import (
    TradingDecisionService,
    as_wib,
    compute_protective_prices,
    entry_safety_blocks,
    higher_timeframe_confirmation,
    minutes_in_window,
)
from .models import PriceBar, Signal
from .position_state import PositionActionType, PositionSide, PositionStateMachine
from .scalping import ScalpingStrategy


@dataclass(frozen=True)
class TransactionCostModel:
    """Direct and implicit costs applied to every simulated fill."""

    spread_points: float = 10.0
    slippage_points: float = 0.0
    commission_per_order: float = 0.0
    commission_per_unit: float = 0.0

    def __post_init__(self) -> None:
        for name, value in asdict(self).items():
            if value < 0:
                raise ValueError(f"{name} must be non-negative")


@dataclass(frozen=True)
class EquityPoint:
    timestamp: datetime
    equity: float
    balance: float


@dataclass(frozen=True)
class DatasetDiagnostics:
    bars: int
    start: datetime
    end: datetime
    duplicate_timestamps: int
    out_of_order_timestamps: int
    median_interval_minutes: float
    large_gap_count: int
    largest_gap_minutes: float


@dataclass(frozen=True)
class CompletedTrade:
    ticket: str
    side: str
    opened_at: datetime
    closed_at: datetime
    entry_mid: float
    exit_mid: float
    entry_fill: float
    exit_fill: float
    quantity: float
    gross_pnl: float
    net_pnl: float
    commission: float
    spread_cost: float
    slippage_cost: float
    session: str
    exit_reason: str

    @property
    def total_cost(self) -> float:
        return self.commission + self.spread_cost + self.slippage_cost


@dataclass(frozen=True)
class DrawdownAnalysis:
    max_drawdown_pct: float
    peak_time: datetime | None
    trough_time: datetime | None
    recovery_time: datetime | None
    max_underwater_bars: int
    max_underwater_minutes: float


@dataclass(frozen=True)
class SessionPerformance:
    session: str
    trades: int
    wins: int
    losses: int
    win_rate_pct: float
    net_pnl: float
    total_cost: float
    profit_factor: float | None


@dataclass(frozen=True)
class PerformanceMetrics:
    start_equity: float
    end_equity: float
    net_profit: float
    return_pct: float
    order_count: int
    completed_trades: int
    wins: int
    losses: int
    win_rate_pct: float
    profit_factor: float | None
    average_trade: float
    total_commission: float
    total_spread_cost: float
    total_slippage_cost: float
    total_transaction_cost: float
    drawdown: DrawdownAnalysis
    sessions: tuple[SessionPerformance, ...]


@dataclass(frozen=True)
class SimulationResult:
    metrics: PerformanceMetrics
    trades: tuple[CompletedTrade, ...]
    equity_curve: tuple[EquityPoint, ...]
    last_signal: Signal
    cost_model: TransactionCostModel
    warmup_bars: int

    def to_dict(self, *, include_equity_curve: bool = False) -> dict[str, Any]:
        payload = _serialize({
            "metrics": self.metrics,
            "trades": self.trades,
            "last_signal": self.last_signal,
            "cost_model": self.cost_model,
            "warmup_bars": self.warmup_bars,
        })
        if include_equity_curve:
            payload["equity_curve"] = _serialize(self.equity_curve)
        return payload


@dataclass
class _OpenTrade:
    ticket: str
    side: PositionSide
    opened_at: datetime
    entry_mid: float
    entry_fill: float
    quantity: float
    commission: float
    spread_cost: float
    slippage_cost: float


def infer_point_size(config: BotConfig) -> float:
    upper = config.symbol.upper()
    if "XAU" in upper or "GOLD" in upper:
        return 0.01
    if "JPY" in upper:
        return 0.001
    if config.market.lower() == "forex":
        return 0.00001
    return 0.01


def classify_session(timestamp: datetime, config) -> str:
    """Classify entries into mutually exclusive WIB research sessions."""
    local = as_wib(timestamp)
    minute = local.hour * 60 + local.minute
    london = minutes_in_window(
        minute,
        config.session_london_start * 60,
        config.session_london_end * 60,
    )
    new_york = minutes_in_window(
        minute,
        config.session_ny_start * 60 + 30,
        config.session_ny_end * 60,
    )
    if london:
        return "london"
    if new_york:
        return "new_york"
    if minutes_in_window(minute, 7 * 60, 14 * 60):
        return "asia"
    return "off_session"


def analyze_dataset(bars: list[PriceBar]) -> DatasetDiagnostics:
    if not bars:
        raise ValueError("dataset is empty")
    intervals = [
        (bars[index].date - bars[index - 1].date).total_seconds() / 60.0
        for index in range(1, len(bars))
    ]
    positive = sorted(value for value in intervals if value > 0)
    if positive:
        middle = len(positive) // 2
        median = (
            positive[middle]
            if len(positive) % 2
            else (positive[middle - 1] + positive[middle]) / 2
        )
    else:
        median = 0.0
    gap_threshold = median * 1.5 if median > 0 else float("inf")
    return DatasetDiagnostics(
        bars=len(bars),
        start=bars[0].date,
        end=bars[-1].date,
        duplicate_timestamps=sum(value == 0 for value in intervals),
        out_of_order_timestamps=sum(value < 0 for value in intervals),
        median_interval_minutes=median,
        large_gap_count=sum(value > gap_threshold for value in intervals),
        largest_gap_minutes=max(positive, default=0.0),
    )


def simulate_scalping(
    config: BotConfig,
    bars: list[PriceBar],
    *,
    cost_model: TransactionCostModel | None = None,
    warmup_bars: int = 0,
    history_size: int = 50,
    liquidate_at_end: bool = False,
) -> SimulationResult:
    """Run the shared strategy/decision/state stack with detailed accounting."""
    if len(bars) < 2:
        raise ValueError("butuh minimal 2 bar harga")
    if warmup_bars < 0 or warmup_bars >= len(bars):
        raise ValueError("warmup_bars must be between 0 and len(bars)-1")
    costs = cost_model or TransactionCostModel(
        spread_points=min(10.0, max(0.0, config.scalping.max_spread_points)),
    )
    point_size = infer_point_size(config)
    contract_size = infer_contract_size(config.symbol, config.market)
    broker = PaperBroker(
        initial_cash=config.risk.initial_cash,
        point_size=point_size,
        spread_points=costs.spread_points,
        slippage_points=costs.slippage_points,
        commission_per_order=costs.commission_per_order,
        commission_per_unit=costs.commission_per_unit,
        contract_size=contract_size,
        leverage=infer_leverage(config.market),
    )
    broker.connect()
    strategy = ScalpingStrategy(config.scalping)
    machine = PositionStateMachine.from_config(
        config.scalping,
        broker_supports_short=broker.supports_short_positions,
        broker_supports_multiple=broker.supports_multiple_positions,
    )
    decisions = TradingDecisionService(config.scalping, machine)
    open_trades: dict[str, _OpenTrade] = {}
    completed: list[CompletedTrade] = []
    equity_curve: list[EquityPoint] = [EquityPoint(
        bars[0].date,
        config.risk.initial_cash,
        config.risk.initial_cash,
    )]
    last_signal = Signal(
        config.symbol,
        "hold",
        0.0,
        bars[0].close,
        "awal scalping backtest",
        bars[0].date,
    )

    def close_ticket(ticket: str, reason: str, bar: PriceBar) -> None:
        nonlocal last_signal
        position = machine.get(ticket)
        if position is None:
            return
        result = broker.close_position(ticket)
        machine.apply_close_result(ticket, result)
        if result.status != OrderStatus.FILLED:
            return
        record = open_trades.pop(ticket, None)
        if record is None:
            return
        multiplier = 1.0 if record.side == PositionSide.LONG else -1.0
        gross_pnl = (
            (bar.close - record.entry_mid)
            * record.quantity
            * multiplier
            * contract_size
        )
        fill_pnl = (
            (result.avg_fill_price - record.entry_fill)
            * record.quantity
            * multiplier
            * contract_size
        )
        close_commission = float(result.raw.get("commission", 0.0))
        commission = record.commission + close_commission
        spread_cost = record.spread_cost + float(result.raw.get("spread_cost", 0.0))
        slippage_cost = (
            record.slippage_cost + float(result.raw.get("slippage_cost", 0.0))
        )
        completed.append(CompletedTrade(
            ticket=ticket,
            side=record.side.name.lower(),
            opened_at=record.opened_at,
            closed_at=bar.date,
            entry_mid=record.entry_mid,
            exit_mid=bar.close,
            entry_fill=record.entry_fill,
            exit_fill=result.avg_fill_price,
            quantity=record.quantity,
            gross_pnl=gross_pnl,
            net_pnl=fill_pnl - commission,
            commission=commission,
            spread_cost=spread_cost,
            slippage_cost=slippage_cost,
            session=classify_session(record.opened_at, config.scalping),
            exit_reason=reason,
        ))
        last_signal = Signal(
            config.symbol,
            "sell" if record.side == PositionSide.LONG else "buy",
            last_signal.confidence,
            result.avg_fill_price,
            reason,
            bar.date,
        )

    for index, latest in enumerate(bars):
        window = bars[max(0, index - history_size + 1):index + 1]
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
        machine.sync(broker.get_positions(config.symbol))

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
        if index < warmup_bars:
            blockers.append("walk-forward warmup")
        confirmed, confirmation_reason = higher_timeframe_confirmation(
            [bar.close for bar in window[-25:]],
            last_signal.action,
        )
        plan = decisions.decide(
            last_signal.action,
            config.symbol,
            point_size=quote.point_size,
            now=latest.date,
            entry_block_reasons=blockers,
            higher_timeframe_confirmed=confirmed,
            higher_timeframe_reason=confirmation_reason,
        )

        for action in plan.actions:
            if action.action == PositionActionType.HOLD:
                continue
            if action.action == PositionActionType.CLOSE:
                close_ticket(action.ticket, action.reason, latest)
                continue
            side = (
                PositionSide.LONG
                if action.action == PositionActionType.OPEN_LONG
                else PositionSide.SHORT
            )
            order_side = OrderSide.BUY if side == PositionSide.LONG else OrderSide.SELL
            entry_price = quote.ask if side == PositionSide.LONG else quote.bid
            account = broker.get_account()
            quantity = decisions.entry_quantity(
                account.balance,
                account.equity,
                entry_price,
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
                stop_loss=(
                    protection["sl"] if config.scalping.stop_loss_pips > 0 else None
                ),
                take_profit=(
                    protection["tp"] if config.scalping.take_profit_pips > 0 else None
                ),
            )
            machine.record_entry_result(config.symbol, side, result)
            if (
                result.status in {OrderStatus.FILLED, OrderStatus.PARTIAL}
                and result.filled_qty > 0
            ):
                open_trades[result.order_id] = _OpenTrade(
                    ticket=result.order_id,
                    side=side,
                    opened_at=result.timestamp,
                    entry_mid=latest.close,
                    entry_fill=result.avg_fill_price,
                    quantity=result.filled_qty,
                    commission=float(result.raw.get("commission", 0.0)),
                    spread_cost=float(result.raw.get("spread_cost", 0.0)),
                    slippage_cost=float(result.raw.get("slippage_cost", 0.0)),
                )

        machine.sync(broker.get_positions(config.symbol))
        account = broker.get_account()
        equity_curve.append(EquityPoint(latest.date, account.equity, account.balance))

    if liquidate_at_end:
        latest = bars[-1]
        machine.sync(broker.get_positions(config.symbol))
        for position in list(machine.active_positions(config.symbol)):
            close_ticket(position.ticket, "end of evaluation window", latest)
        account = broker.get_account()
        equity_curve.append(EquityPoint(latest.date, account.equity, account.balance))

    account = broker.get_account()
    metrics = _performance_metrics(
        config.risk.initial_cash,
        account.equity,
        broker,
        completed,
        equity_curve,
    )
    broker.disconnect()
    return SimulationResult(
        metrics,
        tuple(completed),
        tuple(equity_curve),
        last_signal,
        costs,
        warmup_bars,
    )


def _performance_metrics(
    start_equity: float,
    end_equity: float,
    broker: PaperBroker,
    trades: list[CompletedTrade],
    equity_curve: list[EquityPoint],
) -> PerformanceMetrics:
    winning = [trade.net_pnl for trade in trades if trade.net_pnl > 0]
    losing = [trade.net_pnl for trade in trades if trade.net_pnl <= 0]
    gross_profit = sum(winning)
    gross_loss = abs(sum(losing))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else None
    sessions = tuple(
        _session_performance(name, [trade for trade in trades if trade.session == name])
        for name in ("asia", "london", "new_york", "off_session")
        if any(trade.session == name for trade in trades)
    )
    net_profit = end_equity - start_equity
    return PerformanceMetrics(
        start_equity=start_equity,
        end_equity=end_equity,
        net_profit=net_profit,
        return_pct=(net_profit / start_equity * 100) if start_equity else 0.0,
        order_count=len(broker.trade_log),
        completed_trades=len(trades),
        wins=len(winning),
        losses=len(losing),
        win_rate_pct=(len(winning) / len(trades) * 100) if trades else 0.0,
        profit_factor=profit_factor,
        average_trade=(sum(trade.net_pnl for trade in trades) / len(trades) if trades else 0.0),
        total_commission=broker.total_commission,
        total_spread_cost=broker.total_spread_cost,
        total_slippage_cost=broker.total_slippage_cost,
        total_transaction_cost=broker.total_transaction_cost,
        drawdown=analyze_drawdown(equity_curve),
        sessions=sessions,
    )


def _session_performance(
    name: str,
    trades: list[CompletedTrade],
) -> SessionPerformance:
    winning = [trade.net_pnl for trade in trades if trade.net_pnl > 0]
    losing = [trade.net_pnl for trade in trades if trade.net_pnl <= 0]
    loss_value = abs(sum(losing))
    return SessionPerformance(
        session=name,
        trades=len(trades),
        wins=len(winning),
        losses=len(losing),
        win_rate_pct=(len(winning) / len(trades) * 100) if trades else 0.0,
        net_pnl=sum(trade.net_pnl for trade in trades),
        total_cost=sum(trade.total_cost for trade in trades),
        profit_factor=(sum(winning) / loss_value if loss_value > 0 else None),
    )


def analyze_drawdown(equity_curve: list[EquityPoint]) -> DrawdownAnalysis:
    if not equity_curve:
        return DrawdownAnalysis(0.0, None, None, None, 0, 0.0)
    peak_equity = equity_curve[0].equity
    peak_index = 0
    max_drawdown = 0.0
    max_peak_index = 0
    trough_index = 0
    recovery_index: int | None = None
    underwater_start: int | None = None
    longest_start: int | None = None
    longest_end: int | None = None
    longest_bars = 0

    for index, point in enumerate(equity_curve):
        if point.equity >= peak_equity:
            peak_equity = point.equity
            peak_index = index
            if underwater_start is not None:
                duration = index - underwater_start
                if duration > longest_bars:
                    longest_bars = duration
                    longest_start, longest_end = underwater_start, index
                underwater_start = None
            if max_drawdown > 0 and recovery_index is None and index > trough_index:
                recovery_index = index
        else:
            if underwater_start is None:
                underwater_start = max(0, index - 1)
            drawdown = (peak_equity - point.equity) / peak_equity if peak_equity else 0.0
            if drawdown > max_drawdown:
                max_drawdown = drawdown
                max_peak_index = peak_index
                trough_index = index
                recovery_index = None

    if underwater_start is not None:
        duration = len(equity_curve) - 1 - underwater_start
        if duration > longest_bars:
            longest_bars = duration
            longest_start, longest_end = underwater_start, len(equity_curve) - 1

    longest_minutes = 0.0
    if longest_start is not None and longest_end is not None:
        longest_minutes = max(
            0.0,
            (equity_curve[longest_end].timestamp - equity_curve[longest_start].timestamp)
            .total_seconds() / 60.0,
        )
    return DrawdownAnalysis(
        max_drawdown_pct=max_drawdown * 100,
        peak_time=equity_curve[max_peak_index].timestamp if max_drawdown > 0 else None,
        trough_time=equity_curve[trough_index].timestamp if max_drawdown > 0 else None,
        recovery_time=(
            equity_curve[recovery_index].timestamp if recovery_index is not None else None
        ),
        max_underwater_bars=longest_bars,
        max_underwater_minutes=longest_minutes,
    )


def _serialize(value):
    if hasattr(value, "__dataclass_fields__"):
        return {key: _serialize(item) for key, item in asdict(value).items()}
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    return value

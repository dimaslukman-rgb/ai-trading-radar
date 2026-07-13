"""Walk-forward strategy selection with strictly out-of-sample evaluation."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from itertools import product
from typing import Any

from .config import BotConfig
from .models import PriceBar
from .research import (
    CompletedTrade,
    PerformanceMetrics,
    SessionPerformance,
    TransactionCostModel,
    simulate_scalping,
)


@dataclass(frozen=True)
class StrategyCandidate:
    ema_fast: int
    ema_slow: int
    min_buy_score: float
    min_sell_score: float
    stop_loss_pips: float
    take_profit_pips: float

    def __post_init__(self) -> None:
        if self.ema_fast <= 0 or self.ema_slow <= self.ema_fast:
            raise ValueError("EMA windows must satisfy 0 < fast < slow")
        if self.stop_loss_pips <= 0 or self.take_profit_pips <= 0:
            raise ValueError("SL and TP must be positive")

    @property
    def label(self) -> str:
        return (
            f"ema{self.ema_fast}-{self.ema_slow}_"
            f"score{self.min_buy_score:g}/{self.min_sell_score:g}_"
            f"sl{self.stop_loss_pips:g}_tp{self.take_profit_pips:g}"
        )

    def apply(self, config: BotConfig) -> BotConfig:
        return replace(config, scalping=replace(
            config.scalping,
            ema_fast=self.ema_fast,
            ema_slow=self.ema_slow,
            min_buy_score=self.min_buy_score,
            min_sell_score=self.min_sell_score,
            stop_loss_pips=self.stop_loss_pips,
            take_profit_pips=self.take_profit_pips,
            trailing_stop_pips=min(
                config.scalping.trailing_stop_pips,
                self.take_profit_pips,
            ),
        ))


@dataclass(frozen=True)
class WalkForwardFold:
    fold: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime
    selected: StrategyCandidate
    train_score: float
    train_metrics: PerformanceMetrics
    test_metrics: PerformanceMetrics


@dataclass(frozen=True)
class WalkForwardSummary:
    folds: int
    out_of_sample_net_profit: float
    mean_return_pct: float
    worst_drawdown_pct: float
    completed_trades: int
    wins: int
    losses: int
    win_rate_pct: float
    profit_factor: float | None
    total_transaction_cost: float
    sessions: tuple[SessionPerformance, ...]


@dataclass(frozen=True)
class WalkForwardResult:
    train_bars: int
    test_bars: int
    step_bars: int
    warmup_bars: int
    cost_model: TransactionCostModel
    candidates: tuple[StrategyCandidate, ...]
    folds: tuple[WalkForwardFold, ...]
    selection_counts: tuple[tuple[str, int], ...]
    summary: WalkForwardSummary

    def to_dict(self) -> dict[str, Any]:
        return _serialize(self)


def default_candidate_grid() -> tuple[StrategyCandidate, ...]:
    """Small, predeclared grid to limit multiple-testing and overfitting risk."""
    ema_pairs = ((3, 7), (5, 13), (9, 21))
    thresholds = ((0.05, -0.05), (0.10, -0.07))
    exits = ((20.0, 12.0), (30.0, 20.0))
    return tuple(
        StrategyCandidate(fast, slow, buy, sell, stop, take)
        for (fast, slow), (buy, sell), (stop, take)
        in product(ema_pairs, thresholds, exits)
    )


def walk_forward_optimize(
    config: BotConfig,
    bars: list[PriceBar],
    *,
    candidates: tuple[StrategyCandidate, ...] | list[StrategyCandidate] | None = None,
    train_bars: int,
    test_bars: int,
    step_bars: int | None = None,
    warmup_bars: int = 50,
    cost_model: TransactionCostModel | None = None,
    minimum_train_trades: int = 5,
) -> WalkForwardResult:
    """Optimize on each train window, then evaluate once on its unseen test window."""
    selected_candidates = tuple(candidates or default_candidate_grid())
    step = step_bars or test_bars
    costs = cost_model or TransactionCostModel(spread_points=20.0, slippage_points=2.0)
    if not selected_candidates:
        raise ValueError("at least one candidate is required")
    if train_bars < 2 or test_bars < 2 or step < 1:
        raise ValueError("train_bars/test_bars must be >=2 and step_bars >=1")
    if step < test_bars:
        raise ValueError("step_bars must be >= test_bars to avoid overlapping OOS windows")
    if train_bars + test_bars > len(bars):
        raise ValueError("not enough bars for one train/test fold")
    if any(bars[index].date > bars[index + 1].date for index in range(len(bars) - 1)):
        raise ValueError("bars must be chronological")

    folds: list[WalkForwardFold] = []
    out_of_sample_trades: list[CompletedTrade] = []
    selection_counter: Counter[str] = Counter()
    test_results: list[PerformanceMetrics] = []
    fold_number = 0
    for train_start in range(0, len(bars) - train_bars - test_bars + 1, step):
        train_end = train_start + train_bars
        test_end = train_end + test_bars
        train_window = bars[train_start:train_end]
        best_candidate: StrategyCandidate | None = None
        best_score = float("-inf")
        best_train = None
        train_warmup = min(warmup_bars, len(train_window) - 1)

        for candidate in selected_candidates:
            simulation = simulate_scalping(
                candidate.apply(config),
                train_window,
                cost_model=costs,
                warmup_bars=train_warmup,
                liquidate_at_end=True,
            )
            score = optimization_score(
                simulation.metrics,
                minimum_trades=minimum_train_trades,
            )
            if score > best_score:
                best_candidate = candidate
                best_score = score
                best_train = simulation

        if best_candidate is None or best_train is None:
            raise RuntimeError("candidate selection produced no result")

        context_start = max(0, train_end - warmup_bars)
        test_window = bars[context_start:test_end]
        test_warmup = train_end - context_start
        test_simulation = simulate_scalping(
            best_candidate.apply(config),
            test_window,
            cost_model=costs,
            warmup_bars=test_warmup,
            liquidate_at_end=True,
        )
        fold_number += 1
        folds.append(WalkForwardFold(
            fold=fold_number,
            train_start=train_window[0].date,
            train_end=train_window[-1].date,
            test_start=bars[train_end].date,
            test_end=bars[test_end - 1].date,
            selected=best_candidate,
            train_score=best_score,
            train_metrics=best_train.metrics,
            test_metrics=test_simulation.metrics,
        ))
        selection_counter[best_candidate.label] += 1
        out_of_sample_trades.extend(test_simulation.trades)
        test_results.append(test_simulation.metrics)

    return WalkForwardResult(
        train_bars=train_bars,
        test_bars=test_bars,
        step_bars=step,
        warmup_bars=warmup_bars,
        cost_model=costs,
        candidates=selected_candidates,
        folds=tuple(folds),
        selection_counts=tuple(sorted(
            selection_counter.items(),
            key=lambda item: (-item[1], item[0]),
        )),
        summary=_aggregate_summary(test_results, out_of_sample_trades),
    )


def optimization_score(
    metrics: PerformanceMetrics,
    *,
    minimum_trades: int = 5,
) -> float:
    """Risk-adjusted train-only score with a hard activity floor."""
    if metrics.completed_trades < minimum_trades:
        return -1_000_000.0 + metrics.completed_trades
    profit_factor = min(metrics.profit_factor or 0.0, 3.0)
    return (
        metrics.return_pct
        - 1.5 * metrics.drawdown.max_drawdown_pct
        + 0.05 * profit_factor
    )


def _aggregate_summary(
    metrics: list[PerformanceMetrics],
    trades: list[CompletedTrade],
) -> WalkForwardSummary:
    winning = [trade.net_pnl for trade in trades if trade.net_pnl > 0]
    losing = [trade.net_pnl for trade in trades if trade.net_pnl <= 0]
    gross_loss = abs(sum(losing))
    sessions = tuple(
        _aggregate_session(name, [trade for trade in trades if trade.session == name])
        for name in ("asia", "london", "new_york", "off_session")
        if any(trade.session == name for trade in trades)
    )
    return WalkForwardSummary(
        folds=len(metrics),
        out_of_sample_net_profit=sum(item.net_profit for item in metrics),
        mean_return_pct=(
            sum(item.return_pct for item in metrics) / len(metrics) if metrics else 0.0
        ),
        worst_drawdown_pct=max(
            (item.drawdown.max_drawdown_pct for item in metrics),
            default=0.0,
        ),
        completed_trades=len(trades),
        wins=len(winning),
        losses=len(losing),
        win_rate_pct=(len(winning) / len(trades) * 100) if trades else 0.0,
        profit_factor=(sum(winning) / gross_loss if gross_loss > 0 else None),
        total_transaction_cost=sum(item.total_transaction_cost for item in metrics),
        sessions=sessions,
    )


def _aggregate_session(name: str, trades: list[CompletedTrade]) -> SessionPerformance:
    winning = [trade.net_pnl for trade in trades if trade.net_pnl > 0]
    losing = [trade.net_pnl for trade in trades if trade.net_pnl <= 0]
    gross_loss = abs(sum(losing))
    return SessionPerformance(
        session=name,
        trades=len(trades),
        wins=len(winning),
        losses=len(losing),
        win_rate_pct=(len(winning) / len(trades) * 100) if trades else 0.0,
        net_pnl=sum(trade.net_pnl for trade in trades),
        total_cost=sum(trade.total_cost for trade in trades),
        profit_factor=(sum(winning) / gross_loss if gross_loss > 0 else None),
    )


def _serialize(value):
    if hasattr(value, "__dataclass_fields__"):
        return _serialize(asdict(value))
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _serialize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(item) for item in value]
    return value

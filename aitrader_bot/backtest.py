from __future__ import annotations

from dataclasses import dataclass

from .config import BotConfig
from .models import PriceBar, Signal
from .portfolio import Portfolio
from .risk import RiskManager
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
    from .research import simulate_scalping

    simulation = simulate_scalping(config, bars)
    metrics = simulation.metrics
    return BacktestResult(
        start_equity=metrics.start_equity,
        end_equity=metrics.end_equity,
        return_pct=metrics.return_pct,
        max_drawdown_pct=metrics.drawdown.max_drawdown_pct,
        trade_count=metrics.order_count,
        last_signal=simulation.last_signal,
    )

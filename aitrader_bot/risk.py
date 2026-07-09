from __future__ import annotations

from .config import RiskConfig
from .models import Position, Signal
from .portfolio import Portfolio


class RiskManager:
    def __init__(self, config: RiskConfig):
        self.config = config

    def buy_quantity(self, portfolio: Portfolio, signal: Signal, prices: dict[str, float]) -> float:
        if signal.price <= 0 or portfolio.cash <= self.config.min_cash:
            return 0.0
        equity = portfolio.equity(prices)
        max_position_value = equity * self.config.max_position_pct
        max_trade_value = equity * self.config.max_trade_pct
        current = portfolio.position(signal.symbol)
        current_value = current.market_value(signal.price) if current else 0.0
        available_position_value = max(0.0, max_position_value - current_value)
        budget = min(portfolio.cash - self.config.min_cash, max_trade_value, available_position_value)
        budget *= min(1.0, max(0.1, signal.confidence))
        return max(0.0, budget / signal.price)

    def sell_quantity(self, position: Position, signal: Signal) -> float:
        if signal.action == "sell":
            return position.quantity
        return 0.0

    def forced_exit_reason(self, position: Position | None, price: float) -> str | None:
        if not position:
            return None
        change = (price - position.avg_price) / position.avg_price
        if change <= -self.config.stop_loss_pct:
            return f"stop loss {change:.2%}"
        if change >= self.config.take_profit_pct:
            return f"take profit {change:.2%}"
        return None

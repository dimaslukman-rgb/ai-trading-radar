from __future__ import annotations

from .models import Position, Signal, Trade


class Portfolio:
    def __init__(self, cash: float):
        self.cash = cash
        self.positions: dict[str, Position] = {}
        self.trades: list[Trade] = []

    def equity(self, prices: dict[str, float]) -> float:
        total = self.cash
        for symbol, position in self.positions.items():
            total += position.market_value(prices.get(symbol, position.avg_price))
        return total

    def position(self, symbol: str) -> Position | None:
        return self.positions.get(symbol)

    def buy(self, signal: Signal, quantity: float, reason: str) -> Trade | None:
        cost = quantity * signal.price
        if quantity <= 0 or cost > self.cash:
            return None
        current = self.positions.get(signal.symbol)
        if current:
            total_quantity = current.quantity + quantity
            current.avg_price = ((current.avg_price * current.quantity) + cost) / total_quantity
            current.quantity = total_quantity
        else:
            self.positions[signal.symbol] = Position(signal.symbol, quantity, signal.price)
        self.cash -= cost
        trade = Trade(signal.symbol, "buy", quantity, signal.price, self.cash, signal.created_at, reason)
        self.trades.append(trade)
        return trade

    def sell(self, signal: Signal, quantity: float, reason: str) -> Trade | None:
        current = self.positions.get(signal.symbol)
        if not current or quantity <= 0:
            return None
        quantity = min(quantity, current.quantity)
        self.cash += quantity * signal.price
        current.quantity -= quantity
        if current.quantity <= 1e-12:
            del self.positions[signal.symbol]
        trade = Trade(signal.symbol, "sell", quantity, signal.price, self.cash, signal.created_at, reason)
        self.trades.append(trade)
        return trade

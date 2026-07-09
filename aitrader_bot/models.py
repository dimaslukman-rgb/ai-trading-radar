from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PriceBar:
    date: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Signal:
    symbol: str
    action: str
    confidence: float
    price: float
    reason: str
    created_at: datetime


@dataclass(frozen=True)
class Trade:
    symbol: str
    action: str
    quantity: float
    price: float
    cash_after: float
    created_at: datetime
    reason: str


@dataclass
class Position:
    symbol: str
    quantity: float
    avg_price: float

    def market_value(self, price: float) -> float:
        return self.quantity * price

    def unrealized_pnl(self, price: float) -> float:
        return (price - self.avg_price) * self.quantity

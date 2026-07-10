"""Base broker interface and shared data types for multi-exchange support."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class ExchangeType(Enum):
    """Supported exchange types in the system."""
    PAPER = "paper"
    MT5 = "mt5"            # MetaTrader 5 (Finex)
    BINANCE = "binance"    # Binance via CCXT
    ALPACA = "alpaca"      # Alpaca for US stocks


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderStatus(Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIAL = "partial"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Quote:
    """Unified market quote — normalized from any exchange."""
    symbol: str
    exchange: ExchangeType
    bid: float
    ask: float
    last: float
    volume: float
    timestamp: datetime
    raw: dict = field(default_factory=dict)  # original exchange data
    point_size: float | None = None

    @property
    def spread(self) -> float:
        return self.ask - self.bid

    @property
    def spread_pct(self) -> float:
        mid = (self.bid + self.ask) / 2
        return self.spread / mid if mid > 0 else 0.0

    @property
    def spread_points(self) -> float | None:
        """Return the spread in broker points when point size is known."""
        if self.point_size is None or self.point_size <= 0:
            return None
        return self.spread / self.point_size

    @property
    def mid(self) -> float:
        return (self.bid + self.ask) / 2


@dataclass(frozen=True)
class Candle:
    """Normalized OHLCV candle from any exchange/timeframe."""
    symbol: str
    exchange: ExchangeType
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    timeframe: str = "5m"  # e.g. "5m", "1m", "1d"


@dataclass(frozen=True)
class OrderResult:
    """Normalized order result from any exchange."""
    exchange: ExchangeType
    order_id: str
    status: OrderStatus
    symbol: str
    side: OrderSide
    quantity: float
    filled_qty: float
    price: float        # requested or filled price
    avg_fill_price: float
    message: str
    timestamp: datetime
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class PositionInfo:
    """Unified position info from any exchange."""
    symbol: str
    exchange: ExchangeType
    quantity: float
    avg_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float = 0.0
    ticket: str = ""
    side: str = ""
    opened_at: datetime | None = None
    stop_loss: float | None = None
    take_profit: float | None = None


@dataclass(frozen=True)
class AccountInfo:
    """Unified account summary."""
    exchange: ExchangeType
    balance: float
    equity: float
    margin: float = 0.0
    margin_free: float = 0.0
    leverage: int = 1
    currency: str = "USD"
    buying_power: float = 0.0


class BaseBroker(ABC):
    """Abstract broker interface — each exchange implements this."""

    @property
    @abstractmethod
    def exchange_type(self) -> ExchangeType:
        ...

    @property
    def supports_attached_protection(self) -> bool:
        """Whether entry orders can atomically attach broker-side SL/TP."""
        return False

    @abstractmethod
    def connect(self) -> bool:
        """Connect to the exchange/broker."""
        ...

    @abstractmethod
    def disconnect(self) -> None:
        """Disconnect gracefully."""
        ...

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        ...

    @abstractmethod
    def get_account(self) -> AccountInfo:
        """Get account balance, equity, margin info."""
        ...

    @abstractmethod
    def get_quote(self, symbol: str) -> Quote | None:
        """Get latest bid/ask/last quote."""
        ...

    @abstractmethod
    def fetch_candles(self, symbol: str, timeframe: str = "5m", count: int = 100) -> list[Candle]:
        """Fetch historical OHLCV candles for strategy."""
        ...

    @abstractmethod
    def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: str = "market",
        price: float | None = None,
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> OrderResult:
        """Place a trade order, optionally with attached protective prices."""
        ...

    @abstractmethod
    def get_positions(self, symbol: str | None = None) -> list[PositionInfo]:
        """Get open positions."""
        ...

    @abstractmethod
    def close_position(self, ticket: str) -> OrderResult:
        """Close a position by ticket."""
        ...

    def set_position_protection(
        self,
        ticket: str,
        stop_loss: float | None,
        take_profit: float | None,
    ) -> OrderResult:
        """Set broker-side SL/TP on an existing position."""
        now = datetime.now(timezone.utc)
        return OrderResult(
            self.exchange_type,
            "",
            OrderStatus.REJECTED,
            "",
            OrderSide.BUY,
            0.0,
            0.0,
            0.0,
            0.0,
            "position protection is not supported by this broker",
            now,
        )

    def get_symbol_map(self, internal_symbol: str) -> str:
        """Map internal symbol (e.g. BTC-USD) to broker-specific symbol (e.g. BTCUSD, BTC/USDT)."""
        return internal_symbol

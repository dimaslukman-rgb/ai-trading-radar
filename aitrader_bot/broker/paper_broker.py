"""Paper broker — in-memory simulation for testing. Supports multi-asset."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from .base import (
    AccountInfo,
    BaseBroker,
    Candle,
    ExchangeType,
    OrderResult,
    OrderSide,
    OrderStatus,
    PositionInfo,
    Quote,
)


class PaperBroker(BaseBroker):
    """In-memory simulated broker for testing scalping strategies."""

    def __init__(self, initial_cash: float = 10000.0):
        self._cash = initial_cash
        self._positions: dict[str, PositionInfo] = {}
        self._connected = False
        self._last_price: dict[str, float] = {}
        self._last_volume: dict[str, float] = {}
        self._trade_log: list[OrderResult] = []
        self._candle_history: dict[str, list[Candle]] = {}

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def exchange_type(self) -> ExchangeType:
        return ExchangeType.PAPER

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ── Connection ─────────────────────────────────────────────────────

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    # ── Account ────────────────────────────────────────────────────────

    def get_account(self) -> AccountInfo:
        equity = self._cash + sum(
            pos.quantity * self._last_price.get(pos.symbol, pos.avg_price)
            for pos in self._positions.values()
        )
        return AccountInfo(
            exchange=ExchangeType.PAPER,
            balance=round(self._cash, 2),
            equity=round(equity, 2),
            margin=0.0,
            margin_free=round(equity, 2),
            leverage=1,
            currency="USD",
            buying_power=round(self._cash, 2),
        )

    # ── Price management ───────────────────────────────────────────────

    def update_price(self, symbol: str, price: float, volume: float = 1000.0) -> None:
        """Push a new price (used by backtest / live feed)."""
        self._last_price[symbol] = price
        self._last_volume[symbol] = volume

    def update_candles(self, symbol: str, candles: list[Candle]) -> None:
        """Store candle history and update latest price."""
        self._candle_history[symbol] = candles
        if candles:
            self._last_price[symbol] = candles[-1].close
            self._last_volume[symbol] = candles[-1].volume

    # ── Quote ─────────────────────────────────────────────────────────

    def get_quote(self, symbol: str) -> Quote | None:
        price = self._last_price.get(symbol)
        if price is None:
            return None
        return Quote(
            symbol=symbol,
            exchange=ExchangeType.PAPER,
            bid=price * 0.9995,
            ask=price * 1.0005,
            last=price,
            volume=self._last_volume.get(symbol, 1000),
            timestamp=datetime.now(timezone.utc),
        )

    # ── Candles ────────────────────────────────────────────────────────

    def fetch_candles(self, symbol: str, timeframe: str = "5m", count: int = 100) -> list[Candle]:
        candles = self._candle_history.get(symbol, [])
        return candles[-count:] if candles else []

    # ── Orders ─────────────────────────────────────────────────────────

    def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: str = "market",
        price: float | None = None,
    ) -> OrderResult:
        now = datetime.now(timezone.utc)
        fill_price = price or self._last_price.get(symbol)
        if fill_price is None or fill_price <= 0:
            return OrderResult(
                ExchangeType.PAPER, "", OrderStatus.REJECTED,
                symbol, side, quantity, 0.0, 0.0, 0.0,
                f"no price for {symbol}", now,
            )

        if side == OrderSide.BUY:
            cost = quantity * fill_price
            if cost > self._cash:
                return OrderResult(
                    ExchangeType.PAPER, "", OrderStatus.REJECTED,
                    symbol, side, quantity, 0.0, 0.0, 0.0,
                    "insufficient cash", now,
                )

            # Add or increase position
            existing = self._positions.get(symbol)
            if existing:
                new_qty = existing.quantity + quantity
                new_avg = ((existing.avg_price * existing.quantity) + cost) / new_qty
                self._positions[symbol] = PositionInfo(
                    symbol=symbol,
                    exchange=ExchangeType.PAPER,
                    quantity=new_qty,
                    avg_price=new_avg,
                    current_price=fill_price,
                    unrealized_pnl=0.0,
                    ticket=str(uuid.uuid4()),
                )
            else:
                self._positions[symbol] = PositionInfo(
                    symbol=symbol,
                    exchange=ExchangeType.PAPER,
                    quantity=quantity,
                    avg_price=fill_price,
                    current_price=fill_price,
                    unrealized_pnl=0.0,
                    ticket=str(uuid.uuid4()),
                )
            self._cash -= cost

        else:  # SELL
            existing = self._positions.get(symbol)
            if not existing:
                return OrderResult(
                    ExchangeType.PAPER, "", OrderStatus.REJECTED,
                    symbol, side, quantity, 0.0, 0.0, 0.0,
                    "no position to sell", now,
                )
            qty = min(quantity, existing.quantity)
            pnl = qty * (fill_price - existing.avg_price)
            self._cash += qty * fill_price
            remaining = existing.quantity - qty
            if remaining <= 1e-12:
                del self._positions[symbol]
            else:
                self._positions[symbol] = PositionInfo(
                    symbol=symbol,
                    exchange=ExchangeType.PAPER,
                    quantity=remaining,
                    avg_price=existing.avg_price,
                    current_price=fill_price,
                    unrealized_pnl=pnl,
                    ticket=existing.ticket,
                )

        order_id = str(uuid.uuid4())[:8]
        result = OrderResult(
            exchange=ExchangeType.PAPER,
            order_id=order_id,
            status=OrderStatus.FILLED,
            symbol=symbol,
            side=side,
            quantity=quantity,
            filled_qty=quantity,
            price=fill_price,
            avg_fill_price=fill_price,
            message=f"{side.value} {quantity:.4f} {symbol} @ {fill_price}",
            timestamp=now,
        )
        self._trade_log.append(result)
        return result

    # ── Positions ──────────────────────────────────────────────────────

    def get_positions(self, symbol: str | None = None) -> list[PositionInfo]:
        if symbol:
            pos = self._positions.get(symbol)
            result = []
            if pos:
                cur = self._last_price.get(symbol, pos.avg_price)
                result.append(PositionInfo(
                    symbol=pos.symbol,
                    exchange=ExchangeType.PAPER,
                    quantity=pos.quantity,
                    avg_price=pos.avg_price,
                    current_price=cur,
                    unrealized_pnl=(cur - pos.avg_price) * pos.quantity,
                    ticket=pos.ticket,
                ))
            return result

        result = []
        for sym, pos in self._positions.items():
            cur = self._last_price.get(sym, pos.avg_price)
            result.append(PositionInfo(
                symbol=sym,
                exchange=ExchangeType.PAPER,
                quantity=pos.quantity,
                avg_price=pos.avg_price,
                current_price=cur,
                unrealized_pnl=(cur - pos.avg_price) * pos.quantity,
                ticket=pos.ticket,
            ))
        return result

    def close_position(self, ticket: str) -> OrderResult:
        for sym, pos in list(self._positions.items()):
            if pos.ticket == ticket:
                price = self._last_price.get(sym, pos.avg_price)
                return self.place_order(sym, OrderSide.SELL, pos.quantity, price=price)
        now = datetime.now(timezone.utc)
        return OrderResult(
            ExchangeType.PAPER, "", OrderStatus.REJECTED,
            "", OrderSide.SELL, 0, 0.0, 0.0, 0.0,
            f"ticket {ticket} not found", now,
        )

    @property
    def cash(self) -> float:
        return self._cash

    @property
    def trade_log(self) -> list[OrderResult]:
        return list(self._trade_log)

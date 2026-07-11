"""Deterministic broker test double used by integration tests."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from aitrader_bot.broker.base import (
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


class FakeBroker(BaseBroker):
    """In-memory fake with controllable next order and close statuses."""

    def __init__(self, balance: float = 10000.0) -> None:
        self.balance = balance
        self._connected = False
        self._quote: Quote | None = None
        self._candles: list[Candle] = []
        self._positions: dict[str, PositionInfo] = {}
        self._sequence = 0
        self.next_order_status = OrderStatus.FILLED
        self.next_close_status = OrderStatus.FILLED
        self.order_requests: list[dict] = []
        self.close_requests: list[str] = []

    @property
    def exchange_type(self) -> ExchangeType:
        return ExchangeType.PAPER

    @property
    def supports_attached_protection(self) -> bool:
        return True

    @property
    def supports_short_positions(self) -> bool:
        return True

    @property
    def supports_multiple_positions(self) -> bool:
        return True

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def set_quote(self, symbol: str, price: float, *, spread: float = 0.1) -> None:
        now = datetime.now(timezone.utc)
        self._quote = Quote(
            symbol,
            ExchangeType.PAPER,
            price - spread / 2,
            price + spread / 2,
            price,
            1000.0,
            now,
            point_size=0.01,
        )

    def set_candles(self, candles: list[Candle]) -> None:
        self._candles = list(candles)

    def get_account(self) -> AccountInfo:
        equity = self.balance + sum(
            position.unrealized_pnl for position in self.get_positions()
        )
        return AccountInfo(
            ExchangeType.PAPER,
            self.balance,
            equity,
            buying_power=self.balance,
        )

    def get_quote(self, symbol: str) -> Quote | None:
        if self._quote is None or self._quote.symbol != symbol:
            return None
        return self._quote

    def fetch_candles(
        self,
        symbol: str,
        timeframe: str = "5m",
        count: int = 100,
    ) -> list[Candle]:
        return [
            candle for candle in self._candles
            if candle.symbol == symbol and candle.timeframe == timeframe
        ][-count:]

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
        del order_type
        self._sequence += 1
        ticket = f"fake-{self._sequence}"
        quote = self._require_quote(symbol)
        fill_price = price or (quote.ask if side == OrderSide.BUY else quote.bid)
        status = self.next_order_status
        self.next_order_status = OrderStatus.FILLED
        filled = (
            quantity if status == OrderStatus.FILLED
            else quantity / 2 if status == OrderStatus.PARTIAL
            else 0.0
        )
        self.order_requests.append({
            "symbol": symbol,
            "side": side,
            "quantity": quantity,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
        })
        now = datetime.now(timezone.utc)
        if filled > 0:
            side_value = "buy" if side == OrderSide.BUY else "sell"
            self._positions[ticket] = PositionInfo(
                symbol,
                ExchangeType.PAPER,
                filled,
                fill_price,
                fill_price,
                0.0,
                ticket=ticket,
                side=side_value,
                opened_at=now,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
        return OrderResult(
            ExchangeType.PAPER,
            ticket,
            status,
            symbol,
            side,
            quantity,
            filled,
            fill_price,
            fill_price if filled else 0.0,
            f"fake {status.value}",
            now,
        )

    def get_positions(self, symbol: str | None = None) -> list[PositionInfo]:
        positions: list[PositionInfo] = []
        for ticket, position in self._positions.items():
            if symbol is not None and position.symbol != symbol:
                continue
            quote = self._require_quote(position.symbol)
            current = quote.bid if position.side == "buy" else quote.ask
            difference = (
                current - position.avg_price
                if position.side == "buy"
                else position.avg_price - current
            )
            updated = replace(
                position,
                current_price=current,
                unrealized_pnl=difference * position.quantity * 100,
                ticket=ticket,
            )
            positions.append(updated)
        return positions

    def close_position(self, ticket: str) -> OrderResult:
        self.close_requests.append(ticket)
        position = self._positions.get(ticket)
        now = datetime.now(timezone.utc)
        if position is None:
            return OrderResult(
                ExchangeType.PAPER,
                ticket,
                OrderStatus.REJECTED,
                "",
                OrderSide.SELL,
                0.0,
                0.0,
                0.0,
                0.0,
                "position not found",
                now,
            )
        status = self.next_close_status
        self.next_close_status = OrderStatus.FILLED
        filled = (
            position.quantity if status == OrderStatus.FILLED
            else position.quantity / 2 if status == OrderStatus.PARTIAL
            else 0.0
        )
        quote = self._require_quote(position.symbol)
        close_side = OrderSide.SELL if position.side == "buy" else OrderSide.BUY
        fill_price = quote.bid if position.side == "buy" else quote.ask
        if status == OrderStatus.FILLED:
            del self._positions[ticket]
        elif status == OrderStatus.PARTIAL:
            self._positions[ticket] = replace(
                position,
                quantity=position.quantity - filled,
            )
        return OrderResult(
            ExchangeType.PAPER,
            ticket,
            status,
            position.symbol,
            close_side,
            position.quantity,
            filled,
            fill_price,
            fill_price if filled else 0.0,
            f"fake close {status.value}",
            now,
        )

    def set_position_protection(
        self,
        ticket: str,
        stop_loss: float | None,
        take_profit: float | None,
    ) -> OrderResult:
        position = self._positions.get(ticket)
        if position is None:
            return super().set_position_protection(ticket, stop_loss, take_profit)
        self._positions[ticket] = replace(
            position,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        now = datetime.now(timezone.utc)
        return OrderResult(
            ExchangeType.PAPER,
            ticket,
            OrderStatus.FILLED,
            position.symbol,
            OrderSide.BUY if position.side == "buy" else OrderSide.SELL,
            position.quantity,
            position.quantity,
            position.current_price,
            position.current_price,
            "protection updated",
            now,
        )

    def _require_quote(self, symbol: str) -> Quote:
        quote = self.get_quote(symbol)
        if quote is None:
            raise RuntimeError(f"quote unavailable for {symbol}")
        return quote

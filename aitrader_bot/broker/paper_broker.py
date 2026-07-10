"""Paper broker — in-memory simulation for testing. Supports multi-asset."""

from __future__ import annotations

import uuid
from dataclasses import replace
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

    def __init__(
        self,
        initial_cash: float = 10000.0,
        point_size: float = 0.01,
        spread_points: float = 10.0,
    ):
        self._cash = initial_cash
        self._point_size = point_size
        self._spread_points = spread_points
        self._positions: dict[str, PositionInfo] = {}
        self._connected = False
        self._last_price: dict[str, float] = {}
        self._last_volume: dict[str, float] = {}
        self._trade_log: list[OrderResult] = []
        self._candle_history: dict[str, list[Candle]] = {}
        self._current_time: datetime | None = None

    # ── Properties ─────────────────────────────────────────────────────

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
        equity = self._cash
        for pos in self._positions.values():
            current = self._last_price.get(pos.symbol, pos.avg_price)
            market_value = pos.quantity * current
            equity += market_value if pos.side != "sell" else -market_value
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

    def update_price(
        self,
        symbol: str,
        price: float,
        volume: float = 1000.0,
        timestamp: datetime | None = None,
    ) -> None:
        """Push a new price (used by backtest / live feed)."""
        self._last_price[symbol] = price
        self._last_volume[symbol] = volume
        if timestamp is not None:
            self._current_time = timestamp

    def update_candles(self, symbol: str, candles: list[Candle]) -> None:
        """Store candle history and update latest price."""
        self._candle_history[symbol] = candles
        if candles:
            self._last_price[symbol] = candles[-1].close
            self._last_volume[symbol] = candles[-1].volume
            self._current_time = candles[-1].timestamp

    # ── Quote ─────────────────────────────────────────────────────────

    def get_quote(self, symbol: str) -> Quote | None:
        price = self._last_price.get(symbol)
        if price is None:
            return None
        half_spread = self._spread_points * self._point_size / 2
        return Quote(
            symbol=symbol,
            exchange=ExchangeType.PAPER,
            bid=price - half_spread,
            ask=price + half_spread,
            last=price,
            volume=self._last_volume.get(symbol, 1000),
            timestamp=self._now(),
            point_size=self._point_size,
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
        stop_loss: float | None = None,
        take_profit: float | None = None,
    ) -> OrderResult:
        now = self._now()
        fill_price = price
        if fill_price is None:
            market_price = self._last_price.get(symbol)
            if market_price is not None:
                half_spread = self._spread_points * self._point_size / 2
                fill_price = (
                    market_price + half_spread
                    if side == OrderSide.BUY
                    else market_price - half_spread
                )
        if fill_price is None or fill_price <= 0:
            return OrderResult(
                ExchangeType.PAPER, "", OrderStatus.REJECTED,
                symbol, side, quantity, 0.0, 0.0, 0.0,
                f"no price for {symbol}", now,
            )
        if quantity <= 0:
            return OrderResult(
                ExchangeType.PAPER, "", OrderStatus.REJECTED,
                symbol, side, quantity, 0.0, fill_price, 0.0,
                "quantity must be positive", now,
            )

        if side == OrderSide.BUY:
            if stop_loss is not None and stop_loss >= fill_price:
                return OrderResult(
                    ExchangeType.PAPER, "", OrderStatus.REJECTED,
                    symbol, side, quantity, 0.0, 0.0, 0.0,
                    "buy stop loss must be below entry price", now,
                )
            if take_profit is not None and take_profit <= fill_price:
                return OrderResult(
                    ExchangeType.PAPER, "", OrderStatus.REJECTED,
                    symbol, side, quantity, 0.0, 0.0, 0.0,
                    "buy take profit must be above entry price", now,
                )
        else:
            if stop_loss is not None and stop_loss <= fill_price:
                return OrderResult(
                    ExchangeType.PAPER, "", OrderStatus.REJECTED,
                    symbol, side, quantity, 0.0, 0.0, 0.0,
                    "sell stop loss must be above entry price", now,
                )
            if take_profit is not None and take_profit >= fill_price:
                return OrderResult(
                    ExchangeType.PAPER, "", OrderStatus.REJECTED,
                    symbol, side, quantity, 0.0, 0.0, 0.0,
                    "sell take profit must be below entry price", now,
                )

        notional = quantity * fill_price
        account_equity = max(0.0, self.get_account().equity)
        available = min(self._cash, account_equity) if side == OrderSide.BUY else account_equity
        if notional > max(0.0, available):
            return OrderResult(
                ExchangeType.PAPER, "", OrderStatus.REJECTED,
                symbol, side, quantity, 0.0, 0.0, 0.0,
                "insufficient equity", now,
            )

        ticket = str(uuid.uuid4())
        side_value = "buy" if side == OrderSide.BUY else "sell"
        self._positions[ticket] = PositionInfo(
            symbol=symbol,
            exchange=ExchangeType.PAPER,
            quantity=quantity,
            avg_price=fill_price,
            current_price=fill_price,
            unrealized_pnl=0.0,
            ticket=ticket,
            side=side_value,
            opened_at=now,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        if side == OrderSide.BUY:
            self._cash -= notional
        else:
            self._cash += notional

        result = OrderResult(
            exchange=ExchangeType.PAPER,
            order_id=ticket,
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
        result = []
        for pos in self._positions.values():
            if symbol is not None and pos.symbol != symbol:
                continue
            cur = self._last_price.get(pos.symbol, pos.avg_price)
            price_diff = cur - pos.avg_price
            if pos.side == "sell":
                price_diff *= -1
            result.append(PositionInfo(
                symbol=pos.symbol,
                exchange=ExchangeType.PAPER,
                quantity=pos.quantity,
                avg_price=pos.avg_price,
                current_price=cur,
                unrealized_pnl=price_diff * pos.quantity,
                ticket=pos.ticket,
                side=pos.side,
                opened_at=pos.opened_at,
                stop_loss=pos.stop_loss,
                take_profit=pos.take_profit,
            ))
        return result

    def close_position(self, ticket: str) -> OrderResult:
        now = self._now()
        pos = self._positions.get(ticket)
        if pos is not None:
            market_price = self._last_price.get(pos.symbol, pos.avg_price)
            half_spread = self._spread_points * self._point_size / 2
            price = (
                market_price + half_spread
                if pos.side == "sell"
                else market_price - half_spread
            )
            close_side = OrderSide.SELL if pos.side != "sell" else OrderSide.BUY
            if pos.side == "sell":
                self._cash -= pos.quantity * price
            else:
                self._cash += pos.quantity * price
            del self._positions[ticket]
            result = OrderResult(
                ExchangeType.PAPER,
                str(uuid.uuid4()),
                OrderStatus.FILLED,
                pos.symbol,
                close_side,
                pos.quantity,
                pos.quantity,
                price,
                price,
                f"close {pos.side} {pos.quantity:.4f} {pos.symbol} @ {price}",
                now,
            )
            self._trade_log.append(result)
            return result
        return OrderResult(
            ExchangeType.PAPER, "", OrderStatus.REJECTED,
            "", OrderSide.SELL, 0, 0.0, 0.0, 0.0,
            f"ticket {ticket} not found", now,
        )

    def set_position_protection(
        self,
        ticket: str,
        stop_loss: float | None,
        take_profit: float | None,
    ) -> OrderResult:
        now = self._now()
        position = self._positions.get(ticket)
        if position is not None:
            current_price = self._last_price.get(position.symbol, position.current_price)
            if position.side in ("", "buy"):
                if stop_loss is not None and stop_loss >= current_price:
                    return OrderResult(
                        ExchangeType.PAPER, "", OrderStatus.REJECTED,
                        position.symbol, OrderSide.BUY, position.quantity, 0.0, 0.0, 0.0,
                        "buy stop loss must be below current price", now,
                    )
                if take_profit is not None and take_profit <= current_price:
                    return OrderResult(
                        ExchangeType.PAPER, "", OrderStatus.REJECTED,
                        position.symbol, OrderSide.BUY, position.quantity, 0.0, 0.0, 0.0,
                        "buy take profit must be above current price", now,
                    )
            else:
                if stop_loss is not None and stop_loss <= current_price:
                    return OrderResult(
                        ExchangeType.PAPER, "", OrderStatus.REJECTED,
                        position.symbol, OrderSide.SELL, position.quantity, 0.0, 0.0, 0.0,
                        "sell stop loss must be above current price", now,
                    )
                if take_profit is not None and take_profit >= current_price:
                    return OrderResult(
                        ExchangeType.PAPER, "", OrderStatus.REJECTED,
                        position.symbol, OrderSide.SELL, position.quantity, 0.0, 0.0, 0.0,
                        "sell take profit must be below current price", now,
                    )
            self._positions[ticket] = replace(
                position,
                current_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
            return OrderResult(
                ExchangeType.PAPER,
                ticket,
                OrderStatus.FILLED,
                position.symbol,
                OrderSide.BUY if position.side in ("", "buy") else OrderSide.SELL,
                position.quantity,
                position.quantity,
                current_price,
                current_price,
                "position protection updated",
                now,
            )
        return OrderResult(
            ExchangeType.PAPER, "", OrderStatus.REJECTED,
            "", OrderSide.BUY, 0.0, 0.0, 0.0, 0.0,
            f"ticket {ticket} not found", now,
        )

    @property
    def cash(self) -> float:
        return self._cash

    def _now(self) -> datetime:
        return self._current_time or datetime.now(timezone.utc)

    @property
    def trade_log(self) -> list[OrderResult]:
        return list(self._trade_log)

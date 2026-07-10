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

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def exchange_type(self) -> ExchangeType:
        return ExchangeType.PAPER

    @property
    def supports_attached_protection(self) -> bool:
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
        half_spread = self._spread_points * self._point_size / 2
        return Quote(
            symbol=symbol,
            exchange=ExchangeType.PAPER,
            bid=price - half_spread,
            ask=price + half_spread,
            last=price,
            volume=self._last_volume.get(symbol, 1000),
            timestamp=datetime.now(timezone.utc),
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
        now = datetime.now(timezone.utc)
        fill_price = price or self._last_price.get(symbol)
        if fill_price is None or fill_price <= 0:
            return OrderResult(
                ExchangeType.PAPER, "", OrderStatus.REJECTED,
                symbol, side, quantity, 0.0, 0.0, 0.0,
                f"no price for {symbol}", now,
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
                    ticket=existing.ticket,
                    side=existing.side or "buy",
                    opened_at=existing.opened_at or now,
                    stop_loss=stop_loss if stop_loss is not None else existing.stop_loss,
                    take_profit=take_profit if take_profit is not None else existing.take_profit,
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
                    side="buy",
                    opened_at=now,
                    stop_loss=stop_loss,
                    take_profit=take_profit,
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
                    side=existing.side,
                    opened_at=existing.opened_at,
                    stop_loss=existing.stop_loss,
                    take_profit=existing.take_profit,
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
                    side=pos.side,
                    opened_at=pos.opened_at,
                    stop_loss=pos.stop_loss,
                    take_profit=pos.take_profit,
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
                side=pos.side,
                opened_at=pos.opened_at,
                stop_loss=pos.stop_loss,
                take_profit=pos.take_profit,
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

    def set_position_protection(
        self,
        ticket: str,
        stop_loss: float | None,
        take_profit: float | None,
    ) -> OrderResult:
        now = datetime.now(timezone.utc)
        for symbol, position in self._positions.items():
            if position.ticket != ticket:
                continue
            current_price = self._last_price.get(symbol, position.current_price)
            if position.side in ("", "buy"):
                if stop_loss is not None and stop_loss >= current_price:
                    return OrderResult(
                        ExchangeType.PAPER, "", OrderStatus.REJECTED,
                        symbol, OrderSide.BUY, position.quantity, 0.0, 0.0, 0.0,
                        "buy stop loss must be below current price", now,
                    )
                if take_profit is not None and take_profit <= current_price:
                    return OrderResult(
                        ExchangeType.PAPER, "", OrderStatus.REJECTED,
                        symbol, OrderSide.BUY, position.quantity, 0.0, 0.0, 0.0,
                        "buy take profit must be above current price", now,
                    )
            self._positions[symbol] = replace(
                position,
                current_price=current_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
            return OrderResult(
                ExchangeType.PAPER,
                ticket,
                OrderStatus.FILLED,
                symbol,
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

    @property
    def trade_log(self) -> list[OrderResult]:
        return list(self._trade_log)

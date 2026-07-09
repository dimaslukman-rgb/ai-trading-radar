"""MT5 broker — connects to MetaTrader 5 terminal for Finex integration.

PT Finex Bisnis Solusi Futures — Indonesian futures broker (BAPPEBTI).
Uses MetaTrader 5 standard. No custom API.

Key MT5 best practices implemented:
  - order_check() BEFORE order_send()
  - filling_mode detection via symbol_info().filling_mode bitmask
  - symbol_select() to enable symbols
  - Single initialize() / shutdown() lifecycle
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

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

# Timeframe constants
TIMEFRAMES = {
    "1m": 1,       # PERIOD_M1
    "5m": 5,       # PERIOD_M5
    "15m": 15,     # PERIOD_M15
    "1h": 60,      # PERIOD_H1
    "4h": 240,     # PERIOD_H4
    "1d": 1440,    # PERIOD_D1
}


class Mt5Broker(BaseBroker):
    """MetaTrader 5 broker — compatible with Finex and other MT5 brokers."""

    SYMBOL_MAP: dict[str, str] = {
        "BTC-USD": "BTCUSD",
        "ETH-USD": "ETHUSD",
        "XAU-USD": "XAUUSD",
        "XAUUSD": "XAUUSD",
    }

    def __init__(self, server: str = "", login: int | None = None, password: str = ""):
        self._server = server
        self._login = login
        self._password = password
        self._connected = False
        self._mt5 = None

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def exchange_type(self) -> ExchangeType:
        return ExchangeType.MT5

    @property
    def is_connected(self) -> bool:
        return self._connected and self._mt5 is not None

    # ── Connection ─────────────────────────────────────────────────────

    def connect(self) -> bool:
        try:
            import MetaTrader5 as mt5
            self._mt5 = mt5
        except ImportError:
            raise ImportError(
                "MetaTrader5 tidak terinstall. Jalankan: pip install MetaTrader5"
            )

        if not self._mt5.initialize():
            err = self._mt5.last_error()
            raise ConnectionError(f"MT5 initialize gagal: {err}")

        if self._login is not None:
            authorized = self._mt5.login(
                self._login, password=self._password, server=self._server,
            )
            if not authorized:
                err = self._mt5.last_error()
                raise PermissionError(f"MT5 login gagal: {err}")

        self._connected = True
        return True

    def disconnect(self) -> None:
        if self._mt5:
            try:
                self._mt5.shutdown()
            except Exception:
                pass
        self._connected = False

    # ── Symbol mapping ─────────────────────────────────────────────────

    def get_symbol_map(self, internal_symbol: str) -> str:
        return self.SYMBOL_MAP.get(internal_symbol, internal_symbol)

    def _select_symbol(self, symbol: str) -> bool:
        """Enable symbol in MT5 Market Watch."""
        if not self._mt5:
            return False
        return self._mt5.symbol_select(symbol, True)

    # ── Account ────────────────────────────────────────────────────────

    def get_account(self) -> AccountInfo:
        self._ensure_connected()
        info = self._mt5.account_info()
        if info is None:
            raise RuntimeError(f"Gagal get account: {self._mt5.last_error()}")
        return AccountInfo(
            exchange=ExchangeType.MT5,
            balance=info.balance,
            equity=info.equity,
            margin=info.margin,
            margin_free=info.margin_free,
            leverage=info.leverage,
            currency=info.currency,
            buying_power=info.margin_free,
        )

    # ── Quote ──────────────────────────────────────────────────────────

    def get_quote(self, symbol: str) -> Quote | None:
        self._ensure_connected()
        mapped = self.get_symbol_map(symbol)
        self._select_symbol(mapped)
        tick = self._mt5.symbol_info_tick(mapped)
        if tick is None:
            return None
        return Quote(
            symbol=mapped,
            exchange=ExchangeType.MT5,
            bid=tick.bid,
            ask=tick.ask,
            last=(tick.bid + tick.ask) / 2,
            volume=float(tick.volume or 0),
            timestamp=datetime.fromtimestamp(tick.time, tz=timezone.utc),
            raw={"bid": tick.bid, "ask": tick.ask, "time": tick.time},
        )

    # ── Candles ────────────────────────────────────────────────────────

    def fetch_candles(self, symbol: str, timeframe: str = "5m", count: int = 100) -> list[Candle]:
        self._ensure_connected()
        mapped = self.get_symbol_map(symbol)
        self._select_symbol(mapped)

        mt5_tf = TIMEFRAMES.get(timeframe, 5)
        from datetime import timedelta

        # Fetch from now backward
        rates = self._mt5.copy_rates_from_pos(mapped, mt5_tf, 0, count)
        if rates is None:
            raise RuntimeError(f"Gagal fetch candles {mapped}: {self._mt5.last_error()}")

        candles: list[Candle] = []
        for r in rates:
            candles.append(Candle(
                symbol=mapped,
                exchange=ExchangeType.MT5,
                timestamp=datetime.fromtimestamp(r["time"], tz=timezone.utc),
                open=float(r["open"]),
                high=float(r["high"]),
                low=float(r["low"]),
                close=float(r["close"]),
                volume=float(r["tick_volume"] or 0),
                timeframe=timeframe,
            ))
        return candles

    # ── Orders ─────────────────────────────────────────────────────────

    def _detect_filling_mode(self, symbol: str) -> int:
        """Detect the best filling mode for a symbol.

        Uses getattr with hardcoded fallbacks for MT5 constants that
        may not be exported in all MetaTrader5 Python package versions.

        MT5 filling mode bitmask values:
          FOK (Fill or Kill)   = 1
          IOC (Immediate/Cancel)= 2
          RETURN                = 4
        """
        mt5 = self._mt5

        # Safe constant access with fallback to MT5 standard values
        SYMBOL_FILLING_FOK = getattr(mt5, "SYMBOL_FILLING_FOK", 1)
        SYMBOL_FILLING_IOC = getattr(mt5, "SYMBOL_FILLING_IOC", 2)
        SYMBOL_FILLING_RETURN = getattr(mt5, "SYMBOL_FILLING_RETURN", 4)
        ORDER_FILLING_FOK = getattr(mt5, "ORDER_FILLING_FOK", 0)
        ORDER_FILLING_IOC = getattr(mt5, "ORDER_FILLING_IOC", 1)
        ORDER_FILLING_RETURN = getattr(mt5, "ORDER_FILLING_RETURN", 2)

        info = mt5.symbol_info(symbol)
        if info is None:
            return ORDER_FILLING_IOC

        fm = info.filling_mode
        if fm & SYMBOL_FILLING_FOK:
            return ORDER_FILLING_FOK
        elif fm & SYMBOL_FILLING_IOC:
            return ORDER_FILLING_IOC
        elif fm & SYMBOL_FILLING_RETURN:
            return ORDER_FILLING_RETURN
        return ORDER_FILLING_IOC

    def _normalize_volume(self, symbol: str, quantity: float) -> float:
        """Normalize lot volume to MT5 symbol requirements (min, max, step)."""
        if not self._mt5:
            return round(quantity, 2)
        info = self._mt5.symbol_info(symbol)
        if info is None:
            return round(quantity, 2)
        vol_min = info.volume_min or 0.01
        vol_max = info.volume_max or 999.0
        vol_step = info.volume_step or 0.01
        # Round to nearest valid step
        quantity = round(quantity / vol_step) * vol_step
        # Clamp to min/max
        quantity = max(vol_min, min(vol_max, quantity))
        # Round to 2 decimal places for safety
        return round(quantity, 2)

    def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: str = "market",
        price: float | None = None,
    ) -> OrderResult:
        self._ensure_connected()
        mapped = self.get_symbol_map(symbol)
        self._select_symbol(mapped)
        now = datetime.now(timezone.utc)

        # Normalize volume to MT5 requirements
        quantity = self._normalize_volume(mapped, quantity)

        # Get current price
        tick = self._mt5.symbol_info_tick(mapped)
        if tick is None:
            return OrderResult(
                ExchangeType.MT5, "", OrderStatus.REJECTED,
                mapped, side, quantity, 0.0, 0.0, 0.0,
                f"no tick for {mapped}", now,
            )
        if quantity <= 0:
            return OrderResult(
                ExchangeType.MT5, "", OrderStatus.REJECTED,
                mapped, side, quantity, 0.0, 0.0, 0.0,
                f"invalid volume {quantity} after normalization", now,
            )

        # Determine order type and price
        if order_type == "market":
            mt5_type = (
                self._mt5.ORDER_TYPE_BUY if side == OrderSide.BUY
                else self._mt5.ORDER_TYPE_SELL
            )
            order_price = tick.ask if side == OrderSide.BUY else tick.bid
        else:
            mt5_type = (
                self._mt5.ORDER_TYPE_BUY_LIMIT if side == OrderSide.BUY
                else self._mt5.ORDER_TYPE_SELL_LIMIT
            )
            order_price = price or (tick.ask if side == OrderSide.BUY else tick.bid)

        # Detect filling mode
        fill_mode = self._detect_filling_mode(mapped)

        # Build request with normalized volume
        request = {
            "action": self._mt5.TRADE_ACTION_DEAL,
            "symbol": mapped,
            "volume": quantity,
            "type": mt5_type,
            "price": order_price,
            "deviation": 20,
            "magic": 123456,
            "comment": "ai-scalping-bot",
            "type_time": self._mt5.ORDER_TIME_GTC,
            "type_filling": fill_mode,
        }

        # STEP 1: order_check — validate BEFORE sending
        check = self._mt5.order_check(request)
        if check.retcode != 0:
            return OrderResult(
                ExchangeType.MT5, "", OrderStatus.REJECTED,
                mapped, side, quantity, 0.0, 0.0, 0.0,
                f"order_check gagal (code {check.retcode}): {check.comment}",
                now,
            )

        # STEP 2: order_send — execute
        result = self._mt5.order_send(request)
        if result.retcode != self._mt5.TRADE_RETCODE_DONE:
            return OrderResult(
                ExchangeType.MT5, "", OrderStatus.REJECTED,
                mapped, side, quantity, 0.0, 0.0, 0.0,
                f"order gagal (code {result.retcode})",
                now,
            )

        return OrderResult(
            exchange=ExchangeType.MT5,
            order_id=str(result.order),
            status=OrderStatus.FILLED,
            symbol=mapped,
            side=side,
            quantity=quantity,
            filled_qty=float(result.volume or quantity),
            price=order_price,
            avg_fill_price=float(result.price or order_price),
            message=f"{side.value} {quantity} {mapped} @ {order_price}",
            timestamp=now,
        )

    # ── Positions ──────────────────────────────────────────────────────

    def get_positions(self, symbol: str | None = None) -> list[PositionInfo]:
        self._ensure_connected()
        if symbol:
            mapped = self.get_symbol_map(symbol)
            positions = self._mt5.positions_get(symbol=mapped)
        else:
            positions = self._mt5.positions_get()

        if positions is None:
            return []

        result: list[PositionInfo] = []
        for pos in positions:
            result.append(PositionInfo(
                symbol=pos.symbol,
                exchange=ExchangeType.MT5,
                quantity=float(pos.volume),
                avg_price=float(pos.price_open),
                current_price=float(pos.price_current),
                unrealized_pnl=float(pos.profit),
                ticket=str(pos.ticket),
            ))
        return result

    def close_position(self, ticket: str) -> OrderResult:
        self._ensure_connected()
        positions = self._mt5.positions_get()
        if positions is None:
            now = datetime.now(timezone.utc)
            return OrderResult(
                ExchangeType.MT5, "", OrderStatus.REJECTED,
                "", OrderSide.SELL, 0, 0.0, 0.0, 0.0,
                f"ticket {ticket} not found", now,
            )

        target = None
        for pos in positions:
            if str(pos.ticket) == ticket:
                target = pos
                break

        if target is None:
            now = datetime.now(timezone.utc)
            return OrderResult(
                ExchangeType.MT5, "", OrderStatus.REJECTED,
                "", OrderSide.SELL, 0, 0.0, 0.0, 0.0,
                f"ticket {ticket} not found", now,
            )

        # Determine close side
        close_side = (
            self._mt5.ORDER_TYPE_SELL
            if target.type == self._mt5.ORDER_TYPE_BUY
            else self._mt5.ORDER_TYPE_BUY
        )
        tick = self._mt5.symbol_info_tick(target.symbol)
        close_price = tick.bid if close_side == self._mt5.ORDER_TYPE_SELL else tick.ask

        request = {
            "action": self._mt5.TRADE_ACTION_DEAL,
            "symbol": target.symbol,
            "volume": target.volume,
            "type": close_side,
            "position": target.ticket,
            "price": close_price,
            "deviation": 20,
            "magic": 123456,
            "comment": "ai-scalping-close",
            "type_time": self._mt5.ORDER_TIME_GTC,
            "type_filling": self._mt5.ORDER_FILLING_IOC,
        }

        # Check before closing
        check = self._mt5.order_check(request)
        if check.retcode != 0:
            now = datetime.now(timezone.utc)
            return OrderResult(
                ExchangeType.MT5, "", OrderStatus.REJECTED,
                target.symbol, OrderSide.SELL, 0, 0.0, 0.0, 0.0,
                f"close check gagal (code {check.retcode})", now,
            )

        result = self._mt5.order_send(request)
        now = datetime.now(timezone.utc)
        if result.retcode != self._mt5.TRADE_RETCODE_DONE:
            return OrderResult(
                ExchangeType.MT5, "", OrderStatus.REJECTED,
                target.symbol, OrderSide.SELL, 0, 0.0, 0.0, 0.0,
                f"close gagal (code {result.retcode})", now,
            )

        return OrderResult(
            exchange=ExchangeType.MT5,
            order_id=str(result.order),
            status=OrderStatus.FILLED,
            symbol=target.symbol,
            side=OrderSide.SELL,
            quantity=float(target.volume),
            filled_qty=float(result.volume or target.volume),
            price=close_price,
            avg_fill_price=float(result.price or close_price),
            message=f"close {target.symbol} @ {close_price}",
            timestamp=now,
        )

    # ── Internal ─────────────────────────────────────────────────────────

    def _ensure_connected(self) -> None:
        if not self.is_connected:
            raise RuntimeError("MT5 belum connect. Panggil connect() dulu.")

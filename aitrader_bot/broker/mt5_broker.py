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


def _mt5_order_status(mt5, result) -> OrderStatus:
    if result is None:
        return OrderStatus.REJECTED
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        return OrderStatus.FILLED
    if result.retcode == getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010):
        return OrderStatus.PARTIAL
    if result.retcode == getattr(mt5, "TRADE_RETCODE_PLACED", 10008):
        return OrderStatus.PENDING
    return OrderStatus.REJECTED


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
    def supports_attached_protection(self) -> bool:
        return True

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
        """Disconnect from MT5 terminal."""
        if self._mt5:
            try:
                self._mt5.shutdown()
            except Exception:
                pass
        self._connected = False

    def get_connection_status(self) -> dict:
        """Get current connection status and account information."""
        status = {
            "connected": self.is_connected,
            "login": self._login,
            "server": self._server,
            "last_error": ""
        }

        if not self.is_connected:
            return status

        try:
            account_info = self.get_account()
            status["account_info"] = {
                "balance": account_info.balance,
                "equity": account_info.equity,
                "margin": account_info.margin,
                "margin_free": account_info.margin_free,
                "leverage": account_info.leverage,
                "currency": account_info.currency
            }
        except Exception as e:
            status["last_error"] = str(e)
            status["connected"] = False

        return status

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
        info = self._mt5.symbol_info(mapped)
        point_size = float(info.point) if info is not None and info.point else None
        return Quote(
            symbol=mapped,
            exchange=ExchangeType.MT5,
            bid=tick.bid,
            ask=tick.ask,
            last=(tick.bid + tick.ask) / 2,
            volume=float(tick.volume or 0),
            timestamp=datetime.fromtimestamp(tick.time, tz=timezone.utc),
            raw={"bid": tick.bid, "ask": tick.ask, "time": tick.time},
            point_size=point_size,
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

    def _normalize_protective_prices(
        self,
        symbol: str,
        side: OrderSide,
        entry_price: float,
        stop_loss: float | None,
        take_profit: float | None,
    ) -> tuple[float | None, float | None, str | None]:
        """Normalize and validate broker-side protective prices."""
        if stop_loss is None and take_profit is None:
            return None, None, None
        info = self._mt5.symbol_info(symbol) if self._mt5 else None
        if info is None:
            return stop_loss, take_profit, f"symbol info unavailable for {symbol}"

        digits = int(getattr(info, "digits", 2) or 0)
        point = float(getattr(info, "point", 0.0) or 0.0)
        min_distance = float(getattr(info, "trade_stops_level", 0) or 0) * point

        sl = round(float(stop_loss), digits) if stop_loss is not None else None
        tp = round(float(take_profit), digits) if take_profit is not None else None

        if sl is not None and sl <= 0:
            return sl, tp, "stop loss must be positive"
        if tp is not None and tp <= 0:
            return sl, tp, "take profit must be positive"

        tolerance = max(point * 0.01, 1e-12)

        def invalid_distance(distance: float) -> bool:
            return distance <= tolerance or distance + tolerance < min_distance

        if side == OrderSide.BUY:
            if sl is not None and invalid_distance(entry_price - sl):
                return sl, tp, "buy stop loss is not below entry by the broker minimum distance"
            if tp is not None and invalid_distance(tp - entry_price):
                return sl, tp, "buy take profit is not above entry by the broker minimum distance"
        else:
            if sl is not None and invalid_distance(sl - entry_price):
                return sl, tp, "sell stop loss is not above entry by the broker minimum distance"
            if tp is not None and invalid_distance(entry_price - tp):
                return sl, tp, "sell take profit is not below entry by the broker minimum distance"

        return sl, tp, None

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

        stop_loss, take_profit, protection_error = self._normalize_protective_prices(
            mapped, side, order_price, stop_loss, take_profit,
        )
        if protection_error:
            return OrderResult(
                ExchangeType.MT5, "", OrderStatus.REJECTED,
                mapped, side, quantity, 0.0, order_price, 0.0,
                protection_error, now,
            )

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
        if stop_loss is not None:
            request["sl"] = stop_loss
        if take_profit is not None:
            request["tp"] = take_profit

        # STEP 1: order_check — validate BEFORE sending
        check = self._mt5.order_check(request)
        if check is None or check.retcode != 0:
            code = getattr(check, "retcode", "none")
            comment = getattr(check, "comment", self._mt5.last_error())
            return OrderResult(
                ExchangeType.MT5, "", OrderStatus.REJECTED,
                mapped, side, quantity, 0.0, 0.0, 0.0,
                f"order_check gagal (code {code}): {comment}",
                now,
            )

        # STEP 2: order_send — execute
        result = self._mt5.order_send(request)
        status = _mt5_order_status(self._mt5, result)
        if status == OrderStatus.REJECTED:
            code = getattr(result, "retcode", "none")
            return OrderResult(
                ExchangeType.MT5, "", OrderStatus.REJECTED,
                mapped, side, quantity, 0.0, 0.0, 0.0,
                f"order gagal (code {code})",
                now,
            )

        return OrderResult(
            exchange=ExchangeType.MT5,
            order_id=str(result.order),
            status=status,
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
            side = "buy" if pos.type == self._mt5.ORDER_TYPE_BUY else "sell"
            result.append(PositionInfo(
                symbol=pos.symbol,
                exchange=ExchangeType.MT5,
                quantity=float(pos.volume),
                avg_price=float(pos.price_open),
                current_price=float(pos.price_current),
                unrealized_pnl=float(pos.profit),
                ticket=str(pos.ticket),
                side=side,
                opened_at=datetime.fromtimestamp(pos.time, tz=timezone.utc) if pos.time else None,
                stop_loss=float(pos.sl) if getattr(pos, "sl", 0) else None,
                take_profit=float(pos.tp) if getattr(pos, "tp", 0) else None,
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
        if tick is None:
            now = datetime.now(timezone.utc)
            return OrderResult(
                ExchangeType.MT5, "", OrderStatus.REJECTED,
                target.symbol, OrderSide.SELL, 0, 0.0, 0.0, 0.0,
                f"no tick for {target.symbol}", now,
            )
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
            "type_filling": self._detect_filling_mode(target.symbol),
        }

        # Check before closing
        check = self._mt5.order_check(request)
        if check is None or check.retcode != 0:
            now = datetime.now(timezone.utc)
            code = getattr(check, "retcode", "none")
            return OrderResult(
                ExchangeType.MT5, "", OrderStatus.REJECTED,
                target.symbol, OrderSide.SELL, 0, 0.0, 0.0, 0.0,
                f"close check gagal (code {code})", now,
            )

        result = self._mt5.order_send(request)
        now = datetime.now(timezone.utc)
        status = _mt5_order_status(self._mt5, result)
        if status == OrderStatus.REJECTED:
            code = getattr(result, "retcode", "none")
            return OrderResult(
                ExchangeType.MT5, "", OrderStatus.REJECTED,
                target.symbol, OrderSide.SELL, 0, 0.0, 0.0, 0.0,
                f"close gagal (code {code})", now,
            )

        return OrderResult(
            exchange=ExchangeType.MT5,
            order_id=str(result.order),
            status=status,
            symbol=target.symbol,
            side=OrderSide.SELL,
            quantity=float(target.volume),
            filled_qty=float(result.volume or target.volume),
            price=close_price,
            avg_fill_price=float(result.price or close_price),
            message=f"close {target.symbol} @ {close_price}",
            timestamp=now,
        )

    def set_position_protection(
        self,
        ticket: str,
        stop_loss: float | None,
        take_profit: float | None,
    ) -> OrderResult:
        """Attach or repair SL/TP for an existing MT5 position."""
        self._ensure_connected()
        now = datetime.now(timezone.utc)
        positions = self._mt5.positions_get()
        target = next((p for p in (positions or []) if str(p.ticket) == ticket), None)
        if target is None:
            return OrderResult(
                ExchangeType.MT5, "", OrderStatus.REJECTED,
                "", OrderSide.BUY, 0.0, 0.0, 0.0, 0.0,
                f"ticket {ticket} not found", now,
            )

        side = OrderSide.BUY if target.type == self._mt5.ORDER_TYPE_BUY else OrderSide.SELL
        tick = self._mt5.symbol_info_tick(target.symbol)
        if tick is None:
            return OrderResult(
                ExchangeType.MT5, "", OrderStatus.REJECTED,
                target.symbol, side, float(target.volume), 0.0, 0.0, 0.0,
                f"no tick for {target.symbol}", now,
            )
        entry_reference = tick.bid if side == OrderSide.BUY else tick.ask
        stop_loss, take_profit, error = self._normalize_protective_prices(
            target.symbol, side, entry_reference, stop_loss, take_profit,
        )
        if error:
            return OrderResult(
                ExchangeType.MT5, "", OrderStatus.REJECTED,
                target.symbol, side, float(target.volume), 0.0, entry_reference, 0.0,
                error, now,
            )

        request = {
            "action": self._mt5.TRADE_ACTION_SLTP,
            "symbol": target.symbol,
            "position": target.ticket,
            "sl": stop_loss or 0.0,
            "tp": take_profit or 0.0,
            "magic": 123456,
            "comment": "ai-scalping-protection",
        }
        check = self._mt5.order_check(request)
        if check is None or check.retcode != 0:
            code = getattr(check, "retcode", "none")
            return OrderResult(
                ExchangeType.MT5, "", OrderStatus.REJECTED,
                target.symbol, side, float(target.volume), 0.0, entry_reference, 0.0,
                f"protection check failed (code {code})", now,
            )

        result = self._mt5.order_send(request)
        if result is None or result.retcode != self._mt5.TRADE_RETCODE_DONE:
            code = getattr(result, "retcode", "none")
            return OrderResult(
                ExchangeType.MT5, "", OrderStatus.REJECTED,
                target.symbol, side, float(target.volume), 0.0, entry_reference, 0.0,
                f"protection update failed (code {code})", now,
            )
        return OrderResult(
            ExchangeType.MT5,
            str(getattr(result, "order", target.ticket)),
            OrderStatus.FILLED,
            target.symbol,
            side,
            float(target.volume),
            float(target.volume),
            entry_reference,
            entry_reference,
            "position protection updated",
            now,
        )

    # ── Internal ─────────────────────────────────────────────────────────

    def _ensure_connected(self) -> None:
        if not self.is_connected:
            raise RuntimeError("MT5 belum connect. Panggil connect() dulu.")

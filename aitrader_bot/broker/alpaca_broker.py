"""Alpaca broker — for US stocks scalping (AAPL, SPY, TSLA, etc.).

Requires: pip install alpaca-py

Supports:
- Paper trading via paper=True
- Market & limit orders via TradingClient
- Real-time quotes via StockDataStream (WebSocket)
- Account info and positions
"""

from __future__ import annotations

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


def _order_value(order, name: str, default=None):
    if isinstance(order, dict):
        return order.get(name, default)
    return getattr(order, name, default)


def _map_alpaca_order_status(status, filled_qty: float, requested_qty: float) -> OrderStatus:
    filled_qty = abs(filled_qty)
    requested_qty = abs(requested_qty)
    value = getattr(status, "value", status)
    value = str(value or "").lower()
    if value == "filled" or (requested_qty > 0 and filled_qty >= requested_qty):
        return OrderStatus.FILLED
    if value == "partially_filled" or filled_qty > 0:
        return OrderStatus.PARTIAL
    if value == "rejected":
        return OrderStatus.REJECTED
    if value in {"canceled", "expired", "done_for_day", "stopped", "suspended"}:
        return OrderStatus.CANCELLED
    return OrderStatus.PENDING


def _order_timestamp(order, default: datetime) -> datetime:
    created_at = _order_value(order, "created_at")
    if not isinstance(created_at, datetime):
        return default
    if created_at.tzinfo is None:
        return created_at.replace(tzinfo=timezone.utc)
    return created_at


class AlpacaBroker(BaseBroker):
    """Broker adapter for Alpaca — US stocks & ETFs."""

    SYMBOL_MAP: dict[str, str] = {}  # Internal → Alpaca, usually same

    def __init__(self, api_key: str = "", secret_key: str = "", paper: bool = True):
        self._api_key = api_key
        self._secret_key = secret_key
        self._paper = paper
        self._trading_client = None
        self._data_client = None
        self._connected = False

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def exchange_type(self) -> ExchangeType:
        return ExchangeType.ALPACA

    @property
    def supports_short_positions(self) -> bool:
        return True

    @property
    def is_connected(self) -> bool:
        return self._connected and self._trading_client is not None

    # ── Connection ─────────────────────────────────────────────────────

    def connect(self) -> bool:
        try:
            from alpaca.trading.client import TradingClient
            from alpaca.data.historical.stock import StockHistoricalDataClient

            self._trading_client = TradingClient(
                self._api_key, self._secret_key, paper=self._paper,
            )
            self._data_client = StockHistoricalDataClient(
                self._api_key, self._secret_key,
            )

            # Test connection
            self._trading_client.get_account()
            self._connected = True
            return True

        except ImportError:
            raise ImportError(
                "alpaca-py belum terinstall. Jalankan: pip install alpaca-py"
            )
        except Exception as e:
            raise ConnectionError(f"Alpaca connect gagal: {e}")

    def disconnect(self) -> None:
        self._connected = False
        self._trading_client = None
        self._data_client = None

    # ── Symbol mapping ─────────────────────────────────────────────────

    def get_symbol_map(self, internal_symbol: str) -> str:
        return self.SYMBOL_MAP.get(internal_symbol, internal_symbol)

    # ── Account ────────────────────────────────────────────────────────

    def get_account(self) -> AccountInfo:
        self._ensure_connected()
        try:
            acct = self._trading_client.get_account()
            return AccountInfo(
                exchange=ExchangeType.ALPACA,
                balance=float(acct.cash),
                equity=float(acct.equity),
                buying_power=float(acct.buying_power),
                currency="USD",
                leverage=1,
            )
        except Exception as e:
            raise RuntimeError(f"Gagal get account: {e}")

    # ── Quote ──────────────────────────────────────────────────────────

    def get_quote(self, symbol: str) -> Quote | None:
        self._ensure_connected()
        mapped = self.get_symbol_map(symbol)
        try:
            from alpaca.data.requests import StockLatestQuoteRequest

            request = StockLatestQuoteRequest(symbol_or_symbols=[mapped])
            quotes = self._data_client.get_stock_latest_quote(request)
            if mapped not in quotes:
                return None
            q = quotes[mapped]
            return Quote(
                symbol=mapped,
                exchange=ExchangeType.ALPACA,
                bid=float(q.bid_price),
                ask=float(q.ask_price),
                last=(float(q.bid_price) + float(q.ask_price)) / 2,
                volume=float(q.bid_size or 0) + float(q.ask_size or 0),
                timestamp=q.timestamp.replace(tzinfo=timezone.utc)
                if q.timestamp.tzinfo is None
                else q.timestamp,
                raw={"bid": q.bid_price, "ask": q.ask_price, "bid_size": q.bid_size, "ask_size": q.ask_size},
                point_size=0.01,
            )
        except Exception:
            return None

    # ── Candles ────────────────────────────────────────────────────────

    def fetch_candles(self, symbol: str, timeframe: str = "5m", count: int = 100) -> list[Candle]:
        self._ensure_connected()
        mapped = self.get_symbol_map(symbol)

        # Map timeframe to Alpaca format
        tf_map = {
            "1m": "Min",
            "5m": "5Min",
            "15m": "15Min",
            "1h": "Hour",
            "1d": "Day",
        }
        alpaca_tf = tf_map.get(timeframe, "5Min")

        try:
            from alpaca.data.requests import StockBarsRequest
            from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

            # Build Alpaca TimeFrame
            if alpaca_tf == "Min":
                tf = TimeFrame(1, TimeFrameUnit.Minute)
            elif alpaca_tf == "5Min":
                tf = TimeFrame(5, TimeFrameUnit.Minute)
            elif alpaca_tf == "15Min":
                tf = TimeFrame(15, TimeFrameUnit.Minute)
            elif alpaca_tf == "Hour":
                tf = TimeFrame(1, TimeFrameUnit.Hour)
            else:
                tf = TimeFrame(1, TimeFrameUnit.Day)

            from datetime import timedelta
            now = datetime.now(timezone.utc)
            start = now - timedelta(minutes=count * 5) if timeframe == "5m" else now - timedelta(days=count)

            request = StockBarsRequest(
                symbol_or_symbols=[mapped],
                timeframe=tf,
                start=start,
                limit=count,
            )
            bars = self._data_client.get_stock_bars(request)

            candles: list[Candle] = []
            if mapped in bars.data:
                for bar in bars.data[mapped]:
                    candles.append(Candle(
                        symbol=mapped,
                        exchange=ExchangeType.ALPACA,
                        timestamp=bar.timestamp.replace(tzinfo=timezone.utc),
                        open=float(bar.open),
                        high=float(bar.high),
                        low=float(bar.low),
                        close=float(bar.close),
                        volume=float(bar.volume),
                        timeframe=timeframe,
                    ))
            return candles

        except ImportError:
            raise ImportError("alpaca-py butuh pandas. Jalankan: pip install pandas")
        except Exception as e:
            raise RuntimeError(f"Gagal fetch candles {mapped}: {e}")

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
        self._ensure_connected()
        mapped = self.get_symbol_map(symbol)
        now = datetime.now(timezone.utc)

        if stop_loss is not None or take_profit is not None:
            return OrderResult(
                ExchangeType.ALPACA, "", OrderStatus.REJECTED,
                mapped, side, quantity, 0.0, 0.0, 0.0,
                "attached protective orders are not implemented by the Alpaca adapter",
                now,
            )

        try:
            from alpaca.trading.requests import LimitOrderRequest, MarketOrderRequest
            from alpaca.trading.enums import OrderSide as AlpacaSide, TimeInForce

            alpaca_side = AlpacaSide.BUY if side == OrderSide.BUY else AlpacaSide.SELL

            if order_type == "market":
                order_data = MarketOrderRequest(
                    symbol=mapped,
                    qty=quantity,
                    side=alpaca_side,
                    time_in_force=TimeInForce.DAY,
                )
            else:
                if price is None:
                    return OrderResult(
                        ExchangeType.ALPACA, "", OrderStatus.REJECTED,
                        mapped, side, quantity, 0.0, 0.0, 0.0,
                        "limit order butuh price", now,
                    )
                order_data = LimitOrderRequest(
                    symbol=mapped,
                    qty=quantity,
                    side=alpaca_side,
                    limit_price=price,
                    time_in_force=TimeInForce.DAY,
                )

            order = self._trading_client.submit_order(order_data=order_data)
            filled_qty = float(_order_value(order, "filled_qty", 0) or 0)
            status = _map_alpaca_order_status(
                _order_value(order, "status"), filled_qty, quantity,
            )
            avg_price = float(_order_value(order, "filled_avg_price", 0) or 0)
            created_at = _order_timestamp(order, now)

            return OrderResult(
                exchange=ExchangeType.ALPACA,
                order_id=str(_order_value(order, "id", "")),
                status=status,
                symbol=mapped,
                side=side,
                quantity=quantity,
                filled_qty=filled_qty,
                price=price or avg_price,
                avg_fill_price=avg_price,
                message=f"{alpaca_side.value} {quantity} {mapped} @ {avg_price or price}",
                timestamp=created_at,
            )

        except Exception as e:
            return OrderResult(
                ExchangeType.ALPACA, "", OrderStatus.REJECTED,
                mapped, side, quantity, 0.0, 0.0, 0.0,
                f"order gagal: {e}", now,
            )

    # ── Positions ──────────────────────────────────────────────────────

    def get_positions(self, symbol: str | None = None) -> list[PositionInfo]:
        self._ensure_connected()
        try:
            if symbol:
                mapped = self.get_symbol_map(symbol)
                pos = self._trading_client.get_open_position(mapped)
                return [PositionInfo(
                    symbol=pos.symbol,
                    exchange=ExchangeType.ALPACA,
                    quantity=abs(float(pos.qty)),
                    avg_price=float(pos.avg_entry_price),
                    current_price=float(pos.current_price),
                    unrealized_pnl=float(pos.unrealized_pl),
                    realized_pnl=float(pos.unrealized_plpc),
                    ticket=str(pos.asset_id),
                    side=str(getattr(pos.side, "value", pos.side)).lower(),
                )] if pos else []

            positions_raw = self._trading_client.get_all_positions()
            result: list[PositionInfo] = []
            for pos in positions_raw:
                result.append(PositionInfo(
                    symbol=pos.symbol,
                    exchange=ExchangeType.ALPACA,
                    quantity=abs(float(pos.qty)),
                    avg_price=float(pos.avg_entry_price),
                    current_price=float(pos.current_price),
                    unrealized_pnl=float(pos.unrealized_pl),
                    realized_pnl=float(pos.unrealized_plpc),
                    ticket=str(pos.asset_id),
                    side=str(getattr(pos.side, "value", pos.side)).lower(),
                ))
            return result

        except Exception:
            return []

    def close_position(self, ticket: str) -> OrderResult:
        self._ensure_connected()
        try:
            # ticket is asset_id, need to find symbol first
            positions = self.get_positions()
            target = next((p for p in positions if p.ticket == ticket), None)
            if not target:
                now = datetime.now(timezone.utc)
                return OrderResult(
                    ExchangeType.ALPACA, "", OrderStatus.REJECTED,
                    "", OrderSide.SELL, 0, 0.0, 0.0, 0.0,
                    f"position ticket {ticket} not found", now,
                )

            order = self._trading_client.close_position(target.symbol)
            now = datetime.now(timezone.utc)
            close_side = (
                OrderSide.BUY
                if target.side in {"sell", "short"}
                else OrderSide.SELL
            )
            filled_qty = float(_order_value(order, "filled_qty", 0) or 0)
            requested_qty = abs(target.quantity)
            status = _map_alpaca_order_status(
                _order_value(order, "status"), filled_qty, requested_qty,
            )
            avg_price = float(_order_value(order, "filled_avg_price", 0) or 0)
            created_at = _order_timestamp(order, now)
            return OrderResult(
                exchange=ExchangeType.ALPACA,
                order_id=str(_order_value(order, "id", "")),
                status=status,
                symbol=target.symbol,
                side=close_side,
                quantity=requested_qty,
                filled_qty=abs(filled_qty),
                price=target.current_price,
                avg_fill_price=avg_price,
                message=f"close {target.symbol} status={status.value} filled={filled_qty}",
                timestamp=created_at,
            )

        except Exception as e:
            now = datetime.now(timezone.utc)
            return OrderResult(
                ExchangeType.ALPACA, "", OrderStatus.REJECTED,
                "", OrderSide.SELL, 0, 0.0, 0.0, 0.0,
                f"close gagal: {e}", now,
            )

    # ── Internal ─────────────────────────────────────────────────────────

    def _ensure_connected(self) -> None:
        if not self.is_connected:
            raise RuntimeError("Alpaca belum connect. Panggil connect() dulu.")

"""Binance broker via CCXT — for crypto scalping (BTC, ETH, etc.).

Requires: pip install ccxt

Supports:
- REST API for candles, orders, account info
- Rate limiting via enableRateLimit
- Symbol mapping (BTC-USD → BTC/USDT)
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


class CcxtBroker(BaseBroker):
    """Broker adapter for CCXT-supported exchanges (Binance)."""

    SYMBOL_MAP = {
        "BTC-USD": "BTC/USDT",
        "ETH-USD": "ETH/USDT",
        "SOL-USD": "SOL/USDT",
        "BNB-USD": "BNB/USDT",
        "ADA-USD": "ADA/USDT",
        "XRP-USD": "XRP/USDT",
        "DOT-USD": "DOT/USDT",
        "DOGE-USD": "DOGE/USDT",
    }
    TIMEFRAME_MAP = {
        "1m": "1m",
        "5m": "5m",
        "15m": "15m",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d",
    }

    def __init__(
        self,
        exchange_id: str = "binance",
        api_key: str = "",
        secret: str = "",
        sandbox: bool = False,
    ):
        self._exchange_id = exchange_id
        self._api_key = api_key
        self._secret = secret
        self._sandbox = sandbox
        self._exchange = None
        self._connected = False

    # ── Properties ─────────────────────────────────────────────────────

    @property
    def exchange_type(self) -> ExchangeType:
        return ExchangeType.BINANCE

    @property
    def is_connected(self) -> bool:
        return self._connected and self._exchange is not None

    # ── Connection ─────────────────────────────────────────────────────

    def connect(self) -> bool:
        import ccxt

        exchange_class = getattr(ccxt, self._exchange_id)
        self._exchange = exchange_class({
            "apiKey": self._api_key,
            "secret": self._secret,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })

        if self._sandbox:
            self._exchange.set_sandbox_mode(True)

        # Test connection by fetching ticker
        try:
            self._exchange.fetch_ticker("BTC/USDT")
            self._connected = True
            return True
        except Exception as e:
            raise ConnectionError(f"CCXT connect gagal: {e}")

    def disconnect(self) -> None:
        if self._exchange:
            self._exchange.close()
        self._connected = False

    # ── Symbol mapping ─────────────────────────────────────────────────

    def get_symbol_map(self, internal_symbol: str) -> str:
        return self.SYMBOL_MAP.get(internal_symbol, internal_symbol)

    # ── Account ────────────────────────────────────────────────────────

    def get_account(self) -> AccountInfo:
        self._ensure_connected()
        try:
            bal = self._exchange.fetch_balance()
            total_usd = bal.get("USDT", {}).get("total", 0)
            free_usd = bal.get("USDT", {}).get("free", 0)
            return AccountInfo(
                exchange=ExchangeType.BINANCE,
                balance=float(free_usd),
                equity=float(total_usd),
                margin=0.0,
                margin_free=float(free_usd),
                leverage=1,
                currency="USDT",
                buying_power=float(free_usd),
            )
        except Exception as e:
            raise RuntimeError(f"Gagal get account: {e}")

    # ── Quote ──────────────────────────────────────────────────────────

    def get_quote(self, symbol: str) -> Quote | None:
        self._ensure_connected()
        mapped = self.get_symbol_map(symbol)
        try:
            ticker = self._exchange.fetch_ticker(mapped)
            if ticker is None or ticker.get("last") is None:
                return None
            market = self._exchange.market(mapped)
            price_precision = (market.get("precision") or {}).get("price")
            point_size = None
            if isinstance(price_precision, int) and price_precision >= 0:
                point_size = 10 ** (-price_precision)
            elif isinstance(price_precision, (int, float)) and price_precision > 0:
                point_size = float(price_precision)
            return Quote(
                symbol=mapped,
                exchange=ExchangeType.BINANCE,
                bid=float(ticker.get("bid", ticker["last"])),
                ask=float(ticker.get("ask", ticker["last"])),
                last=float(ticker["last"]),
                volume=float(ticker.get("baseVolume", 0)),
                timestamp=datetime.fromtimestamp(
                    ticker.get("timestamp", datetime.now().timestamp()) / 1000,
                    tz=timezone.utc,
                ),
                raw=ticker,
                point_size=point_size,
            )
        except Exception:
            return None

    # ── Candles ────────────────────────────────────────────────────────

    def fetch_candles(self, symbol: str, timeframe: str = "5m", count: int = 100) -> list[Candle]:
        self._ensure_connected()
        mapped = self.get_symbol_map(symbol)
        tf = self.TIMEFRAME_MAP.get(timeframe, "5m")
        try:
            raw = self._exchange.fetch_ohlcv(mapped, tf, limit=count)
            candles: list[Candle] = []
            for item in raw:
                candles.append(Candle(
                    symbol=mapped,
                    exchange=ExchangeType.BINANCE,
                    timestamp=datetime.fromtimestamp(item[0] / 1000, tz=timezone.utc),
                    open=float(item[1]),
                    high=float(item[2]),
                    low=float(item[3]),
                    close=float(item[4]),
                    volume=float(item[5]),
                    timeframe=tf,
                ))
            return candles
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
        ccxt_side = "buy" if side == OrderSide.BUY else "sell"
        now = datetime.now(timezone.utc)

        if stop_loss is not None or take_profit is not None:
            return OrderResult(
                ExchangeType.BINANCE, "", OrderStatus.REJECTED,
                mapped, side, quantity, 0.0, 0.0, 0.0,
                "attached protective orders are not supported by the generic CCXT adapter",
                now,
            )

        try:
            if order_type == "market":
                order = self._exchange.create_order(mapped, "market", ccxt_side, quantity)
            else:
                if price is None:
                    return OrderResult(
                        ExchangeType.BINANCE, "", OrderStatus.REJECTED,
                        mapped, side, quantity, 0.0, 0.0, 0.0,
                        "limit order butuh price", now,
                    )
                order = self._exchange.create_order(mapped, "limit", ccxt_side, quantity, price)

            filled_qty = float(order.get("filled", 0))
            status = OrderStatus.FILLED if filled_qty >= quantity else OrderStatus.PARTIAL
            avg_price = float(order.get("price", 0)) or float(order.get("average", 0))

            return OrderResult(
                exchange=ExchangeType.BINANCE,
                order_id=str(order.get("id", "")),
                status=status,
                symbol=mapped,
                side=side,
                quantity=quantity,
                filled_qty=filled_qty,
                price=price or avg_price,
                avg_fill_price=avg_price,
                message=f"{ccxt_side} {quantity} {mapped} @ {avg_price}",
                timestamp=now,
                raw=order,
            )

        except Exception as e:
            err_msg = str(e)
            return OrderResult(
                ExchangeType.BINANCE, "", OrderStatus.REJECTED,
                mapped, side, quantity, 0.0, 0.0, 0.0,
                f"order gagal: {err_msg}", now,
            )

    # ── Positions ──────────────────────────────────────────────────────

    def get_positions(self, symbol: str | None = None) -> list[PositionInfo]:
        self._ensure_connected()
        try:
            bal = self._exchange.fetch_balance()
            positions: list[PositionInfo] = []
            for asset, data in bal.get("total", {}).items():
                if asset == "USDT" or asset == "USD":
                    continue
                qty = float(data)
                if qty <= 0:
                    continue
                # Fetch current price
                ticker_symbol = f"{asset}/USDT"
                try:
                    ticker = self._exchange.fetch_ticker(ticker_symbol)
                    cur_price = float(ticker.get("last", 0))
                except Exception:
                    cur_price = 0.0

                positions.append(PositionInfo(
                    symbol=ticker_symbol,
                    exchange=ExchangeType.BINANCE,
                    quantity=qty,
                    avg_price=0.0,  # CCXT doesn't easily provide avg entry
                    current_price=cur_price,
                    unrealized_pnl=0.0,
                    realized_pnl=0.0,
                    ticket=asset,
                ))
            return positions
        except Exception:
            return []

    def close_position(self, ticket: str) -> OrderResult:
        self._ensure_connected()
        # ticket is the asset name (e.g. "BTC")
        symbol = f"{ticket}/USDT"
        try:
            bal = self._exchange.fetch_balance()
            qty = float(bal.get("free", {}).get(ticket, 0))
            if qty <= 0:
                now = datetime.now(timezone.utc)
                return OrderResult(
                    ExchangeType.BINANCE, "", OrderStatus.REJECTED,
                    symbol, OrderSide.SELL, 0, 0.0, 0.0, 0.0,
                    f"no {ticket} balance to close", now,
                )
            return self.place_order(symbol, OrderSide.SELL, qty)
        except Exception as e:
            now = datetime.now(timezone.utc)
            return OrderResult(
                ExchangeType.BINANCE, "", OrderStatus.REJECTED,
                symbol, OrderSide.SELL, 0, 0.0, 0.0, 0.0,
                f"close gagal: {e}", now,
            )

    # ── Internal ─────────────────────────────────────────────────────────

    def _ensure_connected(self) -> None:
        if not self.is_connected:
            raise RuntimeError("CCXT belum connect. Panggil connect() dulu.")

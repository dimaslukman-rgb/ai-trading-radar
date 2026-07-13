"""Market quote and candle acquisition for live trading."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from ..broker.base import Candle, Quote
from ..models import PriceBar


@dataclass(frozen=True)
class MarketSnapshot:
    quote: Quote
    bars: tuple[PriceBar, ...]
    candles: tuple[Candle, ...]


class MarketDataService:
    """Build consistent strategy snapshots from broker market data."""

    def __init__(
        self,
        broker,
        symbol: str,
        timeframe: str,
        *,
        history_size: int = 50,
        clock: Callable[[], datetime] = datetime.now,
    ) -> None:
        self.broker = broker
        self.symbol = symbol
        self.timeframe = timeframe
        self.history_size = max(2, history_size)
        self.clock = clock
        self._candles: list[Candle] = []
        self._fallback_bars: list[PriceBar] = []

    def snapshot(self) -> MarketSnapshot | None:
        quote = self.broker.get_quote(self.symbol)
        if quote is None:
            return None

        try:
            self._candles = list(self.broker.fetch_candles(
                self.symbol,
                self.timeframe,
                self.history_size,
            ))
        except Exception:
            # Preserve the last valid candle window during a transient broker
            # history failure, matching the prior engine behavior.
            pass

        if self._candles:
            bars = [
                PriceBar(
                    date=candle.timestamp,
                    open=candle.open,
                    high=candle.high,
                    low=candle.low,
                    close=candle.close,
                    volume=candle.volume,
                )
                for candle in self._candles
            ]
            self._fallback_bars = bars[-self.history_size:]
        else:
            self._fallback_bars.append(PriceBar(
                date=self.clock(),
                open=quote.last,
                high=quote.last,
                low=quote.last,
                close=quote.last,
                volume=quote.volume,
            ))
            self._fallback_bars = self._fallback_bars[-self.history_size:]
            bars = self._fallback_bars

        return MarketSnapshot(quote, tuple(bars), tuple(self._candles))

    def closes(self, timeframe: str, count: int) -> list[float]:
        candles = self.broker.fetch_candles(self.symbol, timeframe, count)
        return [candle.close for candle in candles]

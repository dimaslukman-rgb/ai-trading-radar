"""Signal generation and read-only market analysis."""

from __future__ import annotations

from dataclasses import dataclass

from ..decision import higher_timeframe_confirmation
from ..indicators import ema, macd, rsi, volatility
from ..models import PriceBar, Signal
from .market_data import MarketDataService, MarketSnapshot


def compute_analysis(bars: list[PriceBar] | tuple[PriceBar, ...], config) -> dict[str, bool]:
    """Compute multi-factor analysis for the dashboard radar."""
    closes = [bar.close for bar in bars]
    highs = [bar.high for bar in bars]
    lows = [bar.low for bar in bars]
    volumes = [bar.volume for bar in bars]
    analysis = {
        "trend": False,
        "ema": False,
        "bos": False,
        "order_block": False,
        "liquidity_sweep": False,
        "volume": False,
        "rsi": False,
        "macd": False,
        "fvg": False,
        "news_clear": True,
    }
    if len(closes) < 25:
        return analysis
    ema_fast = ema(closes, config.ema_fast)
    ema_slow = ema(closes, config.ema_slow)
    if ema_fast is not None and ema_slow is not None:
        analysis["ema"] = True
        analysis["trend"] = ema_fast > ema_slow
    _, _, histogram = macd(
        closes,
        config.macd_fast,
        config.macd_slow,
        config.macd_signal,
    )
    if histogram is not None:
        analysis["macd"] = abs(histogram) > 0.05
    relative_strength = rsi(closes, 14)
    if relative_strength is not None:
        analysis["rsi"] = 45 < relative_strength < 55
    if len(volumes) >= 10:
        average_volume = sum(volumes[-10:-1]) / 9 if len(volumes) > 1 else volumes[-1]
        if average_volume > 0:
            analysis["volume"] = volumes[-1] / average_volume > 1.2
    if len(closes) >= 6:
        analysis["bos"] = (
            closes[-1] > max(closes[-6:-1])
            or closes[-1] < min(closes[-6:-1])
        )
    if len(closes) >= 5:
        last_move = closes[-1] - closes[-3]
        previous_move = closes[-3] - closes[-5]
        analysis["order_block"] = (
            last_move * previous_move < 0
            and abs(last_move) > abs(previous_move) * 0.5
        )
    if len(highs) >= 6 and len(lows) >= 6:
        analysis["liquidity_sweep"] = (
            highs[-1] > max(highs[-6:-1])
            or lows[-1] < min(lows[-6:-1])
        )
    if len(closes) >= 3 and len(highs) >= 3 and len(lows) >= 3:
        analysis["fvg"] = lows[-1] > highs[-3] or highs[-1] < lows[-3]
    return analysis


def compute_confidence(analysis: dict[str, bool]) -> tuple[int, str]:
    weights = {
        "trend": 10,
        "ema": 10,
        "bos": 10,
        "order_block": 10,
        "liquidity_sweep": 10,
        "volume": 10,
        "rsi": 5,
        "macd": 5,
        "fvg": 10,
        "news_clear": 10,
    }
    total = sum(weight for key, weight in weights.items() if analysis.get(key, False))
    if total >= 95:
        category = "STRONG CONFIRMED"
    elif total >= 85:
        category = "HIGH PROBABILITY"
    elif total >= 70:
        category = "GOOD SETUP"
    elif total >= 50:
        category = "WATCHLIST"
    else:
        category = "NO TRADE"
    return total, category


def compute_volatility(closes: list[float]) -> str:
    if len(closes) < 20:
        return "NORMAL"
    value = volatility(closes, 20)
    if value is None:
        return "NORMAL"
    if value < 0.002:
        return "LOW"
    if value < 0.005:
        return "NORMAL"
    if value < 0.01:
        return "HIGH"
    return "EXTREME"


def compute_sentiment(
    closes: list[float],
    highs: list[float],
    lows: list[float],
) -> dict[str, int]:
    del highs, lows  # Kept in the contract for future range-aware sentiment.
    if len(closes) < 10:
        return {"bullish": 0, "bearish": 0, "neutral": 100}
    bullish = 0
    bearish = 0
    for index in range(-10, 0):
        if closes[index] > closes[index - 1]:
            bullish += 1
        elif closes[index] < closes[index - 1]:
            bearish += 1
    neutral = 10 - bullish - bearish
    return {
        "bullish": round(bullish / 10 * 100),
        "bearish": round(bearish / 10 * 100),
        "neutral": round(max(0, neutral) / 10 * 100),
    }


@dataclass(frozen=True)
class SignalEvaluation:
    signal: Signal
    higher_timeframe_confirmed: bool
    higher_timeframe_reason: str
    analysis: dict[str, bool]
    confidence_pct: int
    confidence_category: str
    sentiment: dict[str, int]
    volatility: str


class SignalService:
    """Generate the strategy signal and its read-only confirmation context."""

    def __init__(self, strategy, market_data: MarketDataService) -> None:
        self.strategy = strategy
        self.market_data = market_data

    def evaluate(
        self,
        symbol: str,
        snapshot: MarketSnapshot,
        *,
        entry_blocked: bool,
    ) -> SignalEvaluation:
        bars = list(snapshot.bars)
        signal = self.strategy.generate(symbol, bars, snapshot.quote)
        confirmed = True
        reason = ""
        if not entry_blocked and signal.action in {"buy", "sell"}:
            try:
                closes = self.market_data.closes("5m", 25)
                confirmed, reason = higher_timeframe_confirmation(closes, signal.action)
            except Exception:
                pass

        analysis = compute_analysis(bars, self.strategy.config)
        confidence_pct, confidence_category = compute_confidence(analysis)
        closes = [bar.close for bar in bars]
        return SignalEvaluation(
            signal=signal,
            higher_timeframe_confirmed=confirmed,
            higher_timeframe_reason=reason,
            analysis=analysis,
            confidence_pct=confidence_pct,
            confidence_category=confidence_category,
            sentiment=compute_sentiment(
                closes,
                [bar.high for bar in bars],
                [bar.low for bar in bars],
            ),
            volatility=compute_volatility(closes),
        )

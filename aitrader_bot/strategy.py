from __future__ import annotations

from datetime import timezone

from .config import StrategyConfig
from .indicators import rsi, sma, volatility
from .models import PriceBar, Signal


class AiMomentumStrategy:
    """Small explainable scoring model for momentum trading."""

    def __init__(self, config: StrategyConfig):
        self.config = config

    def generate(self, symbol: str, bars: list[PriceBar]) -> Signal:
        if len(bars) < max(self.config.slow_window, self.config.rsi_window) + 1:
            latest = bars[-1]
            return Signal(symbol, "hold", 0.0, latest.close, "data belum cukup", latest.date)

        closes = [bar.close for bar in bars]
        latest = bars[-1]
        fast = sma(closes, self.config.fast_window)
        slow = sma(closes, self.config.slow_window)
        current_rsi = rsi(closes, self.config.rsi_window)
        current_vol = volatility(closes, self.config.slow_window) or 0.0

        score = 0.0
        reasons: list[str] = []

        if fast is not None and slow is not None:
            trend = (fast - slow) / slow
            score += _clamp(trend * 12.0, -0.45, 0.45)
            reasons.append(f"trend {trend:.2%}")

        if current_rsi is not None:
            if current_rsi < 35:
                score += 0.25
                reasons.append(f"RSI rendah {current_rsi:.1f}")
            elif current_rsi > 70:
                score -= 0.30
                reasons.append(f"RSI tinggi {current_rsi:.1f}")
            else:
                reasons.append(f"RSI netral {current_rsi:.1f}")

        if len(closes) >= 6:
            momentum = (closes[-1] - closes[-6]) / closes[-6]
            score += _clamp(momentum * 5.0, -0.35, 0.35)
            reasons.append(f"momentum 5 bar {momentum:.2%}")

        if current_vol > 0.08:
            score -= 0.10
            reasons.append(f"volatilitas tinggi {current_vol:.2%}")

        score = _clamp(score, -1.0, 1.0)
        if score >= self.config.min_buy_score:
            action = "buy"
        elif score <= self.config.min_sell_score:
            action = "sell"
        else:
            action = "hold"

        created_at = latest.date.astimezone(timezone.utc)
        return Signal(symbol, action, abs(score), latest.close, ", ".join(reasons), created_at)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))

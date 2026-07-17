"""Price Action Agent — candlestick patterns, impulse, pullback, rejection."""

from __future__ import annotations

from .base import AgentContext, AgentResult, BaseAgent


class PriceActionAgent(BaseAgent):
    agent_id = "price_action"

    def analyze(self, ctx: AgentContext) -> AgentResult:
        candles = ctx.candles
        if len(candles) < 3:
            return AgentResult(self.agent_id, {
                "pattern": "None", "confirmation": 0
            })

        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        closes = [c["close"] for c in candles]
        opens = [c["open"] for c in candles]

        last = candles[-1]
        prev = candles[-2] if len(candles) >= 2 else None
        prev2 = candles[-3] if len(candles) >= 3 else None

        body = abs(closes[-1] - opens[-1])
        total_range = highs[-1] - lows[-1] or 0.0001
        upper_wick = highs[-1] - max(closes[-1], opens[-1])
        lower_wick = min(closes[-1], opens[-1]) - lows[-1]

        pattern = "None"
        confirmation = 0

        # Pin Bar
        if total_range > 0:
            upper_ratio = upper_wick / total_range
            lower_ratio = lower_wick / total_range
            body_ratio = body / total_range

            if upper_ratio > 0.6 and lower_ratio < 0.1 and body_ratio < 0.3:
                pattern = "Bearish Pin Bar"
                confirmation = int(upper_ratio * 100)
            elif lower_ratio > 0.6 and upper_ratio < 0.1 and body_ratio < 0.3:
                pattern = "Bullish Pin Bar"
                confirmation = int(lower_ratio * 100)

        # Engulfing
        if prev and not pattern.startswith("Pin"):
            prev_body = abs(closes[-2] - opens[-2])
            if closes[-1] > opens[-1] and closes[-2] < opens[-2]:
                if body > prev_body * 1.2 and closes[-1] > opens[-2] and opens[-1] < closes[-2]:
                    pattern = "Bullish Engulfing"
                    confirmation = int(min(100, body / prev_body * 50))
            elif closes[-1] < opens[-1] and closes[-2] > opens[-2]:
                if body > prev_body * 1.2 and closes[-1] < opens[-2] and opens[-1] > closes[-2]:
                    pattern = "Bearish Engulfing"
                    confirmation = int(min(100, body / prev_body * 50))

        # Inside Bar
        if prev and not pattern.startswith(("Pin", "Engulfing")):
            if highs[-1] <= highs[-2] and lows[-1] >= lows[-2]:
                pattern = "Inside Bar"
                confirmation = 60

        # Outside Bar
        if prev and not pattern.startswith(("Pin", "Engulfing", "Inside")):
            if highs[-1] > highs[-2] and lows[-1] < lows[-2]:
                pattern = "Outside Bar"
                confirmation = 50

        # Morning / Evening Star (3-candle pattern)
        if prev and prev2 and not pattern.startswith(("Pin", "Engulfing", "Inside", "Outside")):
            first_bullish = closes[-3] > opens[-3]
            first_bearish = closes[-3] < opens[-3]
            last_bullish = closes[-1] > opens[-1]
            last_bearish = closes[-1] < opens[-1]
            middle_small = abs(closes[-2] - opens[-2]) < body * 1.2 if body > 0 else True

            if first_bearish and middle_small and last_bullish:
                if closes[-1] > (opens[-3] + closes[-3]) / 2:
                    pattern = "Morning Star"
                    confirmation = 80
            elif first_bullish and middle_small and last_bearish:
                if closes[-1] < (opens[-3] + closes[-3]) / 2:
                    pattern = "Evening Star"
                    confirmation = 80

        # Impulse detection (strong move)
        if not pattern.startswith(("Pin", "Engulfing", "Morning", "Evening")):
            if prev and body > prev_body * 2 and body > total_range * 0.7:
                direction = "Bullish" if closes[-1] > opens[-1] else "Bearish"
                pattern = f"{direction} Impulse"
                confirmation = int(min(100, body / prev_body * 40))

        # Rejection
        if not pattern.startswith(("Pin", "Engulfing", "Morning", "Evening", "Impulse")):
            if upper_wick > body * 2 and closes[-1] < opens[-1]:
                pattern = "Bearish Rejection"
                confirmation = int(min(100, upper_wick / total_range * 100))
            elif lower_wick > body * 2 and closes[-1] > opens[-1]:
                pattern = "Bullish Rejection"
                confirmation = int(min(100, lower_wick / total_range * 100))

        return AgentResult(self.agent_id, {
            "pattern": pattern,
            "confirmation": confirmation,
        })

"""Order Flow Agent — buying/selling pressure, delta, aggressive buyers/sellers."""

from __future__ import annotations

from .base import AgentContext, AgentResult, BaseAgent


class OrderFlowAgent(BaseAgent):
    agent_id = "order_flow"

    def analyze(self, ctx: AgentContext) -> AgentResult:
        candles = ctx.candles
        if len(candles) < 5:
            return AgentResult(self.agent_id, {
                "flow": "Neutral", "buyers": 50,
                "sellers": 50, "strength": 0
            })

        closes = [c["close"] for c in candles]
        opens = [c["open"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]

        bullish_volume = 0
        bearish_volume = 0
        total_range = 0

        for i in range(1, min(20, len(candles))):
            candle_range = highs[-i] - lows[-i]
            total_range += candle_range

            if closes[-i] > opens[-i]:
                # Bullish candle - buying pressure
                body = closes[-i] - opens[-i]
                upper_wick = highs[-i] - closes[-i]
                lower_wick = opens[-i] - lows[-i]
                if candle_range > 0:
                    buying_ratio = (body + (candle_range - upper_wick)) / (candle_range * 2)
                    bullish_volume += buying_ratio * 100
                    bearish_volume += (1 - buying_ratio) * 100
            else:
                # Bearish candle - selling pressure
                body = opens[-i] - closes[-i]
                upper_wick = highs[-i] - opens[-i]
                lower_wick = closes[-i] - lows[-i]
                if candle_range > 0:
                    selling_ratio = (body + (candle_range - lower_wick)) / (candle_range * 2)
                    bearish_volume += selling_ratio * 100
                    bullish_volume += (1 - selling_ratio) * 100

        count = min(20, len(candles)) - 1
        if count > 0:
            bullish_volume /= count
            bearish_volume /= count

        total = bullish_volume + bearish_volume
        if total > 0:
            buyers_pct = int(bullish_volume / total * 100)
            sellers_pct = int(bearish_volume / total * 100)
        else:
            buyers_pct = 50
            sellers_pct = 50

        # Flow direction
        if buyers_pct > 55:
            flow = "Bullish"
        elif sellers_pct > 55:
            flow = "Bearish"
        else:
            flow = "Neutral"

        # Strength
        strength = abs(buyers_pct - sellers_pct)

        return AgentResult(self.agent_id, {
            "flow": flow,
            "buyers": buyers_pct,
            "sellers": sellers_pct,
            "strength": strength,
        })

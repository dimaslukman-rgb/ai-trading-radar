"""Entry Strategy Agent — generates entry price and type from confirmed setup."""

from __future__ import annotations

from .base import AgentContext, AgentResult, BaseAgent


class EntryStrategyAgent(BaseAgent):
    agent_id = "entry_strategy"

    def analyze(self, ctx: AgentContext) -> AgentResult:
        candles = ctx.candles
        if len(candles) < 5:
            return AgentResult(self.agent_id, {
                "entry": ctx.price, "entry_type": "Market", "quality": 0
            })

        closes = [c["close"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        current_price = closes[-1]

        # Find recent support/resistance for limit orders
        recent_high = max(highs[-5:]) if len(highs) >= 5 else max(highs)
        recent_low = min(lows[-5:]) if len(lows) >= 5 else min(lows)

        # Determine entry type based on price position
        range_size = recent_high - recent_low or 1
        retracement = (current_price - recent_low) / range_size

        if retracement < 0.3:
            # Near support - buy on bounce
            entry = recent_low + (range_size * 0.05)
            entry_type = "Limit"
            quality = 70
        elif retracement > 0.7:
            # Near resistance - sell on rejection
            entry = recent_high - (range_size * 0.05)
            entry_type = "Limit"
            quality = 65
        elif 0.4 < retracement < 0.6:
            # Mid range - wait for breakout
            entry = current_price
            entry_type = "Market"
            quality = 40
        else:
            entry = current_price
            entry_type = "Market"
            quality = 30

        return AgentResult(self.agent_id, {
            "entry": round(entry, 5),
            "entry_type": entry_type,
            "quality": quality,
        })

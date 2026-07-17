"""Volatility Agent — ATR, spread, slippage, trade safety check."""

from __future__ import annotations

from .base import AgentContext, AgentResult, BaseAgent


class VolatilityAgent(BaseAgent):
    agent_id = "volatility"

    def analyze(self, ctx: AgentContext) -> AgentResult:
        candles = ctx.candles
        if len(candles) < 5:
            return AgentResult(self.agent_id, {
                "volatility": "Normal", "spread_ok": True, "trade_allowed": True
            })

        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        closes = [c["close"] for c in candles]

        # ATR calculation (simplified)
        ranges = []
        for i in range(1, min(14, len(candles))):
            tr = max(
                highs[-i] - lows[-i],
                abs(highs[-i] - closes[-i - 1]),
                abs(lows[-i] - closes[-i - 1])
            )
            ranges.append(tr)
        atr = sum(ranges) / len(ranges) if ranges else 0

        # Average range
        avg_range = sum(highs[-i] - lows[-i] for i in range(1, min(14, len(candles)))) / min(14, len(candles) - 1) or 1
        current_range = (highs[-1] - lows[-1]) if len(candles) >= 2 else avg_range

        # Volatility classification
        range_ratio = current_range / avg_range if avg_range > 0 else 1
        if range_ratio > 2.5:
            volatility = "Extreme"
            trade_allowed = False
        elif range_ratio > 1.8:
            volatility = "High"
            trade_allowed = range_ratio < 2.0
        elif range_ratio > 0.7:
            volatility = "Normal"
            trade_allowed = True
        else:
            volatility = "Low"
            trade_allowed = True

        # Spread check (informational only — entry gating handled by risk service)
        spread = abs(ctx.ask - ctx.bid) if ctx.ask and ctx.bid else 0
        spread_ok = spread < (avg_range * 0.15) if avg_range > 0 else True

        return AgentResult(self.agent_id, {
            "volatility": volatility,
            "spread_ok": spread_ok,
            "trade_allowed": trade_allowed,
        })

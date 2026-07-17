"""Trend Analyst Agent — trend alignment across timeframes."""

from __future__ import annotations

from .base import AgentContext, AgentResult, BaseAgent


class TrendAnalystAgent(BaseAgent):
    agent_id = "trend_analyst"

    def analyze(self, ctx: AgentContext) -> AgentResult:
        candles = ctx.candles
        if len(candles) < 10:
            return AgentResult(self.agent_id, {
                "weekly": "Neutral", "daily": "Neutral",
                "h4": "Neutral", "h1": "Neutral", "m15": "Neutral",
                "alignment": 0, "overall": "Neutral"
            })

        closes = [c["close"] for c in candles]

        def trend_for_window(data: list[float], window: int) -> str:
            if len(data) < window:
                return "Neutral"
            segment = data[-window:]
            ema = sum(segment) / len(segment)
            current = segment[-1]
            prev = segment[-2] if len(segment) > 1 else current
            if current > ema * 1.001 and current > prev:
                return "Bullish"
            elif current < ema * 0.999 and current < prev:
                return "Bearish"
            return "Neutral"

        tf_results = {
            "weekly": trend_for_window(closes, min(100, len(closes))),
            "daily": trend_for_window(closes, min(50, len(closes))),
            "h4": trend_for_window(closes, min(30, len(closes))),
            "h1": trend_for_window(closes, min(20, len(closes))),
            "m15": trend_for_window(closes, min(10, len(closes))),
        }

        bullish_count = sum(1 for v in tf_results.values() if v == "Bullish")
        bearish_count = sum(1 for v in tf_results.values() if v == "Bearish")
        total = len(tf_results)

        alignment = int(max(bullish_count, bearish_count) / total * 100)

        if bullish_count > bearish_count and alignment >= 60:
            overall = "Bullish"
        elif bearish_count > bullish_count and alignment >= 60:
            overall = "Bearish"
        elif alignment < 40:
            overall = "Mixed"
        else:
            overall = "Neutral"

        return AgentResult(self.agent_id, {
            "weekly": tf_results["weekly"],
            "daily": tf_results["daily"],
            "h4": tf_results["h4"],
            "h1": tf_results["h1"],
            "m15": tf_results["m15"],
            "alignment": alignment,
            "overall": overall,
        })

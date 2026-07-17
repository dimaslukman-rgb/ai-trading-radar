"""Smart Money Agent — order blocks, FVG, premium/discount zones."""

from __future__ import annotations

from .base import AgentContext, AgentResult, BaseAgent


class SmartMoneyAgent(BaseAgent):
    agent_id = "smart_money"

    def analyze(self, ctx: AgentContext) -> AgentResult:
        candles = ctx.candles
        if len(candles) < 10:
            return AgentResult(self.agent_id, {
                "order_block": "None", "fvg": "None",
                "discount_zone": False, "institutional_bias": "Neutral",
                "score": 0
            })

        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        closes = [c["close"] for c in candles]
        opens = [c["open"] for c in candles]
        current_price = closes[-1]

        # Order Block detection
        order_block = "None"
        for i in range(2, min(15, len(candles))):
            bearish_candle = closes[-i] < opens[-i]
            prev_bullish = closes[-i - 1] > opens[-i - 1] if i + 1 < len(candles) else False

            if bearish_candle and prev_bullish:
                # Bearish OB: last bullish candle before bearish move
                ob_high = highs[-i - 1]
                if current_price < ob_high:
                    order_block = "Bearish"
                    break
            elif not bearish_candle and i + 1 < len(candles):
                prev_bearish = closes[-i - 1] < opens[-i - 1]
                if prev_bearish:
                    ob_low = lows[-i - 1]
                    if current_price > ob_low:
                        order_block = "Bullish"
                        break

        # Fair Value Gap detection
        fvg = "None"
        for i in range(1, min(10, len(candles) - 1)):
            upper = min(lows[i - 1], lows[i]) if i > 0 else lows[i]
            lower = max(highs[i - 1], highs[i]) if i > 0 else highs[i]
            if upper > lower:
                gap_top = upper
                gap_bottom = lower
                if gap_bottom <= current_price <= gap_top:
                    fvg = "Valid"
                    break
                elif current_price < gap_bottom:
                    fvg = "Invalid"
                elif current_price > gap_top:
                    fvg = "Mitigated"

        # Premium / Discount zone (based on 50% range)
        period_high = max(highs[-20:]) if len(highs) >= 20 else max(highs)
        period_low = min(lows[-20:]) if len(lows) >= 20 else min(lows)
        mid = (period_high + period_low) / 2
        discount_zone = current_price < mid

        # Institutional bias
        inst_bias = "Neutral"
        score = 50

        if order_block == "Bullish" and discount_zone:
            inst_bias = "Bullish"
            score = 80
        elif order_block == "Bearish" and not discount_zone:
            inst_bias = "Bearish"
            score = 70
        elif order_block == "Bullish":
            inst_bias = "Bullish"
            score = 60
        elif order_block == "Bearish":
            inst_bias = "Bearish"
            score = 55
        elif discount_zone:
            inst_bias = "Bullish"
            score = 45

        if fvg == "Valid":
            score += 15
        elif fvg == "Mitigated":
            score -= 10

        score = min(100, max(0, score))

        return AgentResult(self.agent_id, {
            "order_block": order_block,
            "fvg": fvg,
            "discount_zone": discount_zone,
            "institutional_bias": inst_bias,
            "score": score,
        })

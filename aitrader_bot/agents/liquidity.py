"""Liquidity Agent — equal highs/lows, buy/sell side liquidity, sweep, inducement."""

from __future__ import annotations

from .base import AgentContext, AgentResult, BaseAgent


class LiquidityAgent(BaseAgent):
    agent_id = "liquidity"

    def analyze(self, ctx: AgentContext) -> AgentResult:
        candles = ctx.candles
        if len(candles) < 10:
            return AgentResult(self.agent_id, {
                "liquidity": "None", "sweep": False,
                "inducement": False, "next_target": "Unknown"
            })

        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        closes = [c["close"] for c in candles]
        current_price = closes[-1]

        # Equal highs / equal lows
        eq_highs = 0
        eq_lows = 0
        for i in range(1, min(10, len(candles))):
            if abs(highs[-i] - highs[-i - 1]) / (highs[-i] or 1) < 0.0005:
                eq_highs += 1
            if abs(lows[-i] - lows[-i - 1]) / (lows[-i] or 1) < 0.0005:
                eq_lows += 1

        # Buy side / Sell side liquidity
        recent_high = max(highs[-5:]) if len(highs) >= 5 else max(highs)
        recent_low = min(lows[-5:]) if len(lows) >= 5 else min(lows)

        buy_side_liquidity = current_price < recent_high
        sell_side_liquidity = current_price > recent_low

        # Liquidity sweep detection
        sweep = False
        if buy_side_liquidity and current_price >= recent_high * 0.999:
            sweep = True
        if sell_side_liquidity and current_price <= recent_low * 1.001:
            sweep = True

        # Inducement (false breakout)
        inducement = False
        if len(candles) >= 5:
            range_high = max(highs[-5:-1])
            range_low = min(lows[-5:-1])
            prev_close = closes[-2] if len(closes) > 1 else current_price
            # Price broke out then reversed
            if prev_close > range_high and current_price < range_high:
                inducement = True
            elif prev_close < range_low and current_price > range_low:
                inducement = True

        # Determine liquidity type
        if buy_side_liquidity and sell_side_liquidity:
            liquidity = "Both"
        elif buy_side_liquidity:
            liquidity = "Buy Side"
        elif sell_side_liquidity:
            liquidity = "Sell Side"
        else:
            liquidity = "None"

        # Next target
        if sweep and liquidity == "Buy Side":
            next_target = "Previous High"
        elif sweep and liquidity == "Sell Side":
            next_target = "Previous Low"
        elif buy_side_liquidity:
            next_target = f"{recent_high:.2f}"
        elif sell_side_liquidity:
            next_target = f"{recent_low:.2f}"
        else:
            next_target = "Unknown"

        return AgentResult(self.agent_id, {
            "liquidity": liquidity,
            "sweep": sweep,
            "inducement": inducement,
            "next_target": next_target,
        })

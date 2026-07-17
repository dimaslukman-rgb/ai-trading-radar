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

        # Wilder-style ATR estimate gives every proximity/sweep threshold a
        # scale appropriate to the symbol and current market regime.
        true_ranges = []
        for index in range(1, len(candles)):
            true_ranges.append(max(
                highs[index] - lows[index],
                abs(highs[index] - closes[index - 1]),
                abs(lows[index] - closes[index - 1]),
            ))
        atr = sum(true_ranges[-14:]) / min(14, len(true_ranges)) if true_ranges else 0.0
        tolerance = max(atr * 0.20, current_price * 0.00005)

        # Equal highs / equal lows
        eq_highs = 0
        eq_lows = 0
        for i in range(1, min(10, len(candles))):
            if abs(highs[-i] - highs[-i - 1]) <= tolerance:
                eq_highs += 1
            if abs(lows[-i] - lows[-i - 1]) <= tolerance:
                eq_lows += 1

        # Buy side / Sell side liquidity
        recent_high = max(highs[-5:]) if len(highs) >= 5 else max(highs)
        recent_low = min(lows[-5:]) if len(lows) >= 5 else min(lows)

        buy_side_liquidity = current_price < recent_high - tolerance
        sell_side_liquidity = current_price > recent_low + tolerance

        # Liquidity sweep detection
        sweep = False
        last_high, last_low = highs[-1], lows[-1]
        previous_high = max(highs[-6:-1]) if len(highs) >= 6 else recent_high
        previous_low = min(lows[-6:-1]) if len(lows) >= 6 else recent_low
        sweep_direction = "None"
        if last_high > previous_high + tolerance and current_price < previous_high:
            sweep, sweep_direction = True, "Buy Side Sweep"
        elif last_low < previous_low - tolerance and current_price > previous_low:
            sweep, sweep_direction = True, "Sell Side Sweep"

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
            "sweep_direction": sweep_direction,
            "atr": round(atr, 8),
            "equal_highs": eq_highs,
            "equal_lows": eq_lows,
        })

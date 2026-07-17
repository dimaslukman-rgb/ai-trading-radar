"""Market Structure Agent — identifies HH/HL, BOS, CHoCH, trend phase."""

from __future__ import annotations

from .base import AgentContext, AgentResult, BaseAgent


class MarketStructureAgent(BaseAgent):
    agent_id = "market_structure"

    def analyze(self, ctx: AgentContext) -> AgentResult:
        candles = ctx.candles
        if len(candles) < 20:
            return AgentResult(self.agent_id, {
                "market_structure": "Insufficient Data",
                "trend": "Unknown",
                "bos": "None",
                "choch": "None",
                "phase": "Unknown",
                "strength": 0,
                "summary": "Not enough candles to analyze structure"
            })

        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        closes = [c["close"] for c in candles]

        # Swing highs/lows
        swing_highs = []
        swing_lows = []
        for i in range(2, len(candles) - 2):
            if highs[i] > highs[i - 1] and highs[i] > highs[i - 2] and highs[i] > highs[i + 1] and highs[i] > highs[i + 2]:
                swing_highs.append((i, highs[i]))
            if lows[i] < lows[i - 1] and lows[i] < lows[i - 2] and lows[i] < lows[i + 1] and lows[i] < lows[i + 2]:
                swing_lows.append((i, lows[i]))

        # HH/HL detection
        recent_highs = [h for _, h in swing_highs[-5:]]
        recent_lows = [l for _, l in swing_lows[-5:]]

        hh = len(recent_highs) >= 2 and recent_highs[-1] > recent_highs[-2]
        hl = len(recent_lows) >= 2 and recent_lows[-1] > recent_lows[-2]
        lh = len(recent_highs) >= 2 and recent_highs[-1] < recent_highs[-2]
        ll = len(recent_lows) >= 2 and recent_lows[-1] < recent_lows[-2]

        # BOS (Break of Structure)
        bos = "None"
        if swing_highs and closes[-1] > max(h[-5:] for h in swing_highs[-3:] if h):
            bos = "Bullish"
        elif swing_lows and closes[-1] < min(l[-5:] for l in swing_lows[-3:] if l):
            bos = "Bearish"

        # CHoCH (Change of Character)
        choch = "None"
        if lh and hl:
            choch = "Bullish"
        elif hh and ll:
            choch = "Bearish"

        # Market phase
        ema_fast = sum(closes[-5:]) / 5 if len(closes) >= 5 else closes[-1]
        ema_slow = sum(closes[-20:]) / 20 if len(closes) >= 20 else closes[-1]
        price_vs_ema = closes[-1] - ema_slow

        if bos == "Bullish" and price_vs_ema > 0:
            phase = "Expansion" if abs(closes[-1] - closes[-5]) > abs(closes[-1] - closes[-5]) * 0.5 else "Bullish Trend"
        elif bos == "Bearish" and price_vs_ema < 0:
            phase = "Expansion" if abs(closes[-1] - closes[-5]) > abs(closes[-1] - closes[-5]) * 0.5 else "Bearish Trend"
        elif abs(price_vs_ema) < (ema_slow * 0.002):
            phase = "Range"
        elif hh and hl:
            phase = "Accumulation"
        elif lh and ll:
            phase = "Distribution"
        elif bos != "None":
            phase = "Expansion"
        else:
            phase = "Correction"

        # Determine overall structure
        if hh and hl:
            market_structure = "Bullish"
            trend = "HH HL"
        elif lh and ll:
            market_structure = "Bearish"
            trend = "LL LH"
        elif bos == "Bullish":
            market_structure = "Bullish"
            trend = "BOS Up"
        elif bos == "Bearish":
            market_structure = "Bearish"
            trend = "BOS Down"
        else:
            market_structure = "Range"
            trend = "Sideway"

        # Strength score
        strength = 50
        if hh and hl:
            strength += 25
        elif lh and ll:
            strength += 20
        if bos != "None":
            strength += 15
        if phase in ("Expansion", "Accumulation"):
            strength += 10
        strength = min(100, max(0, strength))

        return AgentResult(self.agent_id, {
            "market_structure": market_structure,
            "trend": trend,
            "bos": bos,
            "choch": choch,
            "phase": phase,
            "strength": strength,
            "summary": f"{market_structure} structure with {trend}, phase: {phase}"
        })

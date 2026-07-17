"""Volume Profile Agent — POC, VAH, VAL, HVN, LVN, acceptance/rejection."""

from __future__ import annotations

from .base import AgentContext, AgentResult, BaseAgent


class VolumeProfileAgent(BaseAgent):
    agent_id = "volume_profile"

    def analyze(self, ctx: AgentContext) -> AgentResult:
        candles = ctx.candles
        if len(candles) < 10:
            return AgentResult(self.agent_id, {
                "bias": "Neutral", "location": "Unknown",
                "volume_acceptance": False
            })

        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        closes = [c["close"] for c in candles]
        current_price = closes[-1]

        # Build volume profile (simplified: price levels divided into 10 zones)
        period_high = max(highs[-30:]) if len(highs) >= 30 else max(highs)
        period_low = min(lows[-30:]) if len(lows) >= 30 else min(lows)
        range_size = (period_high - period_low) or 1
        zone_height = range_size / 10

        zones = {i: {"touches": 0, "volume": 0} for i in range(10)}
        for c in candles[-30:]:
            for i in range(10):
                zone_low = period_low + (i * zone_height)
                zone_high = zone_low + zone_height
                if zone_low <= c["close"] <= zone_high:
                    candle_range = c["high"] - c["low"]
                    zones[i]["touches"] += 1
                    zones[i]["volume"] += candle_range
                    break

        # POC (Point of Control) = zone with most touches
        poc_zone = max(zones, key=lambda k: zones[k]["touches"])
        poc_price = period_low + (poc_zone * zone_height) + (zone_height / 2)

        # VAH / VAL (simple: top/bottom 30% of value area)
        sorted_zones = sorted(zones.items(), key=lambda x: x[1]["touches"], reverse=True)
        cumulative = 0
        total_touches = sum(v["touches"] for v in zones.values()) or 1
        value_area_zones = []
        for zone_idx, data in sorted_zones:
            cumulative += data["touches"]
            value_area_zones.append(zone_idx)
            if cumulative / total_touches >= 0.70:
                break

        if value_area_zones:
            vah = period_low + (max(value_area_zones) * zone_height) + zone_height
            val = period_low + (min(value_area_zones) * zone_height)
        else:
            vah = period_high
            val = period_low

        # HVN / LVN detection
        avg_volume = sum(v["volume"] for v in zones.values()) / max(len(zones), 1) or 1
        hvn_zones = [i for i in zones if zones[i]["volume"] > avg_volume * 1.5]
        lvn_zones = [i for i in zones if zones[i]["volume"] < avg_volume * 0.5]

        # Location relative to POC
        if current_price > poc_price + zone_height:
            location = "Above POC"
            if current_price > vah:
                location = "Above VAH"
        elif current_price < poc_price - zone_height:
            location = "Below POC"
            if current_price < val:
                location = "Below VAL"
        else:
            location = "At POC"

        # Volume acceptance
        current_zone = int((current_price - period_low) / zone_height)
        current_zone = min(9, max(0, current_zone))
        volume_acceptance = zones[current_zone]["volume"] > avg_volume

        # Bias
        if location in ("Below VAL", "Below POC") and volume_acceptance:
            bias = "Bullish"
        elif location in ("Above VAH", "Above POC") and volume_acceptance:
            bias = "Bearish"
        elif current_price < val and not volume_acceptance:
            bias = "Bullish"
        elif current_price > vah and not volume_acceptance:
            bias = "Bearish"
        else:
            bias = "Neutral"

        return AgentResult(self.agent_id, {
            "bias": bias,
            "location": location,
            "volume_acceptance": volume_acceptance,
        })

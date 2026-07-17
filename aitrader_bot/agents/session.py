"""Session Agent — trading session detection, kill zone, liquidity quality."""

from __future__ import annotations

from datetime import datetime, timezone

from .base import AgentContext, AgentResult, BaseAgent

# Session times in GMT
SESSION_TIMES = {
    "Sydney": (22, 7),
    "Tokyo": (0, 9),
    "London": (7, 16),
    "New York": (12, 21),
}

KILL_ZONES = {
    "London Open": (7, 9),
    "NY Open": (12, 14),
    "NY Close": (20, 22),
}

OVERLAPS = [
    ("Tokyo/London", 6, 8),
    ("London/NY", 12, 16),
    ("Sydney/Tokyo", 22, 7),
]


class SessionAgent(BaseAgent):
    agent_id = "session"

    def analyze(self, ctx: AgentContext) -> AgentResult:
        now = datetime.now(timezone.utc)
        current_hour = now.hour + now.minute / 60

        # Detect active sessions
        active = []
        for name, (start, end) in SESSION_TIMES.items():
            if start <= end:
                if start <= current_hour < end:
                    active.append(name)
            else:
                # Overnight session
                if current_hour >= start or current_hour < end:
                    active.append(name)

        # Detect overlaps
        overlap_name = None
        for name, start, end in OVERLAPS:
            if start <= end:
                if start <= current_hour < end:
                    overlap_name = name
                    break
            else:
                if current_hour >= start or current_hour < end:
                    overlap_name = name
                    break

        # Detect kill zone
        kill_zone = None
        for name, (start, end) in KILL_ZONES.items():
            if start <= current_hour < end:
                kill_zone = name
                break

        # Determine primary session
        if kill_zone:
            session = "Kill Zone"
        elif overlap_name:
            session = overlap_name
        elif active:
            session = active[0]
        else:
            session = "Off Hours"

        # Liquidity level
        if overlap_name:
            liquidity = "Very High"
        elif kill_zone:
            liquidity = "High"
        elif active:
            if active[0] in ("London", "New York"):
                liquidity = "High"
            else:
                liquidity = "Medium"
        else:
            liquidity = "Low"

        # Quality score
        quality = 0
        if liquidity == "Very High":
            quality = 90
        elif liquidity == "High":
            quality = 75
        elif liquidity == "Medium":
            quality = 50
        else:
            quality = 20

        if kill_zone:
            quality = min(100, quality + 10)

        return AgentResult(self.agent_id, {
            "session": session,
            "liquidity": liquidity,
            "quality": quality,
        })

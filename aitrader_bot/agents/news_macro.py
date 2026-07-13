"""News & Macro Agent — high-impact news, risk level, trade safety."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .base import AgentContext, AgentResult, BaseAgent

HIGH_IMPACT_EVENTS = [
    "NFP", "CPI", "PPI", "FOMC", "Interest Rate",
    "Powell Speech", "Central Bank", "GDP", "Unemployment",
    "ISM Manufacturing", "ISM Services", "Retail Sales",
]


class NewsMacroAgent(BaseAgent):
    agent_id = "news_macro"

    def analyze(self, ctx: AgentContext) -> AgentResult:
        events = ctx.macro_events or []

        # Check for high-impact news within 2 hours
        high_impact_found = False
        for event in events:
            name = event.get("name", event.get("title", ""))
            impact = event.get("impact", event.get("risk", "Low"))
            if impact in ("High", "Extreme"):
                for keyword in HIGH_IMPACT_EVENTS:
                    if keyword.lower() in name.lower():
                        high_impact_found = True
                        break

        # Risk level
        risk = "Low"
        if high_impact_found:
            risk = "High"
        elif ctx.news_risk:
            risk = ctx.news_risk

        # Trade allowed
        trade_allowed = not high_impact_found and risk not in ("High", "Extreme")

        return AgentResult(self.agent_id, {
            "high_impact_news": high_impact_found,
            "risk": risk,
            "trade_allowed": trade_allowed,
        })

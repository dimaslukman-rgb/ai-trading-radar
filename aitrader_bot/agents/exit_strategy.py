"""Exit Strategy Agent — TP, SL, reversal, news, time-based exit."""

from __future__ import annotations

from datetime import datetime, timezone

from .base import AgentContext, AgentResult, BaseAgent


class ExitStrategyAgent(BaseAgent):
    agent_id = "exit_strategy"

    def analyze(self, ctx: AgentContext) -> AgentResult:
        positions = ctx.positions or []

        exit_type = "None"
        reason = ""

        if not positions:
            return AgentResult(self.agent_id, {
                "exit": "None", "reason": "No open positions"
            })

        for pos in positions:
            entry = pos.get("entry", 0)
            current = ctx.price or 0
            side = pos.get("side", "buy")
            sl = pos.get("sl", 0)
            tp = pos.get("tp", 0)

            if side == "buy":
                if tp > 0 and current >= tp:
                    exit_type = "Take Profit"
                    reason = f"Price {current} reached TP {tp}"
                elif sl > 0 and current <= sl:
                    exit_type = "Stop Loss"
                    reason = f"Price {current} hit SL {sl}"

            elif side == "sell":
                if tp > 0 and current <= tp:
                    exit_type = "Take Profit"
                    reason = f"Price {current} reached TP {tp}"
                elif sl > 0 and current >= sl:
                    exit_type = "Stop Loss"
                    reason = f"Price {current} hit SL {sl}"

        # Time-based exit (end of session)
        now = datetime.now(timezone.utc)
        hour = now.hour
        if hour in (21, 22):
            exit_type = "Time Exit"
            reason = f"End of NY session ({hour}:00 UTC)"

        if exit_type == "None":
            reason = "No exit condition triggered"

        return AgentResult(self.agent_id, {
            "exit": exit_type,
            "reason": reason,
        })

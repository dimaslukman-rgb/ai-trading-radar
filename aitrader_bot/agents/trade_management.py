"""Trade Management Agent — trailing stop, break even, partial close, scale out."""

from __future__ import annotations

from .base import AgentContext, AgentResult, BaseAgent


class TradeManagementAgent(BaseAgent):
    agent_id = "trade_management"

    def analyze(self, ctx: AgentContext) -> AgentResult:
        positions = ctx.positions or []

        action = "Hold"
        new_sl = 0.0

        if not positions:
            return AgentResult(self.agent_id, {
                "action": "Hold", "new_sl": 0
            })

        for pos in positions:
            entry = pos.get("entry", 0)
            current = ctx.price or 0
            side = pos.get("side", "buy")
            sl = pos.get("sl", 0)

            if side == "buy" and entry > 0:
                profit_pct = (current - entry) / entry * 100

                if profit_pct >= 0.5:
                    # Break even
                    action = "Break Even"
                    new_sl = round(entry, 5)
                elif profit_pct >= 0.3:
                    # Trailing stop
                    action = "Trailing Stop"
                    new_sl = round(current * 0.997, 5)
                elif profit_pct >= 1.0:
                    # Take partial profit
                    action = "Partial Close"
                    new_sl = round(entry, 5)

            elif side == "sell" and entry > 0:
                profit_pct = (entry - current) / entry * 100

                if profit_pct >= 0.5:
                    action = "Break Even"
                    new_sl = round(entry, 5)
                elif profit_pct >= 0.3:
                    action = "Trailing Stop"
                    new_sl = round(current * 1.003, 5)
                elif profit_pct >= 1.0:
                    action = "Partial Close"
                    new_sl = round(entry, 5)

        return AgentResult(self.agent_id, {
            "action": action,
            "new_sl": new_sl,
        })

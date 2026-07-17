"""Trade Execution Agent — validates and executes orders."""

from __future__ import annotations

from .base import AgentContext, AgentResult, BaseAgent


class TradeExecutionAgent(BaseAgent):
    agent_id = "trade_execution"

    def analyze(self, ctx: AgentContext) -> AgentResult:
        spread = abs(ctx.ask - ctx.bid) if ctx.ask and ctx.bid else 0
        price = ctx.price or 0

        spread_ok = spread < price * 0.001 if price > 0 else True
        slippage_ok = True

        status = "Executed" if (spread_ok and slippage_ok) else "Rejected"
        ticket = "SIMULATED" if status == "Executed" else ""

        return AgentResult(self.agent_id, {
            "status": status,
            "ticket": ticket,
        })

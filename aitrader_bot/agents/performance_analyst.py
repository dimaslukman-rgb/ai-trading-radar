"""Performance Analyst Agent — win rate, profit factor, drawdown, grade."""

from __future__ import annotations

from .base import AgentContext, AgentResult, BaseAgent


class PerformanceAnalystAgent(BaseAgent):
    agent_id = "performance_analyst"

    def analyze(self, ctx: AgentContext) -> AgentResult:
        trades = ctx.trades_history or []

        if not trades:
            return AgentResult(self.agent_id, {
                "winrate": 0, "profit_factor": 1.0,
                "drawdown": 0, "grade": "Fair"
            })

        wins = sum(1 for t in trades if t.get("pnl", 0) > 0)
        losses = sum(1 for t in trades if t.get("pnl", 0) < 0)
        total = len(trades)

        winrate = int(wins / total * 100) if total > 0 else 0

        gross_profit = sum(t.get("pnl", 0) for t in trades if t.get("pnl", 0) > 0)
        gross_loss = abs(sum(t.get("pnl", 0) for t in trades if t.get("pnl", 0) < 0))
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else gross_profit

        # Max drawdown (simplified)
        peak = 0
        max_dd = 0
        running_pnl = 0
        for t in trades:
            running_pnl += t.get("pnl", 0)
            if running_pnl > peak:
                peak = running_pnl
            dd = peak - running_pnl
            if dd > max_dd:
                max_dd = dd

        balance = ctx.balance or 10000
        drawdown = round(max_dd / balance * 100, 1) if balance > 0 else 0

        # Grade
        if winrate >= 60 and profit_factor >= 2.0 and drawdown < 5:
            grade = "Excellent"
        elif winrate >= 50 and profit_factor >= 1.5 and drawdown < 10:
            grade = "Good"
        elif winrate >= 40 and profit_factor >= 1.0 and drawdown < 20:
            grade = "Fair"
        else:
            grade = "Poor"

        return AgentResult(self.agent_id, {
            "winrate": winrate,
            "profit_factor": profit_factor,
            "drawdown": drawdown,
            "grade": grade,
        })

"""Risk Manager Agent — per-trade risk, daily/weekly limits."""

from __future__ import annotations

from .base import AgentContext, AgentResult, BaseAgent

MAX_RISK_PER_TRADE_PCT = 0.5
MAX_DAILY_LOSS_PCT = 2.0
MAX_WEEKLY_LOSS_PCT = 5.0


class RiskManagerAgent(BaseAgent):
    agent_id = "risk_manager"

    def analyze(self, ctx: AgentContext) -> AgentResult:
        balance = ctx.balance or 10000
        equity = ctx.equity or balance

        # Calculate max risk amount
        max_risk_amount = balance * (MAX_RISK_PER_TRADE_PCT / 100)
        risk_percent = MAX_RISK_PER_TRADE_PCT

        # Check equity vs balance for daily loss
        daily_loss_pct = max(0, (balance - equity) / balance * 100) if balance > 0 else 0
        daily_limit_ok = daily_loss_pct < MAX_DAILY_LOSS_PCT

        # Weekly loss (simplified: use same daily check)
        weekly_loss_pct = daily_loss_pct
        weekly_limit_ok = weekly_loss_pct < MAX_WEEKLY_LOSS_PCT

        # Approval
        approved = daily_limit_ok and weekly_limit_ok

        reason = ""
        if not daily_limit_ok:
            reason = f"Daily loss {daily_loss_pct:.1f}% > {MAX_DAILY_LOSS_PCT}% limit"
        elif not weekly_limit_ok:
            reason = f"Weekly loss {weekly_loss_pct:.1f}% > {MAX_WEEKLY_LOSS_PCT}% limit"

        sl = ctx.price * 0.003  # 0.3% default SL
        tp = ctx.price * 0.006  # 0.6% default TP (1:2 RR)

        return AgentResult(self.agent_id, {
            "risk_percent": round(risk_percent, 2),
            "daily_limit_ok": daily_limit_ok,
            "approved": approved,
            "reason": reason,
            "sl": round(sl, 5),
            "tp": round(tp, 5),
        })

"""Position Sizing Agent — lot size, risk amount, margin check."""

from __future__ import annotations

from .base import AgentContext, AgentResult, BaseAgent


class PositionSizingAgent(BaseAgent):
    agent_id = "position_sizing"

    def analyze(self, ctx: AgentContext) -> AgentResult:
        balance = ctx.balance or 10000
        price = ctx.price or 100

        # Risk parameters
        risk_pct = 0.5  # 0.5% per trade
        sl_pips = 30  # 30 pips SL for XAUUSD
        pip_value = 0.01  # XAUUSD pip = 0.01
        lot_size_per_pip = 10  # standard lot = $10 per pip

        risk_amount = balance * (risk_pct / 100)

        # Lot size = risk_amount / (SL_pips * pip_value * lot_units)
        lot = risk_amount / (sl_pips * pip_value * lot_size_per_pip)
        lot = max(0.01, round(lot, 2))

        # Margin check (simplified)
        margin_per_lot = price * 100 * 0.01  # 1% margin
        required_margin = lot * margin_per_lot
        margin_ok = required_margin < balance * 0.5  # max 50% margin

        return AgentResult(self.agent_id, {
            "lot": lot,
            "risk_amount": round(risk_amount, 2),
            "margin_ok": margin_ok,
        })

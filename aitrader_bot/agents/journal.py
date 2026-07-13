"""Journal Agent — records trades, evaluates performance, generates reports."""

from __future__ import annotations

from datetime import datetime

from .base import AgentContext, AgentResult, BaseAgent

TRADE_LOG: list[dict] = []
JOURNAL_COUNTER = 0


class JournalAgent(BaseAgent):
    agent_id = "journal"

    def analyze(self, ctx: AgentContext) -> AgentResult:
        global JOURNAL_COUNTER

        positions = ctx.positions or []
        JOURNAL_COUNTER += 1

        # Record any new trades
        for pos in positions:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "symbol": ctx.symbol,
                "side": pos.get("side", "unknown"),
                "entry": pos.get("entry", 0),
                "lot": pos.get("quantity", 0),
                "sl": pos.get("sl", 0),
                "tp": pos.get("tp", 0),
            }
            if entry not in TRADE_LOG:
                TRADE_LOG.append(entry)

        # Analyze performance from trade history
        total_trades = len(TRADE_LOG)
        wins = sum(1 for t in TRADE_LOG if t.get("pnl", 0) > 0)
        losses = sum(1 for t in TRADE_LOG if t.get("pnl", 0) < 0)

        winrate = int(wins / total_trades * 100) if total_trades > 0 else 0

        grade = "A"
        if winrate >= 60:
            grade = "A"
        elif winrate >= 50:
            grade = "B"
        elif winrate >= 40:
            grade = "C"
        elif winrate >= 30:
            grade = "D"
        else:
            grade = "F"

        discipline = min(100, winrate + 20)

        return AgentResult(self.agent_id, {
            "journal_id": f"TRD{JOURNAL_COUNTER:03d}",
            "grade": grade,
            "discipline": discipline,
            "rule_violation": max(0, 5 - losses),
            "mistakes": ["Entered too early"] if losses > wins else [],
            "strengths": ["Following trend", "Good risk management"] if wins >= losses else [],
            "improvements": ["Wait for confirmation", "Tighter SL"] if losses > wins else [],
            "next_focus": "Patience" if losses > wins else "Scale management",
        })

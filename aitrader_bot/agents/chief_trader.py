"""Chief Trader — aggregates all agent outputs into a final decision."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .base import AgentContext, AgentResult, BaseAgent
from .performance_registry import PerformanceRegistry


@dataclass
class ChiefDecision:
    action: str = "HOLD"
    confidence: float = 0.0
    entry: float = 0.0
    sl: float = 0.0
    tp: float = 0.0
    lot: float = 0.0
    reason: str = ""
    agent_votes: dict[str, Any] = field(default_factory=dict)
    rejected_by: list[str] = field(default_factory=list)
    approved: bool = False


class ChiefTrader(BaseAgent):
    agent_id = "chief_trader"

    def __init__(self, performance_registry: PerformanceRegistry | None = None) -> None:
        super().__init__()
        self.agents: dict[str, BaseAgent] = {}
        self.performance_registry = performance_registry or PerformanceRegistry()

    def register(self, agent: BaseAgent) -> None:
        self.agents[agent.agent_id] = agent

    def analyze(self, ctx: AgentContext) -> AgentResult:
        results: dict[str, AgentResult] = {}
        for agent_id, agent in self.agents.items():
            results[agent_id] = agent.run(ctx)

        decision = self._decide(results, ctx)
        return AgentResult(
            agent_id=self.agent_id,
            output={
                "decision": decision.action,
                "confidence": decision.confidence,
                "entry": decision.entry,
                "sl": decision.sl,
                "tp": decision.tp,
                "lot": decision.lot,
                "reason": decision.reason,
                "approved": decision.approved,
                "agents_used": len(results),
                "rejected_by": decision.rejected_by,
                "agent_votes": {
                    aid: r.output for aid, r in results.items()
                },
                "agent_weights": {
                    aid: self.performance_registry.weight(aid) for aid in results
                },
            },
            confidence=decision.confidence,
        )

    def _decide(self, results: dict[str, AgentResult], ctx: AgentContext) -> ChiefDecision:
        decision = ChiefDecision()

        # 1. Risk Manager veto
        risk_result = results.get("risk_manager")
        if risk_result and risk_result.output.get("approved") is False:
            decision.rejected_by.append("risk_manager")
            decision.reason = risk_result.output.get("reason", "Risk manager rejected")
            return decision

        # 2. News & Macro veto
        news_result = results.get("news_macro")
        if news_result and news_result.output.get("trade_allowed") is False:
            decision.rejected_by.append("news_macro")
            decision.reason = f"News risk: {news_result.output.get('risk', 'High')}"
            return decision

        # 3. Volatility check — only block on Extreme volatility
        vol_result = results.get("volatility")
        vol_level = vol_result.output.get("volatility", "Normal") if vol_result else "Normal"
        if vol_level == "Extreme":
            decision.rejected_by.append("volatility")
            decision.reason = f"Volatility: Extreme"
            return decision

        # 4. Session check — only block extremely low quality (off hours)
        session_result = results.get("session")
        if session_result and session_result.output.get("quality", 50) < 5:
            decision.rejected_by.append("session")
            decision.reason = f"Session quality too low: {session_result.output.get('quality', 0)}"
            return decision

        # 5. Aggregate bias from analysis agents
        structure = results.get("market_structure", AgentResult("", {})).output
        trend = results.get("trend_analyst", AgentResult("", {})).output
        smc = results.get("smart_money", AgentResult("", {})).output
        liquidity = results.get("liquidity", AgentResult("", {})).output
        flow = results.get("order_flow", AgentResult("", {})).output
        pa = results.get("price_action", AgentResult("", {})).output
        indicator = results.get("indicator_confirmation", AgentResult("", {})).output

        bullish_score = 0.0
        bearish_score = 0.0
        total_weight = 0.0

        def weighted(agent_id: str, base_weight: float) -> float:
            return base_weight * self.performance_registry.weight(agent_id)

        # Market structure (weight: 3)
        weight = weighted("market_structure", 3)
        if structure.get("market_structure") in ("Bullish", "Accumulation", "Expansion"):
            bullish_score += weight
        elif structure.get("market_structure") in ("Bearish", "Distribution"):
            bearish_score += weight
        total_weight += weight

        # Trend alignment (weight: 3)
        weight = weighted("trend_analyst", 3)
        trend_overall = trend.get("overall", "Neutral")
        if trend_overall == "Bullish":
            bullish_score += weight
        elif trend_overall == "Bearish":
            bearish_score += weight
        total_weight += weight

        # SMC bias (weight: 2)
        weight = weighted("smart_money", 2)
        inst_bias = smc.get("institutional_bias", "Neutral")
        if inst_bias == "Bullish":
            bullish_score += weight
        elif inst_bias == "Bearish":
            bearish_score += weight
        total_weight += weight

        # Order flow (weight: 2)
        weight = weighted("order_flow", 2)
        flow_bias = flow.get("flow", "Neutral")
        if flow_bias == "Bullish":
            bullish_score += weight
        elif flow_bias == "Bearish":
            bearish_score += weight
        total_weight += weight

        # Price action (weight: 1)
        weight = weighted("price_action", 1)
        pattern = pa.get("pattern", "")
        if pattern and "Bullish" in pattern:
            bullish_score += weight
        elif pattern and "Bearish" in pattern:
            bearish_score += weight
        total_weight += weight

        # Indicator confirmation (weight: 2)
        weight = weighted("indicator_confirmation", 2)
        ind_bias = indicator.get("macd", "Neutral")
        if ind_bias in ("Bullish", "Crossing Up"):
            bullish_score += weight
        elif ind_bias in ("Bearish", "Crossing Down"):
            bearish_score += weight
        total_weight += weight

        # Entry strategy
        entry_result = results.get("entry_strategy")
        if entry_result and entry_result.output.get("quality", 0) > 0:
            decision.entry = entry_result.output.get("entry", ctx.price)
            decision.entry_type = entry_result.output.get("entry_type", "Market")

        # Position sizing
        sizing_result = results.get("position_sizing")
        if sizing_result:
            decision.lot = sizing_result.output.get("lot", 0.01)

        # Risk manager SL/TP
        if risk_result:
            decision.sl = risk_result.output.get("sl", 0)
            decision.tp = risk_result.output.get("tp", 0)

        # Final decision
        total_score = bullish_score - bearish_score
        max_score = total_weight or 1
        confidence_pct = abs(total_score) / max_score * 100

        if total_score > 0 and confidence_pct >= 10:
            decision.action = "BUY"
            decision.confidence = round(confidence_pct, 1)
            decision.reason = f"Bullish weighted bias ({bullish_score:.1f}-{bearish_score:.1f})"
            decision.approved = True
        elif total_score < 0 and confidence_pct >= 10:
            decision.action = "SELL"
            decision.confidence = round(confidence_pct, 1)
            decision.reason = f"Bearish weighted bias ({bullish_score:.1f}-{bearish_score:.1f})"
            decision.approved = True
        else:
            decision.action = "HOLD"
            decision.confidence = round(100 - confidence_pct, 1)
            decision.reason = f"Neutral / conflicting signals ({bullish_score:.1f}-{bearish_score:.1f})"

        # Correlation confirmation
        corr_result = results.get("correlation")
        if corr_result and corr_result.output.get("gold_bias") == "Bearish" and decision.action == "BUY":
            decision.confidence = max(0, decision.confidence - 15)
            decision.reason += "; gold bias conflict with correlation"
        elif corr_result and corr_result.output.get("gold_bias") == "Bullish" and decision.action == "SELL":
            decision.confidence = max(0, decision.confidence - 15)
            decision.reason += "; gold bias conflict with correlation"

        # Round entry price
        if ctx.point_size:
            decision.entry = round(decision.entry or ctx.price, 5)

        return decision

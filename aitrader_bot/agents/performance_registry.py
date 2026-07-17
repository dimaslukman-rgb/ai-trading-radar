"""Bounded, direction-aware performance scoring for the trading agents."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any


def _direction(output: dict[str, Any]) -> str | None:
    """Extract a directional vote from the heterogeneous agent outputs."""
    values = (
        output.get("overall"), output.get("market_structure"),
        output.get("institutional_bias"), output.get("flow"),
        output.get("macd"), output.get("bias"), output.get("decision"),
    )
    for value in values:
        text = str(value or "").lower()
        if "bull" in text or text in {"buy", "long", "crossing up"}:
            return "buy"
        if "bear" in text or text in {"sell", "short", "crossing down"}:
            return "sell"
    return None


@dataclass(frozen=True)
class AgentScore:
    resolved: int
    correct: int
    weight: float


class PerformanceRegistry:
    """Scores prior directional calls without persisting sensitive trade data.

    Each new price resolves the preceding prediction for that symbol.  Scores
    are bounded, start neutral, and never turn a vetoing risk agent into a
    signal generator.
    """

    def __init__(self, *, window: int = 40, min_weight: float = 0.5, max_weight: float = 1.5) -> None:
        self.window = max(5, window)
        self.min_weight = min_weight
        self.max_weight = max_weight
        self._history: dict[str, deque[bool]] = defaultdict(lambda: deque(maxlen=self.window))
        self._pending: dict[str, tuple[float, dict[str, str]]] = {}

    def settle(self, symbol: str, price: float) -> None:
        pending = self._pending.pop(symbol, None)
        if pending is None or price <= 0:
            return
        prior_price, votes = pending
        if prior_price <= 0 or price == prior_price:
            return
        actual = "buy" if price > prior_price else "sell"
        for agent_id, vote in votes.items():
            self._history[agent_id].append(vote == actual)

    def record(self, symbol: str, price: float, agent_votes: dict[str, dict[str, Any]]) -> None:
        votes = {
            agent_id: direction
            for agent_id, output in agent_votes.items()
            if (direction := _direction(output)) is not None
        }
        if votes and price > 0:
            self._pending[symbol] = (price, votes)

    def weight(self, agent_id: str) -> float:
        history = self._history[agent_id]
        if not history:
            return 1.0
        accuracy = sum(history) / len(history)
        # 50% remains neutral. Sparse observations are deliberately damped.
        confidence = min(1.0, len(history) / 10)
        raw = 1.0 + (accuracy - 0.5) * 2 * 0.5 * confidence
        return round(max(self.min_weight, min(self.max_weight, raw)), 3)

    def score(self, agent_id: str) -> AgentScore:
        history = self._history[agent_id]
        return AgentScore(len(history), sum(history), self.weight(agent_id))

    def snapshot(self) -> dict[str, dict[str, float | int]]:
        return {
            agent_id: {
                "resolved": score.resolved,
                "correct": score.correct,
                "accuracy_pct": round(score.correct / score.resolved * 100, 1) if score.resolved else 50.0,
                "weight": score.weight,
            }
            for agent_id in self._history
            if (score := self.score(agent_id))
        }

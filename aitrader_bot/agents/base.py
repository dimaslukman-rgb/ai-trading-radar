"""Base agent class for the institutional multi-agent trading system."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentResult:
    agent_id: str
    output: dict[str, Any]
    confidence: float = 1.0
    error: str | None = None


@dataclass
class AgentContext:
    symbol: str = ""
    price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    point_size: float = 0.00001
    candles: list[dict] = field(default_factory=list)
    daily_candles: list[dict] = field(default_factory=list)
    weekly_candles: list[dict] = field(default_factory=list)
    balance: float = 0.0
    equity: float = 0.0
    positions: list[dict] = field(default_factory=list)
    trades_history: list[dict] = field(default_factory=list)
    current_time: str = ""
    session_label: str = ""
    macro_events: list[dict] = field(default_factory=list)
    news_risk: str = "Low"


class BaseAgent(ABC):
    agent_id: str = "base"

    def __init__(self) -> None:
        self.last_result: AgentResult | None = None

    @abstractmethod
    def analyze(self, ctx: AgentContext) -> AgentResult:
        ...

    def run(self, ctx: AgentContext) -> AgentResult:
        try:
            result = self.analyze(ctx)
            self.last_result = result
            return result
        except Exception as e:
            result = AgentResult(
                agent_id=self.agent_id,
                output={"error": str(e)},
                confidence=0.0,
                error=str(e),
            )
            self.last_result = result
            return result

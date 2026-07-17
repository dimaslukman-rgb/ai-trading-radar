"""Optional, fail-closed Gemini macro sentiment enrichment."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote
from urllib.request import Request, urlopen

from .base import AgentContext, AgentResult, BaseAgent


class GeminiSentimentAgent(BaseAgent):
    """Ask Gemini for a concise macro narrative when explicitly configured.

    The agent never supplies an execution instruction.  Network/API failures
    return a neutral result so the local risk path stays deterministic.
    """

    agent_id = "gemini_sentiment"

    def __init__(self, api_key: str = "", model: str = "gemini-2.0-flash", timeout_seconds: float = 8.0) -> None:
        super().__init__()
        self.api_key = api_key.strip()
        self.model = model.strip() or "gemini-2.0-flash"
        self.timeout_seconds = max(1.0, float(timeout_seconds))

    def analyze(self, ctx: AgentContext) -> AgentResult:
        if not self.api_key:
            return AgentResult(self.agent_id, {
                "enabled": False, "bias": "NEUTRAL", "summary": "Gemini API key not configured.",
            }, confidence=0.0)

        events = [str(event.get("name", event.get("title", ""))) for event in ctx.macro_events[:5]]
        prompt = (
            f"Analyze macro sentiment for {ctx.symbol}. Price: {ctx.price}. "
            f"Upcoming events: {', '.join(events) or 'none'}. "
            "Return strict JSON only with bias (BULLISH, BEARISH, or NEUTRAL), "
            "risk_score (0-100), and summary (maximum 30 words). Do not give trading advice."
        )
        body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
        url = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{quote(self.model, safe='-._')}:generateContent?key={quote(self.api_key, safe='')}"
        )
        try:
            request = Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
            parsed = json.loads(text.strip().removeprefix("```json").removesuffix("```").strip())
            bias = str(parsed.get("bias", "NEUTRAL")).upper()
            if bias not in {"BULLISH", "BEARISH", "NEUTRAL"}:
                bias = "NEUTRAL"
            return AgentResult(self.agent_id, {
                "enabled": True,
                "bias": bias,
                "risk_score": max(0, min(100, int(parsed.get("risk_score", 50)))),
                "summary": str(parsed.get("summary", "No narrative returned."))[:280],
            }, confidence=0.6)
        except Exception as exc:
            return AgentResult(self.agent_id, {
                "enabled": True, "bias": "NEUTRAL", "risk_score": 50,
                "summary": f"Gemini unavailable: {type(exc).__name__}",
            }, confidence=0.0, error=str(exc))

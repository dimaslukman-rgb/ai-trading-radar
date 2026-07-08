from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass

from .models import Signal


@dataclass(frozen=True)
class AiTraderClient:
    token: str
    base_url: str = "https://ai4trade.ai/api"

    def publish_strategy(self, market: str, signal: Signal) -> dict:
        payload = {
            "market": market,
            "title": f"{signal.symbol} {signal.action.upper()} signal",
            "content": f"Action: {signal.action}. Confidence: {signal.confidence:.2f}. Reason: {signal.reason}",
            "symbols": [signal.symbol],
            "tags": ["ai-bot", "paper-trading"],
        }
        return self._post("/signals/strategy", payload)

    def _post(self, path: str, payload: dict) -> dict:
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json",
                "User-Agent": "ai-trading-bot/0.1",
            },
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

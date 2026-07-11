"""Risk gates, shared decisions, sizing, and protective price policy."""

from __future__ import annotations

from datetime import datetime

from ..decision import (
    DecisionPlan,
    TradingDecisionService,
    as_wib,
    compute_protective_prices,
    entry_safety_blocks,
    minutes_in_window,
)


def detect_sessions(now: datetime | None = None) -> dict[str, bool]:
    local = as_wib(now)
    current = local.hour * 60 + local.minute
    return {
        "sydney": minutes_in_window(current, 0, 9 * 60),
        "tokyo": minutes_in_window(current, 7 * 60, 16 * 60),
        "london": minutes_in_window(current, 13 * 60, 22 * 60),
        "new_york": minutes_in_window(current, 19 * 60 + 30, 4 * 60 + 30),
    }


def current_session_label(sessions: dict[str, bool]) -> str:
    active = [key for key, value in sessions.items() if value]
    if not active:
        return "Off-Hours"
    labels = {
        "sydney": "Sydney",
        "tokyo": "Tokyo",
        "london": "London",
        "new_york": "New York",
    }
    return ", ".join(labels.get(session, session.title()) for session in active)


class RiskService:
    """Facade over the common live/backtest decision and risk functions."""

    def __init__(self, config, position_machine) -> None:
        self.config = config
        self.decisions = TradingDecisionService(config, position_machine)

    def entry_blocks(
        self,
        quote,
        *,
        supports_attached_protection: bool,
        now: datetime | None = None,
        news_event: dict | None = None,
    ) -> list[str]:
        return entry_safety_blocks(
            self.config,
            quote,
            supports_attached_protection=supports_attached_protection,
            now=now,
            news_event=news_event,
        )

    def decide(
        self,
        signal_action: str,
        symbol: str,
        *,
        point_size: float | None,
        now: datetime,
        entry_block_reasons: list[str] | tuple[str, ...] = (),
        higher_timeframe_confirmed: bool = True,
        higher_timeframe_reason: str = "",
    ) -> DecisionPlan:
        return self.decisions.decide(
            signal_action,
            symbol,
            point_size=point_size,
            now=now,
            entry_block_reasons=entry_block_reasons,
            higher_timeframe_confirmed=higher_timeframe_confirmed,
            higher_timeframe_reason=higher_timeframe_reason,
        )

    def entry_quantity(self, balance: float, equity: float, price: float) -> float:
        return self.decisions.entry_quantity(balance, equity, price)

    def protective_prices(
        self,
        price: float,
        side: str,
        *,
        symbol: str,
        point_size: float | None,
    ) -> dict[str, float]:
        return compute_protective_prices(
            price,
            side,
            self.config,
            symbol=symbol,
            point_size=point_size,
        )

"""Risk gates, shared decisions, sizing, and protective price policy."""

from __future__ import annotations

from dataclasses import replace
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
        self._protection_config = config

    def set_market_atr(self, atr: float, point_size: float | None) -> dict[str, float | bool]:
        """Apply bounded ATR protection distances for the next order only.

        Disabled by default.  The method intentionally leaves the position
        state machine and exit rules unchanged; attached broker SL/TP remains
        the safety boundary for entries made with this mode enabled.
        """
        self._protection_config = self.config
        if not getattr(self.config, "atr_risk_enabled", False) or atr <= 0 or not point_size:
            return {"enabled": False, "atr": max(0.0, atr)}
        pip_value = point_size * 10
        if pip_value <= 0:
            return {"enabled": False, "atr": atr}
        atr_pips = atr / pip_value
        stop_pips = min(
            self.config.atr_max_stop_pips,
            max(self.config.atr_min_stop_pips, atr_pips * self.config.atr_stop_multiplier),
        )
        target_pips = max(stop_pips, atr_pips * self.config.atr_target_multiplier)
        self._protection_config = replace(
            self.config,
            stop_loss_pips=stop_pips,
            take_profit_pips=target_pips,
        )
        return {
            "enabled": True,
            "atr": atr,
            "atr_pips": round(atr_pips, 2),
            "stop_loss_pips": round(stop_pips, 2),
            "take_profit_pips": round(target_pips, 2),
        }

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
            self._protection_config,
            symbol=symbol,
            point_size=point_size,
        )

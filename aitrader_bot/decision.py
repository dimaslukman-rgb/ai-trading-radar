"""Shared trading decisions used by live execution, CLI, and backtests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from .position_state import (
    PositionAction,
    PositionActionType,
    PositionPhase,
    PositionStateMachine,
)
from .scalping import ScalpingRiskManager


WIB = timezone(timedelta(hours=7), name="WIB")


def minutes_in_window(current: int, start: int, end: int) -> bool:
    if start <= end:
        return start <= current < end
    return current >= start or current < end


def as_wib(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(WIB)
    if now.tzinfo is None:
        return now.replace(tzinfo=WIB)
    return now.astimezone(WIB)


def is_entry_session_open(config, now: datetime | None = None) -> bool:
    """Check configured entry sessions in WIB; exits are never gated."""
    if not config.session_filter_enabled:
        return True
    local = as_wib(now)
    current = local.hour * 60 + local.minute
    london_start = config.session_london_start * 60
    london_end = config.session_london_end * 60
    ny_start = config.session_ny_start * 60 + 30
    ny_end = config.session_ny_end * 60
    return (
        minutes_in_window(current, london_start, london_end)
        or minutes_in_window(current, ny_start, ny_end)
    )


def _check_circuit_breaker(
    config,
    daily_trade_count: int,
    daily_realized_pnl: float,
    equity: float,
    balance: float,
) -> str | None:
    """Check daily circuit breakers and return a block reason if triggered, else None.

    Checks:
      - daily_trade_cap: max completed trades per day
      - daily_loss_limit_pct: max realized loss as % of equity per day
    """
    # Trade count cap
    if config.daily_trade_cap > 0 and daily_trade_count >= config.daily_trade_cap:
        return f"daily trade cap reached ({daily_trade_count}/{config.daily_trade_cap})"

    # Daily loss limit
    if config.daily_loss_limit_pct > 0 and equity > 0:
        loss_pct = -daily_realized_pnl / equity
        if loss_pct >= config.daily_loss_limit_pct:
            return f"daily loss limit triggered ({loss_pct*100:.2f}% >= {config.daily_loss_limit_pct*100:.0f}%)"

    return None


def entry_safety_blocks(
    config,
    quote,
    *,
    supports_attached_protection: bool,
    now: datetime | None = None,
    news_event: dict | None = None,
    daily_trade_count: int = 0,
    daily_realized_pnl: float = 0.0,
    equity: float = 0.0,
    balance: float = 0.0,
) -> list[str]:
    """Return fail-closed reasons that prevent a new entry order."""
    blocks: list[str] = []

    # Daily circuit breakers
    circuit = _check_circuit_breaker(
        config,
        daily_trade_count,
        daily_realized_pnl,
        equity,
        balance,
    )
    if circuit:
        blocks.append(circuit)

    if not is_entry_session_open(config, now):
        blocks.append(f"outside trading session (WIB {as_wib(now):%H:%M})")
    if config.news_filter_enabled and news_event:
        blocks.append(f"news filter: {news_event['name']} ({news_event['phase']})")
    if config.max_spread_points > 0:
        spread_points = quote.spread_points
        if spread_points is None:
            blocks.append("spread point size unavailable")
        elif spread_points > config.max_spread_points:
            blocks.append(
                f"spread {spread_points:.1f}pts > max {config.max_spread_points:.1f}pts"
            )
    protection_required = config.stop_loss_pips > 0 or config.take_profit_pips > 0
    if protection_required and not supports_attached_protection:
        blocks.append("broker does not support attached SL/TP")
    return blocks


def higher_timeframe_confirmation(
    closes: list[float],
    signal_action: str,
) -> tuple[bool, str]:
    """Apply the shared EMA 9/21 strong-trend rejection rule."""
    from .indicators import ema

    if signal_action not in {"buy", "sell"} or len(closes) < 21:
        return True, ""
    ema_fast = ema(closes, 9)
    ema_slow = ema(closes, 21)
    latest = closes[-1]
    if ema_fast is None or ema_slow is None or latest <= 0:
        return True, ""
    divergence = abs(ema_fast - ema_slow) / latest * 100
    bullish = ema_fast > ema_slow
    if signal_action == "buy" and not bullish and divergence > 1.0:
        return False, f"M5 strongly bearish ({divergence:.2f}%), skip BUY"
    if signal_action == "sell" and bullish and divergence > 1.0:
        return False, f"M5 strongly bullish ({divergence:.2f}%), skip SELL"
    direction = "bullish" if bullish else "bearish"
    return True, f"M5 {direction} divergence {divergence:.2f}% -- ok"


def compute_protective_prices(
    price: float,
    action: str,
    config,
    symbol: str = "XAUUSD",
    point_size: float | None = None,
) -> dict[str, float]:
    """Compute entry, broker-side SL/TP, and reward/risk ratio."""
    sl_pips = config.stop_loss_pips
    tp_pips = config.take_profit_pips
    if point_size is not None and point_size > 0:
        pip_value = point_size * 10
        digits = max(0, -Decimal(str(point_size)).normalize().as_tuple().exponent)
    else:
        upper = symbol.upper()
        if "XAU" in upper or "GOLD" in upper:
            pip_value, digits = 0.1, 2
        elif "JPY" in upper:
            pip_value, digits = 0.01, 3
        else:
            pip_value, digits = 0.0001, 5
    if action in {"sell", "short"}:
        sl = round(price + sl_pips * pip_value, digits)
        tp = round(price - tp_pips * pip_value, digits)
    else:
        sl = round(price - sl_pips * pip_value, digits)
        tp = round(price + tp_pips * pip_value, digits)
    rr = round(tp_pips / sl_pips, 1) if sl_pips > 0 else 0.0
    return {"entry": price, "sl": sl, "tp": tp, "rr": rr}


@dataclass(frozen=True)
class DecisionPlan:
    actions: tuple[PositionAction, ...]
    risk_exit: bool = False
    entry_block_reasons: tuple[str, ...] = ()
    circuit_breaker_reason: str | None = None


class TradingDecisionService:
    """Single source of truth for risk exits and signal-driven position actions."""

    def __init__(self, config, position_machine: PositionStateMachine) -> None:
        self.config = config
        self.position_machine = position_machine
        self.risk_manager = ScalpingRiskManager(config)

        # Daily stats for circuit breaker (reset at midnight WIB)
        self._daily_trade_count: int = 0
        self._daily_realized_pnl: float = 0.0
        self._daily_reset_date: str | None = None

    def _reset_daily_if_needed(self, now: datetime | None = None) -> None:
        """Reset daily counters at midnight WIB."""
        local = as_wib(now)
        today = local.strftime("%Y-%m-%d")
        if self._daily_reset_date != today:
            self._daily_trade_count = 0
            self._daily_realized_pnl = 0.0
            self._daily_reset_date = today

    def record_closed_trade(self, pnl: float) -> None:
        """Record a closed trade for daily tracking."""
        self._reset_daily_if_needed()
        self._daily_trade_count += 1
        self._daily_realized_pnl += pnl

    def daily_stats(self) -> tuple[int, float]:
        """Return (trade_count, realized_pnl) for today."""
        self._reset_daily_if_needed()
        return self._daily_trade_count, self._daily_realized_pnl

    def entry_quantity(
        self,
        balance: float,
        equity: float,
        price: float,
    ) -> float:
        quantity = self.risk_manager.buy_quantity(balance, equity, price)
        if self.config.aggressive_mode and quantity < 0.05:
            max_by_equity = balance * self.config.max_trade_pct / price
            quantity = max(0.05, min(max_by_equity, balance * 0.05 / price))
        return quantity if quantity > 0 else 0.01

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
        equity: float = 0.0,
        balance: float = 0.0,
    ) -> DecisionPlan:
        self._reset_daily_if_needed(now)

        risk_actions: list[PositionAction] = []
        for position in self.position_machine.active_positions(symbol):
            if position.phase == PositionPhase.CLOSING:
                continue
            reason = self.risk_manager.forced_exit_reason(
                position.avg_price,
                position.current_price,
                entry_time=position.opened_at,
                current_time=now,
                side=position.side.value,
                point_size=point_size,
            )
            if reason:
                risk_actions.append(PositionAction(
                    PositionActionType.CLOSE,
                    symbol,
                    side=position.side,
                    ticket=position.ticket,
                    quantity=position.quantity,
                    reason=reason,
                ))
        if risk_actions:
            return DecisionPlan(tuple(risk_actions), risk_exit=True)

        blockers = list(entry_block_reasons)
        if not higher_timeframe_confirmed:
            blockers.append(higher_timeframe_reason or "higher timeframe rejected entry")

        # Pre-entry circuit breaker check
        circuit = _check_circuit_breaker(
            self.config,
            self._daily_trade_count,
            self._daily_realized_pnl,
            equity,
            balance,
        )
        if circuit:
            blockers.append(circuit)

        actions = self.position_machine.plan_signal(
            signal_action,
            symbol,
            entry_allowed=not blockers,
            entry_block_reason="; ".join(blockers),
        )
        return DecisionPlan(
            tuple(actions),
            entry_block_reasons=tuple(blockers),
            circuit_breaker_reason=circuit,
        )

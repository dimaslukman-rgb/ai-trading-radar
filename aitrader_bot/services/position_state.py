"""Broker-authoritative position synchronization service."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ..broker.base import PositionInfo
from ..position_state import (
    ManagedPosition,
    PositionSide,
    PositionStateMachine,
    SyncResult,
)


def position_entry_time(position) -> datetime | None:
    """Normalize a broker position timestamp to aware UTC."""
    opened_at = getattr(position, "opened_at", None)
    if opened_at is None:
        return None
    if opened_at.tzinfo is None:
        return opened_at.replace(tzinfo=timezone.utc)
    return opened_at.astimezone(timezone.utc)


def dashboard_position_rows(
    positions: list[ManagedPosition] | tuple[ManagedPosition, ...],
    point_size: float | None,
) -> list[dict]:
    pip_value = point_size * 10 if point_size else 0.1
    rows: list[dict] = []
    for position in positions:
        price_diff = position.current_price - position.avg_price
        if position.side == PositionSide.SHORT:
            price_diff *= -1
        pnl_pips = price_diff / pip_value if pip_value > 0 else 0.0
        rows.append({
            "ticket": position.ticket,
            "symbol": position.symbol,
            "side": position.side.name,
            "qty": round(position.quantity, 4),
            "entry": round(position.avg_price, 5),
            "current": round(position.current_price, 5),
            "pnl": round(position.unrealized_pnl, 2),
            "pnl_pips": round(pnl_pips, 1),
            "opened_at": position.opened_at.isoformat() if position.opened_at else None,
            "sl": position.stop_loss,
            "tp": position.take_profit,
            "phase": position.phase.value,
            "last_error": position.last_error,
        })
    return rows


@dataclass(frozen=True)
class PositionSnapshot:
    broker_positions: tuple[PositionInfo, ...]
    managed_positions: tuple[ManagedPosition, ...]
    sync_result: SyncResult
    earliest_entry_time: datetime | None


class PositionStateService:
    """Own synchronization between broker positions and the state machine."""

    def __init__(self, broker, symbol: str, machine: PositionStateMachine) -> None:
        self.broker = broker
        self.symbol = symbol
        self.machine = machine

    @classmethod
    def from_config(cls, broker, symbol: str, config) -> "PositionStateService":
        machine = PositionStateMachine.from_config(
            config,
            broker_supports_short=broker.supports_short_positions,
            broker_supports_multiple=broker.supports_multiple_positions,
        )
        return cls(broker, symbol, machine)

    def sync(self) -> PositionSnapshot:
        broker_positions = tuple(self.broker.get_positions(self.symbol))
        sync_result = self.machine.sync(list(broker_positions))
        managed = tuple(self.machine.active_positions(self.symbol))
        opened = [
            normalized
            for position in managed
            if (normalized := position_entry_time(position)) is not None
        ]
        return PositionSnapshot(
            broker_positions,
            managed,
            sync_result,
            min(opened) if opened else None,
        )

    def dashboard_rows(self, point_size: float | None) -> list[dict]:
        return dashboard_position_rows(
            self.machine.active_positions(self.symbol),
            point_size,
        )

"""Broker-authoritative position state and entry/exit planning."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

from .broker.base import OrderResult, OrderStatus, PositionInfo


class PositionSide(str, Enum):
    LONG = "buy"
    SHORT = "sell"


class PositionPhase(str, Enum):
    OPEN = "open"
    CLOSING = "closing"
    CLOSED = "closed"


class PositionActionType(str, Enum):
    OPEN_LONG = "open_long"
    OPEN_SHORT = "open_short"
    CLOSE = "close"
    HOLD = "hold"


@dataclass(frozen=True)
class ManagedPosition:
    ticket: str
    symbol: str
    side: PositionSide
    quantity: float
    avg_price: float
    current_price: float
    unrealized_pnl: float
    opened_at: datetime | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    phase: PositionPhase = PositionPhase.OPEN
    last_error: str = ""


@dataclass(frozen=True)
class PositionAction:
    action: PositionActionType
    symbol: str
    side: PositionSide | None = None
    ticket: str = ""
    quantity: float = 0.0
    reason: str = ""


@dataclass(frozen=True)
class PositionPolicy:
    allow_long_entries: bool = True
    allow_short_entries: bool = True
    max_open_positions: int = 1
    max_positions_per_side: int = 1
    allow_scale_in: bool = False
    hedging_enabled: bool = False
    close_on_opposite_signal: bool = True
    opposite_exit_only_in_profit: bool = True


@dataclass(frozen=True)
class SyncResult:
    opened: tuple[str, ...] = ()
    updated: tuple[str, ...] = ()
    closed: tuple[str, ...] = ()


@dataclass(frozen=True)
class PendingEntry:
    order_id: str
    symbol: str
    side: PositionSide
    quantity: float
    created_at: datetime
    baseline_count: int
    baseline_quantity: float


def normalize_position_side(side: str | PositionSide, quantity: float = 0.0) -> PositionSide:
    if isinstance(side, PositionSide):
        return side
    value = str(side or "").strip().lower()
    if value in {"sell", "short"} or (not value and quantity < 0):
        return PositionSide.SHORT
    return PositionSide.LONG


class PositionStateMachine:
    """Tracks broker positions and produces deterministic trading actions."""

    def __init__(
        self,
        policy: PositionPolicy,
        *,
        broker_supports_short: bool,
        broker_supports_multiple: bool,
    ) -> None:
        self.policy = policy
        self.broker_supports_short = broker_supports_short
        self.broker_supports_multiple = broker_supports_multiple
        self._active: dict[str, ManagedPosition] = {}
        self._closed: dict[str, ManagedPosition] = {}
        self._pending_entries: dict[str, PendingEntry] = {}

    @classmethod
    def from_config(
        cls,
        config,
        *,
        broker_supports_short: bool,
        broker_supports_multiple: bool,
    ) -> "PositionStateMachine":
        return cls(
            PositionPolicy(
                allow_long_entries=config.allow_long_entries,
                allow_short_entries=config.allow_short_entries,
                max_open_positions=max(1, config.max_open_positions),
                max_positions_per_side=max(1, config.max_positions_per_side),
                allow_scale_in=config.allow_scale_in,
                hedging_enabled=config.hedging_enabled,
                close_on_opposite_signal=config.close_on_opposite_signal,
                opposite_exit_only_in_profit=config.opposite_exit_only_in_profit,
            ),
            broker_supports_short=broker_supports_short,
            broker_supports_multiple=broker_supports_multiple,
        )

    def sync(self, broker_positions: list[PositionInfo]) -> SyncResult:
        seen: set[str] = set()
        opened: list[str] = []
        updated: list[str] = []

        for index, position in enumerate(broker_positions):
            ticket = position.ticket or f"{position.symbol}:{index}"
            seen.add(ticket)
            managed = ManagedPosition(
                ticket=ticket,
                symbol=position.symbol,
                side=normalize_position_side(position.side, position.quantity),
                quantity=abs(position.quantity),
                avg_price=position.avg_price,
                current_price=position.current_price,
                unrealized_pnl=position.unrealized_pnl,
                opened_at=position.opened_at,
                stop_loss=position.stop_loss,
                take_profit=position.take_profit,
            )
            if ticket in self._active:
                previous = self._active[ticket]
                self._active[ticket] = replace(
                    managed,
                    phase=(
                        PositionPhase.CLOSING
                        if previous.phase == PositionPhase.CLOSING
                        else PositionPhase.OPEN
                    ),
                    last_error=previous.last_error if previous.phase == PositionPhase.CLOSING else "",
                )
                updated.append(ticket)
            else:
                self._active[ticket] = managed
                opened.append(ticket)
            self._closed.pop(ticket, None)

        closed: list[str] = []
        for ticket in tuple(self._active):
            if ticket in seen:
                continue
            position = replace(self._active.pop(ticket), phase=PositionPhase.CLOSED)
            self._closed[ticket] = position
            closed.append(ticket)

        for order_id, pending in tuple(self._pending_entries.items()):
            matching = self.active_positions(pending.symbol, pending.side)
            total_quantity = sum(position.quantity for position in matching)
            if (
                len(matching) > pending.baseline_count
                or total_quantity > pending.baseline_quantity + 1e-12
            ):
                del self._pending_entries[order_id]

        return SyncResult(tuple(opened), tuple(updated), tuple(closed))

    def active_positions(
        self,
        symbol: str | None = None,
        side: PositionSide | None = None,
    ) -> list[ManagedPosition]:
        positions = list(self._active.values())
        if symbol is not None:
            positions = [p for p in positions if p.symbol == symbol]
        if side is not None:
            positions = [p for p in positions if p.side == side]
        return sorted(
            positions,
            key=lambda p: (
                p.opened_at.timestamp() if p.opened_at is not None else float("-inf"),
                p.ticket,
            ),
        )

    def closed_positions(self) -> list[ManagedPosition]:
        return list(self._closed.values())

    def get(self, ticket: str) -> ManagedPosition | None:
        return self._active.get(ticket) or self._closed.get(ticket)

    def pending_entries(self, symbol: str | None = None) -> list[PendingEntry]:
        entries = list(self._pending_entries.values())
        if symbol is not None:
            entries = [entry for entry in entries if entry.symbol == symbol]
        return entries

    def record_entry_result(
        self,
        symbol: str,
        side: PositionSide,
        result: OrderResult | None,
    ) -> None:
        if result is None or result.status != OrderStatus.PENDING:
            return
        order_id = result.order_id or f"pending:{symbol}:{side.value}"
        matching = self.active_positions(symbol, side)
        self._pending_entries[order_id] = PendingEntry(
            order_id=order_id,
            symbol=symbol,
            side=side,
            quantity=abs(result.quantity),
            created_at=result.timestamp,
            baseline_count=len(matching),
            baseline_quantity=sum(position.quantity for position in matching),
        )

    def plan_signal(
        self,
        signal_action: str,
        symbol: str,
        *,
        entry_allowed: bool,
        entry_block_reason: str = "",
    ) -> list[PositionAction]:
        action = signal_action.strip().lower()
        if action not in {"buy", "sell"}:
            return [PositionAction(PositionActionType.HOLD, symbol, reason="no actionable signal")]

        target_side = PositionSide.LONG if action == "buy" else PositionSide.SHORT
        opposite_side = PositionSide.SHORT if target_side == PositionSide.LONG else PositionSide.LONG
        opposing = self.active_positions(symbol, opposite_side)

        if any(position.phase == PositionPhase.CLOSING for position in opposing):
            return [PositionAction(
                PositionActionType.HOLD,
                symbol,
                reason="opposite position close is still pending",
            )]

        must_resolve_opposite = bool(opposing) and (
            self.policy.close_on_opposite_signal or not self.policy.hedging_enabled
        )
        if must_resolve_opposite:
            if not self.policy.close_on_opposite_signal:
                return [PositionAction(
                    PositionActionType.HOLD,
                    symbol,
                    reason="opposite position exists and hedging is disabled",
                )]
            closable = [p for p in opposing if p.phase == PositionPhase.OPEN]
            if self.policy.opposite_exit_only_in_profit:
                closable = [p for p in opposing if p.unrealized_pnl > 0]
            if not closable:
                return [PositionAction(
                    PositionActionType.HOLD,
                    symbol,
                    reason="opposite positions are not profitable enough to close",
                )]
            return [
                PositionAction(
                    PositionActionType.CLOSE,
                    symbol,
                    side=position.side,
                    ticket=position.ticket,
                    quantity=position.quantity,
                    reason=f"opposite {action} signal",
                )
                for position in closable
            ]

        if not entry_allowed:
            return [PositionAction(
                PositionActionType.HOLD,
                symbol,
                side=target_side,
                reason=entry_block_reason or "new entries are blocked",
            )]

        if any(
            pending.symbol == symbol and pending.side == target_side
            for pending in self._pending_entries.values()
        ):
            return [PositionAction(
                PositionActionType.HOLD,
                symbol,
                target_side,
                reason="entry order is still pending",
            )]

        if target_side == PositionSide.LONG and not self.policy.allow_long_entries:
            return [PositionAction(PositionActionType.HOLD, symbol, target_side, reason="long entries disabled")]
        if target_side == PositionSide.SHORT:
            if not self.policy.allow_short_entries:
                return [PositionAction(PositionActionType.HOLD, symbol, target_side, reason="short entries disabled")]
            if not self.broker_supports_short:
                return [PositionAction(PositionActionType.HOLD, symbol, target_side, reason="broker does not support shorts")]

        same_side = self.active_positions(symbol, target_side)
        if same_side and not self.policy.allow_scale_in:
            return [PositionAction(PositionActionType.HOLD, symbol, target_side, reason="scale-in disabled")]

        total = self.active_positions(symbol)
        if len(total) >= self.policy.max_open_positions:
            return [PositionAction(PositionActionType.HOLD, symbol, target_side, reason="max open positions reached")]
        if len(same_side) >= self.policy.max_positions_per_side:
            return [PositionAction(PositionActionType.HOLD, symbol, target_side, reason="max positions per side reached")]
        if total and not self.broker_supports_multiple:
            return [PositionAction(PositionActionType.HOLD, symbol, target_side, reason="broker supports one net position")]

        action_type = (
            PositionActionType.OPEN_LONG
            if target_side == PositionSide.LONG
            else PositionActionType.OPEN_SHORT
        )
        return [PositionAction(action_type, symbol, target_side, reason=f"{action} entry signal")]

    def mark_closing(self, ticket: str) -> None:
        position = self._active.get(ticket)
        if position is not None:
            self._active[ticket] = replace(position, phase=PositionPhase.CLOSING, last_error="")

    def apply_close_result(self, ticket: str, result: OrderResult | None) -> PositionPhase:
        position = self._active.get(ticket)
        if position is None:
            return PositionPhase.CLOSED
        if result is None:
            self._active[ticket] = replace(position, phase=PositionPhase.OPEN, last_error="broker returned no result")
            return PositionPhase.OPEN

        filled = min(abs(result.filled_qty), position.quantity)
        if result.status == OrderStatus.FILLED and filled + 1e-12 >= position.quantity:
            closed = replace(position, phase=PositionPhase.CLOSED, quantity=0.0, last_error="")
            self._closed[ticket] = closed
            del self._active[ticket]
            return PositionPhase.CLOSED
        if result.status == OrderStatus.PARTIAL and filled > 0:
            self._active[ticket] = replace(
                position,
                quantity=position.quantity - filled,
                phase=PositionPhase.OPEN,
                last_error=f"partial close {filled:.4f}/{position.quantity:.4f}",
            )
            return PositionPhase.OPEN
        if result.status == OrderStatus.PENDING:
            self._active[ticket] = replace(position, phase=PositionPhase.CLOSING)
            return PositionPhase.CLOSING

        self._active[ticket] = replace(
            position,
            phase=PositionPhase.OPEN,
            last_error=result.message,
        )
        return PositionPhase.OPEN

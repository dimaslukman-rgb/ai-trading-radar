"""Broker execution and order-result reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..broker import OrderSide, OrderStatus
from ..broker.base import OrderResult
from ..position_state import (
    ManagedPosition,
    PositionAction,
    PositionActionType,
    PositionPhase,
    PositionSide,
)
from .position_state import PositionStateService
from .risk import RiskService


def is_close_complete(result, expected_quantity: float) -> bool:
    return bool(
        result is not None
        and result.status == OrderStatus.FILLED
        and abs(result.filled_qty) + 1e-12 >= abs(expected_quantity)
    )


def order_result_detail(result, expected_quantity: float) -> str:
    expected = abs(expected_quantity)
    if result is None:
        return f"status=missing filled=0.0000/{expected:.4f} | broker returned no result"
    return (
        f"status={result.status.value} filled={abs(result.filled_qty):.4f}/"
        f"{expected:.4f} | {result.message}"
    )


def contract_size(symbol: str) -> int:
    upper = symbol.upper()
    if "XAU" in upper or "GOLD" in upper:
        return 100
    if "XAG" in upper or "SILVER" in upper:
        return 5000
    if "JPY" in upper:
        return 1000
    if any(asset in upper for asset in ("BTC", "ETH", "XRP")):
        return 1
    return 100000


def compute_dollar_pnl(
    symbol: str,
    entry_price: float,
    exit_price: float,
    quantity: float,
    side: str = "buy",
) -> float:
    difference = exit_price - entry_price
    if side.lower() in {"sell", "short"}:
        difference *= -1
    return difference * quantity * contract_size(symbol)


class ExecutionKind(str, Enum):
    HOLD = "hold"
    OPENED = "opened"
    ENTRY_PENDING = "entry_pending"
    ENTRY_REJECTED = "entry_rejected"
    CLOSED = "closed"
    CLOSE_UNCONFIRMED = "close_unconfirmed"


@dataclass(frozen=True)
class ExecutionOutcome:
    kind: ExecutionKind
    action: PositionAction
    message: str
    result: OrderResult | None = None
    position: ManagedPosition | None = None
    side: PositionSide | None = None
    quantity: float = 0.0
    price: float = 0.0
    pnl: float = 0.0


@dataclass(frozen=True)
class ExecutionBatch:
    outcomes: tuple[ExecutionOutcome, ...]
    state_changed: bool = False
    refresh_error: str = ""


@dataclass(frozen=True)
class ProtectionRepairOutcome:
    ticket: str
    quantity: float
    success: bool
    message: str
    result: OrderResult | None = None


class ExecutionService:
    """Execute planned actions and reconcile them through position state."""

    def __init__(
        self,
        broker,
        symbol: str,
        display_symbol: str,
        position_state: PositionStateService,
        risk: RiskService,
    ) -> None:
        self.broker = broker
        self.symbol = symbol
        self.display_symbol = display_symbol
        self.position_state = position_state
        self.risk = risk
        self._protection_failures: set[str] = set()

    def repair_missing_protection(
        self,
        broker_positions: tuple | list,
        point_size: float | None,
    ) -> list[ProtectionRepairOutcome]:
        if not self.broker.supports_attached_protection:
            return []
        outcomes: list[ProtectionRepairOutcome] = []
        for position in broker_positions:
            needs_sl = self.risk.config.stop_loss_pips > 0 and position.stop_loss is None
            needs_tp = self.risk.config.take_profit_pips > 0 and position.take_profit is None
            if not (needs_sl or needs_tp):
                continue
            side = (getattr(position, "side", "") or "buy").lower()
            side = "sell" if side in {"sell", "short"} else "buy"
            desired = self.risk.protective_prices(
                position.avg_price,
                side,
                symbol=self.display_symbol,
                point_size=point_size,
            )
            result = self.broker.set_position_protection(
                position.ticket,
                desired["sl"] if needs_sl else position.stop_loss,
                desired["tp"] if needs_tp else position.take_profit,
            )
            success = result is not None and result.status == OrderStatus.FILLED
            if success:
                self._protection_failures.discard(position.ticket)
                outcomes.append(ProtectionRepairOutcome(
                    position.ticket,
                    abs(position.quantity),
                    True,
                    f"Recovered broker-side SL/TP for position {position.ticket}",
                    result,
                ))
            elif position.ticket not in self._protection_failures:
                self._protection_failures.add(position.ticket)
                detail = order_result_detail(result, position.quantity)
                outcomes.append(ProtectionRepairOutcome(
                    position.ticket,
                    abs(position.quantity),
                    False,
                    f"Failed to restore SL/TP for position {position.ticket}: {detail}",
                    result,
                ))
        return outcomes

    def execute(
        self,
        actions: tuple[PositionAction, ...] | list[PositionAction],
        quote,
        signal_reason: str,
    ) -> ExecutionBatch:
        outcomes: list[ExecutionOutcome] = []
        state_changed = False
        for action in actions:
            if action.action == PositionActionType.HOLD:
                outcomes.append(ExecutionOutcome(
                    ExecutionKind.HOLD,
                    action,
                    f"HOLD {self.symbol} @ {quote.last:.5f} | {action.reason}",
                    price=quote.last,
                    side=action.side,
                ))
                continue
            if action.action == PositionActionType.CLOSE:
                outcome = self._close(action)
            else:
                outcome = self._open(action, quote, signal_reason)
            outcomes.append(outcome)
            if outcome.kind in {
                ExecutionKind.OPENED,
                ExecutionKind.CLOSED,
                ExecutionKind.CLOSE_UNCONFIRMED,
            }:
                state_changed = True

        refresh_error = ""
        if state_changed:
            try:
                self.position_state.sync()
            except Exception as exc:
                refresh_error = str(exc)
        return ExecutionBatch(tuple(outcomes), state_changed, refresh_error)

    def _close(self, action: PositionAction) -> ExecutionOutcome:
        position = self.position_state.machine.get(action.ticket)
        if position is None:
            message = f"CLOSE OPEN {action.ticket} ({action.reason}) | position not found"
            return ExecutionOutcome(
                ExecutionKind.CLOSE_UNCONFIRMED,
                action,
                message,
                side=action.side,
                quantity=action.quantity,
            )
        self.position_state.machine.mark_closing(position.ticket)
        result = self.broker.close_position(position.ticket)
        phase = self.position_state.machine.apply_close_result(position.ticket, result)
        pnl = compute_dollar_pnl(
            self.display_symbol,
            position.avg_price,
            position.current_price,
            position.quantity,
            position.side.value,
        )
        if phase == PositionPhase.CLOSED:
            message = (
                f"CLOSED {position.side.name} {position.ticket} {position.quantity:.4f} "
                f"{self.symbol} @ {position.current_price:.5f} P&L=${pnl:+.2f} | {action.reason}"
            )
            kind = ExecutionKind.CLOSED
        else:
            message = (
                f"CLOSE {phase.value.upper()} {position.ticket} ({action.reason}) | "
                f"{order_result_detail(result, position.quantity)}"
            )
            kind = ExecutionKind.CLOSE_UNCONFIRMED
        return ExecutionOutcome(
            kind,
            action,
            message,
            result=result,
            position=position,
            side=position.side,
            quantity=position.quantity,
            price=position.current_price,
            pnl=pnl,
        )

    def _open(self, action: PositionAction, quote, signal_reason: str) -> ExecutionOutcome:
        side = (
            PositionSide.LONG
            if action.action == PositionActionType.OPEN_LONG
            else PositionSide.SHORT
        )
        order_side = OrderSide.BUY if side == PositionSide.LONG else OrderSide.SELL
        entry_price = quote.ask if side == PositionSide.LONG else quote.bid
        try:
            account = self.broker.get_account()
            balance, equity = account.balance, account.equity
        except Exception:
            balance = equity = 10000.0
        quantity = self.risk.entry_quantity(balance, equity, entry_price)
        protection = self.risk.protective_prices(
            entry_price,
            side.value,
            symbol=self.display_symbol,
            point_size=quote.point_size,
        )
        result = self.broker.place_order(
            self.symbol,
            order_side,
            quantity,
            stop_loss=(
                protection["sl"] if self.risk.config.stop_loss_pips > 0 else None
            ),
            take_profit=(
                protection["tp"] if self.risk.config.take_profit_pips > 0 else None
            ),
        )
        self.position_state.machine.record_entry_result(self.symbol, side, result)
        if (
            result is not None
            and result.status in {OrderStatus.FILLED, OrderStatus.PARTIAL}
            and result.filled_qty > 0
        ):
            price = result.avg_fill_price or entry_price
            return ExecutionOutcome(
                ExecutionKind.OPENED,
                action,
                f"OPENED {side.name} {result.filled_qty:.4f} {self.symbol} "
                f"@ {price:.5f} | {signal_reason}",
                result=result,
                side=side,
                quantity=result.filled_qty,
                price=price,
            )
        if result is not None and result.status == OrderStatus.PENDING:
            return ExecutionOutcome(
                ExecutionKind.ENTRY_PENDING,
                action,
                f"ENTRY PENDING {side.name} {self.symbol} | {result.message}",
                result=result,
                side=side,
                quantity=quantity,
                price=entry_price,
            )
        return ExecutionOutcome(
            ExecutionKind.ENTRY_REJECTED,
            action,
            f"ENTRY REJECTED {side.name} {self.symbol} | "
            f"{order_result_detail(result, quantity)}",
            result=result,
            side=side,
            quantity=quantity,
            price=entry_price,
        )

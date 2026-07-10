"""Tests for explicit long/short and multi-ticket position state."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from aitrader_bot.broker.base import (
    ExchangeType,
    OrderResult,
    OrderSide,
    OrderStatus,
    PositionInfo,
)
from aitrader_bot.broker.paper_broker import PaperBroker
from aitrader_bot.position_state import (
    PositionActionType,
    PositionPhase,
    PositionPolicy,
    PositionSide,
    PositionStateMachine,
    normalize_position_side,
)
from aitrader_bot.config import ScalpingConfig
from aitrader_bot.scalping import ScalpingRiskManager


def _position(
    ticket: str,
    side: str,
    *,
    quantity: float = 0.1,
    pnl: float = 0.0,
    symbol: str = "XAUUSD",
) -> PositionInfo:
    return PositionInfo(
        symbol=symbol,
        exchange=ExchangeType.PAPER,
        quantity=quantity,
        avg_price=3300,
        current_price=3301,
        unrealized_pnl=pnl,
        ticket=ticket,
        side=side,
        opened_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
    )


def _result(status: OrderStatus, filled: float, message: str = "result") -> OrderResult:
    return OrderResult(
        exchange=ExchangeType.PAPER,
        order_id="order-1",
        status=status,
        symbol="XAUUSD",
        side=OrderSide.SELL,
        quantity=0.1,
        filled_qty=filled,
        price=3301,
        avg_fill_price=3301,
        message=message,
        timestamp=datetime(2026, 7, 10, tzinfo=timezone.utc),
    )


class PositionStateSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.machine = PositionStateMachine(
            PositionPolicy(max_open_positions=4, max_positions_per_side=2, allow_scale_in=True),
            broker_supports_short=True,
            broker_supports_multiple=True,
        )

    def test_sync_tracks_multiple_long_and_short_tickets(self) -> None:
        result = self.machine.sync([
            _position("long-1", "buy"),
            _position("long-2", "long"),
            _position("short-1", "sell"),
            _position("short-2", "short"),
        ])
        self.assertEqual(set(result.opened), {"long-1", "long-2", "short-1", "short-2"})
        self.assertEqual(len(self.machine.active_positions()), 4)
        self.assertEqual(len(self.machine.active_positions(side=PositionSide.LONG)), 2)
        self.assertEqual(len(self.machine.active_positions(side=PositionSide.SHORT)), 2)

    def test_negative_quantity_without_side_is_normalized_short(self) -> None:
        self.machine.sync([_position("short-1", "", quantity=-0.2)])
        position = self.machine.active_positions()[0]
        self.assertEqual(position.side, PositionSide.SHORT)
        self.assertEqual(position.quantity, 0.2)

    def test_broker_disappearance_transitions_position_closed(self) -> None:
        self.machine.sync([_position("long-1", "buy")])
        result = self.machine.sync([])
        self.assertEqual(result.closed, ("long-1",))
        self.assertEqual(self.machine.get("long-1").phase, PositionPhase.CLOSED)

    def test_side_normalization(self) -> None:
        self.assertEqual(normalize_position_side("long"), PositionSide.LONG)
        self.assertEqual(normalize_position_side("short"), PositionSide.SHORT)


class PositionPlanningTests(unittest.TestCase):
    def _machine(self, policy: PositionPolicy | None = None, *, shorts=True, multiple=True):
        return PositionStateMachine(
            policy or PositionPolicy(),
            broker_supports_short=shorts,
            broker_supports_multiple=multiple,
        )

    def test_sell_signal_opens_short_when_flat(self) -> None:
        actions = self._machine().plan_signal("sell", "XAUUSD", entry_allowed=True)
        self.assertEqual(actions[0].action, PositionActionType.OPEN_SHORT)
        self.assertEqual(actions[0].side, PositionSide.SHORT)

    def test_short_is_blocked_when_broker_does_not_support_it(self) -> None:
        actions = self._machine(shorts=False).plan_signal("sell", "XAUUSD", entry_allowed=True)
        self.assertEqual(actions[0].action, PositionActionType.HOLD)
        self.assertIn("does not support shorts", actions[0].reason)

    def test_opposite_profitable_positions_close_before_reversal(self) -> None:
        machine = self._machine()
        machine.sync([_position("long-1", "buy", pnl=12)])
        actions = machine.plan_signal("sell", "XAUUSD", entry_allowed=False, entry_block_reason="session")
        self.assertEqual(actions[0].action, PositionActionType.CLOSE)
        self.assertEqual(actions[0].ticket, "long-1")

    def test_opposite_signal_can_close_multiple_profitable_tickets(self) -> None:
        policy = PositionPolicy(max_open_positions=3, max_positions_per_side=3)
        machine = self._machine(policy)
        machine.sync([
            _position("long-1", "buy", pnl=12),
            _position("long-2", "buy", pnl=4),
            _position("long-loss", "buy", pnl=-1),
        ])
        actions = machine.plan_signal("sell", "XAUUSD", entry_allowed=True)
        self.assertEqual({action.ticket for action in actions}, {"long-1", "long-2"})
        self.assertTrue(all(action.action == PositionActionType.CLOSE for action in actions))

    def test_opposite_losing_position_holds_by_default(self) -> None:
        machine = self._machine()
        machine.sync([_position("long-1", "buy", pnl=-5)])
        actions = machine.plan_signal("sell", "XAUUSD", entry_allowed=True)
        self.assertEqual(actions[0].action, PositionActionType.HOLD)
        self.assertIn("not profitable", actions[0].reason)

    def test_entry_gate_blocks_open_but_not_opposite_close(self) -> None:
        machine = self._machine()
        flat = machine.plan_signal("buy", "XAUUSD", entry_allowed=False, entry_block_reason="spread")
        self.assertEqual(flat[0].action, PositionActionType.HOLD)
        self.assertEqual(flat[0].reason, "spread")

        machine.sync([_position("short-1", "sell", pnl=2)])
        closing = machine.plan_signal("buy", "XAUUSD", entry_allowed=False, entry_block_reason="spread")
        self.assertEqual(closing[0].action, PositionActionType.CLOSE)

    def test_scale_in_and_position_caps_are_explicit(self) -> None:
        policy = PositionPolicy(
            max_open_positions=3,
            max_positions_per_side=2,
            allow_scale_in=True,
        )
        machine = self._machine(policy)
        machine.sync([_position("long-1", "buy")])
        action = machine.plan_signal("buy", "XAUUSD", entry_allowed=True)[0]
        self.assertEqual(action.action, PositionActionType.OPEN_LONG)

        machine.sync([_position("long-1", "buy"), _position("long-2", "buy")])
        capped = machine.plan_signal("buy", "XAUUSD", entry_allowed=True)[0]
        self.assertEqual(capped.action, PositionActionType.HOLD)
        self.assertIn("per side", capped.reason)

    def test_netting_broker_rejects_second_independent_ticket(self) -> None:
        policy = PositionPolicy(
            max_open_positions=2,
            max_positions_per_side=2,
            allow_scale_in=True,
        )
        machine = self._machine(policy, multiple=False)
        machine.sync([_position("long-1", "buy")])
        action = machine.plan_signal("buy", "XAUUSD", entry_allowed=True)[0]
        self.assertEqual(action.action, PositionActionType.HOLD)
        self.assertIn("one net position", action.reason)

    def test_hedging_policy_can_open_opposite_side(self) -> None:
        policy = PositionPolicy(
            max_open_positions=2,
            max_positions_per_side=1,
            hedging_enabled=True,
            close_on_opposite_signal=False,
        )
        machine = self._machine(policy)
        machine.sync([_position("long-1", "buy")])
        action = machine.plan_signal("sell", "XAUUSD", entry_allowed=True)[0]
        self.assertEqual(action.action, PositionActionType.OPEN_SHORT)

    def test_pending_entry_prevents_duplicate_order_until_broker_sync(self) -> None:
        machine = self._machine()
        pending = _result(OrderStatus.PENDING, 0.0)
        machine.record_entry_result("XAUUSD", PositionSide.LONG, pending)
        action = machine.plan_signal("buy", "XAUUSD", entry_allowed=True)[0]
        self.assertEqual(action.action, PositionActionType.HOLD)
        self.assertIn("still pending", action.reason)

        machine.sync([_position("long-1", "buy")])
        self.assertEqual(machine.pending_entries(), [])

    def test_scale_in_pending_waits_for_new_ticket_or_quantity(self) -> None:
        policy = PositionPolicy(
            max_open_positions=2,
            max_positions_per_side=2,
            allow_scale_in=True,
        )
        machine = self._machine(policy)
        machine.sync([_position("long-1", "buy", quantity=0.1)])
        machine.record_entry_result(
            "XAUUSD", PositionSide.LONG, _result(OrderStatus.PENDING, 0.0),
        )
        machine.sync([_position("long-1", "buy", quantity=0.1)])
        self.assertEqual(len(machine.pending_entries()), 1)

        machine.sync([
            _position("long-1", "buy", quantity=0.1),
            _position("long-2", "buy", quantity=0.1),
        ])
        self.assertEqual(machine.pending_entries(), [])


class PositionCloseTransitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.machine = PositionStateMachine(
            PositionPolicy(),
            broker_supports_short=True,
            broker_supports_multiple=True,
        )
        self.machine.sync([_position("long-1", "buy", quantity=0.1)])

    def test_full_close_transitions_closed(self) -> None:
        self.machine.mark_closing("long-1")
        phase = self.machine.apply_close_result("long-1", _result(OrderStatus.FILLED, 0.1))
        self.assertEqual(phase, PositionPhase.CLOSED)
        self.assertEqual(self.machine.active_positions(), [])

    def test_partial_close_reduces_quantity_and_returns_open(self) -> None:
        phase = self.machine.apply_close_result("long-1", _result(OrderStatus.PARTIAL, 0.04))
        position = self.machine.get("long-1")
        self.assertEqual(phase, PositionPhase.OPEN)
        self.assertAlmostEqual(position.quantity, 0.06)
        self.assertIn("partial close", position.last_error)

    def test_pending_close_stays_closing(self) -> None:
        phase = self.machine.apply_close_result("long-1", _result(OrderStatus.PENDING, 0))
        self.assertEqual(phase, PositionPhase.CLOSING)
        self.assertEqual(self.machine.get("long-1").phase, PositionPhase.CLOSING)
        self.machine.sync([_position("long-1", "buy", quantity=0.1)])
        self.assertEqual(self.machine.get("long-1").phase, PositionPhase.CLOSING)
        actions = self.machine.plan_signal("sell", "XAUUSD", entry_allowed=True)
        self.assertEqual(actions[0].action, PositionActionType.HOLD)
        self.assertIn("still pending", actions[0].reason)

    def test_rejected_or_missing_close_returns_open_with_error(self) -> None:
        phase = self.machine.apply_close_result(
            "long-1", _result(OrderStatus.REJECTED, 0, "broker rejected"),
        )
        self.assertEqual(phase, PositionPhase.OPEN)
        self.assertEqual(self.machine.get("long-1").last_error, "broker rejected")

        phase = self.machine.apply_close_result("long-1", None)
        self.assertEqual(phase, PositionPhase.OPEN)
        self.assertIn("no result", self.machine.get("long-1").last_error)


class PaperBrokerMultiPositionTests(unittest.TestCase):
    def test_paper_broker_tracks_independent_long_and_short_tickets(self) -> None:
        broker = PaperBroker(initial_cash=10000)
        broker.connect()
        broker.update_price("XAUUSD", 100)
        long_order = broker.place_order(
            "XAUUSD", OrderSide.BUY, 0.1, stop_loss=99, take_profit=102,
        )
        short_order = broker.place_order(
            "XAUUSD", OrderSide.SELL, 0.2, stop_loss=101, take_profit=98,
        )
        positions = broker.get_positions("XAUUSD")
        self.assertEqual(len(positions), 2)
        self.assertNotEqual(long_order.order_id, short_order.order_id)
        self.assertEqual({p.side for p in positions}, {"buy", "sell"})

        broker.update_price("XAUUSD", 110)
        by_side = {p.side: p for p in broker.get_positions("XAUUSD")}
        self.assertAlmostEqual(by_side["buy"].unrealized_pnl, 1.0)
        self.assertAlmostEqual(by_side["sell"].unrealized_pnl, -2.0)

        broker.close_position(long_order.order_id)
        broker.close_position(short_order.order_id)
        self.assertEqual(broker.get_positions("XAUUSD"), [])
        self.assertAlmostEqual(broker.cash, 9999.0)

    def test_short_protection_uses_inverse_price_direction(self) -> None:
        broker = PaperBroker(initial_cash=10000)
        broker.connect()
        broker.update_price("XAUUSD", 100)
        valid = broker.place_order(
            "XAUUSD", OrderSide.SELL, 0.1, stop_loss=101, take_profit=99,
        )
        invalid = broker.place_order(
            "XAUUSD", OrderSide.SELL, 0.1, stop_loss=99, take_profit=98,
        )
        self.assertEqual(valid.status, OrderStatus.FILLED)
        self.assertEqual(invalid.status, OrderStatus.REJECTED)


class LongShortRiskTests(unittest.TestCase):
    def test_forced_exit_is_symmetric_for_long_and_short(self) -> None:
        risk = ScalpingRiskManager(ScalpingConfig(
            stop_loss_pips=10,
            take_profit_pips=5,
            trailing_stop_pips=0,
        ))
        self.assertIn("take profit", risk.forced_exit_reason(100, 100.5, side="buy"))
        self.assertIn("stop loss", risk.forced_exit_reason(100, 99.0, side="buy"))
        self.assertIn("take profit", risk.forced_exit_reason(100, 99.5, side="sell"))
        self.assertIn("stop loss", risk.forced_exit_reason(100, 101.0, side="sell"))

    def test_forced_exit_uses_broker_point_size(self) -> None:
        risk = ScalpingRiskManager(ScalpingConfig(
            stop_loss_pips=10,
            take_profit_pips=5,
            trailing_stop_pips=0,
        ))
        self.assertIn(
            "take profit",
            risk.forced_exit_reason(1.10000, 1.10050, side="buy", point_size=0.00001),
        )


if __name__ == "__main__":
    unittest.main()

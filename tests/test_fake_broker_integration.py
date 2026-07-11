"""End-to-end service-stack tests using a deterministic fake broker."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from aitrader_bot.broker import OrderStatus
from aitrader_bot.config import ScalpingConfig
from aitrader_bot.position_state import PositionActionType
from aitrader_bot.services import (
    ExecutionKind,
    ExecutionService,
    PositionStateService,
    RiskService,
)
from tests.fake_broker import FakeBroker


NOW = datetime(2026, 7, 10, 7, 30, tzinfo=timezone.utc)


class FakeBrokerIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = ScalpingConfig(
            session_filter_enabled=False,
            news_filter_enabled=False,
            stop_loss_pips=10,
            take_profit_pips=10,
            trailing_stop_pips=0,
        )
        self.broker = FakeBroker()
        self.broker.connect()
        self.broker.set_quote("XAUUSD", 100.0)
        self.positions = PositionStateService.from_config(
            self.broker,
            "XAUUSD",
            self.config,
        )
        self.risk = RiskService(self.config, self.positions.machine)
        self.execution = ExecutionService(
            self.broker,
            "XAUUSD",
            "XAUUSD",
            self.positions,
            self.risk,
        )

    def _decision(self, action: str):
        quote = self.broker.get_quote("XAUUSD")
        return self.risk.decide(
            action,
            "XAUUSD",
            point_size=quote.point_size,
            now=NOW,
        )

    def test_shared_decision_to_execution_attaches_protection_and_syncs(self) -> None:
        self.positions.sync()
        decision = self._decision("buy")
        batch = self.execution.execute(
            decision.actions,
            self.broker.get_quote("XAUUSD"),
            "integration entry",
        )

        request = self.broker.order_requests[0]
        active = self.positions.machine.active_positions("XAUUSD")
        self.assertEqual(batch.outcomes[0].kind, ExecutionKind.OPENED)
        self.assertEqual(len(active), 1)
        self.assertLess(request["stop_loss"], batch.outcomes[0].price)
        self.assertGreater(request["take_profit"], batch.outcomes[0].price)

    def test_pending_entry_prevents_duplicate_order(self) -> None:
        self.positions.sync()
        self.broker.next_order_status = OrderStatus.PENDING
        first = self.execution.execute(
            self._decision("buy").actions,
            self.broker.get_quote("XAUUSD"),
            "pending entry",
        )
        second = self._decision("buy")

        self.assertEqual(first.outcomes[0].kind, ExecutionKind.ENTRY_PENDING)
        self.assertEqual(len(self.broker.order_requests), 1)
        self.assertEqual(second.actions[0].action, PositionActionType.HOLD)
        self.assertIn("pending", second.actions[0].reason)

    def test_rejected_risk_close_remains_broker_authoritative_open(self) -> None:
        self.positions.sync()
        self.execution.execute(
            self._decision("buy").actions,
            self.broker.get_quote("XAUUSD"),
            "entry",
        )
        self.broker.set_quote("XAUUSD", 90.0)
        self.positions.sync()
        self.broker.next_close_status = OrderStatus.REJECTED
        risk_exit = self._decision("hold")
        batch = self.execution.execute(
            risk_exit.actions,
            self.broker.get_quote("XAUUSD"),
            "risk exit",
        )

        self.assertTrue(risk_exit.risk_exit)
        self.assertEqual(batch.outcomes[0].kind, ExecutionKind.CLOSE_UNCONFIRMED)
        self.assertEqual(len(self.positions.machine.active_positions("XAUUSD")), 1)
        self.assertEqual(len(self.broker.get_positions("XAUUSD")), 1)


if __name__ == "__main__":
    unittest.main()

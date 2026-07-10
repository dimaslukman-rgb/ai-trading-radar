"""Contract tests for decisions shared by live trading and backtests."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from aitrader_bot.broker.base import ExchangeType, PositionInfo
from aitrader_bot.config import ScalpingConfig
from aitrader_bot.decision import TradingDecisionService
from aitrader_bot.position_state import (
    PositionActionType,
    PositionPolicy,
    PositionSide,
    PositionStateMachine,
)


NOW = datetime(2026, 7, 10, 14, 30, tzinfo=timezone(timedelta(hours=7)))


def _position(
    ticket: str,
    side: str,
    *,
    entry: float = 3300.0,
    current: float = 3300.0,
    pnl: float = 0.0,
    opened_at: datetime | None = NOW,
) -> PositionInfo:
    return PositionInfo(
        symbol="XAUUSD",
        exchange=ExchangeType.PAPER,
        quantity=0.1,
        avg_price=entry,
        current_price=current,
        unrealized_pnl=pnl,
        ticket=ticket,
        side=side,
        opened_at=opened_at,
    )


def _machine(policy: PositionPolicy | None = None) -> PositionStateMachine:
    return PositionStateMachine(
        policy or PositionPolicy(),
        broker_supports_short=True,
        broker_supports_multiple=True,
    )


class SharedDecisionTests(unittest.TestCase):
    def test_risk_exits_take_priority_for_every_long_and_short_ticket(self) -> None:
        config = ScalpingConfig(
            stop_loss_pips=10,
            take_profit_pips=100,
            trailing_stop_pips=0,
        )
        machine = _machine(PositionPolicy(max_open_positions=4, max_positions_per_side=2))
        machine.sync([
            _position("long-loss", "buy", current=3298.9, pnl=-11),
            _position("short-loss", "sell", current=3301.1, pnl=-11),
        ])

        plan = TradingDecisionService(config, machine).decide(
            "buy",
            "XAUUSD",
            point_size=0.01,
            now=NOW,
            entry_block_reasons=["outside session"],
            higher_timeframe_confirmed=False,
        )

        self.assertTrue(plan.risk_exit)
        self.assertEqual({action.ticket for action in plan.actions}, {"long-loss", "short-loss"})
        self.assertTrue(all(action.action == PositionActionType.CLOSE for action in plan.actions))

    def test_entry_filters_do_not_block_opposite_position_exit(self) -> None:
        config = ScalpingConfig(
            stop_loss_pips=100,
            take_profit_pips=100,
            trailing_stop_pips=0,
        )
        machine = _machine()
        machine.sync([_position("long-profit", "buy", current=3300.2, pnl=2)])

        plan = TradingDecisionService(config, machine).decide(
            "sell",
            "XAUUSD",
            point_size=0.01,
            now=NOW,
            entry_block_reasons=["outside session"],
            higher_timeframe_confirmed=False,
            higher_timeframe_reason="M5 rejected SELL",
        )

        self.assertFalse(plan.risk_exit)
        self.assertEqual(plan.actions[0].action, PositionActionType.CLOSE)
        self.assertEqual(plan.actions[0].ticket, "long-profit")

    def test_flat_sell_signal_opens_short_through_shared_decision(self) -> None:
        plan = TradingDecisionService(ScalpingConfig(), _machine()).decide(
            "sell",
            "XAUUSD",
            point_size=0.01,
            now=NOW,
        )

        self.assertEqual(plan.actions[0].action, PositionActionType.OPEN_SHORT)
        self.assertEqual(plan.actions[0].side, PositionSide.SHORT)

    def test_flat_entry_is_held_when_any_shared_filter_blocks_it(self) -> None:
        plan = TradingDecisionService(ScalpingConfig(), _machine()).decide(
            "buy",
            "XAUUSD",
            point_size=0.01,
            now=NOW,
            entry_block_reasons=["spread too wide"],
            higher_timeframe_confirmed=False,
            higher_timeframe_reason="M5 rejected BUY",
        )

        self.assertEqual(plan.actions[0].action, PositionActionType.HOLD)
        self.assertIn("spread too wide", plan.actions[0].reason)
        self.assertIn("M5 rejected BUY", plan.actions[0].reason)

    def test_timeout_accepts_mixed_timezone_timestamp_styles(self) -> None:
        config = ScalpingConfig(
            aggressive_mode=True,
            timeout_exit_minutes=10,
            stop_loss_pips=100,
            take_profit_pips=100,
            trailing_stop_pips=0,
        )
        machine = _machine()
        machine.sync([_position(
            "naive-entry",
            "buy",
            opened_at=datetime(2026, 7, 10, 14, 0),
        )])

        plan = TradingDecisionService(config, machine).decide(
            "hold",
            "XAUUSD",
            point_size=0.01,
            now=NOW,
        )

        self.assertTrue(plan.risk_exit)
        self.assertEqual(plan.actions[0].action, PositionActionType.CLOSE)
        self.assertIn("timeout 10m", plan.actions[0].reason)

    def test_identical_state_and_inputs_produce_identical_live_backtest_plan(self) -> None:
        config = ScalpingConfig(
            stop_loss_pips=100,
            take_profit_pips=100,
            trailing_stop_pips=0,
        )
        live_machine = _machine()
        backtest_machine = _machine()
        positions = [_position("ticket-1", "sell", current=3299.8, pnl=2)]
        live_machine.sync(positions)
        backtest_machine.sync(positions)

        arguments = dict(
            point_size=0.01,
            now=NOW,
            entry_block_reasons=["news window"],
            higher_timeframe_confirmed=True,
        )
        live_plan = TradingDecisionService(config, live_machine).decide(
            "buy", "XAUUSD", **arguments,
        )
        backtest_plan = TradingDecisionService(config, backtest_machine).decide(
            "buy", "XAUUSD", **arguments,
        )

        self.assertEqual(live_plan, backtest_plan)


if __name__ == "__main__":
    unittest.main()

"""Unit contracts for the five live-engine service boundaries."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from aitrader_bot.broker import OrderSide, PaperBroker
from aitrader_bot.broker.base import Candle, ExchangeType, Quote
from aitrader_bot.config import ScalpingConfig
from aitrader_bot.models import PriceBar, Signal
from aitrader_bot.position_state import (
    PositionAction,
    PositionActionType,
    PositionSide,
)
from aitrader_bot.services import (
    ExecutionKind,
    ExecutionService,
    MarketDataService,
    MarketSnapshot,
    PositionStateService,
    RiskService,
    SignalService,
)


NOW = datetime(2026, 7, 10, 7, 30, tzinfo=timezone.utc)


def _quote(price: float = 100.0) -> Quote:
    return Quote(
        symbol="XAUUSD",
        exchange=ExchangeType.PAPER,
        bid=price - 0.05,
        ask=price + 0.05,
        last=price,
        volume=1000,
        timestamp=NOW,
        point_size=0.01,
    )


class MarketDataServiceTests(unittest.TestCase):
    def test_snapshot_normalizes_candles_and_retains_last_good_window(self) -> None:
        broker = PaperBroker(initial_cash=10000)
        broker.connect()
        broker.update_price("XAUUSD", 100.0, timestamp=NOW)
        candle = Candle(
            "XAUUSD",
            ExchangeType.PAPER,
            NOW,
            99.0,
            101.0,
            98.0,
            100.0,
            1000,
            "5m",
        )
        broker.update_candles("XAUUSD", [candle])
        service = MarketDataService(broker, "XAUUSD", "5m")

        first = service.snapshot()
        with patch.object(broker, "fetch_candles", side_effect=RuntimeError("temporary")):
            second = service.snapshot()

        self.assertEqual(first.bars[0].close, 100.0)
        self.assertEqual(second.bars, first.bars)


class SignalServiceTests(unittest.TestCase):
    def test_evaluation_owns_strategy_and_higher_timeframe_context(self) -> None:
        config = ScalpingConfig()

        class FixedStrategy:
            def __init__(self) -> None:
                self.config = config

            def generate(self, symbol, bars, quote):
                return Signal(symbol, "buy", 0.9, quote.last, "fixed", NOW)

        market_data = SimpleNamespace(
            closes=lambda timeframe, count: [200.0 - index * 3 for index in range(25)],
        )
        bars = tuple(
            PriceBar(NOW, 100, 101, 99, 100 + index * 0.1, 1000)
            for index in range(25)
        )
        evaluation = SignalService(FixedStrategy(), market_data).evaluate(
            "XAUUSD",
            MarketSnapshot(_quote(), bars, ()),
            entry_blocked=False,
        )

        self.assertEqual(evaluation.signal.action, "buy")
        self.assertFalse(evaluation.higher_timeframe_confirmed)
        self.assertIn("bearish", evaluation.higher_timeframe_reason)
        self.assertIn("macd", evaluation.analysis)


class RiskServiceTests(unittest.TestCase):
    def test_risk_facade_applies_entry_gates_and_shared_position_plan(self) -> None:
        config = ScalpingConfig(
            session_filter_enabled=False,
            news_filter_enabled=False,
            max_spread_points=25,
        )
        broker = PaperBroker(initial_cash=10000)
        position_state = PositionStateService.from_config(broker, "XAUUSD", config)
        service = RiskService(config, position_state.machine)

        blocks = service.entry_blocks(
            _quote(),
            supports_attached_protection=True,
            now=NOW,
        )
        decision = service.decide(
            "sell",
            "XAUUSD",
            point_size=0.01,
            now=NOW,
            entry_block_reasons=blocks,
        )

        self.assertEqual(blocks, [])
        self.assertEqual(decision.actions[0].action, PositionActionType.OPEN_SHORT)


class PositionStateServiceTests(unittest.TestCase):
    def test_sync_exposes_broker_and_managed_multi_ticket_state(self) -> None:
        config = ScalpingConfig(
            max_open_positions=2,
            max_positions_per_side=1,
            hedging_enabled=True,
        )
        broker = PaperBroker(initial_cash=10000)
        broker.connect()
        broker.update_price("XAUUSD", 100.0, timestamp=NOW)
        broker.place_order("XAUUSD", OrderSide.BUY, 0.1)
        broker.place_order("XAUUSD", OrderSide.SELL, 0.1)
        service = PositionStateService.from_config(broker, "XAUUSD", config)

        snapshot = service.sync()

        self.assertEqual(len(snapshot.broker_positions), 2)
        self.assertEqual(len(snapshot.managed_positions), 2)
        self.assertEqual(
            {position.side for position in snapshot.managed_positions},
            {PositionSide.LONG, PositionSide.SHORT},
        )


class ExecutionServiceTests(unittest.TestCase):
    def test_execution_opens_and_closes_through_position_state(self) -> None:
        config = ScalpingConfig(
            session_filter_enabled=False,
            news_filter_enabled=False,
            stop_loss_pips=10,
            take_profit_pips=10,
            trailing_stop_pips=0,
        )
        broker = PaperBroker(initial_cash=10000)
        broker.connect()
        broker.update_price("XAUUSD", 100.0, timestamp=NOW)
        positions = PositionStateService.from_config(broker, "XAUUSD", config)
        risk = RiskService(config, positions.machine)
        execution = ExecutionService(
            broker,
            "XAUUSD",
            "XAUUSD",
            positions,
            risk,
        )

        opened = execution.execute((PositionAction(
            PositionActionType.OPEN_LONG,
            "XAUUSD",
            PositionSide.LONG,
            reason="unit entry",
        ),), _quote(), "unit entry")
        active = positions.machine.active_positions("XAUUSD")
        closed = execution.execute((PositionAction(
            PositionActionType.CLOSE,
            "XAUUSD",
            PositionSide.LONG,
            ticket=active[0].ticket,
            quantity=active[0].quantity,
            reason="unit close",
        ),), _quote(), "unit close")

        self.assertEqual(opened.outcomes[0].kind, ExecutionKind.OPENED)
        self.assertEqual(closed.outcomes[0].kind, ExecutionKind.CLOSED)
        self.assertEqual(positions.machine.active_positions("XAUUSD"), [])


if __name__ == "__main__":
    unittest.main()

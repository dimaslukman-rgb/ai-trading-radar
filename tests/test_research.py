"""Tests for cost accounting, drawdown, sessions, and walk-forward isolation."""

from __future__ import annotations

import math
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from aitrader_bot.broker import OrderSide, PaperBroker, create_broker
from aitrader_bot.config import BotConfig, ScalpingConfig
from aitrader_bot.models import PriceBar
from aitrader_bot.research import (
    EquityPoint,
    TransactionCostModel,
    analyze_dataset,
    analyze_drawdown,
    classify_session,
    simulate_scalping,
)
from aitrader_bot.walk_forward import StrategyCandidate, walk_forward_optimize


def _bars(count: int = 400) -> list[PriceBar]:
    start = datetime(2026, 1, 1, 7, 0, tzinfo=timezone.utc)
    result = []
    for index in range(count):
        close = 100.0 + math.sin(index / 4) * 2.5 + index * 0.005
        result.append(PriceBar(
            start + timedelta(minutes=5 * index),
            close - 0.2,
            close + 0.5,
            close - 0.5,
            close,
            1000 + (index % 7) * 100,
        ))
    return result


def _config() -> BotConfig:
    return replace(BotConfig(symbol="XAUUSD", market="forex"), scalping=ScalpingConfig(
        session_filter_enabled=False,
        news_filter_enabled=False,
        min_buy_score=0.01,
        min_sell_score=-0.01,
        stop_loss_pips=10,
        take_profit_pips=10,
        trailing_stop_pips=0,
    ))


class TransactionCostTests(unittest.TestCase):
    def test_factory_infers_xau_cfd_contract_settings(self) -> None:
        broker = create_broker(
            "paper",
            initial_cash=10000,
            symbol="XAUUSD",
            market="forex",
            spread_points=0,
        )
        broker.connect()
        broker.update_price("XAUUSD", 100)
        broker.place_order("XAUUSD", OrderSide.BUY, 0.1)

        self.assertAlmostEqual(broker.get_account().margin, 10.0)

    def test_cfd_contract_size_and_leverage_drive_margin_and_pnl(self) -> None:
        broker = PaperBroker(
            initial_cash=10000,
            point_size=0.01,
            spread_points=0,
            contract_size=100,
            leverage=100,
        )
        broker.connect()
        broker.update_price("XAUUSD", 100)
        opened = broker.place_order("XAUUSD", OrderSide.BUY, 0.1)
        self.assertAlmostEqual(broker.get_account().margin, 10.0)
        broker.update_price("XAUUSD", 101)
        self.assertAlmostEqual(broker.get_account().equity, 10010.0)
        broker.close_position(opened.order_id)
        self.assertAlmostEqual(broker.get_account().balance, 10010.0)

    def test_paper_broker_applies_and_reports_each_cost_component(self) -> None:
        broker = PaperBroker(
            initial_cash=10000,
            point_size=0.01,
            spread_points=10,
            slippage_points=2,
            commission_per_order=1,
            commission_per_unit=0.5,
        )
        broker.connect()
        broker.update_price("XAUUSD", 100)
        opened = broker.place_order("XAUUSD", OrderSide.BUY, 1)
        broker.update_price("XAUUSD", 101)
        closed = broker.close_position(opened.order_id)

        self.assertAlmostEqual(opened.avg_fill_price, 100.07)
        self.assertAlmostEqual(closed.avg_fill_price, 100.93)
        self.assertAlmostEqual(broker.total_commission, 3.0)
        self.assertAlmostEqual(broker.total_spread_cost, 0.1)
        self.assertAlmostEqual(broker.total_slippage_cost, 0.04)
        self.assertAlmostEqual(broker.total_transaction_cost, 3.14)
        self.assertAlmostEqual(broker.get_account().equity, 9997.86, places=2)

    def test_cost_model_rejects_negative_assumptions(self) -> None:
        with self.assertRaises(ValueError):
            TransactionCostModel(slippage_points=-1)

    def test_completed_trade_net_equals_gross_less_all_costs(self) -> None:
        result = simulate_scalping(
            _config(),
            _bars(250),
            cost_model=TransactionCostModel(10, 2, 0.1, 0.05),
            warmup_bars=30,
            liquidate_at_end=True,
        )

        self.assertGreater(len(result.trades), 0)
        for trade in result.trades:
            self.assertAlmostEqual(
                trade.net_pnl,
                trade.gross_pnl - trade.total_cost,
                places=8,
            )


class ResearchAnalyticsTests(unittest.TestCase):
    def test_dataset_diagnostics_report_duplicates_and_gaps(self) -> None:
        bars = _bars(4)
        bars[2] = replace(bars[2], date=bars[1].date)
        bars[3] = replace(bars[3], date=bars[1].date + timedelta(minutes=30))

        diagnostics = analyze_dataset(bars)

        self.assertEqual(diagnostics.duplicate_timestamps, 1)
        self.assertEqual(diagnostics.out_of_order_timestamps, 0)
        self.assertEqual(diagnostics.large_gap_count, 1)
        self.assertEqual(diagnostics.largest_gap_minutes, 30)

    def test_drawdown_tracks_peak_trough_recovery_and_duration(self) -> None:
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        curve = [
            EquityPoint(start + timedelta(minutes=5 * index), equity, equity)
            for index, equity in enumerate((100, 110, 88, 90, 111))
        ]

        result = analyze_drawdown(curve)

        self.assertAlmostEqual(result.max_drawdown_pct, 20.0)
        self.assertEqual(result.peak_time, curve[1].timestamp)
        self.assertEqual(result.trough_time, curve[2].timestamp)
        self.assertEqual(result.recovery_time, curve[4].timestamp)
        self.assertEqual(result.max_underwater_bars, 3)
        self.assertEqual(result.max_underwater_minutes, 15)

    def test_session_classification_uses_mutually_exclusive_wib_windows(self) -> None:
        config = ScalpingConfig()
        self.assertEqual(
            classify_session(datetime(2026, 1, 1, 8, 0), config),
            "asia",
        )
        self.assertEqual(
            classify_session(datetime(2026, 1, 1, 14, 0), config),
            "london",
        )
        self.assertEqual(
            classify_session(datetime(2026, 1, 1, 19, 30), config),
            "new_york",
        )

    def test_walk_forward_test_windows_follow_train_windows_without_overlap(self) -> None:
        candidate = StrategyCandidate(5, 13, 0.01, -0.01, 10, 10)
        result = walk_forward_optimize(
            _config(),
            _bars(400),
            candidates=[candidate],
            train_bars=200,
            test_bars=100,
            step_bars=100,
            warmup_bars=30,
            cost_model=TransactionCostModel(10, 1),
            minimum_train_trades=0,
        )

        self.assertEqual(len(result.folds), 2)
        for fold in result.folds:
            self.assertLess(fold.train_end, fold.test_start)
            self.assertEqual(fold.selected, candidate)
        self.assertLess(result.folds[0].test_end, result.folds[1].test_start)

    def test_walk_forward_rejects_overlapping_oos_windows(self) -> None:
        with self.assertRaisesRegex(ValueError, "overlapping"):
            walk_forward_optimize(
                _config(),
                _bars(400),
                candidates=[StrategyCandidate(5, 13, 0.01, -0.01, 10, 10)],
                train_bars=200,
                test_bars=100,
                step_bars=50,
            )


if __name__ == "__main__":
    unittest.main()

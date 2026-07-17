"""Contracts for v3 multi-pair, adaptive-agent, and dashboard foundations."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aitrader_bot.agents.gemini_sentiment import GeminiSentimentAgent
from aitrader_bot.agents.liquidity import LiquidityAgent
from aitrader_bot.agents.performance_registry import PerformanceRegistry
from aitrader_bot.agents.base import AgentContext
from aitrader_bot.app import dashboard_data as dd
from aitrader_bot.config import load_config


class V3ConfigurationTests(unittest.TestCase):
    def test_mt5_terminal_startup_options_are_loaded(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            json.dump({
                "brokers": {
                    "mt5": {
                        "backend": "mt5",
                        "terminal_path": "C:/MetaTrader/terminal64.exe",
                        "timeout_ms": 45000,
                        "portable": True,
                    }
                }
            }, handle)
            path = Path(handle.name)
        self.addCleanup(lambda: path.unlink(missing_ok=True))

        broker = load_config(path).brokers["mt5"]
        self.assertEqual(broker.terminal_path, "C:/MetaTrader/terminal64.exe")
        self.assertEqual(broker.timeout_ms, 45000)
        self.assertTrue(broker.portable)

    def test_symbols_are_isolated_and_legacy_symbol_remains_compatible(self) -> None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as handle:
            json.dump({
                "symbol": "XAUUSD",
                "market": "forex",
                "symbols": [
                    {"symbol": "XAUUSD", "scalping": {"interval_seconds": 60}},
                    {"symbol": "EURUSD", "enabled": True, "scalping": {"stop_loss_pips": 12}},
                    {"symbol": "BTCUSD", "enabled": False},
                ],
            }, handle)
            path = Path(handle.name)
        self.addCleanup(lambda: path.unlink(missing_ok=True))

        config = load_config(path)
        self.assertEqual([item.symbol for item in config.enabled_symbols], ["XAUUSD", "EURUSD"])
        self.assertEqual(config.scalping_for(config.enabled_symbols[0]).interval_seconds, 60)
        self.assertEqual(config.scalping_for(config.enabled_symbols[1]).stop_loss_pips, 12)


class V3AgentTests(unittest.TestCase):
    def test_performance_registry_rewards_correct_direction_without_unbounded_weight(self) -> None:
        registry = PerformanceRegistry()
        registry.record("XAUUSD", 100.0, {"trend_analyst": {"overall": "Bullish"}})
        registry.settle("XAUUSD", 101.0)
        score = registry.score("trend_analyst")
        self.assertEqual((score.resolved, score.correct), (1, 1))
        self.assertGreater(score.weight, 1.0)
        self.assertLessEqual(score.weight, 1.5)

    def test_gemini_without_key_stays_neutral_and_offline(self) -> None:
        output = GeminiSentimentAgent().run(AgentContext(symbol="XAUUSD")).output
        self.assertFalse(output["enabled"])
        self.assertEqual(output["bias"], "NEUTRAL")

    def test_liquidity_reports_atr_and_sweep_shape(self) -> None:
        candles = [
            {"open": 100 + i, "high": 101 + i, "low": 99 + i, "close": 100.5 + i, "volume": 1}
            for i in range(12)
        ]
        output = LiquidityAgent().run(AgentContext(candles=candles)).output
        self.assertIn("atr", output)
        self.assertIn("sweep_direction", output)
        self.assertGreater(output["atr"], 0)


class V3DashboardTests(unittest.TestCase):
    def test_snapshot_includes_per_symbol_reasoning_and_equity_history(self) -> None:
        dd.reset_account_metrics(1000.0, 1000.0)
        dd.update(symbol="EURUSD", last_price=1.1, agent_reasoning=[{"agent": "trend"}])
        dd.update(equity=1010.0)
        snapshot = dd.snapshot()
        self.assertIn("equity_history", snapshot)
        self.assertGreaterEqual(len(snapshot["equity_history"]), 2)
        self.assertEqual(snapshot["all_symbols"]["EURUSD"]["last_price"], 1.1)
        self.assertEqual(snapshot["all_symbols"]["EURUSD"]["agent_reasoning"][0]["agent"], "trend")


if __name__ == "__main__":
    unittest.main()

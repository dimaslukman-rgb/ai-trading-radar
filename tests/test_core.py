"""Tests for multi-broker scalping bot — strategy, brokers, backtest."""

import unittest
from datetime import datetime, timezone

from aitrader_bot.backtest import run_backtest
from aitrader_bot.broker import (
    ExchangeType,
    OrderSide,
    OrderStatus,
    PaperBroker,
    create_broker,
)
from aitrader_bot.broker.base import Candle
from aitrader_bot.config import BotConfig, ScalpingConfig
from aitrader_bot.models import PriceBar
from aitrader_bot.scalping import ScalpingRiskManager, ScalpingStrategy
from aitrader_bot.strategy import AiMomentumStrategy
from aitrader_bot.version import VERSION_MAJOR, VERSION_MINOR, VERSION_PATCH, VERSION_TUPLE


def _bars() -> list[PriceBar]:
    return [
        PriceBar(
            date=datetime(2026, 1, day, tzinfo=timezone.utc),
            open=100 + day, high=102 + day,
            low=99 + day, close=100 + day, volume=1000,
        )
        for day in range(1, 29)
    ]


def _volatile_bars() -> list[PriceBar]:
    """Bars with clear up/down swings for scalping signals."""
    raw = [
        100, 101, 102, 101, 100, 99, 98, 97, 98, 99,
        100, 101, 102, 103, 104, 103, 102, 101, 100, 99,
        98, 97, 96, 97, 98, 99, 100, 101, 102, 103,
    ]
    return [
        PriceBar(
            date=datetime(2026, 1, i + 1, tzinfo=timezone.utc),
            open=v - 1, high=v + 2, low=v - 2, close=v,
            volume=1000 + i * 100,
        )
        for i, v in enumerate(raw)
    ]


# ══════════════════════════════════════════════════════════════════════════
#  Core tests
# ══════════════════════════════════════════════════════════════════════════

class BotCoreTests(unittest.TestCase):
    def test_version_tuple_matches_version_components(self) -> None:
        """The package initializer and updater both require this export."""
        self.assertEqual(
            VERSION_TUPLE,
            (VERSION_MAJOR, VERSION_MINOR, VERSION_PATCH),
        )

    def test_strategy_returns_signal(self) -> None:
        config = BotConfig()
        signal = AiMomentumStrategy(config.strategy).generate("TEST", _bars())
        self.assertIn(signal.action, {"buy", "sell", "hold"})
        self.assertGreater(signal.price, 0)

    def test_backtest_momentum_returns_metrics(self) -> None:
        result = run_backtest(BotConfig(), _bars())
        self.assertGreater(result.start_equity, 0)
        self.assertGreater(result.end_equity, 0)

    def test_backtest_scalping_mode(self) -> None:
        result = run_backtest(BotConfig(), _volatile_bars(), mode="scalping")
        self.assertGreater(result.start_equity, 0)
        self.assertGreater(result.end_equity, 0)


# ══════════════════════════════════════════════════════════════════════════
#  Scalping strategy tests
# ══════════════════════════════════════════════════════════════════════════

class ScalpingTests(unittest.TestCase):
    def test_scalping_returns_signal(self) -> None:
        cfg = ScalpingConfig()
        signal = ScalpingStrategy(cfg).generate("BTC-USD", _volatile_bars())
        self.assertIn(signal.action, {"buy", "sell", "hold"})
        self.assertGreaterEqual(signal.confidence, 0.0)

    def test_scalping_with_broker_quote(self) -> None:
        from aitrader_bot.broker import Quote
        cfg = ScalpingConfig(max_spread_points=25.0)
        quote = Quote(
            symbol="BTC-USD",
            exchange=ExchangeType.PAPER,
            bid=100.0, ask=101.0, last=100.5,
            volume=1000, timestamp=datetime.now(timezone.utc),
        )
        signal = ScalpingStrategy(cfg).generate("BTC-USD", _volatile_bars(), quote)
        self.assertIn(signal.action, {"buy", "sell", "hold"})

    def test_scalping_risk_buy_quantity(self) -> None:
        cfg = ScalpingConfig(max_trade_pct=0.05, risk_per_trade_pct=0.02, stop_loss_pips=30.0)
        rm = ScalpingRiskManager(cfg)
        qty = rm.buy_quantity(10000, 10000, 100)
        # risk_amount = 10000 * 0.02 = 200; qty = 200 / (30 * 10) = 0.667
        self.assertAlmostEqual(qty, 0.667, places=3)

    def test_scalping_risk_sl_tp(self) -> None:
        cfg = ScalpingConfig(stop_loss_pips=30.0, take_profit_pips=15.0)
        rm = ScalpingRiskManager(cfg)
        # 30 pips = price diff of 3.0 (for XAUUSD, 1 pip ≈ 0.1 price diff)
        self.assertIsNotNone(rm.forced_exit_reason(100, 96.5))   # -3.5 price diff > 30 pips SL
        self.assertIsNone(rm.forced_exit_reason(100, 98.0))      # -2.0 price diff < 30 pips SL
        self.assertIsNotNone(rm.forced_exit_reason(100, 102.5))  # +2.5 price diff > 15 pips TP


# ══════════════════════════════════════════════════════════════════════════
#  Broker tests
# ══════════════════════════════════════════════════════════════════════════

class BrokerTests(unittest.TestCase):
    def test_create_paper_broker(self) -> None:
        broker = create_broker("paper", initial_cash=5000)
        self.assertIsInstance(broker, PaperBroker)

    def test_paper_broker_connect(self) -> None:
        broker = create_broker("paper")
        self.assertTrue(broker.connect())
        self.assertTrue(broker.is_connected)

    def test_paper_broker_account(self) -> None:
        broker = create_broker("paper", initial_cash=10000)
        broker.connect()
        acct = broker.get_account()
        self.assertEqual(acct.balance, 10000)
        self.assertEqual(acct.exchange, ExchangeType.PAPER)

    def test_paper_broker_buy_sell(self) -> None:
        broker = create_broker("paper", initial_cash=10000)
        broker.connect()
        broker.update_price("BTCUSD", 50000)

        # Buy
        result = broker.place_order("BTCUSD", OrderSide.BUY, 0.1)
        self.assertEqual(result.status, OrderStatus.FILLED)
        self.assertAlmostEqual(broker.cash, 10000 - 0.1 * 50000)

        # Verify position
        positions = broker.get_positions()
        self.assertEqual(len(positions), 1)

        # Sell
        result = broker.place_order("BTCUSD", OrderSide.SELL, 0.1)
        self.assertEqual(result.status, OrderStatus.FILLED)
        self.assertAlmostEqual(broker.cash, 10000)
        self.assertEqual(len(broker.get_positions()), 0)

    def test_paper_broker_insufficient_funds(self) -> None:
        broker = create_broker("paper", initial_cash=100)
        broker.connect()
        broker.update_price("BTCUSD", 50000)
        result = broker.place_order("BTCUSD", OrderSide.BUY, 1.0)
        self.assertEqual(result.status, OrderStatus.REJECTED)

    def test_paper_broker_no_position_to_sell(self) -> None:
        broker = create_broker("paper", initial_cash=10000)
        broker.connect()
        broker.update_price("BTCUSD", 50000)
        result = broker.place_order("BTCUSD", OrderSide.SELL, 0.1)
        self.assertEqual(result.status, OrderStatus.REJECTED)
        self.assertIn("no position", result.message.lower())

    def test_paper_broker_get_quote(self) -> None:
        broker = create_broker("paper")
        broker.connect()
        broker.update_price("AAPL", 150.0)
        quote = broker.get_quote("AAPL")
        self.assertIsNotNone(quote)
        self.assertEqual(quote.last, 150.0)
        self.assertAlmostEqual(quote.bid, 150.0 * 0.9995)
        self.assertAlmostEqual(quote.ask, 150.0 * 1.0005)

    def test_paper_broker_close_position_by_ticket(self) -> None:
        broker = create_broker("paper", initial_cash=10000)
        broker.connect()
        broker.update_price("ETHUSD", 3000)
        broker.place_order("ETHUSD", OrderSide.BUY, 1.0)
        positions = broker.get_positions()
        self.assertEqual(len(positions), 1)
        ticket = positions[0].ticket

        result = broker.close_position(ticket)
        self.assertEqual(result.status, OrderStatus.FILLED)
        self.assertEqual(len(broker.get_positions()), 0)

    def test_create_broker_factory_paper(self) -> None:
        broker = create_broker("paper", initial_cash=9999)
        self.assertIsInstance(broker, PaperBroker)
        broker.connect()
        self.assertEqual(broker.get_account().balance, 9999)

    def test_create_broker_unknown_fallback_paper(self) -> None:
        broker = create_broker("unknown_backend", initial_cash=5000)
        self.assertIsInstance(broker, PaperBroker)

    def test_exchange_type_enum_values(self) -> None:
        self.assertEqual(ExchangeType.PAPER.value, "paper")
        self.assertEqual(ExchangeType.MT5.value, "mt5")
        self.assertEqual(ExchangeType.BINANCE.value, "binance")
        self.assertEqual(ExchangeType.ALPACA.value, "alpaca")


# ══════════════════════════════════════════════════════════════════════════
#  Indicator tests
# ══════════════════════════════════════════════════════════════════════════

class IndicatorTests(unittest.TestCase):
    def test_ema_calculation(self) -> None:
        from aitrader_bot.indicators import ema
        values = [10, 11, 12, 13, 14, 15, 16, 17]
        result = ema(values, 5)
        self.assertIsNotNone(result)
        self.assertGreater(result, 0)

    def test_macd_calculation(self) -> None:
        from aitrader_bot.indicators import macd
        values = [float(i) for i in range(30, 60)]
        macd_line, signal, hist = macd(values, 12, 26, 9)
        self.assertIsNotNone(hist)


# ══════════════════════════════════════════════════════════════════════════
#  Config tests
# ══════════════════════════════════════════════════════════════════════════

class ConfigTests(unittest.TestCase):
    def test_config_defaults(self) -> None:
        cfg = BotConfig()
        self.assertEqual(cfg.symbol, "BTC-USD")
        self.assertEqual(cfg.scalping.ema_slow, 21)  # Dual-state: EMA 21
        self.assertEqual(cfg.brokers["default"].backend, "paper")

    def test_scalping_config_defaults(self) -> None:
        cfg = ScalpingConfig()
        self.assertEqual(cfg.ema_fast, 9)       # Dual-state: EMA 9
        self.assertEqual(cfg.ema_slow, 21)      # Dual-state: EMA 21
        self.assertEqual(cfg.macd_fast, 12)
        self.assertEqual(cfg.bb_window, 20)
        self.assertEqual(cfg.max_trade_pct, 0.05)


if __name__ == "__main__":
    unittest.main()

"""Regression tests for live-entry and position-management safety."""

from __future__ import annotations

import json
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from aitrader_bot.app.engine import (
    WIB,
    _compute_sl_tp,
    _detect_sessions,
    _entry_safety_blocks,
    _is_close_complete,
    _is_entry_session_open,
    _position_entry_time,
    TradingEngine,
)
from aitrader_bot.broker import ExchangeType, OrderSide, OrderStatus, PaperBroker
from aitrader_bot.broker.base import OrderResult, PositionInfo, Quote
from aitrader_bot.broker.mt5_broker import Mt5Broker, _mt5_order_status
from aitrader_bot.broker.alpaca_broker import AlpacaBroker, _map_alpaca_order_status
from aitrader_bot.config import ScalpingConfig
from aitrader_bot.cli import _cmd_scalp
from aitrader_bot.models import Signal


def _quote(*, bid: float = 3300.00, ask: float = 3300.20, point_size=0.01) -> Quote:
    return Quote(
        symbol="XAUUSD",
        exchange=ExchangeType.MT5,
        bid=bid,
        ask=ask,
        last=(bid + ask) / 2,
        volume=10,
        timestamp=datetime(2026, 7, 10, tzinfo=timezone.utc),
        point_size=point_size,
    )


def _order_result(status: OrderStatus, filled_qty: float) -> OrderResult:
    return OrderResult(
        exchange=ExchangeType.PAPER,
        order_id="test",
        status=status,
        symbol="XAUUSD",
        side=OrderSide.SELL,
        quantity=0.1,
        filled_qty=filled_qty,
        price=3300.0,
        avg_fill_price=3300.0,
        message="test result",
        timestamp=datetime(2026, 7, 10, tzinfo=timezone.utc),
    )


class SessionSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = ScalpingConfig(
            session_filter_enabled=True,
            session_london_start=14,
            session_london_end=18,
            session_ny_start=19,
            session_ny_end=22,
            news_filter_enabled=False,
        )

    def test_entry_session_gate_uses_wib_boundaries(self) -> None:
        self.assertFalse(_is_entry_session_open(self.config, datetime(2026, 7, 10, 13, 59, tzinfo=WIB)))
        self.assertTrue(_is_entry_session_open(self.config, datetime(2026, 7, 10, 14, 0, tzinfo=WIB)))
        self.assertTrue(_is_entry_session_open(self.config, datetime(2026, 7, 10, 19, 30, tzinfo=WIB)))
        self.assertFalse(_is_entry_session_open(self.config, datetime(2026, 7, 10, 22, 0, tzinfo=WIB)))

    def test_disabled_session_filter_allows_entry(self) -> None:
        config = ScalpingConfig(session_filter_enabled=False)
        self.assertTrue(_is_entry_session_open(config, datetime(2026, 7, 10, 3, 0, tzinfo=WIB)))

    def test_dashboard_sessions_handle_overnight_window(self) -> None:
        sessions = _detect_sessions(datetime(2026, 7, 10, 3, 0, tzinfo=WIB))
        self.assertTrue(sessions["new_york"])


class EntrySafetyGateTests(unittest.TestCase):
    def test_spread_is_converted_from_price_to_broker_points(self) -> None:
        self.assertAlmostEqual(_quote().spread_points, 20.0)

    def test_open_session_and_safe_spread_have_no_blocks(self) -> None:
        config = ScalpingConfig(news_filter_enabled=False, max_spread_points=25)
        blocks = _entry_safety_blocks(
            config,
            _quote(),
            supports_attached_protection=True,
            now=datetime(2026, 7, 10, 14, 0, tzinfo=WIB),
        )
        self.assertEqual(blocks, [])

    def test_gate_fails_closed_for_high_or_unknown_spread(self) -> None:
        config = ScalpingConfig(news_filter_enabled=False, max_spread_points=25)
        high = _entry_safety_blocks(
            config,
            _quote(ask=3300.30),
            supports_attached_protection=True,
            now=datetime(2026, 7, 10, 14, 0, tzinfo=WIB),
        )
        unknown = _entry_safety_blocks(
            config,
            _quote(point_size=None),
            supports_attached_protection=True,
            now=datetime(2026, 7, 10, 14, 0, tzinfo=WIB),
        )
        self.assertTrue(any("spread 30.0pts" in reason for reason in high))
        self.assertIn("spread point size unavailable", unknown)

    def test_gate_blocks_news_and_unprotected_broker(self) -> None:
        config = ScalpingConfig(news_filter_enabled=True, max_spread_points=25)
        blocks = _entry_safety_blocks(
            config,
            _quote(),
            supports_attached_protection=False,
            now=datetime(2026, 7, 10, 14, 0, tzinfo=WIB),
            news_event={"name": "CPI", "phase": "before"},
        )
        self.assertTrue(any("news filter" in reason for reason in blocks))
        self.assertIn("broker does not support attached SL/TP", blocks)


class PositionRecoveryTests(unittest.TestCase):
    def test_position_entry_time_is_normalized_to_utc(self) -> None:
        opened_at = datetime(2026, 7, 10, 14, 5, tzinfo=WIB)
        position = PositionInfo(
            symbol="XAUUSD",
            exchange=ExchangeType.MT5,
            quantity=0.1,
            avg_price=3300,
            current_price=3301,
            unrealized_pnl=10,
            opened_at=opened_at,
        )
        recovered = _position_entry_time(position)
        self.assertEqual(recovered, datetime(2026, 7, 10, 7, 5, tzinfo=timezone.utc))

    def test_missing_entry_time_does_not_invent_timestamp(self) -> None:
        position = PositionInfo("XAUUSD", ExchangeType.MT5, 0.1, 3300, 3301, 10)
        self.assertIsNone(_position_entry_time(position))

    def test_close_only_completes_on_full_fill(self) -> None:
        self.assertTrue(_is_close_complete(_order_result(OrderStatus.FILLED, 0.1), 0.1))
        self.assertFalse(_is_close_complete(_order_result(OrderStatus.PARTIAL, 0.05), 0.1))
        self.assertFalse(_is_close_complete(_order_result(OrderStatus.REJECTED, 0.0), 0.1))
        self.assertFalse(_is_close_complete(None, 0.1))
        self.assertTrue(_is_close_complete(_order_result(OrderStatus.FILLED, 0.1), -0.1))

    def test_alpaca_close_status_is_not_assumed_filled(self) -> None:
        self.assertEqual(
            _map_alpaca_order_status("new", 0.0, 1.0),
            OrderStatus.PENDING,
        )
        self.assertEqual(
            _map_alpaca_order_status("partially_filled", 0.5, 1.0),
            OrderStatus.PARTIAL,
        )
        self.assertEqual(
            _map_alpaca_order_status("filled", 1.0, 1.0),
            OrderStatus.FILLED,
        )

    def test_alpaca_close_adapter_preserves_pending_status(self) -> None:
        position = SimpleNamespace(
            symbol="AAPL",
            qty="1",
            avg_entry_price="190",
            current_price="191",
            unrealized_pl="1",
            unrealized_plpc="0.005",
            asset_id="asset-1",
            side="long",
        )
        close_order = SimpleNamespace(
            id="order-1",
            status="new",
            filled_qty="0",
            filled_avg_price=None,
            created_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
        )
        client = SimpleNamespace(
            get_all_positions=lambda: [position],
            close_position=lambda symbol: close_order,
        )
        broker = AlpacaBroker()
        broker._trading_client = client
        broker._connected = True
        result = broker.close_position("asset-1")
        self.assertEqual(result.status, OrderStatus.PENDING)
        self.assertEqual(result.filled_qty, 0.0)
        self.assertFalse(_is_close_complete(result, 1.0))
        position.side = "short"
        short_close = broker.close_position("asset-1")
        self.assertEqual(short_close.side, OrderSide.BUY)


class ProtectivePriceTests(unittest.TestCase):
    def test_sl_tp_uses_broker_point_size_and_symbol_precision(self) -> None:
        config = ScalpingConfig(stop_loss_pips=30, take_profit_pips=15)
        result = _compute_sl_tp(1.10000, "buy", config, symbol="EURUSD", point_size=0.00001)
        self.assertEqual(result["sl"], 1.09700)
        self.assertEqual(result["tp"], 1.10150)

    def test_paper_position_preserves_protection_and_open_time(self) -> None:
        broker = PaperBroker(initial_cash=10000, point_size=0.01)
        broker.connect()
        broker.update_price("XAUUSD", 3300)
        result = broker.place_order(
            "XAUUSD", OrderSide.BUY, 0.1, stop_loss=3297, take_profit=3301.5,
        )
        self.assertEqual(result.status, OrderStatus.FILLED)
        position = broker.get_positions("XAUUSD")[0]
        self.assertEqual(position.stop_loss, 3297)
        self.assertEqual(position.take_profit, 3301.5)
        self.assertIsNotNone(position.opened_at)
        self.assertEqual(position.side, "buy")

    def test_paper_rejects_invalid_buy_protection(self) -> None:
        broker = PaperBroker(initial_cash=10000)
        broker.connect()
        broker.update_price("XAUUSD", 3300)
        result = broker.place_order(
            "XAUUSD", OrderSide.BUY, 0.1, stop_loss=3301, take_profit=3302,
        )
        self.assertEqual(result.status, OrderStatus.REJECTED)
        self.assertEqual(broker.get_positions(), [])


class _FakeMt5:
    ORDER_TYPE_BUY = 0
    ORDER_TYPE_SELL = 1
    ORDER_TYPE_BUY_LIMIT = 2
    ORDER_TYPE_SELL_LIMIT = 3
    TRADE_ACTION_DEAL = 10
    TRADE_ACTION_SLTP = 11
    ORDER_TIME_GTC = 20
    TRADE_RETCODE_DONE = 10009
    TRADE_RETCODE_DONE_PARTIAL = 10010
    TRADE_RETCODE_PLACED = 10008
    SYMBOL_FILLING_FOK = 1
    ORDER_FILLING_FOK = 0
    ACCOUNT_MARGIN_MODE_RETAIL_HEDGING = 2

    def __init__(self) -> None:
        self.last_request = None
        self.send_count = 0
        self.positions = []
        self.margin_mode = self.ACCOUNT_MARGIN_MODE_RETAIL_HEDGING

    def symbol_select(self, symbol, enabled):
        return True

    def symbol_info(self, symbol):
        return SimpleNamespace(
            point=0.01,
            digits=2,
            trade_stops_level=0,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            filling_mode=1,
        )

    def symbol_info_tick(self, symbol):
        return SimpleNamespace(bid=3300.00, ask=3300.20, volume=5, time=1_720_000_000)

    def order_check(self, request):
        self.last_request = dict(request)
        return SimpleNamespace(retcode=0, comment="ok")

    def order_send(self, request):
        self.send_count += 1
        self.last_request = dict(request)
        return SimpleNamespace(
            retcode=self.TRADE_RETCODE_DONE,
            order=123,
            volume=request.get("volume", 0.0),
            price=request.get("price", 0.0),
        )

    def positions_get(self, **kwargs):
        return self.positions

    def account_info(self):
        return SimpleNamespace(margin_mode=self.margin_mode)

    def last_error(self):
        return (0, "ok")


class Mt5ProtectiveOrderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = _FakeMt5()
        self.broker = Mt5Broker()
        self.broker._mt5 = self.transport
        self.broker._connected = True

    def test_mt5_entry_request_attaches_normalized_sl_tp(self) -> None:
        result = self.broker.place_order(
            "XAUUSD", OrderSide.BUY, 0.1, stop_loss=3297.001, take_profit=3301.999,
        )
        self.assertEqual(result.status, OrderStatus.FILLED)
        self.assertEqual(self.transport.last_request["sl"], 3297.00)
        self.assertEqual(self.transport.last_request["tp"], 3302.00)

    def test_mt5_short_entry_and_close_use_inverse_order_sides(self) -> None:
        entry = self.broker.place_order(
            "XAUUSD", OrderSide.SELL, 0.1, stop_loss=3303.0, take_profit=3299.0,
        )
        self.assertEqual(entry.status, OrderStatus.FILLED)
        self.assertEqual(self.transport.last_request["type"], self.transport.ORDER_TYPE_SELL)
        self.transport.positions = [SimpleNamespace(
            symbol="XAUUSD",
            volume=0.1,
            price_open=3300.0,
            price_current=3299.0,
            profit=10.0,
            ticket=789,
            type=self.transport.ORDER_TYPE_SELL,
            time=1_720_000_000,
            sl=3303.0,
            tp=3299.0,
        )]
        close = self.broker.close_position("789")
        self.assertEqual(close.status, OrderStatus.FILLED)
        self.assertEqual(close.side, OrderSide.BUY)
        self.assertEqual(self.transport.last_request["type"], self.transport.ORDER_TYPE_BUY)

    def test_mt5_rejects_invalid_protection_before_sending(self) -> None:
        result = self.broker.place_order(
            "XAUUSD", OrderSide.BUY, 0.1, stop_loss=3301, take_profit=3302,
        )
        self.assertEqual(result.status, OrderStatus.REJECTED)
        self.assertEqual(self.transport.send_count, 0)

    def test_mt5_partial_and_pending_results_are_not_reported_filled(self) -> None:
        self.assertEqual(
            _mt5_order_status(self.transport, SimpleNamespace(retcode=10010)),
            OrderStatus.PARTIAL,
        )
        self.assertEqual(
            _mt5_order_status(self.transport, SimpleNamespace(retcode=10008)),
            OrderStatus.PENDING,
        )

    def test_mt5_multiple_position_capability_follows_account_mode(self) -> None:
        self.assertTrue(self.broker.supports_multiple_positions)
        self.transport.margin_mode = 0
        self.assertFalse(self.broker.supports_multiple_positions)

    def test_mt5_quote_and_position_expose_safety_metadata(self) -> None:
        opened = 1_720_000_000
        self.transport.positions = [SimpleNamespace(
            symbol="XAUUSD",
            volume=0.1,
            price_open=3300.2,
            price_current=3300.5,
            profit=3.0,
            ticket=456,
            type=self.transport.ORDER_TYPE_BUY,
            time=opened,
            sl=3297.0,
            tp=3302.0,
        )]
        quote = self.broker.get_quote("XAUUSD")
        position = self.broker.get_positions("XAUUSD")[0]
        self.assertAlmostEqual(quote.spread_points, 20.0)
        self.assertEqual(position.opened_at, datetime.fromtimestamp(opened, tz=timezone.utc))
        self.assertEqual(position.stop_loss, 3297.0)
        self.assertEqual(position.take_profit, 3302.0)

    def test_mt5_can_restore_protection_on_existing_position(self) -> None:
        self.transport.positions = [SimpleNamespace(
            symbol="XAUUSD",
            volume=0.1,
            price_open=3300.2,
            price_current=3300.5,
            profit=3.0,
            ticket=456,
            type=self.transport.ORDER_TYPE_BUY,
            time=1_720_000_000,
            sl=0.0,
            tp=0.0,
        )]
        result = self.broker.set_position_protection("456", 3297.0, 3302.0)
        self.assertEqual(result.status, OrderStatus.FILLED)
        self.assertEqual(self.transport.last_request["action"], self.transport.TRADE_ACTION_SLTP)
        self.assertEqual(self.transport.last_request["sl"], 3297.0)
        self.assertEqual(self.transport.last_request["tp"], 3302.0)


class _OneShotPaper(PaperBroker):
    def __init__(self, *args, reject_close: bool = False, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.engine = None
        self.entry_orders = 0
        self.close_attempts = 0
        self.reject_close = reject_close

    def get_quote(self, symbol):
        quote = super().get_quote(symbol)
        if self.engine is not None:
            self.engine._stop.set()
        return quote

    def place_order(self, symbol, side, quantity, *args, **kwargs):
        if side == OrderSide.BUY:
            self.entry_orders += 1
        return super().place_order(symbol, side, quantity, *args, **kwargs)

    def close_position(self, ticket):
        self.close_attempts += 1
        if self.reject_close:
            return _order_result(OrderStatus.REJECTED, 0.0)
        return super().close_position(ticket)


class _FixedStrategy:
    def __init__(self, config, action: str) -> None:
        self.config = config
        self.action = action

    def generate(self, symbol, bars, quote):
        return Signal(
            symbol=symbol,
            action=self.action,
            confidence=0.9,
            price=quote.last,
            reason="test signal",
            created_at=datetime.now(timezone.utc),
        )


class TradingEngineSafetyIntegrationTests(unittest.TestCase):
    def _config_file(self, **scalping_overrides) -> Path:
        scalping = {
            "interval_seconds": 0,
            "session_filter_enabled": True,
            "session_london_start": 14,
            "session_london_end": 18,
            "session_ny_start": 19,
            "session_ny_end": 22,
            "news_filter_enabled": False,
            "max_spread_points": 25,
            "stop_loss_pips": 1,
            "take_profit_pips": 100,
            "trailing_stop_pips": 0,
        }
        scalping.update(scalping_overrides)
        handle = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8")
        with handle:
            json.dump({
                "symbol": "XAUUSD",
                "scalping": scalping,
                "brokers": {"default": {"backend": "paper", "initial_cash": 10000}},
            }, handle)
        self.addCleanup(lambda: Path(handle.name).unlink(missing_ok=True))
        return Path(handle.name)

    @staticmethod
    def _seed_bars(broker: PaperBroker, price: float) -> None:
        bars = [
            SimpleNamespace(
                symbol="XAUUSD",
                exchange=ExchangeType.PAPER,
                timestamp=datetime(2026, 7, 10, minute=i, tzinfo=timezone.utc),
                open=price,
                high=price + 0.1,
                low=price - 0.1,
                close=price,
                volume=1000,
                timeframe="1m",
            )
            for i in range(30)
        ]
        broker.update_candles("XAUUSD", bars)

    def _run_engine_once(
        self,
        broker: _OneShotPaper,
        action: str,
        *,
        wib_hour: int = 13,
        **scalping_overrides,
    ) -> None:
        config_path = self._config_file(**scalping_overrides)
        engine = TradingEngine(str(config_path), "default")
        broker.engine = engine

        def strategy_factory(config):
            return _FixedStrategy(config, action)

        with (
            patch("aitrader_bot.app.engine.create_broker", return_value=broker),
            patch("aitrader_bot.app.engine.ScalpingStrategy", side_effect=strategy_factory),
            patch("aitrader_bot.app.engine.notify_web"),
            patch("aitrader_bot.decision.as_wib", return_value=datetime(2026, 7, 10, wib_hour, 0, tzinfo=WIB)),
        ):
            engine._run()

    def test_closed_session_blocks_entry_in_real_engine_loop(self) -> None:
        broker = _OneShotPaper(initial_cash=10000)
        self._seed_bars(broker, 100.0)
        self._run_engine_once(broker, "buy")
        self.assertEqual(broker.entry_orders, 0)
        self.assertEqual(broker.get_positions(), [])

    def test_rejected_safety_close_keeps_position_open(self) -> None:
        broker = _OneShotPaper(initial_cash=10000, reject_close=True)
        broker.connect()
        broker.update_price("XAUUSD", 100.0)
        broker.place_order("XAUUSD", OrderSide.BUY, 0.1)
        broker.entry_orders = 0
        self._seed_bars(broker, 90.0)
        self._run_engine_once(broker, "hold")
        self.assertEqual(broker.close_attempts, 1)
        self.assertEqual(len(broker.get_positions("XAUUSD")), 1)

    def test_flat_sell_signal_opens_protected_short(self) -> None:
        broker = _OneShotPaper(initial_cash=10000)
        self._seed_bars(broker, 100.0)
        self._run_engine_once(broker, "sell", wib_hour=14)
        positions = broker.get_positions("XAUUSD")
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0].side, "sell")
        self.assertGreater(positions[0].stop_loss, positions[0].avg_price)
        self.assertLess(positions[0].take_profit, positions[0].avg_price)

    def test_scale_in_configuration_allows_multiple_long_tickets(self) -> None:
        broker = _OneShotPaper(initial_cash=10000)
        self._seed_bars(broker, 100.0)
        overrides = {
            "max_open_positions": 2,
            "max_positions_per_side": 2,
            "allow_scale_in": True,
        }
        self._run_engine_once(broker, "buy", wib_hour=14, **overrides)
        self._run_engine_once(broker, "buy", wib_hour=14, **overrides)
        positions = broker.get_positions("XAUUSD")
        self.assertEqual(len(positions), 2)
        self.assertEqual({position.side for position in positions}, {"buy"})
        self.assertEqual(len({position.ticket for position in positions}), 2)

    def test_risk_exit_closes_every_triggered_ticket(self) -> None:
        broker = _OneShotPaper(initial_cash=10000)
        broker.connect()
        broker.update_price("XAUUSD", 100.0)
        broker.place_order("XAUUSD", OrderSide.BUY, 0.1)
        broker.place_order("XAUUSD", OrderSide.SELL, 0.1)
        self._seed_bars(broker, 90.0)
        # With modeled bid/ask spread the short is +99 pips at this price;
        # use a 90-pip TP so both tickets are unambiguously triggered.
        self._run_engine_once(broker, "hold", take_profit_pips=90)
        self.assertEqual(broker.close_attempts, 2)
        self.assertEqual(broker.get_positions("XAUUSD"), [])

    def test_cli_scalp_uses_same_state_machine_for_short_entry(self) -> None:
        broker = _OneShotPaper(initial_cash=10000)
        self._seed_bars(broker, 100.0)
        config_path = self._config_file()
        args = SimpleNamespace(
            config=str(config_path),
            broker="default",
            symbol=None,
            iterations=1,
            interval=0,
        )

        with (
            patch("aitrader_bot.cli.create_broker", return_value=broker),
            patch("aitrader_bot.cli.ScalpingStrategy", side_effect=lambda cfg: _FixedStrategy(cfg, "sell")),
            patch("aitrader_bot.decision.as_wib", return_value=datetime(2026, 7, 10, 14, 0, tzinfo=WIB)),
            redirect_stdout(io.StringIO()),
        ):
            _cmd_scalp(args)

        positions = broker.get_positions("XAUUSD")
        self.assertEqual(len(positions), 1)
        self.assertEqual(positions[0].side, "sell")


if __name__ == "__main__":
    unittest.main()

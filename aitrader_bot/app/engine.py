"""Background multi-pair trading engine.

One engine owns the broker connection and account cadence.  A dedicated
``SymbolProcessor`` owns all symbol-specific services, preventing positions,
risk state, dashboard data, and an agent prediction from leaking between
pairs.
"""

from __future__ import annotations

import time
from datetime import datetime
from queue import Queue
from threading import Event, Thread

from aitrader_bot.agents.performance_registry import PerformanceRegistry
from aitrader_bot.broker import create_broker
from aitrader_bot.config import BotConfig, load_config
from aitrader_bot.decision import (
    WIB,
    compute_protective_prices as _compute_sl_tp,
    entry_safety_blocks as _entry_safety_blocks,
    is_entry_session_open as _is_entry_session_open,
)
from aitrader_bot.scalping import ScalpingStrategy
from aitrader_bot.services.execution import (
    is_close_complete as _is_close_complete,
)
from aitrader_bot.services.position_state import (
    position_entry_time as _position_entry_time,
)
from aitrader_bot.services.risk import detect_sessions as _detect_sessions

from . import dashboard_data as dd
from .logger import setup_logging
from .notifier import TelegramNotifier
from .symbol_processor import SymbolProcessor
from .web_dashboard import notify as notify_web

log = setup_logging(__name__)

ACCOUNT_REFRESH_SECONDS = 10.0


class TradingEngine:
    """Run a safe, isolated processor for each configured trading symbol."""

    def __init__(self, config_path: str, broker_name: str = "mt5") -> None:
        self._config_path = config_path
        self._broker_name = broker_name
        self._thread: Thread | None = None
        self._stop = Event()
        self.queue: Queue = Queue()
        self.config: BotConfig | None = None
        self.broker = None
        self.processors: list[SymbolProcessor] = []
        self._current_status = "stopped"

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def status(self) -> str:
        return self._current_status

    def start(self) -> None:
        if self.is_running:
            return
        self._stop.clear()
        self._thread = Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=10)
        self._current_status = "stopped"
        self._put("status:stopped")

    def _run(self) -> None:
        self._current_status = "starting"
        self._put("status:starting")
        try:
            self.config = load_config(self._config_path)
        except Exception as exc:
            self._fail_startup(f"gagal load config: {exc}")
            return

        broker_cfg = self.config.brokers.get(self._broker_name)
        if not broker_cfg:
            available = ", ".join(self.config.brokers)
            self._fail_startup(
                f"broker '{self._broker_name}' tidak ditemukan. Tersedia: {available}"
            )
            return

        telegram = TelegramNotifier(
            bot_token=self.config.telegram.bot_token,
            chat_id=self.config.telegram.chat_id,
        )
        try:
            self.broker = create_broker(
                broker_cfg.backend,
                api_key=broker_cfg.api_key,
                secret=broker_cfg.secret,
                server=broker_cfg.server,
                login=broker_cfg.login,
                password=broker_cfg.password,
                terminal_path=broker_cfg.terminal_path,
                timeout_ms=broker_cfg.timeout_ms,
                portable=broker_cfg.portable,
                paper=broker_cfg.paper,
                sandbox=broker_cfg.sandbox,
                initial_cash=self.config.risk.initial_cash,
            )
            self.broker.connect()
            account = self.broker.get_account()
            self._publish_connection(account)
            registry = PerformanceRegistry()
            self.processors = [
                SymbolProcessor(
                    broker=self.broker,
                    symbol=item.symbol,
                    scalping_config=self.config.scalping_for(item),
                    ai_config=self.config.ai,
                    telegram=telegram,
                    strategy_factory=ScalpingStrategy,
                    performance_registry=registry,
                    emit=self._put,
                    notify_dashboard=notify_web,
                )
                for item in self.config.enabled_symbols
            ]
            if not self.processors:
                raise RuntimeError("tidak ada symbol aktif untuk diproses")
        except Exception as exc:
            telegram.send_error(f"Connection failed: {exc}")
            self._fail_startup(f"Koneksi gagal: {exc}")
            self._disconnect()
            return

        symbols = ", ".join(processor.symbol for processor in self.processors)
        dd.reset_account_metrics(account.equity, account.balance)
        dd.update(
            status="running",
            broker=self._broker_name,
            telegram=telegram.enabled,
            started_at=datetime.now().isoformat(),
            active_symbols=[processor.symbol for processor in self.processors],
        )
        dd.add_log(f"Connected: {symbols} | Equity ${account.equity:.2f}")
        self._put(f"account:{account.equity}")
        self._put("status:running")
        self._current_status = "running"
        telegram.send_startup(symbols, self._broker_name, account.equity)
        notify_web()

        last_account_refresh = time.monotonic()

        def refresh_account(*, force: bool = False) -> None:
            nonlocal last_account_refresh
            now_tick = time.monotonic()
            if not force and now_tick - last_account_refresh < ACCOUNT_REFRESH_SECONDS:
                return
            try:
                latest = self.broker.get_account()
                last_account_refresh = now_tick
                dd.update(equity=latest.equity, balance=latest.balance)
                self._publish_connection(latest)
                self._put(f"account:{latest.equity}")
                notify_web()
            except Exception as exc:
                log.warning("Account refresh failed: %s", exc)

        while not self._stop.is_set():
            messages: list[str] = []
            saw_market_data = False
            for processor in self.processors:
                if self._stop.is_set():
                    break
                try:
                    result = processor.process_cycle()
                    messages.append(result.message)
                    saw_market_data = saw_market_data or result.had_market_data
                except Exception as exc:
                    error = f"{processor.symbol}: loop error: {exc}"
                    log.exception(error)
                    dd.add_log(f"ERROR: {error}")
                    self._put(f"error:{error}")
                    telegram.send_error(error)
            if messages:
                self._put(f"signal:{' || '.join(messages)}")
            refresh_account()

            if self._stop.is_set():
                break
            interval = min(
                max(0, processor.strategy.config.interval_seconds)
                for processor in self.processors
            )
            # If a market is temporarily unavailable, retry promptly without
            # busy-waiting; otherwise honour the shortest pair interval.
            wait_seconds = 10 if not saw_market_data else interval
            self._wait_with_account_refresh(wait_seconds, refresh_account)

        telegram.send_shutdown("engine stopped")
        self._disconnect()
        dd.update(status="stopped")
        dd.update_mt5_status(False)
        dd.add_log("Engine stopped")
        notify_web()
        self._current_status = "stopped"
        self._put("status:stopped")

    def _publish_connection(self, account) -> None:
        """Publish account and MT5 metadata without exposing credentials."""
        is_mt5 = getattr(getattr(account, "exchange", None), "value", "") == "mt5"
        login = getattr(self.broker, "_login", None) if is_mt5 else None
        server = getattr(self.broker, "_server", "") if is_mt5 else ""
        trade_allowed = None
        if is_mt5 and hasattr(self.broker, "get_connection_status"):
            try:
                connection = self.broker.get_connection_status()
                login = connection.get("login") or login
                server = connection.get("server") or server
                trade_allowed = connection.get("trade_allowed")
                if connection.get("last_error"):
                    dd.update(mt5_last_error=connection.get("last_error"))
            except Exception as exc:
                log.debug("Unable to read active MT5 account metadata: %s", exc)
        info = {
            "balance": account.balance,
            "equity": account.equity,
            "margin": account.margin,
            "margin_free": account.margin_free,
            "leverage": account.leverage,
            "currency": account.currency,
        }
        dd.update_mt5_status(
            is_mt5,
            login=login,
            server=server,
            trade_allowed=trade_allowed,
            account_info=info if is_mt5 else None,
        )

    def _wait_with_account_refresh(self, seconds: float, refresh_account) -> None:
        remaining = max(0.0, float(seconds))
        while remaining > 0 and not self._stop.is_set():
            chunk = min(5.0, remaining)
            time.sleep(chunk)
            remaining -= chunk
            refresh_account()

    def _fail_startup(self, message: str) -> None:
        log.error(message)
        self._put(f"error:{message}")
        dd.update(status="error")
        dd.add_log(f"ERROR: {message}")
        notify_web()
        self._current_status = "error"

    def _disconnect(self) -> None:
        if self.broker is None:
            return
        try:
            self.broker.disconnect()
        except Exception:
            pass

    def _put(self, message: str) -> None:
        try:
            self.queue.put(message, block=False)
        except Exception:
            pass

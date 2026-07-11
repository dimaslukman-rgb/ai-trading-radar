"""Background trading engine — runs scalping loop in a separate thread.

Communicates with GUI/tray via a queue.Queue:

  Engine -> Queue -> Tray/GUI:
    "status:running"
    "status:stopped"
    "signal:bought 0.01 XAUUSD @ 4127.50"
    "signal:sold 0.01 XAUUSD @ 4130.00"
    "error:connection failed: ..."
    "account:7814.51"
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from queue import Queue
from threading import Event, Thread

from aitrader_bot.broker import create_broker
from aitrader_bot.config import BotConfig, load_config
from aitrader_bot.decision import (
    WIB,
    compute_protective_prices as _compute_sl_tp,
    entry_safety_blocks as _entry_safety_blocks,
    is_entry_session_open as _is_entry_session_open,
)
from aitrader_bot.position_state import PositionSide
from aitrader_bot.scalping import ScalpingStrategy
from aitrader_bot.services import (
    ExecutionKind,
    ExecutionService,
    MarketDataService,
    PositionStateService,
    RiskService,
    SignalService,
)
from aitrader_bot.services.execution import (
    compute_dollar_pnl as _compute_dollar_pnl,
    is_close_complete as _is_close_complete,
    order_result_detail as _order_result_detail,
)
from aitrader_bot.services.position_state import (
    dashboard_position_rows as _dashboard_position_rows,
    position_entry_time as _position_entry_time,
)
from aitrader_bot.services.risk import (
    current_session_label as _current_session_label,
    detect_sessions as _detect_sessions,
)
from aitrader_bot.services.signal import (
    compute_analysis as _compute_analysis,
    compute_confidence as _compute_confidence,
    compute_sentiment as _compute_sentiment,
    compute_volatility as _compute_volatility,
)

from . import dashboard_data as dd
from .logger import setup_logging
from .news_filter import get_macro_sentiment, get_upcoming_event
from .notifier import TelegramNotifier
from .web_dashboard import notify as notify_web

log = setup_logging(__name__)

ACCOUNT_REFRESH_SECONDS = 10.0


# Private helper aliases above preserve compatibility for CLI callers and
# existing integrations while their implementations live in focused services.

class TradingEngine:
    """Background thread running the scalping loop."""

    def __init__(self, config_path: str, broker_name: str = "mt5"):
        self._config_path = config_path
        self._broker_name = broker_name
        self._thread: Thread | None = None
        self._stop = Event()
        self.queue: Queue = Queue()
        self.config: BotConfig | None = None
        self.broker = None
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
        try:
            self.queue.put("status:stopped", block=False)
        except Exception:
            pass

    def _run(self) -> None:
        self._current_status = "starting"
        self._put("status:starting")

        # Load config
        try:
            self.config = load_config(self._config_path)
        except Exception as e:
            self._put(f"error:gagal load config: {e}")
            self._current_status = "error"
            return

        # Resolve broker config
        broker_cfg = self.config.brokers.get(self._broker_name)
        if not broker_cfg:
            available = ", ".join(self.config.brokers.keys())
            self._put(f"error:broker '{self._broker_name}' tidak ditemukan. Tersedia: {available}")
            self._current_status = "error"
            return

        # Create broker
        try:
            self.broker = create_broker(
                broker_cfg.backend,
                api_key=broker_cfg.api_key,
                secret=broker_cfg.secret,
                server=broker_cfg.server,
                login=broker_cfg.login,
                password=broker_cfg.password,
                paper=broker_cfg.paper,
                sandbox=broker_cfg.sandbox,
                initial_cash=self.config.risk.initial_cash,
            )
        except Exception as e:
            self._put(f"error:gagal create broker: {e}")
            self._current_status = "error"
            return

        symbol = self.config.symbol
        mapped_symbol = self.broker.get_symbol_map(symbol)
        strategy = ScalpingStrategy(self.config.scalping)

        # Init Telegram notifier
        tg = TelegramNotifier(
            bot_token=self.config.telegram.bot_token,
            chat_id=self.config.telegram.chat_id,
        )
        if tg.enabled:
            self._put("status:telegram enabled")
            log.info("Telegram notifications enabled")

        # Init web dashboard data store
        dd.update(
            status="starting",
            symbol=symbol,
            broker=self._broker_name,
            telegram=tg.enabled,
            started_at=datetime.now().isoformat(),
        )

        log.info(f"Symbol: {symbol} (mapped: {mapped_symbol})")
        timeframe_label = strategy.config.candle_timeframe
        interval_sec = strategy.config.interval_seconds
        sc = strategy.config

        # ── Aggressive mode flag for dashboard ─────────────────────────
        is_aggressive = strategy.config.aggressive_mode
        if is_aggressive:
            log.info(f"⚡ AGGRESSIVE MODE ACTIVE - TP={sc.take_profit_pips:.0f}p ({sc.take_profit_pips*10:.0f}pt) SL={sc.stop_loss_pips:.0f}p timeout={sc.timeout_exit_minutes}m max_lot={sc.max_lot_size}")
            dd.add_log(f"⚡ AGGRESSIVE MODE: TP {sc.take_profit_pips*10:.0f}pt timeout {sc.timeout_exit_minutes}m max_lot {sc.max_lot_size}")
            dd.update(aggressive_mode=True, timeout_minutes=sc.timeout_exit_minutes)
        else:
            dd.update(aggressive_mode=False)

        log.info(f"Strategy: Dual-state MOMENTUM(EMA {sc.ema_fast}/{sc.ema_slow}+MACD) | REVERSION(BB+Stoch {sc.stochastic_k},{sc.stochastic_d},{sc.stochastic_slowing})")
        log.info(f"Risk: SL={sc.stop_loss_pips:.0f}p TP={sc.take_profit_pips:.0f}p lock={sc.trailing_stop_pips:.0f}p spread_max={sc.max_spread_points:.0f}pts")
        log.info(f"Sessions: London {sc.session_london_start}:00-{sc.session_london_end}:00 NY {sc.session_ny_start}:30-{sc.session_ny_end}:00 WIB")
        log.info(f"Timeframe: {timeframe_label}, interval: {interval_sec}s")
        dd.add_log(f"Scalping {timeframe_label} dual-state | SL {sc.stop_loss_pips:.0f}p TP {sc.take_profit_pips:.0f}p")

        # Connect
        try:
            self.broker.connect()
            acct = self.broker.get_account()
            position_state_service = PositionStateService.from_config(
                self.broker,
                mapped_symbol,
                strategy.config,
            )
            risk_service = RiskService(
                strategy.config,
                position_state_service.machine,
            )
            market_data_service = MarketDataService(
                self.broker,
                mapped_symbol,
                strategy.config.candle_timeframe,
            )
            signal_service = SignalService(strategy, market_data_service)
            execution_service = ExecutionService(
                self.broker,
                mapped_symbol,
                symbol,
                position_state_service,
                risk_service,
            )

            # Update MT5 account information for dashboard
            mt5_login = None
            mt5_server = ""
            account_info = None

            if hasattr(self.broker, '_login') and self.broker._login is not None:
                mt5_login = self.broker._login
                mt5_server = getattr(self.broker, '_server', "")

                # Get account info for dashboard
                account_info = {
                    "balance": acct.balance,
                    "equity": acct.equity,
                    "margin": acct.margin,
                    "margin_free": acct.margin_free,
                    "leverage": acct.leverage,
                    "currency": acct.currency
                }

                log.info(f"MT5 Account Info - Login: {mt5_login}, Server: {mt5_server}")
                log.info(f"MT5 Account Details - Balance: {acct.balance}, Equity: {acct.equity}, Currency: {acct.currency}")

                # Update dashboard data with MT5 connection info
                dd.update_mt5_status(
                    connected=True,
                    login=mt5_login,
                    server=mt5_server,
                    account_info=account_info
                )
            else:
                log.warning("MT5 broker does not have login information")
                dd.update_mt5_status(
                    connected=True,
                    login=None,
                    server="",
                    account_info=None
                )

            dd.reset_account_metrics(acct.equity, acct.balance)
            self._put(f"account:{acct.equity}")
            self._put("status:running")
            self._current_status = "running"
            log.info(f"Connected - Account: {acct.balance} {acct.currency}, Equity: {acct.equity}")
            dd.update(
                status="running",
            )
            dd.add_log(f"Connected - Equity: ${acct.equity:.2f}")
            notify_web()
            tg.send_startup(symbol, self._broker_name, acct.equity)
        except Exception as e:
            error_msg = f"Koneksi gagal: {e}"
            self._put(f"error:{error_msg}")
            tg.send_error(f"Connection failed: {e}")
            log.error(error_msg)

            # Update MT5 status to disconnected
            dd.update_mt5_status(
                connected=False,
                login=None,
                server="",
                account_info=None,
                last_error=str(e)
            )

            dd.update(status="error")
            dd.add_log(f"ERROR: {error_msg}")
            notify_web()
            self._current_status = "error"
            return

        iteration = 0
        last_error_iter = -10  # for error notification cooldown
        last_account_refresh = time.monotonic()

        def refresh_account(force: bool = False) -> None:
            nonlocal last_account_refresh
            now_tick = time.monotonic()
            if not force and now_tick - last_account_refresh < ACCOUNT_REFRESH_SECONDS:
                return
            try:
                acct = self.broker.get_account()
                last_account_refresh = now_tick
                self._put(f"account:{acct.equity}")
                dd.update(equity=acct.equity, balance=acct.balance)
                notify_web()
            except Exception:
                pass

        # ── Main loop ──────────────────────────────────────────────────
        while not self._stop.is_set():
            iteration += 1

            try:
                # 1. Acquire one consistent quote/candle/bar snapshot.
                market_snapshot = market_data_service.snapshot()
                if market_snapshot is None:
                    self._put("signal:waiting - no quote, retry in 10s")
                    for _ in range(2):
                        if self._stop.is_set():
                            break
                        time.sleep(5)
                        refresh_account()
                    continue
                quote = market_snapshot.quote

                # 2. Risk gates apply only to entries; position exits remain live.
                news_event = None
                if strategy.config.news_filter_enabled:
                    news_event = get_upcoming_event(buffer_minutes=strategy.config.news_filter_minutes)
                entry_blocks = risk_service.entry_blocks(
                    quote,
                    supports_attached_protection=self.broker.supports_attached_protection,
                    news_event=news_event,
                )
                if entry_blocks:
                    block_summary = "; ".join(entry_blocks)
                    log.info(f"New entries blocked: {block_summary}")
                    self._put(f"signal:entry blocked — {block_summary}")

                # 3. Generate signal context and synchronize broker positions.
                signal_evaluation = signal_service.evaluate(
                    symbol,
                    market_snapshot,
                    entry_blocked=bool(entry_blocks),
                )
                signal = signal_evaluation.signal
                position_snapshot = position_state_service.sync()
                managed_positions = position_snapshot.managed_positions
                for ticket in position_snapshot.sync_result.opened:
                    recovered = position_state_service.machine.get(ticket)
                    log.info(
                        f"Discovered broker position {ticket}: "
                        f"{recovered.side.value} {recovered.quantity:.4f} {recovered.symbol}"
                    )

                dd.update(entry_time=(
                    position_snapshot.earliest_entry_time.isoformat()
                    if position_snapshot.earliest_entry_time else None
                ))

                # 4. Re-establish missing broker-side protection after recovery.
                for repair in execution_service.repair_missing_protection(
                    position_snapshot.broker_positions,
                    quote.point_size,
                ):
                    if repair.success:
                        log.info(repair.message)
                        dd.add_log(f"PROTECTION RESTORED: position {repair.ticket}")
                    else:
                        self._put(f"error:{repair.message}")
                        log.error(repair.message)
                        dd.add_log(f"ERROR: {repair.message}")
                        tg.send_error(repair.message)

                dd.update(open_positions=position_state_service.dashboard_rows(
                    quote.point_size,
                ))

                # 5. Publish the signal service's read-only radar analysis.
                sessions = _detect_sessions()
                session_label = _current_session_label(sessions)
                sltp = risk_service.protective_prices(
                    quote.last,
                    signal.action,
                    symbol=symbol,
                    point_size=quote.point_size,
                )
                macro = get_macro_sentiment()

                # Update dashboard radar data
                dd.update(
                    confidence_pct=signal_evaluation.confidence_pct,
                    confidence_category=signal_evaluation.confidence_category,
                    signal_action=signal.action.upper() if signal.action else "HOLD",
                    entry=sltp["entry"],
                    sl=sltp["sl"],
                    tp=sltp["tp"],
                    rr=sltp["rr"],
                    signal_status=signal_evaluation.confidence_category,
                    current_session=session_label,
                    sessions=sessions,
                    sentiment=signal_evaluation.sentiment,
                    volatility=signal_evaluation.volatility,
                    news_events=macro["events"],
                    macro_sentiment=macro,
                    analysis=signal_evaluation.analysis,
                )

                # 6. Plan risk/signal actions and execute them through one adapter.
                decision_plan = risk_service.decide(
                    signal.action,
                    mapped_symbol,
                    point_size=quote.point_size,
                    now=datetime.now(timezone.utc),
                    entry_block_reasons=entry_blocks,
                    higher_timeframe_confirmed=(
                        signal_evaluation.higher_timeframe_confirmed
                    ),
                    higher_timeframe_reason=signal_evaluation.higher_timeframe_reason,
                )
                execution_batch = execution_service.execute(
                    decision_plan.actions,
                    quote,
                    signal.reason,
                )
                signal_messages: list[str] = []

                for outcome in execution_batch.outcomes:
                    signal_messages.append(outcome.message)
                    if outcome.kind == ExecutionKind.CLOSED:
                        dd.add_trade(
                            f"CLOSE {outcome.side.name}", mapped_symbol,
                            outcome.price, outcome.quantity,
                            outcome.action.reason, outcome.pnl,
                        )
                        dd.add_log(outcome.message)
                        close_action = (
                            "sell" if outcome.side == PositionSide.LONG else "buy"
                        )
                        tg.send_signal(
                            close_action,
                            mapped_symbol,
                            outcome.price,
                            outcome.action.reason,
                            pnl=outcome.pnl,
                        )
                    elif outcome.kind == ExecutionKind.CLOSE_UNCONFIRMED:
                        self._put(f"error:{outcome.message}")
                        log.error(outcome.message)
                        dd.add_log(f"ERROR: {outcome.message}")
                    elif outcome.kind == ExecutionKind.OPENED:
                        dd.add_trade(
                            f"OPEN {outcome.side.name}", mapped_symbol,
                            outcome.price, outcome.quantity, signal.reason,
                        )
                        dd.add_log(outcome.message)
                        tg.send_signal(
                            outcome.side.value,
                            mapped_symbol,
                            outcome.price,
                            signal.reason,
                        )
                        dd.update(
                            entry_time=outcome.result.timestamp.isoformat(),
                            timeout_minutes=strategy.config.timeout_exit_minutes,
                        )
                    elif outcome.kind == ExecutionKind.ENTRY_REJECTED:
                        log.warning(outcome.message)
                        dd.add_log(f"REJECTED: {outcome.message}")

                signal_msg = " || ".join(signal_messages) or (
                    f"HOLD {mapped_symbol} @ {quote.last:.5f} sc={signal.confidence:.3f}"
                )
                self._put(f"signal:{signal_msg}")
                log.info(f"signal:{signal_msg}")

                if execution_batch.refresh_error:
                    log.warning(
                        "Position refresh after execution failed: "
                        f"{execution_batch.refresh_error}"
                    )
                dd.update(open_positions=position_state_service.dashboard_rows(
                    quote.point_size,
                ))

                # Update dashboard data with latest signal (msg always defined now)
                dd.update(
                    last_signal=signal_msg,
                    last_price=quote.last,
                    last_confidence=signal.confidence,
                )
                notify_web()

                # 6. Update dashboard account metrics on a 10-second cadence.
                refresh_account()

            except Exception as e:
                self._put(f"error:loop error: {e}")
                log.error(f"Loop error: {e}")
                dd.add_log(f"ERROR: {e}")
                notify_web()
                if iteration - last_error_iter > 3:
                    tg.send_error(f"Loop error: {e}")
                    last_error_iter = iteration

            # 7. Wait (check stop every 5s, total = interval_seconds)
            wait_cycles = strategy.config.interval_seconds // 5
            for _ in range(wait_cycles):
                if self._stop.is_set():
                    break
                time.sleep(5)
                refresh_account()

        # Cleanup
        tg.send_shutdown("engine stopped")
        log.info("Engine stopped - cleanup complete")
        dd.update(status="stopped")

        # Update MT5 status to disconnected
        dd.update_mt5_status(
            connected=False,
            login=None,
            server="",
            account_info=None
        )

        dd.add_log("Engine stopped")
        notify_web()
        try:
            self.broker.disconnect()
        except Exception:
            pass
        self._current_status = "stopped"
        self._put("status:stopped")
        log.info("status:stopped")

    def _put(self, msg: str) -> None:
        """Thread-safe queue put with non-blocking fallback."""
        try:
            self.queue.put(msg, block=False)
        except Exception:
            pass

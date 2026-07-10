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

import math
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from queue import Queue
from threading import Event, Thread

from aitrader_bot.broker import OrderSide, OrderStatus, create_broker
from aitrader_bot.config import BotConfig, load_config
from aitrader_bot.indicators import ema, macd, bollinger_bands, stochastic, rsi, volatility
from aitrader_bot.models import PriceBar
from aitrader_bot.position_state import (
    PositionActionType,
    PositionPhase,
    PositionSide,
    PositionStateMachine,
)
from aitrader_bot.scalping import ScalpingStrategy, ScalpingRiskManager

from . import dashboard_data as dd
from .logger import setup_logging
from .news_filter import get_macro_sentiment, get_upcoming_event
from .notifier import TelegramNotifier
from .web_dashboard import notify as notify_web

log = setup_logging(__name__)

ACCOUNT_REFRESH_SECONDS = 10.0
WIB = timezone(timedelta(hours=7), name="WIB")


# ═══════════════════════════════════════════════════════════════════════
#  Analysis helpers for AI Trading Radar dashboard
# ═══════════════════════════════════════════════════════════════════════

def _minutes_in_window(current: int, start: int, end: int) -> bool:
    """Return whether a minute-of-day falls in a possibly overnight window."""
    if start <= end:
        return start <= current < end
    return current >= start or current < end


def _as_wib(now: datetime | None = None) -> datetime:
    if now is None:
        return datetime.now(WIB)
    if now.tzinfo is None:
        return now.replace(tzinfo=WIB)
    return now.astimezone(WIB)


def _is_entry_session_open(config, now: datetime | None = None) -> bool:
    """Check the configured entry sessions in WIB; exits are never gated."""
    if not config.session_filter_enabled:
        return True
    local = _as_wib(now)
    current = local.hour * 60 + local.minute
    london_start = config.session_london_start * 60
    london_end = config.session_london_end * 60
    ny_start = config.session_ny_start * 60 + 30
    ny_end = config.session_ny_end * 60
    return (
        _minutes_in_window(current, london_start, london_end)
        or _minutes_in_window(current, ny_start, ny_end)
    )


def _entry_safety_blocks(
    config,
    quote,
    *,
    supports_attached_protection: bool,
    now: datetime | None = None,
    news_event: dict | None = None,
) -> list[str]:
    """Return fail-closed reasons that prevent a new entry order."""
    blocks: list[str] = []
    if not _is_entry_session_open(config, now):
        blocks.append(f"outside trading session (WIB {_as_wib(now):%H:%M})")

    if config.news_filter_enabled and news_event:
        blocks.append(f"news filter: {news_event['name']} ({news_event['phase']})")

    if config.max_spread_points > 0:
        spread_points = quote.spread_points
        if spread_points is None:
            blocks.append("spread point size unavailable")
        elif spread_points > config.max_spread_points:
            blocks.append(
                f"spread {spread_points:.1f}pts > max {config.max_spread_points:.1f}pts"
            )

    protection_required = config.stop_loss_pips > 0 or config.take_profit_pips > 0
    if protection_required and not supports_attached_protection:
        blocks.append("broker does not support attached SL/TP")
    return blocks


def _position_entry_time(position) -> datetime | None:
    """Normalize broker position time to aware UTC for restart recovery."""
    opened_at = getattr(position, "opened_at", None)
    if opened_at is None:
        return None
    if opened_at.tzinfo is None:
        return opened_at.replace(tzinfo=timezone.utc)
    return opened_at.astimezone(timezone.utc)


def _is_close_complete(result, expected_quantity: float) -> bool:
    """Only a fully filled close may transition local state to closed."""
    expected = abs(expected_quantity)
    return (
        result is not None
        and result.status == OrderStatus.FILLED
        and abs(result.filled_qty) + 1e-12 >= expected
    )


def _order_result_detail(result, expected_quantity: float) -> str:
    expected = abs(expected_quantity)
    if result is None:
        return f"status=missing filled=0.0000/{expected:.4f} | broker returned no result"
    return (
        f"status={result.status.value} filled={abs(result.filled_qty):.4f}/"
        f"{expected:.4f} | {result.message}"
    )


def _detect_sessions(now: datetime | None = None) -> dict[str, bool]:
    """Detect active trading sessions (WIB / UTC+7)."""
    local = _as_wib(now)
    minute = local.hour * 60 + local.minute
    return {
        "sydney": _minutes_in_window(minute, 0, 9 * 60),
        "tokyo": _minutes_in_window(minute, 7 * 60, 16 * 60),
        "london": _minutes_in_window(minute, 13 * 60, 22 * 60),
        "new_york": _minutes_in_window(minute, 19 * 60 + 30, 4 * 60 + 30),
    }


def _current_session_label(sessions: dict[str, bool]) -> str:
    """Return the primary active session name."""
    active = [k for k, v in sessions.items() if v]
    if not active:
        return "Off-Hours"
    labels = {"sydney": "Sydney", "tokyo": "Tokyo", "london": "London", "new_york": "New York"}
    return ", ".join(labels.get(s, s.title()) for s in active)


def _compute_analysis(bars: list[PriceBar], config) -> dict[str, bool]:
    """Compute multi-factor analysis for the dashboard radar."""
    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    volumes = [b.volume for b in bars]
    analysis = {
        "trend": False,
        "ema": False,
        "bos": False,
        "order_block": False,
        "liquidity_sweep": False,
        "volume": False,
        "rsi": False,
        "macd": False,
        "fvg": False,
        "news_clear": True,
    }
    if len(closes) < 25:
        return analysis
    # EMA trend
    ema_f = ema(closes, config.ema_fast)
    ema_s = ema(closes, config.ema_slow)
    if ema_f is not None and ema_s is not None:
        analysis["ema"] = True
        analysis["trend"] = ema_f > ema_s
    # MACD
    _, _, hist = macd(closes, config.macd_fast, config.macd_slow, config.macd_signal)
    if hist is not None:
        analysis["macd"] = abs(hist) > 0.05
    # RSI
    r = rsi(closes, 14)
    if r is not None:
        analysis["rsi"] = 45 < r < 55  # neutral zone
    # Volume spike
    if len(volumes) >= 10:
        avg_vol = sum(volumes[-10:-1]) / 9 if len(volumes) > 1 else volumes[-1]
        if avg_vol > 0:
            analysis["volume"] = volumes[-1] / avg_vol > 1.2
    # BOS: new high/low in last 5 bars
    if len(closes) >= 6:
        analysis["bos"] = closes[-1] > max(closes[-6:-1]) or closes[-1] < min(closes[-6:-1])
    # Order Block: sharp move then pullback
    if len(closes) >= 5:
        last_move = closes[-1] - closes[-3]
        prev_move = closes[-3] - closes[-5]
        analysis["order_block"] = (last_move * prev_move < 0) and abs(last_move) > abs(prev_move) * 0.5
    # Liquidity sweep: wick beyond recent range
    if len(highs) >= 6 and len(lows) >= 6:
        recent_high = max(highs[-6:-1])
        recent_low = min(lows[-6:-1])
        analysis["liquidity_sweep"] = highs[-1] > recent_high or lows[-1] < recent_low
    # FVG: gap between bars
    if len(closes) >= 3 and len(highs) >= 3 and len(lows) >= 3:
        gap_up = lows[-1] > highs[-3]
        gap_down = highs[-1] < lows[-3]
        analysis["fvg"] = gap_up or gap_down
    return analysis


def _compute_confidence(analysis: dict[str, bool]) -> tuple[int, str]:
    """Compute confidence percentage and category from analysis factors."""
    factor_weights = {
        "trend": 10, "ema": 10, "bos": 10, "order_block": 10,
        "liquidity_sweep": 10, "volume": 10, "rsi": 5,
        "macd": 5, "fvg": 10, "news_clear": 10,
    }
    total = 0
    for key, weight in factor_weights.items():
        if analysis.get(key, False):
            total += weight
    if total >= 95:
        cat = "STRONG CONFIRMED"
    elif total >= 85:
        cat = "HIGH PROBABILITY"
    elif total >= 70:
        cat = "GOOD SETUP"
    elif total >= 50:
        cat = "WATCHLIST"
    else:
        cat = "NO TRADE"
    return total, cat


def _compute_volatility(closes: list[float]) -> str:
    """Classify volatility level from recent price movement."""
    if len(closes) < 20:
        return "NORMAL"
    vol = volatility(closes, 20)
    if vol is None:
        return "NORMAL"
    if vol < 0.002:
        return "LOW"
    elif vol < 0.005:
        return "NORMAL"
    elif vol < 0.01:
        return "HIGH"
    else:
        return "EXTREME"


def _compute_sentiment(closes: list[float], highs: list[float], lows: list[float]) -> dict[str, int]:
    """Compute market sentiment from recent price action."""
    if len(closes) < 10:
        return {"bullish": 0, "bearish": 0, "neutral": 100}
    bullish = 0
    bearish = 0
    for i in range(-10, 0):
        if closes[i] > closes[i - 1]:
            bullish += 1
        elif closes[i] < closes[i - 1]:
            bearish += 1
    total = bullish + bearish
    neutral = 10 - total
    return {
        "bullish": round(bullish / 10 * 100),
        "bearish": round(bearish / 10 * 100),
        "neutral": round(max(0, neutral) / 10 * 100),
    }


def _contract_size(symbol: str) -> int:
    """Get contract size multiplier for dollar P&L calculation.

    P&L = price_diff * quantity * contract_size

    - XAUUSD: 1 lot = 100 oz, contract_size = 100
    - XAGUSD: 1 lot = 5000 oz, contract_size = 5000
    - Forex: 1 lot = 100,000 units, contract_size = 100000
    - JPY pairs: 1 lot = 100,000 units, but quoted in JPY
    """
    sym = symbol.upper()
    if "XAU" in sym or "GOLD" in sym:
        return 100      # 100 troy ounces per lot
    elif "XAG" in sym or "SILVER" in sym:
        return 5000     # 5000 troy ounces per lot
    elif "JPY" in sym:
        return 1000     # Reduced contract for JPY (simplified)
    elif "BTC" in sym or "ETH" in sym or "XRP" in sym:
        return 1        # Crypto: 1 coin per unit
    else:
        return 100000   # Standard forex: 100k units


def _compute_dollar_pnl(
    symbol: str,
    entry_price: float,
    exit_price: float,
    quantity: float,
    side: str = "buy",
) -> float:
    """Compute actual dollar P&L: price_diff * quantity * contract_size."""
    price_diff = exit_price - entry_price
    if side.lower() in {"sell", "short"}:
        price_diff *= -1
    return price_diff * quantity * _contract_size(symbol)


def _compute_sl_tp(
    price: float,
    action: str,
    config,
    symbol: str = "XAUUSD",
    point_size: float | None = None,
) -> dict[str, float]:
    """Compute entry, SL, TP, and R-R ratio.

    pip_value is symbol-dependent:
      - XAUUSD: 1 pip = $0.10
      - Most forex (EURUSD, GBPUSD etc.): 1 pip = $0.0001
      - JPY pairs: 1 pip = ¥0.01
    """
    sl_pips = config.stop_loss_pips
    tp_pips = config.take_profit_pips
    # MT5 convention used here: one pip is ten broker points.
    if point_size is not None and point_size > 0:
        pip_value = point_size * 10
        digits = max(0, -Decimal(str(point_size)).normalize().as_tuple().exponent)
    else:
        sym_upper = symbol.upper()
        if "XAU" in sym_upper or "GOLD" in sym_upper:
            pip_value, digits = 0.1, 2
        elif "JPY" in sym_upper:
            pip_value, digits = 0.01, 3
        else:
            pip_value, digits = 0.0001, 5
    if action == "buy":
        entry = price
        sl = round(price - sl_pips * pip_value, digits)
        tp = round(price + tp_pips * pip_value, digits)
    elif action == "sell":
        entry = price
        sl = round(price + sl_pips * pip_value, digits)
        tp = round(price - tp_pips * pip_value, digits)
    else:
        entry = price
        sl = round(price - sl_pips * pip_value, digits)
        tp = round(price + tp_pips * pip_value, digits)
    rr = round(tp_pips / sl_pips, 1) if sl_pips > 0 else 0.0
    return {"entry": entry, "sl": sl, "tp": tp, "rr": rr}


def _dashboard_position_rows(positions, point_size: float | None) -> list[dict]:
    pip_value = point_size * 10 if point_size else 0.1
    rows: list[dict] = []
    for position in positions:
        price_diff = position.current_price - position.avg_price
        if position.side == PositionSide.SHORT:
            price_diff *= -1
        pnl_pips = price_diff / pip_value if pip_value > 0 else 0.0
        rows.append({
            "ticket": position.ticket,
            "symbol": position.symbol,
            "side": position.side.name,
            "qty": round(position.quantity, 4),
            "entry": round(position.avg_price, 5),
            "current": round(position.current_price, 5),
            "pnl": round(position.unrealized_pnl, 2),
            "pnl_pips": round(pnl_pips, 1),
            "opened_at": position.opened_at.isoformat() if position.opened_at else None,
            "sl": position.stop_loss,
            "tp": position.take_profit,
            "phase": position.phase.value,
            "last_error": position.last_error,
        })
    return rows


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
        risk_mgr = ScalpingRiskManager(self.config.scalping)

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
            position_machine = PositionStateMachine.from_config(
                strategy.config,
                broker_supports_short=self.broker.supports_short_positions,
                broker_supports_multiple=self.broker.supports_multiple_positions,
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
        bars: list[PriceBar] = []
        candle_history: list = []
        protection_repair_failures: set[str] = set()
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
                # 1. Fetch quote
                quote = self.broker.get_quote(mapped_symbol)

                if quote is None:
                    self._put("signal:waiting - no quote, retry in 10s")
                    for _ in range(2):
                        if self._stop.is_set():
                            break
                        time.sleep(5)
                        refresh_account()
                    continue

                # 1b. Compute fail-closed entry gates. Existing positions still
                # pass through the loop so exits are always managed.
                news_event = None
                if strategy.config.news_filter_enabled:
                    news_event = get_upcoming_event(buffer_minutes=strategy.config.news_filter_minutes)
                entry_blocks = _entry_safety_blocks(
                    strategy.config,
                    quote,
                    supports_attached_protection=self.broker.supports_attached_protection,
                    news_event=news_event,
                )
                if entry_blocks:
                    block_summary = "; ".join(entry_blocks)
                    log.info(f"New entries blocked: {block_summary}")
                    self._put(f"signal:entry blocked — {block_summary}")

                # 2. Fetch candles from broker (configurable timeframe)
                try:
                    candle_timeframe = strategy.config.candle_timeframe
                    candle_history = self.broker.fetch_candles(mapped_symbol, candle_timeframe, 50)
                except Exception:
                    pass

                # 3. Build bar list
                if candle_history:
                    bars = [
                        PriceBar(
                            date=c.timestamp, open=c.open, high=c.high,
                            low=c.low, close=c.close, volume=c.volume,
                        )
                        for c in candle_history
                    ]
                else:
                    now = datetime.now()
                    bars.append(PriceBar(
                        date=now, open=quote.last, high=quote.last,
                        low=quote.last, close=quote.last, volume=quote.volume,
                    ))
                    if len(bars) > 50:
                        bars = bars[-50:]

                # 4. Generate signal
                signal = strategy.generate(symbol, bars, quote)
                positions = self.broker.get_positions(mapped_symbol)
                sync_result = position_machine.sync(positions)
                managed_positions = position_machine.active_positions(mapped_symbol)
                for ticket in sync_result.opened:
                    recovered = position_machine.get(ticket)
                    log.info(
                        f"Discovered broker position {ticket}: "
                        f"{recovered.side.value} {recovered.quantity:.4f} {recovered.symbol}"
                    )

                opened_times = [p.opened_at for p in managed_positions if p.opened_at is not None]
                dd.update(entry_time=min(opened_times).isoformat() if opened_times else None)

                if managed_positions and self.broker.supports_attached_protection:
                    for pos in positions:
                        side = (getattr(pos, "side", "") or "buy").lower()
                        side = "sell" if side in {"sell", "short"} else "buy"
                        needs_sl = strategy.config.stop_loss_pips > 0 and pos.stop_loss is None
                        needs_tp = strategy.config.take_profit_pips > 0 and pos.take_profit is None
                        if not (needs_sl or needs_tp):
                            continue
                        desired = _compute_sl_tp(
                            pos.avg_price,
                            side,
                            strategy.config,
                            symbol=symbol,
                            point_size=quote.point_size,
                        )
                        protection_result = self.broker.set_position_protection(
                            pos.ticket,
                            desired["sl"] if needs_sl else pos.stop_loss,
                            desired["tp"] if needs_tp else pos.take_profit,
                        )
                        if (
                            protection_result is not None
                            and protection_result.status == OrderStatus.FILLED
                        ):
                            protection_repair_failures.discard(pos.ticket)
                            log.info(f"Recovered broker-side SL/TP for position {pos.ticket}")
                            dd.add_log(f"PROTECTION RESTORED: position {pos.ticket}")
                        elif pos.ticket not in protection_repair_failures:
                            detail = _order_result_detail(protection_result, pos.quantity)
                            message = f"Failed to restore SL/TP for position {pos.ticket}: {detail}"
                            protection_repair_failures.add(pos.ticket)
                            self._put(f"error:{message}")
                            log.error(message)
                            dd.add_log(f"ERROR: {message}")
                            tg.send_error(message)

                dashboard_positions = _dashboard_position_rows(
                    managed_positions, quote.point_size,
                )
                dd.update(open_positions=dashboard_positions)

                # 4a. Higher Timeframe Confirmation (M5 → M1)
                # Cek M5 EMA 9/21 — reject only if EMAs are >1% divergent
                tf_confirmed = True
                tf_reason = ""
                if not entry_blocks and signal.action in ("buy", "sell"):
                    try:
                        tf_candles = self.broker.fetch_candles(mapped_symbol, "5m", 25)
                        if len(tf_candles) >= 15:
                            tf_closes = [c.close for c in tf_candles]
                            tf_ema_fast = ema(tf_closes, 9)
                            tf_ema_slow = ema(tf_closes, 21)
                            tf_latest = tf_closes[-1]
                            if tf_ema_fast is not None and tf_ema_slow is not None and tf_latest > 0:
                                # Calculate EMA divergence as % of price
                                ema_diff_pct = abs(tf_ema_fast - tf_ema_slow) / tf_latest * 100
                                tf_bullish = tf_ema_fast > tf_ema_slow
                                # Only reject if EMA divergence > 1.0% (very strong trend)
                                if signal.action == "buy" and not tf_bullish and ema_diff_pct > 1.0:
                                    tf_confirmed = False
                                    tf_reason = f"M5 strongly bearish ({ema_diff_pct:.2f}%), skip BUY"
                                elif signal.action == "sell" and tf_bullish and ema_diff_pct > 1.0:
                                    tf_confirmed = False
                                    tf_reason = f"M5 strongly bullish ({ema_diff_pct:.2f}%), skip SELL"
                                else:
                                    tf_dir = "bullish" if tf_bullish else "bearish"
                                    tf_reason = f"M5 {tf_dir} divergence {ema_diff_pct:.2f}% — ok"
                    except Exception:
                        pass  # If can't fetch M5, just proceed with M1 signal

                # 4b. Compute AI Radar analysis data
                analysis = _compute_analysis(bars, strategy.config)
                conf_pct, conf_cat = _compute_confidence(analysis)
                sessions = _detect_sessions()
                session_label = _current_session_label(sessions)
                senti = _compute_sentiment(closes=[b.close for b in bars], highs=[b.high for b in bars], lows=[b.low for b in bars])
                vol = _compute_volatility([b.close for b in bars])
                sltp = _compute_sl_tp(
                    quote.last,
                    signal.action,
                    strategy.config,
                    symbol=symbol,
                    point_size=quote.point_size,
                )
                macro = get_macro_sentiment()

                # Update dashboard radar data
                dd.update(
                    confidence_pct=conf_pct,
                    confidence_category=conf_cat,
                    signal_action=signal.action.upper() if signal.action else "HOLD",
                    entry=sltp["entry"],
                    sl=sltp["sl"],
                    tp=sltp["tp"],
                    rr=sltp["rr"],
                    signal_status=conf_cat,
                    current_session=session_label,
                    sessions=sessions,
                    sentiment=senti,
                    volatility=vol,
                    news_events=macro["events"],
                    macro_sentiment=macro,
                    analysis=analysis,
                )

                # 5. Execute the position state machine.
                signal_messages: list[str] = []
                close_attempted = False
                broker_state_changed = False

                def execute_close(pos, reason: str) -> None:
                    nonlocal close_attempted, broker_state_changed
                    close_attempted = True
                    broker_state_changed = True
                    position_machine.mark_closing(pos.ticket)
                    result = self.broker.close_position(pos.ticket)
                    phase = position_machine.apply_close_result(pos.ticket, result)
                    pnl_usd = _compute_dollar_pnl(
                        symbol,
                        pos.avg_price,
                        pos.current_price,
                        pos.quantity,
                        pos.side.value,
                    )
                    if phase == PositionPhase.CLOSED:
                        msg = (
                            f"CLOSED {pos.side.name} {pos.ticket} {pos.quantity:.4f} "
                            f"{mapped_symbol} @ {pos.current_price:.5f} P&L=${pnl_usd:+.2f} | {reason}"
                        )
                        signal_messages.append(msg)
                        dd.add_trade(
                            f"CLOSE {pos.side.name}", mapped_symbol, pos.current_price,
                            pos.quantity, reason, pnl_usd,
                        )
                        dd.add_log(msg)
                        close_action = "sell" if pos.side == PositionSide.LONG else "buy"
                        tg.send_signal(close_action, mapped_symbol, pos.current_price, reason, pnl=pnl_usd)
                    else:
                        detail = _order_result_detail(result, pos.quantity)
                        msg = f"CLOSE {phase.value.upper()} {pos.ticket} ({reason}) | {detail}"
                        signal_messages.append(msg)
                        self._put(f"error:{msg}")
                        log.error(msg)
                        dd.add_log(f"ERROR: {msg}")

                # Risk exits are evaluated independently for every ticket.
                now_utc = datetime.now(timezone.utc)
                for pos in list(managed_positions):
                    if pos.phase == PositionPhase.CLOSING:
                        continue
                    forced_exit = risk_mgr.forced_exit_reason(
                        pos.avg_price,
                        pos.current_price,
                        entry_time=pos.opened_at,
                        current_time=now_utc,
                        side=pos.side.value,
                        point_size=quote.point_size,
                    )
                    if forced_exit:
                        execute_close(pos, forced_exit)

                # Do not reverse or add exposure in the same cycle as a risk close.
                if not close_attempted:
                    entry_reason_parts = list(entry_blocks)
                    if not tf_confirmed:
                        entry_reason_parts.append(tf_reason or "higher timeframe rejected entry")
                    actions = position_machine.plan_signal(
                        signal.action,
                        mapped_symbol,
                        entry_allowed=not entry_reason_parts,
                        entry_block_reason="; ".join(entry_reason_parts),
                    )

                    for action in actions:
                        if action.action == PositionActionType.HOLD:
                            signal_messages.append(
                                f"HOLD {mapped_symbol} @ {quote.last:.5f} | {action.reason}"
                            )
                            continue

                        if action.action == PositionActionType.CLOSE:
                            pos = position_machine.get(action.ticket)
                            if pos is not None:
                                execute_close(pos, action.reason)
                            continue

                        side = (
                            PositionSide.LONG
                            if action.action == PositionActionType.OPEN_LONG
                            else PositionSide.SHORT
                        )
                        order_side = OrderSide.BUY if side == PositionSide.LONG else OrderSide.SELL
                        entry_reference = quote.ask if side == PositionSide.LONG else quote.bid
                        try:
                            acct_data = self.broker.get_account()
                            eq = acct_data.equity
                            bal = acct_data.balance
                        except Exception:
                            eq = 10000.0
                            bal = 10000.0
                        qty = risk_mgr.buy_quantity(bal, eq, entry_reference)
                        if strategy.config.aggressive_mode and qty < 0.05:
                            max_by_equity = bal * strategy.config.max_trade_pct / entry_reference
                            qty = max(0.05, min(max_by_equity, bal * 0.05 / entry_reference))
                        if qty <= 0:
                            qty = 0.01

                        protection = _compute_sl_tp(
                            entry_reference,
                            side.value,
                            strategy.config,
                            symbol=symbol,
                            point_size=quote.point_size,
                        )
                        result = self.broker.place_order(
                            mapped_symbol,
                            order_side,
                            qty,
                            stop_loss=protection["sl"] if strategy.config.stop_loss_pips > 0 else None,
                            take_profit=protection["tp"] if strategy.config.take_profit_pips > 0 else None,
                        )
                        position_machine.record_entry_result(mapped_symbol, side, result)
                        if (
                            result is not None
                            and result.status in {OrderStatus.FILLED, OrderStatus.PARTIAL}
                            and result.filled_qty > 0
                        ):
                            broker_state_changed = True
                            msg = (
                                f"OPENED {side.name} {result.filled_qty:.4f} {mapped_symbol} "
                                f"@ {result.avg_fill_price or entry_reference:.5f} | {signal.reason}"
                            )
                            signal_messages.append(msg)
                            dd.add_trade(
                                f"OPEN {side.name}", mapped_symbol,
                                result.avg_fill_price or entry_reference,
                                result.filled_qty, signal.reason,
                            )
                            dd.add_log(msg)
                            tg.send_signal(side.value, mapped_symbol, entry_reference, signal.reason)
                            dd.update(
                                entry_time=result.timestamp.isoformat(),
                                timeout_minutes=strategy.config.timeout_exit_minutes,
                            )
                        elif result is not None and result.status == OrderStatus.PENDING:
                            signal_messages.append(
                                f"ENTRY PENDING {side.name} {mapped_symbol} | {result.message}"
                            )
                        else:
                            detail = _order_result_detail(result, qty)
                            msg = f"ENTRY REJECTED {side.name} {mapped_symbol} | {detail}"
                            signal_messages.append(msg)
                            log.warning(msg)
                            dd.add_log(f"REJECTED: {msg}")

                signal_msg = " || ".join(signal_messages) or (
                    f"HOLD {mapped_symbol} @ {quote.last:.5f} sc={signal.confidence:.3f}"
                )
                self._put(f"signal:{signal_msg}")
                log.info(f"signal:{signal_msg}")

                if broker_state_changed:
                    try:
                        refreshed_positions = self.broker.get_positions(mapped_symbol)
                        position_machine.sync(refreshed_positions)
                    except Exception as e:
                        log.warning(f"Position refresh after execution failed: {e}")
                dd.update(open_positions=_dashboard_position_rows(
                    position_machine.active_positions(mapped_symbol),
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

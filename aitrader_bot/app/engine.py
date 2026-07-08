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
from datetime import datetime, timezone
from queue import Queue
from threading import Event, Thread

from aitrader_bot.broker import OrderSide, OrderStatus, create_broker
from aitrader_bot.config import BotConfig, load_config
from aitrader_bot.indicators import ema, macd, bollinger_bands, stochastic, rsi, volatility
from aitrader_bot.models import PriceBar
from aitrader_bot.scalping import ScalpingStrategy, ScalpingRiskManager

from . import dashboard_data as dd
from .logger import setup_logging
from .news_filter import get_macro_sentiment, get_upcoming_event
from .notifier import TelegramNotifier
from .web_dashboard import notify as notify_web

log = setup_logging(__name__)

ACCOUNT_REFRESH_SECONDS = 10.0


# ═══════════════════════════════════════════════════════════════════════
#  Analysis helpers for AI Trading Radar dashboard
# ═══════════════════════════════════════════════════════════════════════

def _detect_sessions() -> dict[str, bool]:
    """Detect active trading sessions (WIB / UTC+7)."""
    now = datetime.now(timezone.utc)
    utc_h = now.hour
    utc_m = now.minute
    utc_min = utc_h * 60 + utc_m
    return {
        "sydney": 17 * 60 <= utc_min <= 2 * 60,       # 00:00-09:00 WIB
        "tokyo": 0 <= utc_min <= 9 * 60,               # 07:00-16:00 WIB
        "london": 6 * 60 <= utc_min <= 15 * 60,         # 13:00-22:00 WIB
        "new_york": 12 * 60 + 30 <= utc_min <= 21 * 60 + 30,  # 19:30-04:30 WIB
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


def _compute_dollar_pnl(symbol: str, entry_price: float, exit_price: float, quantity: float) -> float:
    """Compute actual dollar P&L: price_diff * quantity * contract_size."""
    price_diff = exit_price - entry_price
    return price_diff * quantity * _contract_size(symbol)


def _compute_sl_tp(price: float, action: str, config, symbol: str = "XAUUSD") -> dict[str, float]:
    """Compute entry, SL, TP, and R-R ratio.

    pip_value is symbol-dependent:
      - XAUUSD: 1 pip = $0.10
      - Most forex (EURUSD, GBPUSD etc.): 1 pip = $0.0001
      - JPY pairs: 1 pip = ¥0.01
    """
    sl_pips = config.stop_loss_pips
    tp_pips = config.take_profit_pips
    # Resolve pip_value per symbol
    sym_upper = symbol.upper()
    if "XAU" in sym_upper or "GOLD" in sym_upper:
        pip_value = 0.1
    elif "JPY" in sym_upper:
        pip_value = 0.01
    else:
        pip_value = 0.0001
    if action == "buy":
        entry = price
        sl = round(price - sl_pips * pip_value, 2)
        tp = round(price + tp_pips * pip_value, 2)
    elif action == "sell":
        entry = price
        sl = round(price + sl_pips * pip_value, 2)
        tp = round(price - tp_pips * pip_value, 2)
    else:
        entry = price
        sl = round(price - sl_pips * pip_value, 2)
        tp = round(price + tp_pips * pip_value, 2)
    rr = round(tp_pips / sl_pips, 1) if sl_pips > 0 else 0.0
    return {"entry": entry, "sl": sl, "tp": tp, "rr": rr}


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
            self._put(f"error:koneksi gagal: {e}")
            tg.send_error(f"Connection failed: {e}")
            log.error(f"Koneksi gagal: {e}")
            dd.update(status="error")
            dd.add_log(f"ERROR: Connection failed: {e}")
            notify_web()
            self._current_status = "error"
            return

        iteration = 0
        last_error_iter = -10  # for error notification cooldown
        bars: list[PriceBar] = []
        candle_history: list = []
        entry_time: datetime | None = None  # Track entry timestamp for timeout exit
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
                # 0. Check trading session (skip if outside London/NY)
                if strategy.config.session_filter_enabled:
                    now_h = datetime.now().hour
                    now_m = datetime.now().minute
                    current_minutes = now_h * 60 + now_m
                    london_start = strategy.config.session_london_start * 60
                    london_end = strategy.config.session_london_end * 60
                    ny_start = strategy.config.session_ny_start * 60 + 30
                    ny_end = strategy.config.session_ny_end * 60
                    in_session = (london_start <= current_minutes <= london_end or
                                  ny_start <= current_minutes <= ny_end)
                    if not in_session:
                        self._put(f"signal:outside trading session (WIB {now_h:02d}:{now_m:02d})")
                        # Still fetch but don't trade

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

                # 1b. News filter — pause near high-impact events
                if strategy.config.news_filter_enabled:
                    news_event = get_upcoming_event(buffer_minutes=strategy.config.news_filter_minutes)
                    if news_event:
                        name = news_event["name"]
                        phase = news_event["phase"]
                        sec = news_event["seconds_until"]
                        log.info(f"News filter: {name} ({phase}) — pausing {abs(sec)}s")
                        self._put(f"signal:news filter — {name} ({phase})")
                        dd.add_log(f"NEWS: {name} ({phase}) — paused")
                        notify_web()
                        # Wait until news passes
                        wait_sec = min(abs(sec) + 60, 300)
                        for _ in range(wait_sec // 5):
                            if self._stop.is_set():
                                break
                            time.sleep(5)
                            refresh_account()
                        continue

                # 1c. Spread check — abort if spread > max allowed
                max_points = strategy.config.max_spread_points
                if quote.spread > max_points:
                    log.info(f"Spread {quote.spread:.1f}pts > max {max_points:.0f}pts — skipping")
                    self._put(f"signal:spread {quote.spread:.1f}pts too high")
                    # Wait and retry
                    for _ in range(6):
                        if self._stop.is_set():
                            break
                        time.sleep(10)
                        refresh_account()
                    continue

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
                has_pos = len(positions) > 0
                dashboard_positions = []
                for p in positions:
                    side = (getattr(p, "side", "") or "buy").upper()
                    pnl_pips = 0.0
                    if p.avg_price:
                        price_diff = quote.last - p.avg_price
                        if side == "SELL":
                            price_diff *= -1
                        pnl_pips = price_diff * 10
                    dashboard_positions.append({
                        "ticket": p.ticket,
                        "symbol": p.symbol,
                        "side": side,
                        "qty": round(p.quantity, 4),
                        "entry": round(p.avg_price, 2),
                        "current": round(quote.last, 2),
                        "pnl": round(p.unrealized_pnl, 2),
                        "pnl_pips": round(pnl_pips, 1),
                    })
                dd.update(open_positions=dashboard_positions)

                # 4a. Higher Timeframe Confirmation (M5 → M1)
                # Cek M5 EMA 9/21 — reject only if EMAs are >1% divergent
                tf_confirmed = True
                tf_reason = ""
                if not has_pos and signal.action in ("buy", "sell"):
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
                sltp = _compute_sl_tp(quote.last, signal.action, strategy.config, symbol=symbol)
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

                # 5. Execute + notify
                qty = 0.01
                signal_msg = ""

                if signal.action == "buy" and not has_pos:
                    # ── Higher TF confirmation filter ────────────────────────
                    if not tf_confirmed:
                        signal_msg = f"TF REJECTED BUY {mapped_symbol} @ {quote.last:.2f} | {tf_reason}"
                        self._put(f"signal:{signal_msg}")
                        log.info(f"signal:{signal_msg}")
                        dd.add_log(f"TF REJECT: {tf_reason}")
                    else:
                        # Calculate dynamic position size
                        try:
                            acct_data = self.broker.get_account()
                            eq = acct_data.equity
                            bal = acct_data.balance
                        except Exception:
                            eq = 10000.0
                            bal = 10000.0
                        qty = risk_mgr.buy_quantity(bal, eq, quote.last)
                        # ── AGGRESSIVE MODE: ensure minimum lot ────────────────
                        if strategy.config.aggressive_mode and qty < 0.05:
                            max_by_equity = bal * strategy.config.max_trade_pct / quote.last
                            qty = max(0.05, min(max_by_equity, bal * 0.05 / quote.last))
                        if qty <= 0:
                            qty = 0.01
                        result = self.broker.place_order(mapped_symbol, OrderSide.BUY, qty)

                        if result.status == OrderStatus.FILLED:
                            signal_msg = f"BOUGHT {qty:.4f} {mapped_symbol} @ {quote.last:.2f} | {signal.reason}"
                            self._put(f"signal:{signal_msg}")
                            log.info(f"signal:{signal_msg}")
                            dd.add_trade("BUY", mapped_symbol, quote.last, qty, signal.reason)
                            dd.add_log(f"BOUGHT {qty:.4f} {mapped_symbol} @ {quote.last:.2f}")
                            tg.send_signal("buy", mapped_symbol, quote.last, signal.reason)
                            entry_time = datetime.now()
                            dd.update(entry_time=entry_time.isoformat(), timeout_minutes=strategy.config.timeout_exit_minutes)
                            log.info(f"[TIMEOUT] Entry tracked at {entry_time.strftime('%H:%M:%S')}, timeout={strategy.config.timeout_exit_minutes}m")
                        else:
                            signal_msg = f"ORDER REJECTED: {result.message} | qty={qty:.4f} @ {quote.last:.2f}"
                            self._put(f"signal:{signal_msg}")
                            log.warning(f"signal:{signal_msg}")
                            dd.add_log(f"REJECTED: {result.message}")

                elif signal.action == "sell" and has_pos:
                    # ── OPPOSITE-SIGNAL EXIT (only if in profit) ──────────────
                    pos = positions[0]
                    pnl_price_diff = quote.last - pos.avg_price if pos.avg_price else 0.0
                    pnl_pips = pnl_price_diff * 10
                    pnl_usd = _compute_dollar_pnl(symbol, pos.avg_price, quote.last, pos.quantity)

                    if pnl_usd > 0:
                        # In profit — close immediately (lock profit)
                        result = self.broker.close_position(pos.ticket)
                        signal_msg = f"SOLD {mapped_symbol} @ {quote.last:.2f} P&L=${pnl_usd:+.2f} | OPPOSITE SIGNAL (profit): {signal.reason}"
                        self._put(f"signal:{signal_msg}")
                        log.info(f"signal:{signal_msg}")
                        dd.add_trade("SELL (opp signal profit)", mapped_symbol, quote.last, pos.quantity, f"Opp profit: {signal.reason}", pnl_usd)
                        dd.add_log(f"SOLD {mapped_symbol} @ {quote.last:.2f} P&L=${pnl_usd:+.2f} (opp signal profit)")
                        tg.send_signal("sell", mapped_symbol, quote.last, f"Opposite signal (profit): {signal.reason}", pnl=pnl_usd)
                        entry_time = None
                        dd.update(entry_time=None)
                    else:
                        # In loss — DO NOT close opposite signal, let SL handle it
                        # Fall through to forced_exit logic below
                        signal_msg = f"OPP SIGNAL HOLD {mapped_symbol} @ {quote.last:.2f} P&L=${pnl_usd:+.2f} — waiting for SL"
                        self._put(f"signal:{signal_msg}")
                        log.info(f"signal:{signal_msg}")
                        dd.add_log(f"OPP SIGNAL HOLD (loss ${pnl_usd:+.2f}) — letting SL handle")

                # ── Skip forced_exit if position was already closed by opposite-signal exit ──
                if has_pos and entry_time is None:
                    has_pos = False

                # ── ALWAYS check forced exit (SL/TP/timeout) for existing positions ──
                forced_exit = None
                if has_pos:
                    pos = positions[0]
                    now = datetime.now()
                    forced_exit = risk_mgr.forced_exit_reason(
                        pos.avg_price, quote.last,
                        entry_time=entry_time,
                        current_time=now,
                    )

                if forced_exit:
                    result = self.broker.close_position(pos.ticket)
                    pnl_price_diff = quote.last - pos.avg_price if pos.avg_price else 0.0
                    pnl_usd = _compute_dollar_pnl(symbol, pos.avg_price, quote.last, pos.quantity)
                    signal_msg = f"CLOSED {mapped_symbol} @ {quote.last:.2f} P&L=${pnl_usd:+.2f} | {forced_exit}"
                    self._put(f"signal:{signal_msg}")
                    log.info(f"signal:{signal_msg}")
                    if "timeout" in forced_exit:
                        trade_type = "SELL (timeout)"
                    elif "lock profit" in forced_exit:
                        trade_type = "SELL (lock profit)"
                    else:
                        trade_type = "SELL (SL/TP)"
                    dd.add_trade(trade_type, mapped_symbol, quote.last, pos.quantity, forced_exit, pnl_usd)
                    dd.add_log(f"CLOSED {mapped_symbol} @ {quote.last:.2f} P&L=${pnl_usd:+.2f} ({forced_exit})")
                    tg.send_signal("sell", mapped_symbol, quote.last, forced_exit, pnl=pnl_usd)
                    entry_time = None
                    dd.update(entry_time=None)
                elif has_pos:
                    hold_label = "HODL"
                    signal_msg = f"{hold_label} {mapped_symbol} @ {quote.last:.2f}  sc={signal.confidence:.3f}  [{signal.reason}]"
                    self._put(f"signal:{signal_msg}")
                    log.info(f"signal:{signal_msg}")
                    dd.add_log(f"{hold_label} {mapped_symbol} @ {quote.last:.2f} sc={signal.confidence:.3f}")

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

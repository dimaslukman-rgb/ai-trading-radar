"""Configuration system — strategy, risk, scalping, and multi-broker settings."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .broker.base import ExchangeType


@dataclass(frozen=True)
class StrategyConfig:
    fast_window: int = 8
    slow_window: int = 21
    rsi_window: int = 14
    min_buy_score: float = 0.35
    min_sell_score: float = -0.25


@dataclass(frozen=True)
class RiskConfig:
    initial_cash: float = 10000.0
    max_position_pct: float = 0.25
    max_trade_pct: float = 0.10
    stop_loss_pct: float = 0.05
    take_profit_pct: float = 0.10
    min_cash: float = 50.0


@dataclass(frozen=True)
class ScalpingConfig:
    """Scalping parameters — dual-state: Momentum (EMA 9/21 + MACD) & Mean Reversion (BB + Stochastic).

    Rules:
      - Timeframe: configurable (M5 default, M1 aggressive)
      - Sessions: London (14:00-18:00 WIB) & New York (19:30-22:00 WIB)
      - News filter: pause near high-impact news
      - Max spread: configurable (25pts M5, 15pts M1)
      - SL/TP: configurable (M5: 30p/15p, M1: 20p/12p)
    """
    # ── State A: Momentum (EMA + MACD) ────────────────────────────
    ema_fast: int = 9           # EMA 9
    ema_slow: int = 21          # EMA 21
    macd_fast: int = 12         # MACD standard
    macd_slow: int = 26
    macd_signal: int = 9
    min_buy_score: float = 0.15
    min_sell_score: float = -0.10
    # ── State B: Mean Reversion (BB + Stochastic) ─────────────────
    bb_window: int = 20         # Bollinger Bands (20,2)
    bb_std: float = 2.0
    stochastic_k: int = 14      # Stochastic %K 14
    stochastic_d: int = 3       # Stochastic %D 3
    stochastic_slowing: int = 3 # Slowing 3
    stochastic_oversold: int = 20
    stochastic_overbought: int = 80
    # ── Market State Detection ─────────────────────────────────────
    volume_threshold: float = 1.5   # spike × average to determine trending vs sideways
    trend_filter_bars: int = 6      # bars for higher-timeframe trend filter (M5→6=M30, M1→5=M5)
    # ── Aggressive M1 Features ─────────────────────────────────────
    rsi_enabled: bool = False       # RSI scoring in momentum state
    rsi_window: int = 7             # RSI period for M1 (fast)
    rsi_bullish_threshold: float = 55.0   # RSI > threshold = bullish
    rsi_bearish_threshold: float = 45.0   # RSI < threshold = bearish
    rsi_score_weight: float = 0.15        # Score weight for RSI
    momentum_velocity_enabled: bool = False  # Price velocity scoring
    velocity_bars: int = 3          # Bars to measure velocity
    velocity_score_weight: float = 0.10  # Score weight for velocity
    multi_confirm_boost: float = 0.10    # Bonus for 3+ confirmations aligned
    min_bars_override: int = 0      # Override min_bars requirement (0=auto)
    # ── News Filter ─────────────────────────────────────────────────
    news_filter_enabled: bool = True     # Pause near high-impact news
    news_filter_minutes: int = 15        # Minutes before/after to pause
    # ── Risk ───────────────────────────────────────────────────────
    max_spread_points: float = 25.0     # 25 points = 2.5 pips max spread
    stop_loss_pips: float = 30.0        # max 30 pips SL
    take_profit_pips: float = 15.0      # 15 pips TP
    trailing_stop_pips: float = 5.0     # lock profit at +5 pips (auto-exit)
    risk_per_trade_pct: float = 0.02    # 2% risk per trade (0.01 = 1%)
    max_trade_pct: float = 0.05         # 5% equity per trade
    # ── Position policy ─────────────────────────────────────────────
    allow_long_entries: bool = True
    allow_short_entries: bool = True
    max_open_positions: int = 1
    max_positions_per_side: int = 1
    allow_scale_in: bool = False
    hedging_enabled: bool = False
    close_on_opposite_signal: bool = True
    opposite_exit_only_in_profit: bool = True
    # ── Trading Sessions (WIB = UTC+7) ──────────────────────────────
    session_filter_enabled: bool = True
    session_london_start: int = 14      # 14:00 WIB
    session_london_end: int = 18        # 18:00 WIB
    session_ny_start: int = 19          # 19:30 WIB
    session_ny_end: int = 22            # 22:00 WIB
    # ── Timeframe ─────────────────────────────────────────────────
    # ── Aggressive Mode ────────────────────────────────────────────
    aggressive_mode: bool = False           # Master switch: aggressive M1 scalping
    timeout_exit_minutes: int = 10          # Auto-exit after N minutes if TP not reached
    max_lot_size: float = 1.0               # Maximum lot size for aggressive mode (0 = no limit)
    aggressive_risk_multiplier: float = 3.0  # Multiply risk_per_trade by this in aggressive mode
    # ── Timeframe ─────────────────────────────────────────────────
    interval_seconds: int = 300         # 300s = 5m
    candle_timeframe: str = "5m"        # M5


@dataclass(frozen=True)
class BrokerConnection:
    """Single broker connection config."""
    backend: str = "paper"       # "paper" | "mt5" | "binance" | "alpaca"
    api_key: str = ""
    secret: str = ""
    server: str = ""             # MT5 server name
    login: int | None = None     # MT5 login
    password: str = ""
    paper: bool = True           # Alpaca paper mode
    sandbox: bool = False        # Binance sandbox
    symbol_map: str | None = None  # optional override


@dataclass(frozen=True)
class TelegramConfig:
    """Telegram notification settings."""
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""


@dataclass(frozen=True)
class BotConfig:
    symbol: str = "BTC-USD"
    market: str = "crypto"
    strategy: StrategyConfig = StrategyConfig()
    scalping: ScalpingConfig = ScalpingConfig()
    risk: RiskConfig = RiskConfig()
    telegram: TelegramConfig = TelegramConfig()
    # Multi-broker: keyed by asset type
    brokers: dict[str, BrokerConnection] = field(default_factory=lambda: {
        "default": BrokerConnection(),
    })


def _parse_brokers(raw: dict) -> dict[str, BrokerConnection]:
    """Parse broker configs from JSON dict."""
    brokers: dict[str, BrokerConnection] = {}
    raw_brokers = raw.get("brokers", raw.get("broker", raw))
    if isinstance(raw_brokers, list):
        # Legacy single broker format
        for b in raw_brokers:
            bk = _single_broker(b)
            brokers[bk.backend] = bk
    elif isinstance(raw_brokers, dict):
        if "backend" in raw_brokers:
            # Single broker config
            brokers["default"] = _single_broker(raw_brokers)
        else:
            # Multi-broker config keyed by name
            for name, b in raw_brokers.items():
                brokers[name] = _single_broker(b)
    if not brokers:
        brokers["default"] = BrokerConnection()
    return brokers


def _single_broker(b: dict) -> BrokerConnection:
    return BrokerConnection(
        backend=b.get("backend", "paper"),
        api_key=b.get("api_key", b.get("apiKey", b.get("key", ""))),
        secret=b.get("secret", b.get("secret_key", b.get("secretKey", b.get("password", "")))),
        server=b.get("server", ""),
        login=b.get("login"),
        password=b.get("password", ""),
        paper=b.get("paper", True),
        sandbox=b.get("sandbox", False),
        symbol_map=b.get("symbol_map"),
    )


def load_config(path: str | Path) -> BotConfig:
    """Load full bot configuration from a JSON file."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    strategy = StrategyConfig(**raw.get("strategy", {}))
    scalping = ScalpingConfig(**raw.get("scalping", {}))
    risk = RiskConfig(**raw.get("risk", {}))
    brokers = _parse_brokers(raw)
    telegram_raw = raw.get("telegram", {})
    telegram = TelegramConfig(
        enabled=telegram_raw.get("enabled", False),
        bot_token=telegram_raw.get("bot_token", ""),
        chat_id=telegram_raw.get("chat_id", ""),
    )

    return BotConfig(
        symbol=raw.get("symbol", "BTC-USD"),
        market=raw.get("market", "crypto"),
        strategy=strategy,
        scalping=scalping,
        risk=risk,
        telegram=telegram,
        brokers=brokers,
    )

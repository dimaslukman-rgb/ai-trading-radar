"""Configuration system -- strategy, risk, scalping, and multi-broker settings."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
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
    """Scalping parameters -- dual-state: Momentum (EMA 9/21 + MACD) & Mean Reversion (BB + Stochastic).

    Rules:
      - Timeframe: configurable (M5 default, M1 aggressive)
      - Sessions: London (14:00-18:00 WIB) & New York (19:30-22:00 WIB)
      - News filter: pause near high-impact news
      - Max spread: configurable (25pts M5, 15pts M1)
      - SL/TP: configurable (M5: 30p/15p, M1: 20p/12p)
    """
    # -- State A: Momentum (EMA + MACD) ----------------------------
    ema_fast: int = 9
    ema_slow: int = 21
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9
    min_buy_score: float = 0.15
    min_sell_score: float = -0.10
    # -- State B: Mean Reversion (BB + Stochastic) ----------------
    bb_window: int = 20
    bb_std: float = 2.0
    stochastic_k: int = 14
    stochastic_d: int = 3
    stochastic_slowing: int = 3
    stochastic_oversold: int = 20
    stochastic_overbought: int = 80
    # -- Market State Detection ------------------------------------
    volume_threshold: float = 1.5
    trend_filter_bars: int = 6
    # -- Aggressive M1 Features ------------------------------------
    rsi_enabled: bool = False
    rsi_window: int = 7
    rsi_bullish_threshold: float = 55.0
    rsi_bearish_threshold: float = 45.0
    rsi_score_weight: float = 0.15
    momentum_velocity_enabled: bool = False
    velocity_bars: int = 3
    velocity_score_weight: float = 0.10
    multi_confirm_boost: float = 0.10
    min_bars_override: int = 0
    # -- News Filter ------------------------------------------------
    news_filter_enabled: bool = True
    news_filter_minutes: int = 15
    # -- Risk ------------------------------------------------------
    max_spread_points: float = 25.0
    stop_loss_pips: float = 30.0
    take_profit_pips: float = 15.0
    trailing_stop_pips: float = 5.0
    risk_per_trade_pct: float = 0.02
    max_trade_pct: float = 0.05
    # -- Adaptive volatility risk ---------------------------------
    atr_risk_enabled: bool = False
    atr_period: int = 14
    atr_stop_multiplier: float = 1.5
    atr_target_multiplier: float = 2.5
    atr_min_stop_pips: float = 5.0
    atr_max_stop_pips: float = 100.0
    # -- Position policy --------------------------------------------
    allow_long_entries: bool = True
    allow_short_entries: bool = True
    max_open_positions: int = 1
    max_positions_per_side: int = 1
    allow_scale_in: bool = False
    hedging_enabled: bool = False
    close_on_opposite_signal: bool = True
    opposite_exit_only_in_profit: bool = True
    # -- Trading Sessions (WIB = UTC+7) ------------------------------
    session_filter_enabled: bool = True
    session_london_start: int = 14
    session_london_end: int = 18
    session_ny_start: int = 19
    session_ny_end: int = 22
    # -- Aggressive Mode -------------------------------------------
    aggressive_mode: bool = False
    timeout_exit_minutes: int = 10
    max_lot_size: float = 1.0
    aggressive_risk_multiplier: float = 3.0
    # -- Daily Circuit Breaker -------------------------------------
    daily_trade_cap: int = 0
    daily_loss_limit_pct: float = 0.0
    # -- Timeframe -------------------------------------------------
    interval_seconds: int = 300
    candle_timeframe: str = "5m"


@dataclass(frozen=True)
class BrokerConnection:
    """Single broker connection config."""
    backend: str = "paper"
    api_key: str = ""
    secret: str = ""
    server: str = ""
    login: int | None = None
    password: str = ""
    terminal_path: str = ""
    timeout_ms: int = 60_000
    portable: bool = False
    paper: bool = True
    sandbox: bool = False
    symbol_map: str | None = None


@dataclass(frozen=True)
class TelegramConfig:
    """Telegram notification settings."""
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""


@dataclass(frozen=True)
class AIConfig:
    """Optional AI enrichment.

    Agent analysis is deliberately separated from order execution.  This keeps
    the existing, tested risk path authoritative until an operator explicitly
    opts in to using agent decisions for entries.
    """

    agents_enabled: bool = True
    agent_execution_enabled: bool = False
    gemini_enabled: bool = False
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    gemini_timeout_seconds: float = 8.0


@dataclass(frozen=True)
class SymbolConfig:
    """One independently processed trading symbol.

    ``scalping`` is an override layer over the global scalping configuration,
    so a multi-pair file can share sensible defaults while tuning a single
    symbol for its own volatility and session behaviour.
    """

    symbol: str
    market: str = ""
    enabled: bool = True
    scalping: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class BotConfig:
    symbol: str = "BTC-USD"
    market: str = "crypto"
    strategy: StrategyConfig = StrategyConfig()
    scalping: ScalpingConfig = ScalpingConfig()
    risk: RiskConfig = RiskConfig()
    telegram: TelegramConfig = TelegramConfig()
    ai: AIConfig = AIConfig()
    symbols: tuple[SymbolConfig, ...] = ()
    brokers: dict[str, BrokerConnection] = field(default_factory=lambda: {
        "default": BrokerConnection(),
    })

    @property
    def enabled_symbols(self) -> tuple[SymbolConfig, ...]:
        """Return configured symbols, retaining the legacy ``symbol`` field."""
        configured = tuple(item for item in self.symbols if item.enabled)
        return configured or (SymbolConfig(symbol=self.symbol, market=self.market),)

    def scalping_for(self, item: SymbolConfig) -> ScalpingConfig:
        """Resolve and validate a symbol's local scalping overrides."""
        if not item.scalping:
            return self.scalping
        return replace(self.scalping, **item.scalping)


def _parse_brokers(raw: dict) -> dict[str, BrokerConnection]:
    """Parse broker configs from JSON dict."""
    brokers: dict[str, BrokerConnection] = {}
    # A top-level configuration may intentionally omit broker credentials
    # (for example a research/optimizer config).  Do not mistake unrelated
    # keys such as ``symbol`` for named broker definitions.
    raw_brokers = raw.get("brokers", raw.get("broker"))
    if isinstance(raw_brokers, list):
        for b in raw_brokers:
            bk = _single_broker(b)
            brokers[bk.backend] = bk
    elif isinstance(raw_brokers, dict):
        if "backend" in raw_brokers:
            brokers["default"] = _single_broker(raw_brokers)
        else:
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
        terminal_path=b.get("terminal_path", b.get("path", "")),
        timeout_ms=int(b.get("timeout_ms", b.get("timeout", 60_000))),
        portable=bool(b.get("portable", False)),
        paper=b.get("paper", True),
        sandbox=b.get("sandbox", False),
        symbol_map=b.get("symbol_map"),
    )


def _parse_symbols(raw: object, legacy_symbol: str, legacy_market: str) -> tuple[SymbolConfig, ...]:
    """Accept a concise list of symbols or per-symbol configuration objects."""
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ValueError("'symbols' must be a JSON list")

    result: list[SymbolConfig] = []
    seen: set[str] = set()
    for item in raw:
        if isinstance(item, str):
            parsed = SymbolConfig(symbol=item, market=legacy_market)
        elif isinstance(item, dict):
            symbol = str(item.get("symbol", "")).strip()
            overrides = item.get("scalping", item.get("scalping_overrides", {}))
            if not isinstance(overrides, dict):
                raise ValueError(f"symbols[{symbol or '?'}].scalping must be an object")
            parsed = SymbolConfig(
                symbol=symbol,
                market=str(item.get("market", legacy_market)),
                enabled=bool(item.get("enabled", True)),
                scalping=dict(overrides),
            )
        else:
            raise ValueError("each 'symbols' entry must be a string or object")

        key = parsed.symbol.upper()
        if not parsed.symbol:
            raise ValueError("each symbols entry needs a non-empty 'symbol'")
        if key in seen:
            raise ValueError(f"duplicate symbol in 'symbols': {parsed.symbol}")
        seen.add(key)
        result.append(parsed)
    return tuple(result)


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
    ai_raw = raw.get("ai", {})
    ai = AIConfig(
        agents_enabled=ai_raw.get("agents_enabled", True),
        agent_execution_enabled=ai_raw.get("agent_execution_enabled", False),
        gemini_enabled=ai_raw.get("gemini_enabled", False),
        gemini_api_key=ai_raw.get("gemini_api_key", ""),
        gemini_model=ai_raw.get("gemini_model", "gemini-2.0-flash"),
        gemini_timeout_seconds=ai_raw.get("gemini_timeout_seconds", 8.0),
    )
    symbol = raw.get("symbol", "BTC-USD")
    market = raw.get("market", "crypto")

    return BotConfig(
        symbol=symbol,
        market=market,
        strategy=strategy,
        scalping=scalping,
        risk=risk,
        telegram=telegram,
        ai=ai,
        symbols=_parse_symbols(raw.get("symbols"), symbol, market),
        brokers=brokers,
    )

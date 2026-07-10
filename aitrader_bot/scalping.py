"""Professional XAUUSD scalping strategy — dual-state system.

STATE A — Momentum Trending (EMA + MACD):
  - Fast EMA 9, Slow EMA 21
  - MACD(12,26,9) histogram zero-line confirmation
  - M15/M30 trend filter: price vs EMA 21 on higher timeframe
  - BUY: EMA 9 > EMA 21 (golden cross) + MACD > 0 + M15 bullish
  - SELL: EMA 9 < EMA 21 (death cross) + MACD < 0 + M15 bearish

STATE B — Mean Reversion / Sideways (BB + Stochastic):
  - Bollinger Bands (20, 2.0)
  - Stochastic(14,3,3)
  - BUY: Price touches lower BB + Stochastic < 20 + bullish crossover
  - SELL: Price touches upper BB + Stochastic > 80 + bearish crossover

Guardrails:
  - Max spread: 25 points (checked in engine)
  - Trading sessions: London (14:00-18:00 WIB) & NY (19:30-22:00 WIB)
  - News filter: pause 15m before/after high-impact news (engine level)
  - SL: max 30-40 pips based on swing high/low
  - TP: 15-20 pips scalping target
  - Lock profit: auto-exit at +5 pips

AGGRESSIVE MODE (M1):
  - Timeout exit: force-close after N minutes if TP not reached
  - Max lot sizing: use up to max_lot_size for aggressive entries
  - Ultra-fast EMAs (3/7) for quick signal generation
  - Target: +100 points (10 pips) per trade
"""

from __future__ import annotations

import math
from datetime import timezone

from .broker.base import Quote as BrokerQuote
from .config import ScalpingConfig
from .indicators import ema, macd, bollinger_bands, stochastic, sma, rsi
from .models import PriceBar, Signal


class ScalpingStrategy:
    """Dual-state XAUUSD scalping: Momentum (trending) or Mean Reversion (sideways)."""

    def __init__(self, config: ScalpingConfig):
        self.config = config

    def generate(
        self,
        symbol: str,
        bars: list[PriceBar],
        quote: BrokerQuote | None = None,
    ) -> Signal:
        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]
        volumes = [b.volume for b in bars]
        latest = bars[-1] if bars else None
        if latest is None:
            raise ValueError("no bars provided")

        # Allow override for M1 aggressive mode
        if self.config.min_bars_override > 0:
            min_bars = self.config.min_bars_override
        else:
            min_bars = max(self.config.ema_slow, self.config.bb_window, self.config.stochastic_k) + 5
        if len(bars) < min_bars:
            return Signal(symbol, "hold", 0.0, latest.close, "data belum cukup", latest.date)

        reasons: list[str] = []

        # ── Detect Market State: Trending (high vol) vs Sideways (low vol) ──
        is_trending = self._detect_trending(volumes, closes)

        if is_trending:
            signal = self._momentum_state(symbol, closes, latest, reasons)
        else:
            signal = self._mean_reversion_state(symbol, highs, lows, closes, latest, reasons)

        return signal

    # ═══════════════════════════════════════════════════════════════════════
    #  Market State Detection
    # ═══════════════════════════════════════════════════════════════════════

    def _detect_trending(self, volumes: list[float], closes: list[float]) -> bool:
        """Detect if market is trending (high vol + directional move) or sideways."""
        # Volume spike detection
        if len(volumes) >= 10 and self.config.volume_threshold > 0:
            recent_vol = volumes[-1]
            avg_vol = sum(volumes[-10:-1]) / 9 if len(volumes) > 1 else recent_vol
            vol_ratio = recent_vol / avg_vol if avg_vol > 0 else 1.0
            if vol_ratio >= self.config.volume_threshold:
                return True  # High volume = likely trending

        # ADX-like: measure directional strength over last 14 bars
        if len(closes) >= 15:
            movements = [abs(closes[i] - closes[i - 1]) for i in range(-14, 0)]
            avg_move = sum(movements) / len(movements)
            total_move = abs(closes[-1] - closes[-15])
            if total_move > avg_move * 3:  # Strong directional move
                return True

        # M1 Aggressive: 3 consecutive bars in same direction = trending
        if len(closes) >= 4:
            d1 = closes[-1] - closes[-2]
            d2 = closes[-2] - closes[-3]
            d3 = closes[-3] - closes[-4]
            if d1 != 0 and d2 != 0 and d3 != 0:
                if all(d > 0 for d in (d1, d2, d3)) or all(d < 0 for d in (d1, d2, d3)):
                    return True  # 3 consecutive same-direction bars = trending

        return False  # Default to mean reversion

    # ═══════════════════════════════════════════════════════════════════════
    #  STATE A: Momentum (EMA + MACD)
    # ═══════════════════════════════════════════════════════════════════════

    def _momentum_state(
        self,
        symbol: str,
        closes: list[float],
        latest: PriceBar,
        reasons: list[str],
    ) -> Signal:
        score = 0.0
        fast = self.config.ema_fast    # 9
        slow = self.config.ema_slow    # 21

        # ── EMA 9/21 Crossover ────────────────────────────────────────
        ema_fast = ema(closes, fast)
        ema_slow = ema(closes, slow)

        if ema_fast is not None and ema_slow is not None and ema_slow > 0:
            if ema_fast > ema_slow:
                score += 0.35
                reasons.append(f"EMA bullish ({fast}/{slow})")
            else:
                score -= 0.35
                reasons.append(f"EMA bearish ({fast}/{slow})")

            # Fresh crossover detection
            prev_fast = ema(closes[:-1], fast)
            prev_slow = ema(closes[:-1], slow)
            if prev_fast is not None and prev_slow is not None:
                if prev_fast <= prev_slow and ema_fast > ema_slow:
                    score += 0.20
                    reasons.append("Golden cross!")
                elif prev_fast >= prev_slow and ema_fast < ema_slow:
                    score -= 0.20
                    reasons.append("Death cross!")

        # ── MACD(12,26,9) ──────────────────────────────────────────────
        macd_line, macd_sig, macd_hist = macd(
            closes, self.config.macd_fast, self.config.macd_slow, self.config.macd_signal,
        )
        if macd_hist is not None:
            if macd_hist > 0:
                score += 0.20
                reasons.append(f"MACD+ {macd_hist:.2f}")
            elif macd_hist < 0:
                score -= 0.20
                reasons.append(f"MACD- {macd_hist:.2f}")
            else:
                reasons.append("MACD flat")

        # ── Higher-Timeframe Trend Filter (configurable) ──────────────
        # For M5: last 6 bars ≈ M30; for M1: last 5 bars ≈ M5
        # Controlled by trend_filter_bars in config
        tf_bars = self.config.trend_filter_bars
        if len(closes) >= tf_bars + 2:
            higher_close = closes[-tf_bars:]
            higher_ema = ema(higher_close, min(tf_bars - 1, 5))
            if higher_ema is not None and higher_ema > 0:
                if closes[-1] > higher_ema:
                    score += 0.15
                    reasons.append(f"TF{tf_bars} bullish")
                else:
                    score -= 0.15
                    reasons.append(f"TF{tf_bars} bearish")

        # ── RSI Scoring (Aggressive M1) ────────────────────────────────
        if self.config.rsi_enabled and len(closes) >= self.config.rsi_window + 2:
            rsi_val = rsi(closes, self.config.rsi_window)
            if rsi_val is not None:
                if rsi_val > self.config.rsi_bullish_threshold:
                    score += self.config.rsi_score_weight
                    reasons.append(f"RSI bullish ({rsi_val:.0f})")
                elif rsi_val < self.config.rsi_bearish_threshold:
                    score -= self.config.rsi_score_weight
                    reasons.append(f"RSI bearish ({rsi_val:.0f})")
                else:
                    reasons.append(f"RSI neutral ({rsi_val:.0f})")

        # ── Momentum Velocity (Aggressive M1) ───────────────────────────
        if self.config.momentum_velocity_enabled and len(closes) >= self.config.velocity_bars + 1:
            n = self.config.velocity_bars
            velocity = (closes[-1] - closes[-n - 1]) / n
            if velocity > 0:
                score += self.config.velocity_score_weight
                reasons.append(f"Velocity +{velocity:.2f}/bar")
            elif velocity < 0:
                score -= self.config.velocity_score_weight
                reasons.append(f"Velocity {velocity:.2f}/bar")

        # ── Multi-Confirmation Boost ────────────────────────────────────
        # If 3+ factors agree, add bonus for stronger conviction
        if self.config.multi_confirm_boost > 0:
            bull_count = sum(1 for r in reasons if "bullish" in r.lower() or "golden cross" in r.lower() or "MACD+" in r or "Velocity +" in r)
            bear_count = sum(1 for r in reasons if "bearish" in r.lower() or "death cross" in r.lower() or "MACD-" in r or "Velocity -" in r)
            if bull_count >= 3:
                score += self.config.multi_confirm_boost
                reasons.append(f"Multi-confirm BOOST ({bull_count} factors)")
            elif bear_count >= 3:
                score -= self.config.multi_confirm_boost
                reasons.append(f"Multi-confirm BOOST ({bear_count} factors)")

        score = self._clamp(score, -1.0, 1.0)

        if score >= self.config.min_buy_score:
            action = "buy"
        elif score <= self.config.min_sell_score:
            action = "sell"
        else:
            action = "hold"

        created_at = latest.date.astimezone(timezone.utc)
        return Signal(symbol, action, abs(score), latest.close,
                      " | ".join(reasons) + " [MOMENTUM]", created_at)

    # ═══════════════════════════════════════════════════════════════════════
    #  STATE B: Mean Reversion (BB + Stochastic)
    # ═══════════════════════════════════════════════════════════════════════

    def _mean_reversion_state(
        self,
        symbol: str,
        highs: list[float],
        lows: list[float],
        closes: list[float],
        latest: PriceBar,
        reasons: list[str],
    ) -> Signal:
        score = 0.0

        # ── Bollinger Bands (20, 2.0) ──────────────────────────────────
        bb_lower, bb_upper, bb_mid = bollinger_bands(
            closes, self.config.bb_window, self.config.bb_std,
        )
        current_close = closes[-1]

        if bb_lower is not None and bb_upper is not None:
            if current_close <= bb_lower:
                score += 0.30
                reasons.append("BB lower touch")
            elif current_close >= bb_upper:
                score -= 0.30
                reasons.append("BB upper touch")
            else:
                bb_pos = ((current_close - bb_lower) / (bb_upper - bb_lower)
                          if bb_upper != bb_lower else 0.5)
                reasons.append(f"BB {bb_pos:.0%}")

        # ── Stochastic(14,3,3) ─────────────────────────────────────────
        k_val, d_val = stochastic(
            highs, lows, closes,
            self.config.stochastic_k,
            self.config.stochastic_d,
            self.config.stochastic_slowing,
        )

        if k_val is not None and d_val is not None:
            oversold = self.config.stochastic_oversold   # 20
            overbought = self.config.stochastic_overbought  # 80

            if k_val < oversold and d_val < oversold:
                score += 0.25
                reasons.append(f"Stoch oversold ({k_val:.0f}/{d_val:.0f})")

                # Bullish crossover detection
                if len(closes) >= self.config.stochastic_k + self.config.stochastic_d + 5:
                    prev_k, prev_d = self._prev_stochastic(highs, lows, closes)
                    if prev_k is not None and prev_d is not None:
                        if prev_k <= prev_d and k_val > d_val:
                            score += 0.20
                            reasons.append("Stoch bullish cross!")

            elif k_val > overbought and d_val > overbought:
                score -= 0.25
                reasons.append(f"Stoch overbought ({k_val:.0f}/{d_val:.0f})")

                # Bearish crossover detection
                if len(closes) >= self.config.stochastic_k + self.config.stochastic_d + 5:
                    prev_k, prev_d = self._prev_stochastic(highs, lows, closes)
                    if prev_k is not None and prev_d is not None:
                        if prev_k >= prev_d and k_val < d_val:
                            score -= 0.20
                            reasons.append("Stoch bearish cross!")
            else:
                reasons.append(f"Stoch {k_val:.0f}/{d_val:.0f}")

        # ── RSI Confirmation (Aggressive M1) ──────────────────────────
        if self.config.rsi_enabled and len(closes) >= self.config.rsi_window + 2:
            rsi_val = rsi(closes, self.config.rsi_window)
            if rsi_val is not None:
                if rsi_val > self.config.rsi_bullish_threshold:
                    score += self.config.rsi_score_weight * 0.5  # lighter weight in reversion
                    reasons.append(f"RSI confirms ({rsi_val:.0f})")
                elif rsi_val < self.config.rsi_bearish_threshold:
                    score -= self.config.rsi_score_weight * 0.5
                    reasons.append(f"RSI confirms ({rsi_val:.0f})")

        score = self._clamp(score, -1.0, 1.0)

        if score >= self.config.min_buy_score:
            action = "buy"
        elif score <= self.config.min_sell_score:
            action = "sell"
        else:
            action = "hold"

        created_at = latest.date.astimezone(timezone.utc)
        return Signal(symbol, action, abs(score), latest.close,
                      " | ".join(reasons) + " [REVERSION]", created_at)

    # ═══════════════════════════════════════════════════════════════════════
    #  Helpers
    # ═══════════════════════════════════════════════════════════════════════

    def _prev_stochastic(
        self, highs: list[float], lows: list[float], closes: list[float],
    ) -> tuple[float | None, float | None]:
        """Get previous bar's Stochastic values for crossover detection."""
        k_vals = []
        for offset in range(1, 3):
            h = highs[:-offset] if offset > 0 else highs
            lo = lows[:-offset] if offset > 0 else lows
            c = closes[:-offset] if offset > 0 else closes
            if len(h) < self.config.stochastic_k + 2:
                return None, None
            k_v, d_v = stochastic(
                h, lo, c,
                self.config.stochastic_k,
                self.config.stochastic_d,
                self.config.stochastic_slowing,
            )
            if k_v is not None:
                k_vals.append(k_v)
        if len(k_vals) >= 2:
            return k_vals[0], k_vals[1]
        return None, None

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        return max(low, min(high, value))


class ScalpingRiskManager:
    """Professional risk management: dynamic sizing based on SL distance, lock profit at +5 pips.

    AGGRESSIVE MODE:
      - Timeout exit: force-close after N minutes if TP not reached
      - Max lot sizing: use max_lot_size cap for aggressive entries
      - TP: 100 points (10 pips) target for scalping
    """

    def __init__(self, config: ScalpingConfig):
        self.config = config

    def buy_quantity(self, cash: float, equity: float, price: float) -> float:
        """Dynamic position sizing — aggressive mode uses max sizing.

        Basket-case rule: 1 position max, no martingale (enforced in engine).
        """
        if price <= 0 or cash <= 10:
            return 0.0

        if self.config.aggressive_mode:
            # ── AGGRESSIVE: maximum lot per trade ───────────────────────────
            # Hitung berdasarkan risk: equity × risk% × multiplier ÷ cost SL
            multiplier = self.config.aggressive_risk_multiplier  # 4x
            risk_amount = equity * self.config.risk_per_trade_pct * multiplier

            # Biaya SL = stop_loss_pips × 10 (konversi pips ke dolar per lot)
            sl_cost = self.config.stop_loss_pips * 10.0
            if sl_cost <= 0:
                sl_cost = 100.0  # fallback
            quantity = risk_amount / sl_cost

            # Cap maksimal: max_trade_pct dari equity
            max_by_equity = equity * self.config.max_trade_pct / price
            # Cash yang tersedia
            max_by_cash = cash / price

            # Tidak ada max_lot_size — biarkan max_trade_pct yang jadi limit
            quantity = min(quantity, max_by_equity, max_by_cash)
            return max(0.0, quantity)

        # ── NORMAL MODE ──────────────────────────────────────────────────
        risk_amount = equity * self.config.risk_per_trade_pct
        sl_distance = self.config.stop_loss_pips * 0.1
        if sl_distance <= 0:
            return 0.0
        quantity = risk_amount / (self.config.stop_loss_pips * 10.0)
        max_trade = equity * self.config.max_trade_pct / price
        return max(0.0, min(quantity, max_trade, cash / price))

    def forced_exit_reason(self, entry_price: float, current_price: float,
                           entry_time=None, current_time=None,
                           side: str = "buy", point_size: float | None = None) -> str | None:
        """Check SL/TP in pips + optional timeout exit.

        Args:
            entry_price: Position entry price
            current_price: Current market price
            entry_time: Datetime when position was entered (for timeout)
            current_time: Current datetime

        Returns:
            str with exit reason, or None if no exit needed
        """
        if entry_price <= 0:
            return None

        sl_pips = self.config.stop_loss_pips
        tp_pips = self.config.take_profit_pips
        pip_value = point_size * 10 if point_size is not None and point_size > 0 else 0.1
        pnl_pips = (current_price - entry_price) / pip_value
        if side.lower() in {"sell", "short"}:
            pnl_pips *= -1

        # ═══ TAK PROFIT ═══════════════════════════════════════════════
        tolerance = 1e-9
        if tp_pips > 0 and pnl_pips + tolerance >= tp_pips:
            return f"take profit +{tp_pips:.0f}p ({tp_pips * 10:.0f}pt)"

        # ═══ STOP LOSS ════════════════════════════════════════════════
        if sl_pips > 0 and pnl_pips - tolerance <= -sl_pips:
            return f"stop loss -{sl_pips:.0f}p ({sl_pips * 10:.0f}pt)"

        # ═══ LOCK PROFIT ═══════════════════════════════════════════════
        lock_pips = self.config.trailing_stop_pips
        if lock_pips > 0 and pnl_pips + tolerance >= lock_pips:
            return f"lock profit +{lock_pips:.0f}p"

        # ═══ TIMEOUT EXIT (aggressive mode) ═══════════════════════════
        if self.config.aggressive_mode and entry_time is not None and current_time is not None:
            elapsed_min = (current_time - entry_time).total_seconds() / 60.0
            timeout = self.config.timeout_exit_minutes
            if timeout > 0 and elapsed_min >= timeout:
                return f"timeout {timeout}m (P&L {pnl_pips:+.0f}p)"

        return None

    def trailing_stop_price(
        self,
        entry_price: float,
        current_price: float,
        side: str = "buy",
        point_size: float | None = None,
    ) -> float | None:
        """Return the lock-profit exit price if triggered, else None."""
        lock_pips = self.config.trailing_stop_pips
        pip_value = point_size * 10 if point_size is not None and point_size > 0 else 0.1
        direction = -1 if side.lower() in {"sell", "short"} else 1
        pnl_pips = (current_price - entry_price) / pip_value * direction
        if lock_pips > 0 and pnl_pips >= lock_pips:
            return entry_price + lock_pips * pip_value * direction
        return None

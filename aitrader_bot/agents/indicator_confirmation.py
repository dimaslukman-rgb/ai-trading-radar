"""Indicator Confirmation Agent — EMA, VWAP, RSI, MACD, ADX, ATR, Stochastic."""

from __future__ import annotations

import math

from .base import AgentContext, AgentResult, BaseAgent


def ema(data: list[float], period: int) -> float:
    if len(data) < period:
        return data[-1] if data else 0
    multiplier = 2 / (period + 1)
    result = sum(data[-period:]) / period
    for i in range(len(data) - period, len(data)):
        result = (data[i] - result) * multiplier + result
    return result


def rsi(data: list[float], period: int = 14) -> float:
    if len(data) < period + 1:
        return 50
    gains, losses = 0, 0
    for i in range(-period, 0):
        diff = data[i] - data[i - 1]
        if diff > 0:
            gains += diff
        else:
            losses -= diff
    avg_gain = gains / period
    avg_loss = losses / period or 0.001
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


class IndicatorConfirmationAgent(BaseAgent):
    agent_id = "indicator_confirmation"

    def analyze(self, ctx: AgentContext) -> AgentResult:
        candles = ctx.candles
        if len(candles) < 20:
            return AgentResult(self.agent_id, {
                "ema": "Neutral", "rsi": 50,
                "adx": 0, "macd": "Neutral", "confirmation": 0
            })

        closes = [c["close"] for c in candles]
        highs = [c["high"] for c in candles]
        lows = [c["low"] for c in candles]
        current_price = closes[-1]

        # EMA
        ema_fast = ema(closes, 9)
        ema_slow = ema(closes, 21)
        if ema_fast > ema_slow and current_price > ema_fast:
            ema_bias = "Bullish"
        elif ema_fast < ema_slow and current_price < ema_fast:
            ema_bias = "Bearish"
        else:
            ema_bias = "Neutral"

        # RSI
        rsi_val = int(round(rsi(closes, 14)))

        # ADX
        adx_val = 0
        if len(candles) >= 15:
            plus_dm_sum, minus_dm_sum, tr_sum = 0, 0, 0
            for i in range(-14, 0):
                high_diff = highs[i] - highs[i - 1]
                low_diff = lows[i - 1] - lows[i]
                tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
                tr_sum += tr
                if high_diff > low_diff and high_diff > 0:
                    plus_dm_sum += high_diff
                elif low_diff > high_diff and low_diff > 0:
                    minus_dm_sum += low_diff
            if tr_sum > 0:
                plus_di = 100 * plus_dm_sum / tr_sum
                minus_di = 100 * minus_dm_sum / tr_sum
                dx = abs(plus_di - minus_di) / (plus_di + minus_di or 1) * 100
                adx_val = int(round(dx))

        # MACD
        ema12 = ema(closes, 12)
        ema26 = ema(closes, 26)
        macd_line = ema12 - ema26
        signal_line = ema(closes[-9:], 9) if len(closes) >= 9 else macd_line
        histogram = macd_line - signal_line

        prev_macd = ema(closes[:-1], 12) - ema(closes[:-1], 26) if len(closes) >= 27 else macd_line
        prev_signal = signal_line

        if macd_line > signal_line and histogram > 0:
            if prev_macd <= prev_signal:
                macd_bias = "Crossing Up"
            else:
                macd_bias = "Bullish"
        elif macd_line < signal_line and histogram < 0:
            if prev_macd >= prev_signal:
                macd_bias = "Crossing Down"
            else:
                macd_bias = "Bearish"
        else:
            macd_bias = "Neutral"

        # ATR
        atr_val = 0
        if len(candles) >= 15:
            tr_values = []
            for i in range(-14, 0):
                tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
                tr_values.append(tr)
            atr_val = sum(tr_values) / len(tr_values) if tr_values else 0

        # Stochastic
        stoch_k = 50
        if len(candles) >= 15:
            period_high = max(highs[-14:])
            period_low = min(lows[-14:])
            if period_high - period_low > 0:
                stoch_k = (current_price - period_low) / (period_high - period_low) * 100

        # Overall confirmation score
        confirmation = 50
        if ema_bias == "Bullish":
            confirmation += 10
        elif ema_bias == "Bearish":
            confirmation += 10

        if rsi_val > 60:
            confirmation += 5
        elif rsi_val < 40:
            confirmation += 5

        if adx_val > 25:
            confirmation += 15
        elif adx_val > 20:
            confirmation += 5

        if "Crossing" in macd_bias:
            confirmation += 15
        elif macd_bias in ("Bullish", "Bearish"):
            confirmation += 10

        confirmation = min(100, max(0, confirmation))

        return AgentResult(self.agent_id, {
            "ema": ema_bias,
            "rsi": rsi_val,
            "adx": adx_val,
            "macd": macd_bias,
            "confirmation": confirmation,
        })

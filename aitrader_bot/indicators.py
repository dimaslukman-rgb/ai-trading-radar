from __future__ import annotations

import math


def sma(values: list[float], window: int) -> float | None:
    if window <= 0 or len(values) < window:
        return None
    return sum(values[-window:]) / window


def rsi(values: list[float], window: int = 14) -> float | None:
    if window <= 0 or len(values) <= window:
        return None
    gains = 0.0
    losses = 0.0
    changes = values[-window - 1 :]
    for previous, current in zip(changes, changes[1:]):
        diff = current - previous
        if diff >= 0:
            gains += diff
        else:
            losses += abs(diff)
    if losses == 0:
        return 100.0
    rs = gains / losses
    return 100.0 - (100.0 / (1.0 + rs))


def volatility(values: list[float], window: int = 20) -> float | None:
    if len(values) < window:
        return None
    sample = values[-window:]
    mean = sum(sample) / len(sample)
    if mean == 0:
        return None
    variance = sum((item - mean) ** 2 for item in sample) / len(sample)
    return math.sqrt(variance) / mean


def ema(values: list[float], window: int) -> float | None:
    """Exponential Moving Average."""
    if len(values) < window:
        return None
    multiplier = 2.0 / (window + 1)
    result = sum(values[:window]) / window
    for price in values[window:]:
        result = (price - result) * multiplier + result
    return result


def macd(
    closes: list[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[float | None, float | None, float | None]:
    """MACD Line, Signal Line, Histogram."""
    macd_fast = ema(closes, fast)
    macd_slow = ema(closes, slow)
    if macd_fast is None or macd_slow is None:
        return None, None, None
    macd_line = macd_fast - macd_slow

    min_bars = max(fast, slow) + signal
    if len(closes) < min_bars + 5:
        return macd_line, macd_line, 0.0

    macd_values: list[float] = []
    for i in range(signal, len(closes) + 1):
        window = closes[:i]
        f = ema(window, fast)
        s = ema(window, slow)
        if f is not None and s is not None:
            macd_values.append(f - s)

    if len(macd_values) < signal:
        return macd_line, macd_line, 0.0

    sig = ema(macd_values, signal)
    if sig is None:
        return macd_line, macd_line, 0.0

    histogram = macd_line - sig
    return macd_line, sig, histogram


def bollinger_bands(
    closes: list[float],
    window: int = 20,
    std_dev: float = 2.0,
) -> tuple[float | None, float | None, float | None]:
    """Bollinger Bands (lower, upper, middle)."""
    if len(closes) < window:
        return None, None, None
    w = closes[-window:]
    mean = sum(w) / len(w)
    variance = sum((x - mean) ** 2 for x in w) / len(w)
    std = variance ** 0.5
    lower = mean - std_dev * std
    upper = mean + std_dev * std
    return lower, upper, mean


def stochastic(
    highs: list[float],
    lows: list[float],
    closes: list[float],
    k_window: int = 14,
    d_window: int = 3,
    slowing: int = 3,
) -> tuple[float | None, float | None]:
    """Stochastic Oscillator — returns (%K, %D) or (None, None)."""
    if len(highs) < k_window + slowing + d_window or len(lows) < k_window or len(closes) < k_window:
        return None, None

    # Calculate raw %K
    raw_k: list[float] = []
    for i in range(k_window - 1, len(closes)):
        high_max = max(highs[i - k_window + 1 : i + 1])
        low_min = min(lows[i - k_window + 1 : i + 1])
        close = closes[i]
        if high_max == low_min:
            raw_k.append(50.0)
        else:
            raw_k.append((close - low_min) / (high_max - low_min) * 100.0)

    if len(raw_k) < slowing + d_window:
        return None, None

    # Apply slowing (SMA of raw %K)
    slowed_k: list[float] = []
    for i in range(slowing - 1, len(raw_k)):
        slowed_k.append(sum(raw_k[i - slowing + 1 : i + 1]) / slowing)

    if len(slowed_k) < d_window:
        return None, None

    # %D is SMA of %K
    k_val = slowed_k[-1]
    d_val = sum(slowed_k[-d_window:]) / d_window
    return k_val, d_val

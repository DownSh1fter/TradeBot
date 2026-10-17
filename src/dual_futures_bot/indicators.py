from collections.abc import Sequence

from .models import Candle


def ema(values: Sequence[float], period: int) -> list[float | None]:
    if period < 1:
        raise ValueError("period must be >= 1")
    out: list[float | None] = [None] * len(values)
    if len(values) < period:
        return out
    alpha = 2.0 / (period + 1)
    current = sum(values[:period]) / period
    out[period - 1] = current
    for i in range(period, len(values)):
        current = alpha * values[i] + (1.0 - alpha) * current
        out[i] = current
    return out


def atr(candles: Sequence[Candle], period: int) -> list[float | None]:
    if period < 1:
        raise ValueError("period must be >= 1")
    out: list[float | None] = [None] * len(candles)
    if len(candles) <= period:
        return out
    tr: list[float] = []
    for i, candle in enumerate(candles):
        prev_close = candles[i - 1].close if i else candle.close
        tr.append(max(candle.high - candle.low, abs(candle.high - prev_close), abs(candle.low - prev_close)))
    current = sum(tr[1 : period + 1]) / period
    out[period] = current
    for i in range(period + 1, len(candles)):
        current = ((period - 1) * current + tr[i]) / period
        out[i] = current
    return out

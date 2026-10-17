from collections.abc import Sequence

from .indicators import atr, ema
from .models import Candle, Signal


def ema_cross_signals(
    candles: Sequence[Candle], fast_period: int = 20, slow_period: int = 50, atr_period: int = 14
) -> list[Signal | None]:
    """Emit a signal after a confirmed close; the simulator fills on the next candle open."""
    if fast_period >= slow_period:
        raise ValueError("fast_period must be smaller than slow_period")
    closes = [c.close for c in candles]
    fast = ema(closes, fast_period)
    slow = ema(closes, slow_period)
    volatility = atr(candles, atr_period)
    signals: list[Signal | None] = [None] * len(candles)
    for i in range(1, len(candles)):
        if fast[i - 1] is None or slow[i - 1] is None or fast[i] is None or slow[i] is None or volatility[i] is None:
            continue
        crossed_up = fast[i - 1] <= slow[i - 1] and fast[i] > slow[i]
        crossed_down = fast[i - 1] >= slow[i - 1] and fast[i] < slow[i]
        if crossed_up:
            signals[i] = Signal("long", candles[i].timestamp, candles[i].close, volatility[i])
        elif crossed_down:
            signals[i] = Signal("short", candles[i].timestamp, candles[i].close, volatility[i])
    return signals

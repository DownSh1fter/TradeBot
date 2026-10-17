from dataclasses import dataclass
from math import isfinite
from collections.abc import Sequence

from .indicators import atr
from .models import Candle, Trade
from .strategy import ema_cross_signals


@dataclass(frozen=True)
class RiskConfig:
    initial_equity: float = 10_000.0
    risk_fraction: float = 0.0025
    max_notional_fraction: float = 0.25
    max_daily_loss_fraction: float = 0.01
    stop_atr_multiple: float = 2.0
    fee_rate: float = 0.0005
    slippage_rate: float = 0.0002

    def validate(self) -> None:
        if not all(isfinite(value) for value in vars(self).values()):
            raise ValueError("risk parameters must be finite")
        if self.initial_equity <= 0:
            raise ValueError("initial_equity must be positive")
        if not 0 < self.risk_fraction <= 0.01:
            raise ValueError("risk_fraction must be in (0, 1%]")
        if not 0 < self.max_notional_fraction <= 1:
            raise ValueError("max_notional_fraction must be in (0, 100%]")
        if not 0 < self.max_daily_loss_fraction <= 0.05:
            raise ValueError("max_daily_loss_fraction must be in (0, 5%]")
        if self.stop_atr_multiple <= 0 or self.fee_rate < 0 or not 0 <= self.slippage_rate < 1:
            raise ValueError("stop and cost parameters are invalid")


def size_for_risk(equity: float, entry: float, stop: float, risk_fraction: float, max_notional_fraction: float) -> float:
    distance = abs(entry - stop)
    if not all(isfinite(x) for x in (equity, entry, stop, risk_fraction, max_notional_fraction)):
        raise ValueError("inputs must be finite")
    if equity <= 0 or entry <= 0 or distance <= 0 or not 0 < risk_fraction <= 1 or not 0 < max_notional_fraction <= 1:
        raise ValueError("invalid position sizing inputs")
    risk_qty = equity * risk_fraction / distance
    notional_cap_qty = equity * max_notional_fraction / entry
    return min(risk_qty, notional_cap_qty)


def _adverse_price(price: float, side: str, is_entry: bool, slip: float) -> float:
    buy = (side == "long" and is_entry) or (side == "short" and not is_entry)
    return price * (1 + slip if buy else 1 - slip)


def simulate(candles: Sequence[Candle], config: RiskConfig = RiskConfig()) -> dict:
    config.validate()
    if len(candles) < 60:
        raise ValueError("at least 60 candles are required")
    for i, candle in enumerate(candles):
        if not all(isfinite(v) for v in vars(candle).values()):
            raise ValueError("candle values must be finite")
        if min(candle.open, candle.high, candle.low, candle.close) <= 0 or candle.volume < 0:
            raise ValueError("prices must be positive and volume nonnegative")
        if candle.low > min(candle.open, candle.close) or candle.high < max(candle.open, candle.close):
            raise ValueError("invalid OHLC range")
        if i and candle.timestamp <= candles[i - 1].timestamp:
            raise ValueError("candle timestamps must be strictly increasing")
    signals = ema_cross_signals(candles)
    atr_values = atr(candles, 14)
    equity = config.initial_equity
    peak = equity
    max_drawdown = 0.0
    trades: list[Trade] = []
    position: dict | None = None
    day_start_equity = equity
    active_day = candles[0].timestamp // 86_400_000
    halted_days: set[int] = set()

    def close_position(price: float, candle: Candle, reason: str) -> None:
        nonlocal position, equity, peak, max_drawdown
        assert position is not None
        side = position["side"]
        exit_price = _adverse_price(price, side, False, config.slippage_rate)
        direction = 1 if side == "long" else -1
        gross = (exit_price - position["entry"]) * position["qty"] * direction
        exit_fee = abs(exit_price * position["qty"]) * config.fee_rate
        fees = position["entry_fee"] + exit_fee
        pnl = gross - fees
        equity += pnl
        peak = max(peak, equity)
        max_drawdown = max(max_drawdown, (peak - equity) / peak if peak > 0 else 0.0)
        trades.append(Trade(side, position["entry_time"], candle.timestamp, position["entry"], exit_price, position["qty"], fees, pnl, reason))
        position = None

    for i in range(1, len(candles)):
        candle = candles[i]
        day = candle.timestamp // 86_400_000
        if day != active_day:
            active_day = day
            day_start_equity = equity
        # A reversal is known at the open, before this candle's intrabar range.
        if position is not None:
            gap_hit = candle.open <= position["stop"] if position["side"] == "long" else candle.open >= position["stop"]
            if gap_hit:
                close_position(candle.open, candle, "trailing_stop")
            elif signals[i - 1] is not None and signals[i - 1].side != position["side"]:
                close_position(candle.open, candle, "reverse_signal")

        daily_loss = max(0.0, (day_start_equity - equity) / day_start_equity) if day_start_equity > 0 else 0.0
        if daily_loss >= config.max_daily_loss_fraction:
            halted_days.add(day)

        # A signal is known only after the previous candle closes; fill at this candle's open.
        signal = signals[i - 1]
        if position is None and equity > 0 and signal is not None and day not in halted_days and atr_values[i - 1] is not None:
            side = signal.side
            entry = _adverse_price(candle.open, side, True, config.slippage_rate)
            stop_distance = signal.atr * config.stop_atr_multiple
            stop = entry - stop_distance if side == "long" else entry + stop_distance
            qty = size_for_risk(equity, entry, stop, config.risk_fraction, config.max_notional_fraction)
            entry_fee = abs(entry * qty) * config.fee_rate
            if qty > 0 and equity > entry_fee:
                position = {"side": side, "entry": entry, "entry_time": candle.timestamp, "qty": qty, "stop": stop, "entry_fee": entry_fee}

        # The active stop also applies to a position opened on this candle.
        if position is not None:
            hit = candle.low <= position["stop"] if position["side"] == "long" else candle.high >= position["stop"]
            if hit:
                close_position(position["stop"], candle, "trailing_stop")
                if day_start_equity > 0 and (day_start_equity - equity) / day_start_equity >= config.max_daily_loss_fraction:
                    halted_days.add(day)

        # Trail only after this candle has completed; it becomes active on the next candle.
        if position is not None and atr_values[i] is not None:
            distance = atr_values[i] * config.stop_atr_multiple
            candidate = candle.close - distance if position["side"] == "long" else candle.close + distance
            position["stop"] = max(position["stop"], candidate) if position["side"] == "long" else min(position["stop"], candidate)

    if position is not None:
        close_position(candles[-1].close, candles[-1], "end_of_data")
    net = equity - config.initial_equity
    winners = sum(t.pnl > 0 for t in trades)
    return {
        "initial_equity": config.initial_equity,
        "final_equity": equity,
        "net_pnl": net,
        "net_return_fraction": net / config.initial_equity,
        "trade_count": len(trades),
        "win_rate": winners / len(trades) if trades else 0.0,
        "max_drawdown_fraction": max_drawdown,
        "fees_paid": sum(t.fees for t in trades),
        "halted_days": len(halted_days),
        "trades": [t.to_dict() for t in trades],
    }

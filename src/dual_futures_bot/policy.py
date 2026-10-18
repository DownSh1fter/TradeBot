"""Causal trend/pullback policy. No model output controls execution."""
from .indicators import atr, ema

TREND_POLICY = 'trend-pullback-v1'


def trend_decisions(candles, roundtrip_cost=.0014):
    closes = [c.close for c in candles]
    fast, slow, volatility = ema(closes, 20), ema(closes, 50), atr(candles, 14)
    out = []
    for i, c in enumerate(candles):
        d = dict(strategy=TREND_POLICY, signal=None, signal_reason='warmup',
                 exit_long=False, exit_short=False, take_profit_atr_multiple=3,
                 max_hold_bars=24, cooldown_bars=3, target_distance_fraction=0,
                 assumed_roundtrip_cost=roundtrip_cost, volume_ratio_20=0, trend_strength_atr=0)
        out.append(d)
        if i < 59 or not volatility[i] or volatility[i] <= 0:
            if i >= 59:
                d['signal_reason'] = 'low_volatility'
            continue
        f, s, v = fast[i], slow[i], volatility[i]
        ratio = v / c.close
        avg_volume = sum(x.volume for x in candles[i-20:i]) / 20
        relative_volume = c.volume / avg_volume if avg_volume > 0 else 0
        direction = 1 if f > s else -1
        d.update(exit_long=f < s, exit_short=f > s, atr14=v, atr_fraction=ratio,
                 trend_strength_atr=abs(f-s)/v, volume_ratio_20=relative_volume,
                 target_distance_fraction=3*v/c.close, assumed_roundtrip_cost=roundtrip_cost)
        reason = None
        if ratio > .05:
            reason = 'high_volatility'
        elif ratio < .0005:
            reason = 'low_volatility'
        elif abs(f-s) < .25*v:
            reason = 'weak_trend'
        elif direction*(f-fast[i-3]) <= 0:
            reason = 'trend_slope_conflict'
        elif relative_volume < .5:
            reason = 'low_volume'
        elif abs(c.close-f) > v:
            reason = 'price_too_far_from_ema'
        elif not any(x.low <= fast[j]+.25*volatility[j] if direction == 1 else x.high >= fast[j]-.25*volatility[j]
                     for j, x in enumerate(candles[i-2:i+1], i-2)):
            reason = 'no_recent_pullback'
        elif direction*(c.close-candles[i-1].close) <= 0 or direction*(c.close-f) < -.25*v:
            reason = 'rebound_not_confirmed'
        elif 3*v/c.close < 2*roundtrip_cost:
            reason = 'target_too_small_for_costs'
        if reason:
            d['signal_reason'] = reason
        else:
            d.update(signal='long' if direction == 1 else 'short', signal_reason='trend_pullback_confirmed')
    return out


def entry_block(state, analysis):
    """Post-exit cooldown only; never prevents exits."""
    if analysis.get('strategy') != TREND_POLICY:
        return None
    last_exit = state.get('last_exit_candle')
    interval = analysis.get('interval_ms', 0)
    if last_exit is not None and interval and analysis['candle_timestamp'] < last_exit + analysis['cooldown_bars']*interval:
        return 'post_exit_cooldown'
    return None


def exit_reason(position, analysis, price):
    if analysis.get('strategy') != TREND_POLICY:
        return None
    side = position['side']
    target = position.get('target')
    if target is not None and (price >= target if side == 'long' else price <= target):
        return 'take_profit'
    if analysis.get('exit_long' if side == 'long' else 'exit_short'):
        return 'trend_invalidated'
    opened = position.get('entry_candle')
    interval = analysis.get('interval_ms', 0)
    if opened is not None and interval and analysis['candle_timestamp'] >= opened + analysis['max_hold_bars']*interval:
        return 'max_holding_time'
    return None

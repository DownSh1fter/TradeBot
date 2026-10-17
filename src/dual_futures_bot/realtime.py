"""Polling market analysis and persistent paper execution. Never sends orders."""
import json
import math
import os
import time
from dataclasses import asdict
from pathlib import Path

from .indicators import atr, ema
from .models import Candle
from .simulator import RiskConfig, size_for_risk
from .strategy import ema_cross_signals


def analyze(candles, now_ms, interval_ms):
    if len(candles) < 60:
        raise ValueError('at least 60 closed candles required')
    for i, c in enumerate(candles):
        if not all(math.isfinite(v) for v in asdict(c).values()):
            raise ValueError('nonfinite candle')
        if min(c.open, c.high, c.low, c.close) <= 0 or c.volume < 0 or c.low > min(c.open, c.close) or c.high < max(c.open, c.close):
            raise ValueError('invalid OHLCV')
        if i and c.timestamp - candles[i - 1].timestamp != interval_ms:
            raise ValueError('unordered or missing candles')
    age = now_ms - (candles[-1].timestamp + interval_ms)
    if age < 0 or age > interval_ms:
        raise ValueError('unfinished or stale candles')
    closes = [c.close for c in candles]
    fast, slow = ema(closes, 20)[-1], ema(closes, 50)[-1]
    volatility = atr(candles, 14)[-1]
    signal = ema_cross_signals(candles)[-1]
    ratio = volatility / closes[-1]
    return {'candle_timestamp': candles[-1].timestamp, 'ema20': fast, 'ema50': slow,
            'trend': 'up' if fast > slow else 'down' if fast < slow else 'flat',
            'atr14': volatility, 'atr_fraction': ratio,
            'signal': signal.side if signal and 0 < ratio <= .05 else None,
            'filter': 'volatility_block' if ratio > .05 else 'ok'}


def step(state, analysis, price, now_ms, config):
    """Paper fills at the observed current quote, never retroactively at a candle open."""
    config.validate()
    if not math.isfinite(price) or price <= 0:
        raise ValueError('invalid quote')
    if now_ms < state.get('updated_at', 0):
        raise ValueError('clock moved backwards')
    day = now_ms // 86_400_000
    if state.get('day') != day:
        state.update(day=day, day_equity=state['equity'], halted=False)
    new_signal = analysis['candle_timestamp'] > state.get('last_candle', -1)
    signal = analysis['signal'] if new_signal else None
    events = []
    p = state['position']
    if p:
        hit = price <= p['stop'] if p['side'] == 'long' else price >= p['stop']
        if hit or (signal and signal != p['side']):
            exit_price = price * (1 - config.slippage_rate if p['side'] == 'long' else 1 + config.slippage_rate)
            gross = (exit_price - p['entry']) * p['quantity'] * (1 if p['side'] == 'long' else -1)
            exit_fee = exit_price * p['quantity'] * config.fee_rate
            net = gross - p['entry_fee'] - exit_fee
            state['equity'] += gross - exit_fee  # entry fee was debited on entry
            events.append(dict(type='exit', side=p['side'], price=exit_price, quantity=p['quantity'],
                               pnl=net, reason='stop' if hit else 'reverse_signal', timestamp=now_ms))
            state['position'] = None
    if state['equity'] <= state['day_equity'] * (1 - config.max_daily_loss_fraction):
        state['halted'] = True
    if state['position'] is None and signal and not state['halted'] and state['equity'] > 0:
        entry = price * (1 + config.slippage_rate if signal == 'long' else 1 - config.slippage_rate)
        stop = entry + analysis['atr14'] * config.stop_atr_multiple * (-1 if signal == 'long' else 1)
        if stop > 0:
            qty = size_for_risk(state['equity'], entry, stop, config.risk_fraction, config.max_notional_fraction)
            fee = entry * qty * config.fee_rate
            state['equity'] -= fee
            state['position'] = dict(side=signal, entry=entry, stop=stop, quantity=qty, entry_fee=fee)
            events.append(dict(type='entry', timestamp=now_ms, **state['position']))
    if state['position'] and new_signal:
        p = state['position']
        candidate = price + analysis['atr14'] * config.stop_atr_multiple * (-1 if p['side'] == 'long' else 1)
        p['stop'] = max(p['stop'], candidate) if p['side'] == 'long' else min(p['stop'], candidate)
    state['last_candle'] = max(state.get('last_candle', -1), analysis['candle_timestamp'])
    state['updated_at'] = now_ms
    state['analysis'] = analysis
    state['last_price'] = price
    state['events'].extend(events)
    return events


def run(exchange_id, symbol, timeframe, limit, equity, state_path, poll_seconds=10, cycles=0, demo=False):
    import ccxt
    config = RiskConfig(initial_equity=equity)
    config.validate()
    if not math.isfinite(poll_seconds) or poll_seconds < 1 or cycles < 0:
        raise ValueError('poll seconds must be >= 1 and cycles >= 0')
    path = Path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(path.suffix + '.lock')
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    exchange = None
    try:
        identity = dict(exchange=exchange_id, symbol=symbol, timeframe=timeframe, mode='bybit_demo' if demo else 'realtime_paper', risk=asdict(config))
        state = json.loads(path.read_text()) if path.exists() else dict(identity=identity, equity=equity, position=None, events=[])
        if state['identity'] != identity:
            raise ValueError('state belongs to different market or risk settings; choose a new state file')
        exchange = getattr(ccxt, exchange_id)({'enableRateLimit': True, 'trust_env': True, 'timeout': 20000, 'options': {'defaultType': 'swap'}})
        if demo:
            if exchange_id != 'bybit':
                raise ValueError('Demo mode only supports Bybit')
            from .demo import connect_demo
            exchange = connect_demo()
        exchange.load_markets()
        market = exchange.market(symbol)
        if not market.get('swap') or not market.get('linear') or market.get('settle') != 'USDT':
            raise ValueError('realtime paper mode requires a linear USDT swap')
        if timeframe not in exchange.timeframes:
            raise ValueError('unsupported timeframe')
        interval = exchange.parse_timeframe(timeframe) * 1000
        count = 0
        while not cycles or count < cycles:
            rows = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            now = exchange.milliseconds()
            candles = [Candle(*row) for row in rows if row[0] + interval <= now]
            analysis = analyze(candles, now, interval)
            ticker = exchange.fetch_ticker(symbol)
            quote_time = ticker.get('timestamp')
            now = exchange.milliseconds()
            analysis = analyze(candles, now, interval)
            if quote_time is None or not 0 <= now - quote_time <= 60_000:
                raise ValueError('quote missing timestamp or older than 60 seconds')
            def save(data):
                temporary = path.with_suffix(path.suffix + '.tmp')
                with temporary.open('w') as output:
                    json.dump(data, output, indent=2, allow_nan=False)
                    output.flush()
                    os.fsync(output.fileno())
                temporary.replace(path)
            if demo:
                from .demo import demo_action
                quote = float(ticker['last'])
                if not math.isfinite(quote) or quote <= 0:
                    raise ValueError('invalid quote')
                events = demo_action(exchange, symbol, analysis, quote, config, state, save)
            else:
                events = step(state, analysis, float(ticker['last']), now, config)
                save(state)
            print(json.dumps(dict(analysis=analysis, paper_equity=None if demo else state['equity'], events=events)), flush=True)
            count += 1
            if not cycles or count < cycles:
                time.sleep(poll_seconds)
    finally:
        os.close(fd)
        lock.unlink(missing_ok=True)
        if exchange is not None:
            close = getattr(exchange, 'close', None)
            if close:
                close()

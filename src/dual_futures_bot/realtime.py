"""Polling analysis with paper or explicitly selected Bybit Demo execution."""
import json
import math
import os
import re
import time
from dataclasses import asdict
from pathlib import Path

from .indicators import atr, ema
from .models import Candle
from .simulator import RiskConfig, size_for_risk
from .strategy import ema_cross_signals
from .policy import TREND_POLICY, entry_block, exit_reason, trend_decisions


def append_audit(path, record):
    with path.with_suffix('.jsonl').open('a') as audit:
        audit.write(json.dumps(record, allow_nan=False) + '\n')


class QuoteUnavailable(ValueError):
    """Public quote rejected before any order processing; safe to poll again."""
    def __init__(self, reason, source, timestamp=None, now=None):
        self.details = {'reason': reason, 'source': source}
        if type(timestamp) in (int, float) and math.isfinite(timestamp) and now is not None:
            self.details.update(timestamp_ms=timestamp, local_time_ms=now, age_seconds=round((now-timestamp)/1000, 3))
        super().__init__(json.dumps(self.details))


def fetch_quote(exchange, symbol, require_book=False):
    """Use timestamped quotes, allowing at most 2 seconds of clock skew ahead."""
    ticker = {'timestamp': None} if require_book else exchange.fetch_ticker(symbol)
    if ticker.get('timestamp') is None:
        source = 'orderbook_midpoint'
        book = exchange.fetch_order_book(symbol, limit=1)
        if not book.get('bids') or not book.get('asks'):
            raise QuoteUnavailable('empty_orderbook', source)
        try:
            bid, ask = float(book['bids'][0][0]), float(book['asks'][0][0])
        except (ValueError, TypeError, IndexError):
            raise QuoteUnavailable('invalid_bid_ask', source) from None
        if not all(math.isfinite(p) and p > 0 for p in (bid, ask)) or bid > ask:
            raise QuoteUnavailable('invalid_bid_ask', source)
        ticker = {'timestamp': book.get('timestamp'), 'last': (bid + ask) / 2, 'source': source, 'spread_fraction': (ask-bid)/((bid+ask)/2)}
    else:
        ticker = dict(ticker, source='ticker_last')
    now = exchange.milliseconds()
    timestamp = ticker.get('timestamp')
    if type(timestamp) not in (int, float) or not math.isfinite(timestamp):
        raise QuoteUnavailable('missing_or_invalid_timestamp', ticker['source'])
    age = now - timestamp
    if age < -2000 or age > 60_000:
        raise QuoteUnavailable('future_timestamp' if age < -2000 else 'stale_quote', ticker['source'], timestamp, now)
    try:
        price = float(ticker['last'])
    except (KeyError, TypeError, ValueError):
        raise QuoteUnavailable('invalid_price', ticker['source']) from None
    if not math.isfinite(price) or price <= 0:
        raise QuoteUnavailable('invalid_price', ticker['source'])
    ticker['age_seconds'] = round(age / 1000, 3)
    return ticker


def analyze(candles, now_ms, interval_ms, strategy='ema-cross', config=RiskConfig()):
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
    result = {'candle_timestamp': candles[-1].timestamp, 'ema20': fast, 'ema50': slow,
            'trend': 'up' if fast > slow else 'down' if fast < slow else 'flat',
            'atr14': volatility, 'atr_fraction': ratio,
            'signal': signal.side if signal and 0 < ratio <= .05 else None,
            'filter': 'volatility_block' if ratio > .05 else 'ok'}
    result.update(strategy='ema-cross', interval_ms=interval_ms,
                  signal_reason='ema_cross_confirmed' if result['signal'] else 'awaiting_ema_cross')
    if strategy == 'trend-pullback':
        result.update(trend_decisions(candles, 2*(config.fee_rate+config.slippage_rate))[-1])
    elif strategy != 'ema-cross':
        raise ValueError('Unknown strategy')
    return result


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
        policy_exit = exit_reason(p, analysis, price)
        if hit or policy_exit or (signal and signal != p['side']):
            exit_price = price * (1 - config.slippage_rate if p['side'] == 'long' else 1 + config.slippage_rate)
            gross = (exit_price - p['entry']) * p['quantity'] * (1 if p['side'] == 'long' else -1)
            exit_fee = exit_price * p['quantity'] * config.fee_rate
            net = gross - p['entry_fee'] - exit_fee
            state['equity'] += gross - exit_fee  # entry fee was debited on entry
            events.append(dict(type='exit', side=p['side'], price=exit_price, quantity=p['quantity'],
                               pnl=net, reason='stop' if hit else policy_exit or 'reverse_signal', timestamp=now_ms))
            state['position'] = None
            state['last_exit_candle'] = analysis['candle_timestamp']
    daily_base = min(state['day_equity'], config.initial_equity) if analysis.get('strategy') == TREND_POLICY else state['day_equity']
    if state['equity'] <= state['day_equity'] - daily_base*config.max_daily_loss_fraction:
        state['halted'] = True
    reason = ('daily_loss_limit' if state['halted'] else entry_block(state, analysis))
    state['decision'] = dict(action='hold' if state['position'] else 'wait',
                             reason=reason or ('position_open' if state['position'] else analysis.get('signal_reason', 'no_signal')))
    if state['position'] is None and signal and not reason and state['equity'] > 0:
        entry = price * (1 + config.slippage_rate if signal == 'long' else 1 - config.slippage_rate)
        stop = entry + analysis['atr14'] * config.stop_atr_multiple * (-1 if signal == 'long' else 1)
        if stop > 0:
            sizing_stop = stop
            if analysis.get('strategy') == TREND_POLICY:
                costs = entry * 2*(config.fee_rate+config.slippage_rate)
                sizing_stop = entry - (abs(entry-stop)+costs) if signal == 'long' else entry + abs(entry-stop)+costs
            sizing_equity = min(state['equity'], config.initial_equity) if analysis.get('strategy') == TREND_POLICY else state['equity']
            qty = size_for_risk(sizing_equity, entry, sizing_stop, config.risk_fraction, config.max_notional_fraction)
            fee = entry * qty * config.fee_rate
            state['equity'] -= fee
            state['position'] = dict(side=signal, entry=entry, stop=stop, quantity=qty, entry_fee=fee)
            state['position'].update(entry_candle=analysis['candle_timestamp'])
            if analysis.get('strategy') == TREND_POLICY:
                state['position']['target'] = entry + analysis['atr14']*analysis['take_profit_atr_multiple']*(1 if signal == 'long' else -1)
            state['decision'] = dict(action='enter', reason=analysis.get('signal_reason', 'signal'))
            events.append(dict(type='entry', timestamp=now_ms, **state['position']))
    if state['position'] and new_signal and analysis.get('strategy') != TREND_POLICY:
        p = state['position']
        candidate = price + analysis['atr14'] * config.stop_atr_multiple * (-1 if p['side'] == 'long' else 1)
        p['stop'] = max(p['stop'], candidate) if p['side'] == 'long' else min(p['stop'], candidate)
    state['last_candle'] = max(state.get('last_candle', -1), analysis['candle_timestamp'])
    state['updated_at'] = now_ms
    state['analysis'] = analysis
    state['last_price'] = price
    state['events'].extend(events)
    return events


def run(exchange_id, symbol, timeframe, limit, equity, state_path, poll_seconds=10, cycles=0, demo=False, ai_report=None, strategy='ema-cross', risk_config=None):
    import ccxt
    config = risk_config or RiskConfig(initial_equity=equity)
    config.validate()
    if not math.isfinite(poll_seconds) or poll_seconds < 1 or cycles < 0:
        raise ValueError('poll seconds must be >= 1 and cycles >= 0')
    path = Path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(path.suffix + '.lock')
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    exchange = None
    notifier = None
    market_fd = None
    market_lock = None
    try:
        if demo:
            name = re.sub(r'[^A-Za-z0-9_-]', '_', exchange_id+'_'+symbol)
            market_lock = Path('reports')/('.execution_'+name+'.lock')
            market_lock.parent.mkdir(parents=True, exist_ok=True)
            market_fd = os.open(market_lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.write(market_fd, str(os.getpid()).encode())
        from .telegram import Telegram
        notifier = Telegram.from_env()
        notifier.send('Запуск / Starting', {'exchange': exchange_id, 'symbol': symbol, 'timeframe': timeframe,
                                          'mode': 'bybit_demo' if demo else 'realtime_paper'})
        identity = dict(exchange=exchange_id, symbol=symbol, timeframe=timeframe, mode='bybit_demo' if demo else 'realtime_paper', risk=asdict(config))
        if strategy != 'ema-cross':
            identity['strategy'] = TREND_POLICY
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
        print(json.dumps(dict(role='trader', mode=identity['mode'], strategy=strategy, state=str(path))), flush=True)
        count = 0
        quote_warning_at = None
        while not cycles or count < cycles:
            rows = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            now = exchange.milliseconds()
            candles = [Candle(*row) for row in rows if row[0] + interval <= now]
            analysis = analyze(candles, now, interval, strategy, config)
            try:
                ticker = fetch_quote(exchange, symbol, require_book=True) if strategy == 'trend-pullback' else fetch_quote(exchange, symbol)
            except QuoteUnavailable as exc:
                # Do not advance signals/state, execute orders or simulate stop fills.
                warning = dict(status='quote_unavailable', symbol=symbol, **exc.details,
                               events=[], note='Cycle skipped; existing positions may remain open. Paper stops cannot run without a valid price.')
                warning.update(role='trader', timestamp=exchange.milliseconds())
                append_audit(path, warning)
                print(json.dumps(warning), flush=True)
                clock = time.monotonic()
                if quote_warning_at is None or clock - quote_warning_at >= 300:
                    notifier.send('Нет свежей цены / Quote unavailable', warning)
                    quote_warning_at = clock
                count += 1  # --cycles counts polling attempts, including rejected quotes.
                if not cycles or count < cycles:
                    time.sleep(poll_seconds)
                continue
            if quote_warning_at is not None:
                recovery = dict(status='quote_recovered', symbol=symbol, source=ticker['source'])
                print(json.dumps(recovery), flush=True)
                notifier.send('Цена восстановлена / Quote recovered', recovery)
                quote_warning_at = None
            now = exchange.milliseconds()
            analysis = analyze(candles, now, interval, strategy, config)
            analysis['quote_source'] = ticker['source']
            analysis['quote_age_seconds'] = ticker['age_seconds']
            analysis['quote_timestamp_ms'] = ticker['timestamp']
            if strategy == 'trend-pullback':
                spread = ticker.get('spread_fraction')
                analysis['spread_fraction'] = spread
                if abs(float(ticker['last'])-candles[-1].close) > analysis['atr14']:
                    analysis.update(signal=None, signal_reason='entry_price_moved')
                elif spread is None or spread > .0008:
                    analysis.update(signal=None, signal_reason='spread_unavailable' if spread is None else 'spread_too_wide')
                elif analysis['target_distance_fraction'] < 2*(2*(config.fee_rate+config.slippage_rate)+spread):
                    analysis.update(signal=None, signal_reason='target_too_small_for_costs')
            if ai_report:
                from .ai_advisor import load_report
                analysis['ai_advisor'] = load_report(ai_report, exchange_id, symbol, timeframe, now)
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
            record = dict(role='trader', timestamp=now, mode=identity['mode'], symbol=symbol,
                          price=float(ticker['last']), analysis=analysis, decision=state.get('decision'),
                          equity=state.get('demo_equity') if demo else state['equity'],
                          positions=state.get('demo_positions') if demo else state.get('position'), events=events)
            append_audit(path, record)
            print(json.dumps(record), flush=True)
            try:
                notifier.update(symbol, identity['mode'], analysis, float(ticker['last']), state, events)
            except Exception:
                # Observability must not interrupt execution or expose token-bearing errors.
                print('Telegram notification formatting failed; check local state.', flush=True)
            count += 1
            if not cycles or count < cycles:
                time.sleep(poll_seconds)
    except KeyboardInterrupt:
        if notifier:
            notifier.send('Остановлен / Stopped', {'note': 'Polling stopped. Positions/orders are NOT closed.'})
        raise
    except Exception as exc:
        if notifier:
            notifier.send('Ошибка / Error', {'error_type': type(exc).__name__,
                                          'note': 'Bot stopped. Check local logs and Bybit positions/orders. No automatic order retry.'})
        raise
    else:
        if notifier:
            notifier.send('Завершён / Finished', {'note': 'Requested cycles completed. Positions/orders are NOT closed.'})
    finally:
        if notifier:
            notifier.close()
        if market_fd is not None:
            os.close(market_fd)
            market_lock.unlink(missing_ok=True)
        os.close(fd)
        lock.unlink(missing_ok=True)
        if exchange is not None:
            close = getattr(exchange, 'close', None)
            if close:
                close()

"""Bybit Demo only. Ambiguous submissions require manual reconciliation."""
import math
import os
import uuid
from urllib.parse import urlsplit

from .simulator import size_for_risk


def connect_demo():
    import ccxt
    key, secret = os.environ.get('BYBIT_DEMO_API_KEY'), os.environ.get('BYBIT_DEMO_API_SECRET')
    if not key or not secret:
        raise ValueError('Set BYBIT_DEMO_API_KEY and BYBIT_DEMO_API_SECRET securely; Demo Trading keys only')
    exchange = ccxt.bybit({'apiKey': key, 'secret': secret, 'enableRateLimit': True,
                           'trust_env': True, 'timeout': 20000,
                           'options': {'defaultType': 'swap', 'maxRetriesOnFailure': 0}})
    exchange.enable_demo_trading(True)
    assert_demo(exchange)
    return exchange


def assert_demo(exchange):
    urls = exchange.urls['api']
    if not exchange.options.get('enableDemoTrading') or any(urlsplit(url.replace('{hostname}', str(exchange.hostname))).hostname != 'api-demo.bybit.com' for url in urls.values()):
        raise ValueError('Refusing orders outside api-demo.bybit.com')


def demo_action(exchange, symbol, analysis, price, config, state, save):
    """Reconcile the account before deciding; journal before any order submission."""
    assert_demo(exchange)
    if state.get('pending_order'):
        raise ValueError('Unresolved demo order: reconcile order ID in Bybit before clearing pending_order')
    positions = exchange.fetch_positions([symbol])
    active = [p for p in positions if float(p.get('contracts') or 0) > 0]
    if len(active) > 1 or any(p.get('hedged') for p in active):
        raise ValueError('Use a dedicated one-way Demo account; hedge positions are unsupported')
    if exchange.fetch_open_orders(symbol):
        raise ValueError('Open orders exist; reconcile in Bybit before continuing')
    balance = exchange.fetch_balance({'type': 'swap'})
    total = float(balance['USDT']['total'])
    if not math.isfinite(total) or total <= 0:
        raise ValueError('Demo account requires positive USDT equity')
    state['demo_equity'] = total
    state['demo_positions'] = [{k: p.get(k) for k in ('side', 'contracts', 'entryPrice', 'markPrice', 'unrealizedPnl', 'stopLossPrice', 'leverage')} for p in active]
    day = exchange.milliseconds() // 86_400_000
    if state.get('demo_day') != day:
        state.update(demo_day=day, demo_day_equity=total, demo_halted=False)
    if total <= state['demo_day_equity'] * (1 - config.max_daily_loss_fraction):
        state['demo_halted'] = True
    new = analysis['candle_timestamp'] > state.get('last_candle', -1)
    signal = analysis['signal'] if new else None
    state['last_candle'] = max(state.get('last_candle', -1), analysis['candle_timestamp'])
    state['analysis'] = analysis
    save(state)
    if not signal:
        return []
    params = {'positionIdx': 0}
    if active:
        position = active[0]
        if signal == position['side']:
            return []
        side = 'sell' if position['side'] == 'long' else 'buy'
        amount = position['contracts']
        params['reduceOnly'] = True
    else:
        if state['demo_halted'] or analysis['atr14'] <= 0:
            return []
        market = exchange.market(symbol)
        stop = price + analysis['atr14'] * config.stop_atr_multiple * (-1 if signal == 'long' else 1)
        if stop <= 0:
            raise ValueError('invalid stop')
        qty = size_for_risk(min(total, config.initial_equity), price, stop, config.risk_fraction, config.max_notional_fraction)
        amount = float(exchange.amount_to_precision(symbol, qty / float(market['contractSize'])))
        minimum = market.get('limits', {}).get('amount', {}).get('min') or 0
        min_cost = market.get('limits', {}).get('cost', {}).get('min') or 0
        if amount <= 0 or amount < minimum or amount * float(market['contractSize']) * price < min_cost:
            raise ValueError('risk-sized order below exchange minimum; risk is not increased automatically')
        side = 'buy' if signal == 'long' else 'sell'
        params['stopLoss'] = {'triggerPrice': float(exchange.price_to_precision(symbol, stop))}
    params['orderLinkId'] = 'tb-' + uuid.uuid4().hex[:28]
    state['pending_order'] = dict(client_id=params['orderLinkId'], side=side, amount=amount)
    save(state)  # Crash/timeout after this point must never cause an automatic duplicate.
    order = exchange.create_order(symbol, 'market', side, amount, None, params)
    # Wait until exchange confirms a terminal status. Partial/open/unknown orders halt safely.
    status = exchange.fetch_order(order['id'], symbol, {'acknowledged': True})
    if status.get('status') not in ('closed', 'canceled', 'rejected', 'expired'):
        raise ValueError('Demo order not terminal; reconcile pending_order in Bybit')
    if not params.get('reduceOnly') and (status.get('status') == 'closed' or float(status.get('filled') or 0) > 0):
        confirmed = [p for p in exchange.fetch_positions([symbol]) if float(p.get('contracts') or 0) > 0]
        if len(confirmed) != 1 or not confirmed[0].get('stopLossPrice'):
            raise ValueError('Demo position stop is unconfirmed; inspect position and pending_order in Bybit')
    event = dict(type='demo_order', id=order['id'], client_id=params['orderLinkId'], status=status['status'],
                 side=side, amount=amount, filled=status.get('filled'), average=status.get('average'),
                 cost=status.get('cost'), fee=status.get('fee'), reduce_only=params.get('reduceOnly', False))
    state['events'].append(event)
    state['pending_order'] = None
    save(state)
    return [event]

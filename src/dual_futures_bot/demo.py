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


def wait_terminal_order(exchange, symbol, order_id):
    import ccxt
    import time
    for attempt in range(10):
        try:
            result = exchange.fetch_order(order_id, symbol, {'acknowledged': True})
        except ccxt.OrderNotFound:
            result = {}
        if result.get('status') in ('closed', 'canceled', 'rejected', 'expired'):
            return result
        if attempt < 9:
            time.sleep(1)
    raise ValueError('Demo order not terminal; reconcile pending_order in Bybit')


def wait_position_presence(exchange, symbol, want_open):
    import time
    for attempt in range(10):
        active = [p for p in exchange.fetch_positions([symbol]) if float(p.get('contracts') or 0) > 0]
        if bool(active) == want_open:
            return active
        if attempt < 9:
            time.sleep(1)
    raise ValueError('Demo position reconciliation timed out; inspect pending_order and exchange')


def only_position_protection(orders, active, state):
    """Allow known position-bound reduce-only SL/TP, never arbitrary working orders."""
    if not orders:
        return True
    if len(active) != 1 or not (state.get('demo_trade') or state.get('demo_positions')):
        return False
    side = 'sell' if active[0]['side'] == 'long' else 'buy'
    kinds = {'StopLoss', 'TakeProfit', 'PartialStopLoss', 'PartialTakeProfit'}
    return all(o.get('reduceOnly') is True and o.get('side') == side and
               o.get('info', {}).get('stopOrderType') in kinds for o in orders)


def demo_action(exchange, symbol, analysis, price, config, state, save):
    from .policy import TREND_POLICY, entry_block, exit_reason
    assert_demo(exchange)
    if state.get('pending_order'):
        raise ValueError('Unresolved demo order: reconcile order ID in Bybit before clearing pending_order')
    trend = analysis.get('strategy') == TREND_POLICY
    active = [p for p in exchange.fetch_positions([symbol]) if float(p.get('contracts') or 0) > 0]
    if len(active) > 1 or any(p.get('hedged') for p in active):
        raise ValueError('Use a dedicated one-way Demo account; hedge positions are unsupported')
    if not only_position_protection(exchange.fetch_open_orders(symbol), active, state):
        raise ValueError('Unrecognized open orders exist; reconcile in Bybit before continuing')
    if trend and active and not state.get('demo_trade'):
        raise ValueError('Unmanaged position: new strategy requires flat account or its original matching state')
    wallet = exchange.fetch_balance({'type': 'swap'})
    balance = wallet['USDT']
    total = float(balance['total'])
    basis = 'wallet_plus_symbol_unrealized'
    total += sum(float(p.get('unrealizedPnl') or 0) for p in active)
    # CCXT total is Bybit walletBalance, not necessarily mark-to-market equity.
    for account in wallet.get('info', {}).get('result', {}).get('list', []):
        for coin in account.get('coin', []):
            if coin.get('coin') == 'USDT' and coin.get('equity') not in (None, ''):
                total = float(coin['equity'])
                basis = 'bybit_usdt_equity'
    state['demo_equity_basis'] = basis
    if not math.isfinite(total) or total <= 0:
        raise ValueError('Demo account requires positive USDT equity')
    events = []
    if state.get('demo_positions') and not active:
        state['last_exit_candle'] = analysis['candle_timestamp']
        state['demo_trade'] = None
        events.append(dict(type='position_closed_observed', timestamp=exchange.milliseconds(),
                           note='Inspect exchange fills for realized PnL/fees and exit reason'))
    state['demo_equity'] = total
    state['demo_positions'] = [{k: p.get(k) for k in ('side', 'contracts', 'entryPrice', 'markPrice', 'unrealizedPnl', 'stopLossPrice', 'takeProfitPrice', 'leverage')} for p in active]
    day = exchange.milliseconds() // 86_400_000
    if state.get('demo_day') != day:
        state.update(demo_day=day, demo_day_equity=total, demo_halted=False)
    daily_base = min(state['demo_day_equity'], config.initial_equity) if trend else state['demo_day_equity']
    state['demo_day_loss_budget'] = daily_base * config.max_daily_loss_fraction
    if total <= state['demo_day_equity'] - state['demo_day_loss_budget']:
        state['demo_halted'] = True
    new = analysis['candle_timestamp'] > state.get('last_candle', -1)
    signal = analysis['signal'] if new else None
    state['last_candle'] = max(state.get('last_candle', -1), analysis['candle_timestamp'])
    state['analysis'] = analysis
    state['events'].extend(events)

    def wait(reason, **details):
        state['decision'] = dict(action='hold' if active else 'wait', reason=reason, **details)
        save(state)
        return events

    params = {'positionIdx': 0}
    metadata = None
    policy_exit = exit_reason(dict(state.get('demo_trade') or {}, side=active[0]['side']), analysis, price) if active else None
    if active:
        position = active[0]
        if not policy_exit and (not signal or signal == position['side']):
            return wait('position_open')
        side = 'sell' if position['side'] == 'long' else 'buy'
        amount = position['contracts']
        params['reduceOnly'] = True
        reason = policy_exit or 'reverse_signal'
    else:
        if state['demo_halted']:
            return wait('daily_loss_limit')
        block = entry_block(state, analysis)
        if block:
            return wait(block)
        if not new:
            return wait('awaiting_next_closed_candle')
        if not signal:
            return wait(analysis.get('signal_reason', 'no_signal'))
        if analysis['atr14'] <= 0:
            return wait('invalid_atr')
        stamp = analysis.get('quote_timestamp_ms')
        if stamp is not None and not -2000 <= exchange.milliseconds()-stamp <= 60000:
            return wait('quote_expired_before_order')
        market = exchange.market(symbol)
        stop = price + analysis['atr14'] * config.stop_atr_multiple * (-1 if signal == 'long' else 1)
        if stop <= 0:
            return wait('invalid_stop')
        stop = float(exchange.price_to_precision(symbol, stop))
        if not math.isfinite(stop) or stop <= 0 or (signal == 'long' and stop >= price) or (signal == 'short' and stop <= price):
            return wait('invalid_rounded_stop')
        sizing_stop = stop
        if trend:
            cost_distance = price * 2*(config.fee_rate+config.slippage_rate)
            sizing_stop = price - abs(price-stop)-cost_distance if signal == 'long' else price + abs(price-stop)+cost_distance
        qty = size_for_risk(min(total, config.initial_equity), price, sizing_stop, config.risk_fraction, config.max_notional_fraction)
        contract_size = float(market['contractSize'])
        if not math.isfinite(contract_size) or contract_size <= 0:
            return wait('invalid_contract_size')
        amount = float(exchange.amount_to_precision(symbol, qty / contract_size))
        if not math.isfinite(amount):
            return wait('invalid_rounded_amount')
        minimum = market.get('limits', {}).get('amount', {}).get('min') or 0
        min_cost = market.get('limits', {}).get('cost', {}).get('min') or 0
        notional = amount * contract_size * price
        if amount <= 0 or amount < minimum or notional < min_cost:
            return wait('below_exchange_minimum', amount=amount, notional=notional, minimum_amount=minimum, minimum_notional=min_cost)
        maximum = market.get('limits', {}).get('amount', {}).get('max')
        if maximum is not None and amount > maximum:
            return wait('above_exchange_maximum')
        if amount * contract_size > qty * (1+1e-9):
            return wait('rounded_size_exceeds_risk')
        if trend:
            free = balance.get('free')
            if free is None or not math.isfinite(float(free)) or notional > float(free):
                return wait('insufficient_free_balance_without_leverage')
        side = 'buy' if signal == 'long' else 'sell'
        params['stopLoss'] = {'triggerPrice': stop}
        if trend:
            target = price + analysis['atr14']*analysis['take_profit_atr_multiple']*(1 if signal == 'long' else -1)
            target = float(exchange.price_to_precision(symbol, target))
            if not math.isfinite(target) or target <= 0 or (signal == 'long' and target <= price) or (signal == 'short' and target >= price):
                return wait('invalid_rounded_target')
            params['takeProfit'] = {'triggerPrice': target}
            metadata = dict(side=signal, entry_candle=analysis['candle_timestamp'], target=params['takeProfit']['triggerPrice'])
        reason = analysis.get('signal_reason', 'signal')
    params['orderLinkId'] = 'tb-' + uuid.uuid4().hex[:28]
    state['decision'] = dict(action='exit' if params.get('reduceOnly') else 'enter', reason=reason, amount=amount)
    state['pending_order'] = dict(client_id=params['orderLinkId'], side=side, amount=amount, metadata=metadata)
    save(state)
    order = exchange.create_order(symbol, 'market', side, amount, None, params)
    status = wait_terminal_order(exchange, symbol, order['id'])
    if not params.get('reduceOnly') and (status.get('status') == 'closed' or float(status.get('filled') or 0) > 0):
        confirmed = wait_position_presence(exchange, symbol, True)
        if len(confirmed) != 1 or confirmed[0].get('side') != signal or float(confirmed[0]['contracts']) > amount*(1+1e-9):
            raise ValueError('Demo position does not match submitted order; reconcile pending_order in Bybit')
        if not confirmed[0].get('stopLossPrice'):
            raise ValueError('Demo position stop is unconfirmed; inspect position and pending_order in Bybit')
        if trend and not confirmed[0].get('takeProfitPrice'):
            raise ValueError('Demo position target is unconfirmed; inspect position and pending_order in Bybit')
        state['demo_trade'] = metadata
        state['demo_positions'] = [{k: p.get(k) for k in ('side', 'contracts', 'entryPrice', 'markPrice', 'unrealizedPnl', 'stopLossPrice', 'takeProfitPrice', 'leverage')} for p in confirmed]
    if params.get('reduceOnly') and status.get('status') == 'closed':
        wait_position_presence(exchange, symbol, False)
        state['demo_trade'] = None
        state['demo_positions'] = []
        state['last_exit_candle'] = analysis['candle_timestamp']
    event = dict(type='demo_order', id=order['id'], client_id=params['orderLinkId'], status=status['status'],
                 side=side, amount=amount, filled=status.get('filled'), average=status.get('average'),
                 cost=status.get('cost'), fee=status.get('fee'), reduce_only=params.get('reduceOnly', False), reason=reason)
    state['events'].append(event)
    events.append(event)
    state['pending_order'] = None
    save(state)
    return events

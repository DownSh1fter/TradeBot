"""One Bybit Demo market entry and immediate reduce-only exit; no strategy signals."""
import argparse
import json
import math
import os
import time
import uuid
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

from .demo import assert_demo, connect_demo
from .realtime import fetch_quote


def positions(exchange, symbol):
    return [p for p in exchange.fetch_positions([symbol]) if float(p.get('contracts') or 0) > 0]


def wait_order(exchange, symbol, order_id):
    import ccxt
    for attempt in range(10):
        try:
            order = exchange.fetch_order(order_id, symbol, {'acknowledged': True})
        except ccxt.OrderNotFound:
            order = {}  # Read-only polling while exchange history catches up.
        if order.get('status') in ('closed', 'canceled', 'rejected', 'expired'):
            return order
        if attempt < 9:
            time.sleep(1)
    raise ValueError('Order status still ambiguous. Reconcile in Bybit; do not resubmit.')


def minimum_amount(exchange, market, symbol, price, max_notional, balance):
    import ccxt
    if exchange.precisionMode != ccxt.TICK_SIZE:
        raise ValueError('Unsupported amount precision mode')
    step = Decimal(str(market['precision']['amount']))
    size = Decimal(str(market['contractSize']))
    if not step.is_finite() or step <= 0 or not size.is_finite() or size <= 0:
        raise ValueError('Invalid contract size or amount precision')
    limits = market.get('limits') or {}
    min_qty = Decimal(str((limits.get('amount') or {}).get('min') or step))
    min_cost = Decimal(str((limits.get('cost') or {}).get('min') or 0))
    # Small buffer over the minimum cost, followed by rounding UP to one lot.
    raw = max(min_qty, min_cost * Decimal('1.01') / (Decimal(str(price)) * size))
    amount = float((raw / step).to_integral_value(rounding=ROUND_CEILING) * step)
    amount = float(exchange.amount_to_precision(symbol, amount))
    notional = amount * float(size) * price
    cap = min(max_notional, balance * .25)
    if amount <= 0 or not math.isfinite(notional) or notional > cap:
        raise ValueError(f'Minimum order reference notional {notional:.2f} exceeds cap {cap:.2f} USDT; no order sent')
    max_qty = (limits.get('amount') or {}).get('max')
    if max_qty is not None and amount > max_qty:
        raise ValueError('Minimum order exceeds maximum amount')
    return amount, notional


def roundtrip(exchange, symbol, max_notional, journal, save):
    assert_demo(exchange)
    exchange.load_markets()
    market = exchange.market(symbol)
    if not market.get('swap') or not market.get('linear') or market.get('settle') != 'USDT':
        raise ValueError('Requires a linear USDT swap')
    if positions(exchange, symbol) or exchange.fetch_open_orders(symbol):
        raise ValueError('Existing position or open orders: stop the strategy and reconcile first')
    balance = float(exchange.fetch_balance({'type': 'swap'})['USDT']['free'])
    if not math.isfinite(balance) or balance <= 0:
        raise ValueError('Positive free Demo USDT balance required')
    quote = fetch_quote(exchange, symbol)
    amount, notional = minimum_amount(exchange, market, symbol, quote['last'], max_notional, balance)
    journal.update(symbol=symbol, mode='bybit_demo_smoke', reference_notional=notional, amount=amount)
    print(f'DEMO ONLY: market buy {amount} contracts, reference notional {notional:.2f} USDT; then reduce-only sell.', flush=True)

    def submit(label, side, qty, params):
        assert_demo(exchange)
        client_id = 'tb-smoke-' + uuid.uuid4().hex[:24]
        journal.update(stage=label + '_pending', client_id=client_id)
        save(journal)  # Do not automatically retry an uncertain submission.
        order = exchange.create_order(symbol, 'market', side, qty, None, dict(params, orderLinkId=client_id, positionIdx=0))
        journal[label + '_order_id'] = order['id']
        save(journal)
        result = wait_order(exchange, symbol, order['id'])
        journal[label] = {k: result.get(k) for k in ('id', 'status', 'filled', 'average', 'fee')}
        journal['stage'] = label + '_confirmed'
        save(journal)
        print(json.dumps({label: journal[label]}), flush=True)
        return result

    stop = float(exchange.price_to_precision(symbol, quote['last'] * .98))
    submit('entry', 'buy', amount, {'stopLoss': {'triggerPrice': stop}})
    active = []
    for attempt in range(10):
        active = positions(exchange, symbol)
        if active:
            break
        # A terminal entry may have filled and immediately stopped out.
        if attempt < 9:
            time.sleep(1)
    if active:
        if len(active) != 1 or active[0].get('side') != 'long' or active[0].get('hedged'):
            raise ValueError('Unexpected Demo position; inspect manually')
        qty = float(active[0]['contracts'])
        if qty > amount * (1 + 1e-9):
            raise ValueError('Position exceeds test size; inspect manually')
        submit('exit', 'sell', qty, {'reduceOnly': True})
    else:
        raise ValueError('Entry position not observed; inspect fills/stop in Bybit. No second entry will be sent.')
    for attempt in range(10):
        if not positions(exchange, symbol) and not exchange.fetch_open_orders(symbol):
            journal['stage'] = 'completed_flat'
            save(journal)
            print('DEMO ROUNDTRIP OK: no position and no open orders for this symbol.', flush=True)
            return
        if attempt < 9:
            time.sleep(1)
    raise ValueError('Exit not confirmed flat. Inspect position and orders in Bybit.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--symbol', default='BTC/USDT:USDT')
    parser.add_argument('--max-notional', type=float, default=250, help='Reference entry cap in Demo USDT, maximum 250')
    parser.add_argument('--execute', action='store_true', help='Required: submit one Demo entry and exit')
    parser.add_argument('--journal', default='reports/demo-smoke.json')
    args = parser.parse_args()
    if not args.execute:
        parser.error('Use --execute to explicitly submit Demo orders. Stop the strategy first.')
    if not math.isfinite(args.max_notional) or not 0 < args.max_notional <= 250:
        parser.error('--max-notional must be in (0, 250]')
    path = Path(args.journal)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation blocks accidental reruns and concurrent tests using this journal.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as output:
        output.write('{"stage": "initializing"}')
    journal = {'stage': 'initializing'}

    def save(data):
        temporary = path.with_suffix(path.suffix + '.tmp')
        with temporary.open('w') as output:
            json.dump(data, output, indent=2, allow_nan=False)
            output.flush()
            os.fsync(output.fileno())
        temporary.replace(path)

    exchange = None
    try:
        exchange = connect_demo()
        roundtrip(exchange, args.symbol, args.max_notional, journal, save)
    except BaseException:
        print('Test interrupted or failed. Inspect Bybit Demo position/orders and journal before any retry.', flush=True)
        raise
    finally:
        if exchange is not None:
            close = getattr(exchange, 'close', None)
            if close:
                close()


if __name__ == '__main__':
    main()

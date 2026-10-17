import copy
import unittest
from unittest.mock import Mock, patch

import ccxt
from dual_futures_bot.demo_smoke import minimum_amount, roundtrip


class DemoSmokeTests(unittest.TestCase):
    def exchange(self):
        ex = Mock()
        ex.options = {'enableDemoTrading': True}
        ex.urls = {'api': {'private': 'https://api-demo.bybit.com'}}
        ex.precisionMode = ccxt.TICK_SIZE
        ex.market.return_value = {'swap': True, 'linear': True, 'settle': 'USDT', 'contractSize': 1,
                                 'precision': {'amount': .001}, 'limits': {'amount': {'min': .001}, 'cost': {'min': 100}}}
        ex.amount_to_precision.side_effect = lambda symbol, qty: str(qty)
        ex.price_to_precision.side_effect = lambda symbol, price: str(price)
        ex.fetch_ticker.return_value = {'timestamp': 1000, 'last': 80000}
        ex.milliseconds.return_value = 1000
        ex.fetch_open_orders.return_value = []
        ex.fetch_positions.side_effect = [[], [{'side': 'long', 'contracts': .002, 'hedged': False}], []]
        ex.fetch_balance.return_value = {'USDT': {'free': 10000}}
        ex.create_order.side_effect = [{'id': 'entry-id'}, {'id': 'exit-id'}]
        ex.fetch_order.return_value = {'status': 'closed', 'filled': .002, 'average': 80000}
        return ex

    def test_demo_entry_then_reduce_only_exit_and_flat(self):
        ex = self.exchange()
        journal, saves = {}, []
        roundtrip(ex, 'BTC', 250, journal, lambda s: saves.append(copy.deepcopy(s)))
        calls = ex.create_order.call_args_list
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].args[2], 'buy')
        self.assertIn('stopLoss', calls[0].args[-1])
        self.assertEqual(calls[1].args[2], 'sell')
        self.assertTrue(calls[1].args[-1]['reduceOnly'])
        self.assertEqual(journal['stage'], 'completed_flat')
        self.assertTrue(any(s['stage'] == 'entry_pending' for s in saves))
        self.assertTrue(any(s['stage'] == 'exit_pending' for s in saves))

    def test_existing_position_never_touched(self):
        ex = self.exchange()
        ex.fetch_positions.side_effect = [[{'contracts': 1}]]
        with self.assertRaises(ValueError): roundtrip(ex, 'BTC', 250, {}, lambda s: None)
        ex.create_order.assert_not_called()

    def test_small_cap_never_opens(self):
        ex = self.exchange()
        with self.assertRaises(ValueError): roundtrip(ex, 'BTC', 100, {}, lambda s: None)
        ex.create_order.assert_not_called()

    def test_ambiguous_entry_never_retried(self):
        ex = self.exchange()
        ex.create_order.side_effect = TimeoutError()
        journal = {}
        with self.assertRaises(TimeoutError): roundtrip(ex, 'BTC', 250, journal, lambda s: None)
        self.assertEqual(ex.create_order.call_count, 1)
        self.assertEqual(journal['stage'], 'entry_pending')

    def test_live_endpoint_never_called(self):
        ex = self.exchange()
        ex.urls['api']['private'] = 'https://api.bybit.com'
        with self.assertRaises(ValueError): roundtrip(ex, 'BTC', 250, {}, lambda s: None)
        ex.create_order.assert_not_called()

    def test_reference_size_rounded_up_and_capped(self):
        ex = self.exchange()
        qty, notional = minimum_amount(ex, ex.market(), 'BTC', 80000, 250, 10000)
        self.assertEqual(qty, .002)
        self.assertEqual(notional, 160)
        with self.assertRaises(ValueError): minimum_amount(ex, ex.market(), 'BTC', 80000, 250, 100)

    def test_delayed_read_status_does_not_resubmit(self):
        ex = self.exchange()
        ex.fetch_order.side_effect = [{'status': 'open'}, {'status': 'closed'}, {'status': 'closed'}]
        with patch('dual_futures_bot.demo_smoke.time.sleep'):
            roundtrip(ex, 'BTC', 250, {}, lambda s: None)
        self.assertEqual(ex.create_order.call_count, 2)

import copy
import unittest
from unittest.mock import Mock

from dual_futures_bot.demo import assert_demo, demo_action
from dual_futures_bot.models import Candle
from dual_futures_bot.realtime import analyze, step
from dual_futures_bot.simulator import RiskConfig


class RealtimeTests(unittest.TestCase):
    def setUp(self):
        self.config = RiskConfig()
        self.state = dict(equity=10000, position=None, events=[])
        self.analysis = dict(candle_timestamp=1000, signal='long', atr14=2)

    def test_entry_once_and_stop_on_same_signal(self):
        self.assertEqual(step(self.state, self.analysis, 100, 2000, self.config)[0]['type'], 'entry')
        self.assertEqual(step(self.state, self.analysis, 101, 3000, self.config), [])
        events = step(self.state, self.analysis, 90, 4000, self.config)
        self.assertEqual(events[0]['reason'], 'stop')
        self.assertIsNone(self.state['position'])
        self.assertLess(self.state['equity'], 10000)

    def test_restart_does_not_replay_signal(self):
        step(self.state, self.analysis, 100, 2000, self.config)
        import json
        restored = json.loads(json.dumps(self.state))
        self.assertEqual(step(restored, self.analysis, 100, 3000, self.config), [])

    def test_stale_and_missing_candles_rejected(self):
        candles = [Candle(i*60000,100,101,99,100,1) for i in range(65)]
        self.assertEqual(analyze(candles,65*60000,60000)['trend'], 'flat')
        with self.assertRaises(ValueError): analyze(candles,68*60000,60000)
        with self.assertRaises(ValueError): analyze(candles[:20]+candles[21:],65*60000,60000)

    def exchange(self):
        ex = Mock()
        ex.urls = {'api': {'public': 'https://api-demo.bybit.com', 'private': 'https://api-demo.bybit.com'}}
        ex.options = {'enableDemoTrading': True}
        ex.fetch_positions.side_effect = [[], [{'contracts': 1, 'side': 'long', 'stopLossPrice': 96}], []]
        ex.fetch_open_orders.return_value = []
        ex.fetch_balance.return_value = {'USDT': {'total': 10000}}
        ex.milliseconds.return_value = 1000
        ex.market.return_value = {'contractSize': 1, 'limits': {}}
        ex.amount_to_precision.side_effect = lambda symbol, amount: str(amount)
        ex.price_to_precision.side_effect = lambda symbol, price: str(price)
        ex.create_order.return_value = {'id': 'demo-123'}
        ex.fetch_order.return_value = {'status': 'closed'}
        return ex

    def test_demo_only_guard(self):
        ex = self.exchange()
        assert_demo(ex)
        ex.urls['api']['private'] = 'https://api.bybit.com'
        with self.assertRaises(ValueError): assert_demo(ex)
        ex.create_order.assert_not_called()

    def test_demo_attached_stop_and_journal(self):
        ex = self.exchange()
        saves = []
        events = demo_action(ex, 'BTC/USDT:USDT', self.analysis, 100, self.config, self.state, lambda s: saves.append(copy.deepcopy(s)))
        params = ex.create_order.call_args.args[-1]
        self.assertEqual(params['stopLoss']['triggerPrice'], 96)
        self.assertEqual(params['positionIdx'], 0)
        self.assertTrue(any(s.get('pending_order') for s in saves))
        self.assertIsNone(self.state['pending_order'])
        self.assertEqual(events[0]['status'], 'closed')
        demo_action(ex, 'BTC/USDT:USDT', self.analysis, 100, self.config, self.state, lambda s: None)
        self.assertEqual(ex.create_order.call_count, 1)

    def test_demo_timeout_never_retries_order(self):
        ex = self.exchange()
        ex.create_order.side_effect = TimeoutError()
        with self.assertRaises(TimeoutError):
            demo_action(ex, 'BTC/USDT:USDT', self.analysis, 100, self.config, self.state, lambda s: None)
        self.assertTrue(self.state['pending_order'])
        with self.assertRaises(ValueError):
            demo_action(ex, 'BTC/USDT:USDT', self.analysis, 100, self.config, self.state, lambda s: None)
        self.assertEqual(ex.create_order.call_count, 1)

    def test_demo_reverse_reduce_only(self):
        ex = self.exchange()
        ex.fetch_positions.side_effect = None
        ex.fetch_positions.return_value = [{'contracts': 2, 'side': 'short', 'hedged': False}]
        demo_action(ex, 'BTC/USDT:USDT', self.analysis, 100, self.config, self.state, lambda s: None)
        self.assertTrue(ex.create_order.call_args.args[-1]['reduceOnly'])
        self.assertEqual(ex.create_order.call_args.args[2], 'buy')


    def test_polling_loop_persists_and_releases_lock(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from dual_futures_bot.realtime import run
        ex = self.exchange()
        ex.market.return_value = {'swap': True, 'linear': True, 'settle': 'USDT'}
        ex.timeframes = {'1m': '1m'}
        ex.parse_timeframe.return_value = 60
        ex.milliseconds.return_value = 65 * 60000
        ex.fetch_ohlcv.return_value = [[i*60000,100,101,99,100,1] for i in range(65)]
        ex.fetch_ticker.return_value = {'timestamp': 65*60000, 'last': 100}
        with tempfile.TemporaryDirectory() as directory, patch('ccxt.bybit', return_value=ex):
            path = Path(directory) / 'state.json'
            run('bybit', 'BTC/USDT:USDT', '1m', 100, 10000, path, cycles=1)
            self.assertEqual(json.loads(path.read_text())['last_candle'], 64*60000)
            self.assertFalse(path.with_suffix('.json.lock').exists())
            run('bybit', 'BTC/USDT:USDT', '1m', 100, 10000, path, cycles=1)
            self.assertEqual(json.loads(path.read_text())['events'], [])

    def test_real_ccxt_demo_template_guard(self):
        import ccxt
        exchange = ccxt.bybit()
        exchange.enable_demo_trading(True)
        assert_demo(exchange)
        exchange.enable_demo_trading(False)
        with self.assertRaises(ValueError):
            assert_demo(exchange)

    def test_missing_demo_stop_keeps_pending_order(self):
        ex = self.exchange()
        ex.fetch_positions.side_effect = [[], [{'contracts': 1, 'side': 'long', 'stopLossPrice': None}]]
        with self.assertRaises(ValueError):
            demo_action(ex, 'BTC/USDT:USDT', self.analysis, 100, self.config, self.state, lambda s: None)
        self.assertTrue(self.state['pending_order'])

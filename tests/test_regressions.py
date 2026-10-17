import unittest
from unittest.mock import patch
from dual_futures_bot.models import Candle, Signal
from dual_futures_bot.simulator import RiskConfig, simulate, size_for_risk
from dual_futures_bot.market_data import fetch_candles


class RegressionTests(unittest.TestCase):
    def candles(self):
        return [Candle(i * 900_000, 100, 101, 99, 100, 1) for i in range(65)]

    def test_stop_on_entry_candle(self):
        candles = self.candles()
        candles[61] = Candle(61 * 900_000, 100, 101, 90, 100, 1)
        signals = [None] * len(candles)
        signals[60] = Signal('long', candles[60].timestamp, 100, 1)
        with patch('dual_futures_bot.simulator.ema_cross_signals', return_value=signals):
            trade = simulate(candles)['trades'][0]
        self.assertEqual(trade['entry_time'], trade['exit_time'])
        self.assertEqual(trade['reason'], 'trailing_stop')
        self.assertLess(trade['pnl'], 0)

    def test_reversal_precedes_intrabar_stop(self):
        candles = self.candles()
        candles[62] = Candle(62 * 900_000, 100, 101, 90, 100, 1)
        signals = [None] * len(candles)
        signals[60] = Signal('long', candles[60].timestamp, 100, 1)
        signals[61] = Signal('short', candles[61].timestamp, 100, 1)
        with patch('dual_futures_bot.simulator.ema_cross_signals', return_value=signals):
            trade = simulate(candles)['trades'][0]
        self.assertEqual(trade['reason'], 'reverse_signal')

    def test_nonfinite_config(self):
        for field in vars(RiskConfig()):
            for value in (float('nan'), float('inf')):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    RiskConfig(**{field: value}).validate()

    def test_invalid_notional_cap(self):
        with self.assertRaises(ValueError):
            size_for_risk(1000, 100, 95, .01, -1)

    def test_unsorted_candles(self):
        candles = self.candles()
        candles[2] = candles[1]
        with self.assertRaises(ValueError):
            simulate(candles)

    def test_fetch_filters_unclosed_candles_without_close_method(self):
        class Exchange:
            def __init__(self, config): pass
            def load_markets(self): pass
            def market(self, symbol): return {'swap': True}
            def milliseconds(self): return 120_000
            def parse_timeframe(self, timeframe): return 60
            def fetch_ohlcv(self, *args, **kwargs):
                return [[60_000,100,101,99,100,1], [120_000,100,101,99,100,1]]
        with patch('ccxt.binance', Exchange):
            candles = fetch_candles('binance', 'BTC/USDT:USDT', '1m', 60)
        self.assertEqual([c.timestamp for c in candles], [60_000])

    def test_cli_writes_report(self):
        import json
        import os
        import sys
        import tempfile
        from pathlib import Path
        from dual_futures_bot.__main__ import main
        old = os.getcwd()
        try:
            with tempfile.TemporaryDirectory() as directory:
                os.chdir(directory)
                with patch.object(sys, 'argv', ['bot', '--exchange', 'bybit']), patch('dual_futures_bot.__main__.fetch_candles', return_value=self.candles()):
                    main()
                report = json.loads(Path('reports/bybit_BTC_USDT_USDT_15m.json').read_text())
                self.assertEqual(report['mode'], 'paper_only')
                self.assertEqual(report['candles'], 65)
                self.assertEqual(report['final_equity'], 10000)
        finally:
            os.chdir(old)

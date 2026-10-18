import math
import unittest
from dual_futures_bot.benchmark import compare
from dual_futures_bot.models import Candle
from dual_futures_bot.policy import TREND_POLICY, trend_decisions
from dual_futures_bot.realtime import analyze, step
from dual_futures_bot.simulator import RiskConfig, simulate
from dual_futures_bot.strategy import ema_cross_signals


def series(count=500, direction=1):
    candles = []
    for i in range(count):
        price = 10000+direction*2*i+50*math.sin(i/7)
        j = max(0,i-1)
        opened = 10000+direction*2*j+50*math.sin(j/7)
        candles.append(Candle(i*900000,opened,max(opened,price)+10,min(opened,price)-10,price,100))
    return candles


class PolicyTests(unittest.TestCase):
    def test_entry_in_existing_trend_without_fresh_ema_cross(self):
        candles = series()
        self.assertTrue(all(s is None for s in ema_cross_signals(candles)))
        signals = [d for d in trend_decisions(candles) if d['signal']]
        self.assertGreater(len(signals), 0)
        self.assertTrue(all(d['signal']=='long' for d in signals))

    def test_short_trend_is_symmetric(self):
        signals = [d for d in trend_decisions(series(direction=-1)) if d['signal']]
        self.assertGreater(len(signals), 0)
        self.assertTrue(all(d['signal']=='short' for d in signals))

    def test_no_lookahead_prefix_invariance(self):
        candles = series()
        decisions = trend_decisions(candles)
        for length in (60,100,230,400):
            self.assertEqual(trend_decisions(candles[:length]), decisions[:length])

    def test_flat_and_expensive_markets_do_not_force_entry(self):
        flat = [Candle(i*900000,10000,10010,9990,10000,100) for i in range(200)]
        self.assertTrue(all(d['signal'] is None for d in trend_decisions(flat)))
        decisions = trend_decisions(series(), roundtrip_cost=.02)
        self.assertTrue(all(d['signal'] is None for d in decisions))
        self.assertIn('target_too_small_for_costs', {d['signal_reason'] for d in decisions})

    def analysis(self):
        return dict(strategy=TREND_POLICY, candle_timestamp=90000000, interval_ms=900000,
                    signal='long', signal_reason='trend_pullback_confirmed', atr14=2,
                    exit_long=False, exit_short=False, take_profit_atr_multiple=3,
                    max_hold_bars=24, cooldown_bars=3)

    def test_paper_entry_target_exit_and_cooldown(self):
        state = dict(equity=1000,position=None,events=[])
        config = RiskConfig(initial_equity=1000)
        a = self.analysis()
        self.assertEqual(step(state,a,100,100000000,config)[0]['type'],'entry')
        pos = state['position']
        risk_cost = abs(pos['entry']-pos['stop']) + pos['entry']*2*(config.fee_rate+config.slippage_rate)
        self.assertLessEqual(pos['quantity']*risk_cost, 1000*config.risk_fraction+1e-9)
        target = pos['target']
        a['candle_timestamp'] += 900000
        events = step(state,a,target+1,100900000,config)
        self.assertEqual(events[0]['reason'],'take_profit')
        self.assertIsNone(state['position'])
        self.assertEqual(state['decision']['reason'],'post_exit_cooldown')

    def test_holding_limit_can_exit_without_entry_signal(self):
        a = self.analysis()
        state = dict(equity=1000,position=None,events=[])
        step(state,a,100,100000000,RiskConfig())
        a = dict(a, signal=None, candle_timestamp=a['candle_timestamp']+24*900000)
        self.assertEqual(step(state,a,100,130000000,RiskConfig())[0]['reason'],'max_holding_time')

    def test_regime_exit_not_blocked_by_entry_cost_filter(self):
        a = self.analysis()
        state = dict(equity=1000,position=None,events=[])
        step(state,a,100,100000000,RiskConfig())
        a = dict(a,signal=None,exit_long=True,signal_reason='target_too_small_for_costs',candle_timestamp=a['candle_timestamp']+900000)
        self.assertEqual(step(state,a,100,100900000,RiskConfig())[0]['reason'],'trend_invalidated')

    def test_benchmark_runs_both_fixed_policies_on_identical_forward_split(self):
        rows = [list(vars(c).values()) for c in series()]
        result = compare(rows)
        self.assertEqual(set(result['policies']), {'ema-cross','trend-pullback'})
        self.assertEqual(result['test_starts_at'], rows[len(rows)*2//3][0])
        self.assertGreater(result['policies']['trend-pullback']['chronological_test']['trade_count'],0)

    def test_backtest_and_live_share_causal_entry_decision(self):
        candles = series()
        decisions = trend_decisions(candles)
        i = next(i for i,d in enumerate(decisions) if d['signal'])
        a = analyze(candles[:i+1], (i+1)*900000,900000,strategy='trend-pullback')
        self.assertEqual(a['signal'],decisions[i]['signal'])
        self.assertEqual(a['signal_reason'],decisions[i]['signal_reason'])
        r = simulate(candles,RiskConfig(initial_equity=1000),'trend-pullback')
        self.assertGreater(r['trade_count'],0)
        self.assertGreater(r['fees_paid'],0)
        self.assertIn('take_profit',{t['reason'] for t in r['trades']})

    def test_full_poll_loop_enters_and_closes_with_audit(self):
        import contextlib
        import io
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import Mock, patch
        from dual_futures_bot.realtime import run
        candles=series()
        index=next(i for i,d in enumerate(trend_decisions(candles)) if d['signal']=='long')
        sample=candles[:index+1]
        price=sample[-1].close
        a=analyze(sample,(index+1)*900000,900000,'trend-pullback')
        target=price*1.0002+a['atr14']*3+1
        ex=Mock()
        ex.market.return_value={'swap':True,'linear':True,'settle':'USDT'}
        ex.timeframes={'15m':'15m'}
        ex.parse_timeframe.return_value=900
        ex.milliseconds.return_value=(index+1)*900000
        ex.fetch_ohlcv.return_value=[list(vars(c).values()) for c in sample]
        ex.fetch_order_book.side_effect=[{'timestamp':ex.milliseconds.return_value,'bids':[[p-.01,1]],'asks':[[p+.01,1]]} for p in (price,target)]
        with tempfile.TemporaryDirectory() as directory, patch('ccxt.bybit',return_value=ex),patch('dual_futures_bot.realtime.time.sleep'),contextlib.redirect_stdout(io.StringIO()):
            path=Path(directory)/'state.json'
            run('bybit','BTC/USDT:USDT','15m',200,1000,path,cycles=2,strategy='trend-pullback')
            rows=[json.loads(line) for line in path.with_suffix('.jsonl').read_text().splitlines()]
            self.assertEqual(rows[0]['events'][0]['type'],'entry')
            self.assertEqual(rows[1]['events'][0]['reason'],'take_profit')
            self.assertEqual(rows[0]['role'],'trader')
            self.assertIsNone(json.loads(path.read_text())['position'])
            ex.create_order.assert_not_called()

    def test_advisor_cannot_override_deterministic_signal(self):
        a=dict(self.analysis(),signal=None,signal_reason='weak_trend',ai_advisor={'bias':'bullish','confidence':1,'action':'buy'})
        state=dict(equity=1000,position=None,events=[])
        self.assertEqual(step(state,a,100,100000000,RiskConfig()),[])
        self.assertIsNone(state['position'])

    def test_wide_spread_blocks_live_entry_but_not_exit_processing(self):
        import contextlib
        import io
        import json
        import tempfile
        from pathlib import Path
        from unittest.mock import Mock, patch
        from dual_futures_bot.realtime import run
        candles=series()
        i=next(i for i,d in enumerate(trend_decisions(candles)) if d['signal']=='long')
        ex=Mock()
        ex.market.return_value={'swap':True,'linear':True,'settle':'USDT'}
        ex.timeframes={'15m':'15m'}
        ex.parse_timeframe.return_value=900
        ex.milliseconds.return_value=(i+1)*900000
        ex.fetch_ohlcv.return_value=[list(vars(c).values()) for c in candles[:i+1]]
        p=candles[i].close
        ex.fetch_order_book.return_value={'timestamp':ex.milliseconds.return_value,'bids':[[p-10,1]],'asks':[[p+10,1]]}
        with tempfile.TemporaryDirectory() as directory,patch('ccxt.bybit',return_value=ex),contextlib.redirect_stdout(io.StringIO()):
            path=Path(directory)/'state.json'
            run('bybit','BTC/USDT:USDT','15m',200,1000,path,cycles=1,strategy='trend-pullback')
            state=json.loads(path.read_text())
            self.assertIsNone(state['position'])
            self.assertEqual(state['decision']['reason'],'spread_too_wide')

    def test_backtest_stop_wins_when_stop_and_target_both_touched(self):
        from unittest.mock import patch
        candles=[Candle(i*900000,100,101,99,100,100) for i in range(65)]
        candles[61]=Candle(61*900000,100,110,90,100,100)
        template=dict(self.analysis(),signal=None)
        decisions=[dict(template,candle_timestamp=c.timestamp) for c in candles]
        decisions[60].update(signal='long',atr14=2)
        with patch('dual_futures_bot.simulator.trend_decisions',return_value=decisions):
            result=simulate(candles,RiskConfig(initial_equity=1000),'trend-pullback')
        self.assertEqual(result['trade_count'],1)
        self.assertLess(result['trades'][0]['pnl'],0)
        self.assertNotEqual(result['trades'][0]['reason'],'take_profit')

    def test_test_period_never_trades_warmup(self):
        candles=series()
        result=simulate(candles,RiskConfig(initial_equity=1000),'trend-pullback',trade_start_index=300)
        self.assertTrue(all(t['entry_time']>=candles[300].timestamp for t in result['trades']))

    def test_zero_atr_policy_still_has_safe_diagnostics(self):
        candles=[Candle(i*900000,100,100,100,100,100) for i in range(65)]
        a=analyze(candles,65*900000,900000,'trend-pullback')
        self.assertIsNone(a['signal'])
        self.assertEqual(a['target_distance_fraction'],0)

import unittest
from unittest.mock import Mock, patch
from dual_futures_bot.demo import demo_action
from dual_futures_bot.policy import TREND_POLICY
from dual_futures_bot.simulator import RiskConfig


class DemoPolicyTests(unittest.TestCase):
    def setup_case(self):
        ex = Mock()
        ex.options = {'enableDemoTrading': True}
        ex.urls = {'api': {'private':'https://api-demo.bybit.com'}}
        ex.fetch_positions.side_effect = [[],[{'side':'long','contracts':.6,'stopLossPrice':96,'takeProfitPrice':106}]]
        ex.fetch_open_orders.return_value=[]
        ex.fetch_balance.return_value={'USDT':{'total':1000,'free':1000}}
        ex.milliseconds.return_value=100000000
        ex.market.return_value={'contractSize':1,'limits':{}}
        ex.amount_to_precision.side_effect=lambda symbol,qty:str(qty)
        ex.price_to_precision.side_effect=lambda symbol,price:str(price)
        ex.create_order.return_value={'id':'test-id'}
        ex.fetch_order.return_value={'status':'closed','filled':.6}
        analysis=dict(strategy=TREND_POLICY,candle_timestamp=99900000,interval_ms=900000,signal='long',atr14=2,
                      signal_reason='trend_pullback_confirmed',exit_long=False,exit_short=False,
                      take_profit_atr_multiple=3,max_hold_bars=24,cooldown_bars=3)
        state=dict(equity=1000,position=None,events=[])
        return ex,analysis,state

    def test_attached_protection_and_terminal_read_polling(self):
        ex,a,s=self.setup_case()
        ex.fetch_order.side_effect=[{'status':'open'},{'status':'closed','filled':.6}]
        with patch('time.sleep'):
            events=demo_action(ex,'BTC',a,100,RiskConfig(initial_equity=1000),s,lambda s:None)
        params=ex.create_order.call_args.args[-1]
        self.assertEqual(params['takeProfit']['triggerPrice'],106)
        self.assertEqual(params['stopLoss']['triggerPrice'],96)
        self.assertEqual(ex.create_order.call_count,1)
        self.assertEqual(s['decision']['action'],'enter')
        self.assertEqual(s['demo_trade']['entry_candle'],a['candle_timestamp'])
        self.assertEqual(events[0]['status'],'closed')

    def test_minimum_or_free_balance_is_wait_not_exception(self):
        for kind in ('minimum','free'):
            ex,a,s=self.setup_case()
            if kind=='minimum': ex.market.return_value['limits']={'cost':{'min':1000}}
            else: ex.fetch_balance.return_value['USDT']['free']=1
            self.assertEqual(demo_action(ex,'BTC',a,100,RiskConfig(initial_equity=1000),s,lambda s:None),[])
            ex.create_order.assert_not_called()
            self.assertIn(s['decision']['reason'],('below_exchange_minimum','insufficient_free_balance_without_leverage'))

    def test_existing_untracked_position_is_not_adopted(self):
        ex,a,s=self.setup_case()
        ex.fetch_positions.side_effect=[[{'side':'long','contracts':1}]]
        with self.assertRaisesRegex(ValueError,'Unmanaged'):
            demo_action(ex,'BTC',a,100,RiskConfig(),s,lambda s:None)
        ex.create_order.assert_not_called()

    def test_no_target_confirmation_keeps_pending_journal(self):
        ex,a,s=self.setup_case()
        ex.fetch_positions.side_effect=[[],[{'side':'long','contracts':.6,'stopLossPrice':96}]]
        with self.assertRaisesRegex(ValueError,'target'):
            demo_action(ex,'BTC',a,100,RiskConfig(),s,lambda s:None)
        self.assertTrue(s['pending_order'])

    def test_exit_allowed_during_daily_entry_halt(self):
        ex,a,s=self.setup_case()
        ex.fetch_positions.side_effect=[[{'side':'long','contracts':.6}],[]]
        s.update(demo_trade={'side':'long','entry_candle':a['candle_timestamp'],'target':106},demo_day=1,demo_day_equity=1100,demo_halted=True)
        a.update(signal=None,exit_long=True)
        events=demo_action(ex,'BTC',a,100,RiskConfig(),s,lambda s:None)
        self.assertTrue(ex.create_order.call_args.args[-1]['reduceOnly'])
        self.assertEqual(events[0]['reason'],'trend_invalidated')
        self.assertIsNone(s['pending_order'])

    def test_entry_quote_expiring_during_account_reads_is_blocked(self):
        ex,a,s=self.setup_case()
        a['quote_timestamp_ms']=1
        demo_action(ex,'BTC',a,100,RiskConfig(),s,lambda s:None)
        self.assertEqual(s['decision']['reason'],'quote_expired_before_order')
        ex.create_order.assert_not_called()

    def test_mark_to_market_loss_halts_entries_even_if_wallet_did_not_change(self):
        ex,a,s=self.setup_case()
        ex.fetch_positions.side_effect=[[]]
        ex.fetch_balance.return_value['info']={'result':{'list':[{'coin':[{'coin':'USDT','equity':'980'}]}]}}
        s.update(demo_day=1,demo_day_equity=1000,demo_halted=False)
        demo_action(ex,'BTC',a,100,RiskConfig(),s,lambda s:None)
        self.assertEqual(s['decision']['reason'],'daily_loss_limit')
        self.assertEqual(s['demo_equity_basis'],'bybit_usdt_equity')
        ex.create_order.assert_not_called()

    def test_exchange_target_disappearance_observed_and_reentry_cooled_down(self):
        ex,a,s=self.setup_case()
        ex.fetch_positions.side_effect=[[],[{'side':'long','contracts':.6,'stopLossPrice':96,'takeProfitPrice':106}],[]]
        demo_action(ex,'BTC',a,100,RiskConfig(initial_equity=1000),s,lambda s:None)
        a['candle_timestamp']+=900000
        events=demo_action(ex,'BTC',a,100,RiskConfig(initial_equity=1000),s,lambda s:None)
        self.assertEqual(events[0]['type'],'position_closed_observed')
        self.assertEqual(s['decision']['reason'],'post_exit_cooldown')
        self.assertEqual(ex.create_order.call_count,1)

    def test_native_protective_orders_are_not_treated_as_foreign_entries(self):
        ex,a,s=self.setup_case()
        ex.fetch_positions.side_effect=[[{'side':'long','contracts':.6}]]
        ex.fetch_open_orders.return_value=[{'reduceOnly':True,'side':'sell','info':{'stopOrderType':'StopLoss'}}]
        s['demo_trade']={'side':'long','entry_candle':a['candle_timestamp'],'target':106}
        self.assertEqual(demo_action(ex,'BTC',a,100,RiskConfig(),s,lambda s:None),[])
        self.assertEqual(s['decision']['reason'],'position_open')
        ex.create_order.assert_not_called()

    def test_foreign_open_orders_still_block_execution(self):
        ex,a,s=self.setup_case()
        ex.fetch_open_orders.return_value=[{'reduceOnly':False,'side':'buy','info':{}}]
        with self.assertRaisesRegex(ValueError,'Unrecognized'):
            demo_action(ex,'BTC',a,100,RiskConfig(),s,lambda s:None)
        ex.create_order.assert_not_called()


    def test_delayed_position_reflection_is_polled_without_new_order(self):
        ex,a,s=self.setup_case()
        ex.fetch_positions.side_effect=[[],[],[{'side':'long','contracts':.6,'stopLossPrice':96,'takeProfitPrice':106}]]
        with patch('time.sleep'):
            demo_action(ex,'BTC',a,100,RiskConfig(initial_equity=1000),s,lambda s:None)
        self.assertEqual(ex.create_order.call_count,1)
        self.assertIsNone(s['pending_order'])

    def test_daily_budget_uses_allocated_capital_not_large_demo_wallet(self):
        ex,a,s=self.setup_case()
        ex.fetch_balance.return_value={'USDT':{'total':99980,'free':99980}}
        s.update(demo_day=1,demo_day_equity=100000,demo_halted=False)
        demo_action(ex,'BTC',a,100,RiskConfig(initial_equity=1000),s,lambda s:None)
        self.assertEqual(s['demo_day_loss_budget'],10)
        self.assertEqual(s['decision']['reason'],'daily_loss_limit')
        ex.create_order.assert_not_called()

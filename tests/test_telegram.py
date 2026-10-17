import contextlib
import io
import os
import unittest
from unittest.mock import Mock, patch

from dual_futures_bot.telegram import Telegram


class TelegramTests(unittest.TestCase):
    def test_disabled_does_not_send(self):
        bot = Telegram()
        bot.session = Mock()
        self.assertFalse(bot.send('test', {}))
        bot.session.post.assert_not_called()

    def test_configuration(self):
        with patch.dict(os.environ, {'TELEGRAM_BOT_TOKEN': 'fake', 'TELEGRAM_CHAT_ID': ''}, clear=True):
            with self.assertRaises(ValueError): Telegram.from_env()
        with patch.dict(os.environ, {'TELEGRAM_STATUS_SECONDS': 'nan'}, clear=True):
            with self.assertRaises(ValueError): Telegram.from_env()

    def test_payload_and_no_exception_secret_leak(self):
        bot = Telegram('fake-secret', '123')
        bot.session = Mock()
        bot.session.post.return_value.status_code = 200
        bot.session.post.return_value.json.return_value = {'ok': True}
        self.assertTrue(bot.send('Trade', {'side': 'long'}))
        self.assertEqual(bot.session.post.call_args.kwargs['json']['chat_id'], '123')
        bot.session.post.side_effect = RuntimeError('https://token-fake-secret/')
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            self.assertFalse(bot.send('Trade', {}))
        self.assertNotIn('fake-secret', output.getvalue())

    def test_events_immediate_status_throttled(self):
        bot = Telegram(interval=300)
        bot.send = Mock()
        state = dict(equity=1000, position=None)
        with patch('dual_futures_bot.telegram.time.monotonic', return_value=1000):
            bot.update('BTC', 'paper', {}, 100, state, [])
            bot.update('BTC', 'paper', {}, 100, state, [])
            self.assertEqual(bot.send.call_count, 1)
            bot.update('BTC', 'paper', {}, 100, state, [{'type': 'entry'}])
            self.assertEqual(bot.send.call_count, 2)

    def test_exchange_stop_position_disappearance_notifies(self):
        bot = Telegram()
        bot.send = Mock()
        state = dict(demo_equity=1000, demo_positions=[{'side': 'long', 'contracts': 1}])
        bot.update('BTC', 'bybit_demo', {}, 100, state, [])
        state['demo_positions'] = []
        bot.update('BTC', 'bybit_demo', {}, 90, state, [])
        self.assertEqual(bot.send.call_count, 2)
        self.assertIn('position_change', bot.send.call_args.args[1])

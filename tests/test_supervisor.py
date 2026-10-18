import contextlib
import io
import os
import signal
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from dual_futures_bot.supervisor import advisor_process


class SupervisorTests(unittest.TestCase):
    def start(self, report):
        return advisor_process(True,report,'bybit','BTC/USDT:USDT','15m','qwen2.5:3b',480,60,512)

    def test_child_has_no_exchange_or_telegram_credentials_and_is_stopped(self):
        child=Mock()
        child.pid=123
        child.poll.return_value=None
        with tempfile.TemporaryDirectory() as directory, patch('dual_futures_bot.supervisor.subprocess.Popen',return_value=child) as launch, patch.dict(os.environ,{'BYBIT_DEMO_API_KEY':'example','TELEGRAM_BOT_TOKEN':'example'}), contextlib.redirect_stdout(io.StringIO()):
            with self.start(Path(directory)/'ai.json'):
                environment=launch.call_args.kwargs['env']
                self.assertNotIn('BYBIT_DEMO_API_KEY',environment)
                self.assertNotIn('TELEGRAM_BOT_TOKEN',environment)
                self.assertIn('--interval',launch.call_args.args[0])
            child.send_signal.assert_called_once_with(signal.SIGINT)
            child.wait.assert_called_once()

    def test_existing_advisor_lock_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory, patch('dual_futures_bot.supervisor.subprocess.Popen') as launch:
            report=Path(directory)/'ai.json'
            report.with_suffix('.json.lock').write_text('')
            with self.assertRaises(ValueError):
                with self.start(report): pass
            launch.assert_not_called()

    def test_disabled_does_not_spawn(self):
        with patch('dual_futures_bot.supervisor.subprocess.Popen') as launch:
            with advisor_process(False,None,'bybit','BTC','15m','model',480,60,512): pass
            launch.assert_not_called()

    def test_main_routes_single_command_to_trading_and_advisor(self):
        from contextlib import contextmanager
        from dual_futures_bot.__main__ import main
        from unittest.mock import patch
        import sys
        @contextmanager
        def managed(*args):
            yield
        argv=['bot','--exchange','bybit','--mode','realtime-paper','--strategy','trend-pullback','--with-ai','--fee-rate','.00055','--cycles','1']
        with patch.object(sys,'argv',argv),patch('dual_futures_bot.supervisor.advisor_process',side_effect=managed) as advisor,patch('dual_futures_bot.realtime.run') as trader,contextlib.redirect_stdout(io.StringIO()):
            main()
        self.assertTrue(advisor.call_args.args[0])
        self.assertEqual(trader.call_args.kwargs['strategy'],'trend-pullback')
        self.assertEqual(trader.call_args.kwargs['ai_report'],'reports/ai-advisor.json')
        self.assertEqual(trader.call_args.kwargs['risk_config'].fee_rate,.00055)

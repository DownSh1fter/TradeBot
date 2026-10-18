"""Own an optional advisor subprocess; trading and inference have separate loops."""
from contextlib import contextmanager
import os
from pathlib import Path
import signal
import subprocess
import sys


@contextmanager
def advisor_process(enabled, report, exchange, symbol, timeframe, model, timeout, interval, max_tokens):
    if not enabled:
        yield
        return
    path = Path(report).resolve()
    if path.with_suffix(path.suffix+'.lock').exists():
        raise ValueError('Advisor already running or stale lock: stop/reconcile it before --with-ai, or use --ai-report without --with-ai')
    path.parent.mkdir(parents=True, exist_ok=True)
    # Observer never needs exchange credentials or Telegram's bot token.
    environment = {k: v for k, v in os.environ.items() if not k.upper().startswith(('BYBIT_', 'TELEGRAM_'))}
    command = [sys.executable, '-m', 'dual_futures_bot.ai_advisor', '--exchange', exchange,
               '--symbol', symbol, '--timeframe', timeframe, '--model', model,
               '--report', str(path), '--history', str(path.with_suffix('.history.jsonl')),
               '--timeout', str(timeout), '--interval', str(interval), '--max-tokens', str(max_tokens)]
    with path.with_suffix('.log').open('a') as output:
        process = subprocess.Popen(command, env=environment, stdout=output, stderr=subprocess.STDOUT)
        try:
            print(f'Advisor started (PID {process.pid}); output: {path.with_suffix(".log")}. Trading remains deterministic.', flush=True)
            yield
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                    print('Advisor required forced termination. Check its lock before restarting.', flush=True)

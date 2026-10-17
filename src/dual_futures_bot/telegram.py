"""Optional outbound Telegram notifications; no remote trading commands."""
import json
import math
import os
import sys
import time
from datetime import datetime, timezone

import requests


class Telegram:
    def __init__(self, token=None, chat_id=None, interval=300):
        self.token = token
        self.chat_id = chat_id
        self.interval = interval
        self.last_status = None
        self.last_position = None
        self.session = requests.Session()

    @classmethod
    def from_env(cls):
        token = os.environ.get('TELEGRAM_BOT_TOKEN')
        chat_id = os.environ.get('TELEGRAM_CHAT_ID')
        if bool(token) != bool(chat_id):
            raise ValueError('Set both TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID, or neither')
        interval = float(os.environ.get('TELEGRAM_STATUS_SECONDS', '300'))
        if not math.isfinite(interval) or interval < 30:
            raise ValueError('TELEGRAM_STATUS_SECONDS must be >= 30')
        return cls(token, chat_id, interval)

    def send(self, title, data):
        if not self.token:
            return False
        try:
            message = 'TradeBot | ' + title + '\n' + datetime.now(timezone.utc).isoformat(timespec='seconds') + '\n' + json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False, default=str)
            response = self.session.post(
                'https://api.telegram.org/bot' + self.token + '/sendMessage',
                json={'chat_id': self.chat_id, 'text': message[:4000]}, timeout=(3, 3))
            if response.status_code != 200 or response.json().get('ok') is not True:
                print('Telegram delivery failed; check token, chat ID and bot access.', file=sys.stderr)
                return False
            return True
        except Exception:
            # Never log exception text: requests errors may contain the token-bearing URL.
            print('Telegram unavailable; trading state is unchanged.', file=sys.stderr)
            return False

    def update(self, symbol, mode, analysis, price, state, events):
        position = state.get('demo_positions') if mode == 'bybit_demo' else state.get('position')
        data = {'symbol': symbol, 'mode': mode, 'price': price, 'analysis': analysis,
                'equity_USDT': state.get('demo_equity') if mode == 'bybit_demo' else state['equity'],
                'position': position, 'entries_halted': state.get('demo_halted') if mode == 'bybit_demo' else state.get('halted', False)}
        # Ignore fluctuating mark-to-market PnL when detecting position changes.
        signature = json.dumps([{k: p.get(k) for k in ('side', 'contracts', 'entryPrice')} for p in position], sort_keys=True) if isinstance(position, list) else json.dumps({k: position.get(k) for k in ('side', 'quantity', 'entry')} if position else None, sort_keys=True)
        changed = self.last_position is not None and signature != self.last_position
        now = time.monotonic()
        if events or changed or self.last_status is None or now - self.last_status >= self.interval:
            data['events'] = events
            if changed:
                data['position_change'] = 'Observed account position change; consult Bybit executions for fill/PnL'
            self.send('Сделка / Trade' if events or changed else 'Статус / Status', data)
            self.last_status = now
        self.last_position = signature

    def close(self):
        self.session.close()

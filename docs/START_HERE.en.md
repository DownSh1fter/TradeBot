# Complete Mac setup: TradeBot, Bybit Demo, Ollama and Telegram

[New single-command operation and trend-pullback policy](REWORK.en.md). Older commands below retain ema-cross unless a strategy is selected.

[Русская версия](START_HERE.ru.md) · [Home](../README.md)

This guide covers the current application. All examples use `~/Downloads/TradeBot-git`. Run commands in macOS Terminal or VS Code's terminal, using bash or zsh. Copy code blocks only: do not type prompt symbols, arrows or `(.venv)`.

## 1. Components and responsibilities

| Component | Purpose | Places orders? |
|---|---|---|
| `backtest` | Historical simulation | No |
| `realtime-paper` | Virtual trades on current market data | No |
| `bybit-demo` | EMA strategy with Bybit Demo execution | Yes, Demo only |
| `ai_advisor` | Local model analysis of charts and headlines | No |
| Telegram | Outbound notifications | No; no trading commands |
| `demo_smoke` | One entry/exit without a strategy signal | Yes, Demo only |

The AI is currently an **observer**. Its assessment appears in output/notifications but does not change entries or exits. EMA20/50 and existing risk rules determine trades. Working software is not evidence of profitability.

## 2. Required applications

- [VS Code](https://code.visualstudio.com/).
- [Python for macOS](https://www.python.org/downloads/macos/): 3.11+ required; examples use 3.12.
- Git: check with `git --version`. Complete Command Line Tools installation if prompted by macOS.
- [Ollama for Mac](https://ollama.com/download/mac), only for AI analysis. Check current macOS compatibility on its download page.
- Bybit **Demo Trading**, only for Demo orders. This is separate from Testnet and the real-money account.

Check in Terminal:

```bash
python3.12 --version
git --version
```

If a command is missing, install the application and open a new terminal. Apple's Python 3.9 is too old for this project.

## 3. Download once

If `TradeBot-git` already exists, do not clone over it; use the update section.

```bash
cd ~/Downloads
git clone https://github.com/DownSh1fter/TradeBot.git TradeBot-git
cd ~/Downloads/TradeBot-git
ls pyproject.toml
```

The last command must find `pyproject.toml`. Otherwise you are outside the project root.

In VS Code use **File → Open Folder → Downloads → TradeBot-git**, then **Terminal → New Terminal**. If the file tree is missing: Cmd+Shift+P → `View: Reset View Locations`, then Cmd+Shift+E.

### Migrating from a ZIP (`TradeBot-main`)

`git pull` updates a Git checkout, not a ZIP download. Stop old processes, check exchange positions and preserve the old folder. If the newly cloned `TradeBot-git` has no `reports` folder yet, you can transfer state:

```bash
cp -R ~/Downloads/TradeBot-main/reports ~/Downloads/TradeBot-git/
```

Skip this if the old reports folder does not exist. If both folders contain reports, compare/back them up before merging. Preserve your own source changes separately. Do not copy the old `.venv`; create a new environment. Never run old and new strategy copies simultaneously.

## 4. Install Python dependencies

From the repository root:

```bash
cd ~/Downloads/TradeBot-git
python3.12 -m venv .venv
source .venv/bin/activate
python --version
python -m pip install --upgrade pip
python -m pip install --only-binary=cryptography -e .
python -m unittest discover -s tests -v
```

The prompt usually gains `(.venv)`. Tests should finish with `OK` and a nonzero executed test count. Offline tests do not validate your API credentials or exchange connectivity.

`--only-binary=cryptography` prevents a known macOS Rust/maturin source-build problem. If no compatible wheel exists, collect macOS/Python versions and the error. Do not disable TLS verification or guess dependency/version changes.

### Every new terminal tab

Start with:

```bash
cd ~/Downloads/TradeBot-git
source .venv/bin/activate
```

Python activation and API configuration are separate. Activation does not load credentials. Exported variables belong to that shell and its child processes; do not assume another tab inherits them. The application does not automatically read `.env`.

## 5. Public-market check without keys/orders

```bash
python -m dual_futures_bot --exchange bybit --mode realtime-paper --timeframe 15m --limit 200 --cycles 1 --state reports/paper-check.json
```

Expect JSON with `analysis` and `events`, without a traceback. `events: []` is normal when there is no signal. State is written to `reports/paper-check.json`.

A separate historical backtest:

```bash
python -m dual_futures_bot --exchange bybit --mode backtest --timeframe 15m --limit 200 --equity 1000
```

## 6. Create and enter Bybit Demo credentials

Switch the Bybit website to **Demo Trading → API**. Create a system-generated key with account reading and contract-order trading permissions (Read-Write / Orders). Withdrawal permission is unnecessary. Select one-way mode for the linear USDT perpetual. Configure margin/leverage in Demo beforehand; the bot does not change them. Fund virtual USDT.

If IP binding is enabled, allow your current external/VPN IP, not a local address such as `192.168...`. Changing networks/VPN servers may change that IP. Revoke/replace keys exposed in screenshots or chat.

### Exactly where to paste values

Call the trading terminal **tab C**. Activate its Python environment as shown in section 4.

**Step 1:** Run only this line, unchanged. Do NOT replace the variable name with your key:

```bash
read -r -s BYBIT_DEMO_API_KEY
```

After Enter, the terminal silently waits for input. Now paste **only the API Key** with Cmd+V and press Enter. No characters or asterisks appear; this is expected.

**Step 2:** After the prompt returns:

```bash
export BYBIT_DEMO_API_KEY
echo
```

**Step 3:** Run separately:

```bash
read -r -s BYBIT_DEMO_API_SECRET
```

Paste **only the API Secret**, then Enter. After the prompt returns:

```bash
export BYBIT_DEMO_API_SECRET
echo
```

Do not paste an entire script together with secrets: `read` needs its own input. Do not include quotation marks around hidden input, or put the token in place of the variable name in the command.

### Check presence/format without displaying credentials

```bash
python - <<'PY'
import os
for name in ('BYBIT_DEMO_API_KEY', 'BYBIT_DEMO_API_SECRET'):
    value = os.environ.get(name, '')
    valid = bool(value) and value.isascii() and not any(c.isspace() for c in value)
    print(name, 'format OK' if valid else 'empty or contains invalid characters')
PY
```

This checks characters/presence only, not authentication or permissions. Do not use environment dumps, `echo "$...SECRET"`, or screenshots of values for diagnosis. HMAC signing requires the actual secret in the process; proxy substitution cannot replace it.

## 7. Optional Telegram setup in tab C

1. Use the verified **@BotFather**, send `/newbot` and keep the token private.
2. Open **your own new bot** and press Start / send `/start`.
3. For a private chat, find your numeric `Id` through **@userinfobot**. It does not need your bot token. The chat ID is not your phone number or @username. For groups, use the group's ID and give your bot send permission. Group members can see the account information sent there.

Run separately:

```bash
read -r -s TELEGRAM_BOT_TOKEN
```

Paste the token with Cmd+V → Enter. Then:

```bash
export TELEGRAM_BOT_TOKEN
echo
```

Request the chat ID separately (visible input):

```bash
read -r TELEGRAM_CHAT_ID
```

Enter only the numeric ID → Enter, then:

```bash
export TELEGRAM_CHAT_ID
export TELEGRAM_STATUS_SECONDS='300'
```

Test delivery without trading:

```bash
python - <<'PY'
import os
from dual_futures_bot.telegram import Telegram
if not os.environ.get('TELEGRAM_BOT_TOKEN') or not os.environ.get('TELEGRAM_CHAT_ID'):
    print('Token or chat ID is empty')
else:
    bot = Telegram.from_env()
    try:
        print('Sent' if bot.send('Connection test', {'message': 'TradeBot connected; no orders sent'}) else 'Delivery failed')
    finally:
        bot.close()
PY
```

Expect a message. Notifications cover startup, stop/error, trades/position changes and summaries every 300 seconds. Minimum interval is 30 seconds. Failed deliveries may be lost; there is no retry queue. Telegram accepts no trading commands.

To disable Telegram before starting:

```bash
unset TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID
```

## 8. Ollama: application or tab A

Install Ollama into Applications and open it. Do not start a second server if the application is already serving requests.

Check:

```bash
ollama --version
ollama list
```

If `ollama` is not found, use:

```bash
/Applications/Ollama.app/Contents/Resources/ollama --version
```

If the server is unavailable, dedicate **tab A** to:

```bash
/Applications/Ollama.app/Contents/Resources/ollama serve
```

Leave it open. If the port is already occupied, inspect the existing app/server rather than starting another one.

Download the model once from another tab:

```bash
/Applications/Ollama.app/Contents/Resources/ollama pull qwen2.5:3b
```

The model runs locally without a cloud API key. It uses disk, RAM and compute. Loading/generation can take minutes. Server `n_gen` and tokens/s indicate generation; an HTTP 500 is not success, so check the observer's final result.

## 9. Test and run the AI observer: tab B

Open **tab B** and activate the project environment:

```bash
cd ~/Downloads/TradeBot-git
source .venv/bin/activate
python -m dual_futures_bot.ai_advisor --exchange bybit --timeframe 15m --cycles 1 --timeout 480 --max-tokens 512
```

Progress lines show market/news retrieval and waiting for Ollama. The final result should have `status: ok`. For `status: error`, read `error_type` and `hint`. JSON output alone does not establish successful analysis.

For continuous operation remove `--cycles 1`:

```bash
python -m dual_futures_bot.ai_advisor --exchange bybit --timeframe 15m --timeout 480 --max-tokens 512
```

The pause between completed runs is 300 seconds, plus the next run's processing time. `--timeout 480` is an Ollama read timeout, not total cycle duration. For `TruncatedModelResponse`, try `--max-tokens 768`. A slower Mac can try downloading `qwen2.5:1.5b` and selecting `--model qwen2.5:1.5b`; quality can be lower.

Inputs include the selected timeframe and 1h, EMA/ATR, returns and relative volume. News consists of RSS headlines from the last 24 hours, not the full web or verified articles. Inspect `news_coverage`: CoinDesk returned `ValueError` in a user validation, so a top-level `status: ok` does not establish crypto-news coverage. The model may answer in English despite the Russian-language instruction.

Files:

- `reports/ai-advisor.json`: latest report;
- `reports/ai-history.jsonl`: assessment/error history;
- `reports/ai-advisor.json.lock`: one-process lock.

Confidence is subjective, not a profit probability. `bias: neutral` is not an instruction to close a position.

## 10. Start trading: tab C

Tab C needs `.venv`, Demo credentials and optional Telegram settings from sections 6–7. **Stop all other trading processes first**, including those using the old `TradeBot-main` folder. Use one strategy process per account/symbol. Different state files do not make simultaneous trading safe.

One iteration with the AI report attached:

```bash
python -m dual_futures_bot --exchange bybit --mode bybit-demo --timeframe 15m --limit 200 --equity 1000 --cycles 1 --ai-report reports/ai-advisor.json --state reports/demo-bybit.json
```

This can submit a Demo order if a signal exists. Account-reading success does not prove order permissions until an order is actually attempted.

Continuous operation:

```bash
python -m dual_futures_bot --exchange bybit --mode bybit-demo --timeframe 15m --limit 200 --equity 1000 --ai-report reports/ai-advisor.json --state reports/demo-bybit.json
```

Without AI, omit `--ai-report reports/ai-advisor.json`; Ollama/observer processes are unnecessary then. To avoid orders, select `realtime-paper` and a separate `--state reports/paper-with-ai.json`.

`--equity 1000` is the sizing base/cap, not each order's size or a guaranteed loss limit. Current risk defaults: 0.25% relative to stop distance, notional up to 25% of sizing equity and entry blocking after a daily equity decline of at least 1%. Exchange minimums/precision apply. Fees, slippage and gaps can increase loss. Demo uses an initial 2×ATR stop; automatic Demo trailing updates are not implemented.

Polling is roughly every ten seconds plus API/notification time. EMA signals require a new crossover on a closed 15m candle, so hours without entries can be normal. AI runs independently and does not replace the trading signals.

## 11. Read output and confirm trades

| Field | Meaning |
|---|---|
| `signal: null` | No fresh strategy signal |
| `events: []` | No new order submitted in this iteration |
| `type: demo_order` | Result confirmed for a submitted Demo order |
| Order `status: closed` | Order finished/filled; not proof the position closed |
| `filled`, `average` | Filled amount and average price, if returned |
| `reduce_only: false` | Entry order |
| `reduce_only: true` | Position reduction/exit |
| `equity` | Observed Demo USDT equity or paper equity |
| `quote_source: orderbook_midpoint` | Reference price is timestamped best bid/ask midpoint |
| `ai_advisor.status: ok` | Fresh valid AI report loaded |
| `unavailable_or_stale` | Missing, failed, mismatched or older-than-ten-minute report |

In Bybit Demo, check **Positions**, Stop Loss, **Order History / Trade History**. Local success messages do not replace exchange reconciliation. The Demo journal is not complete accounting. An exchange-executed stop may not create a new local `demo_order`; Telegram detects position snapshot changes at subsequent polls. A full open/close between polls can be missed by notifications.

AI freshness starts at the input snapshot, not generation completion. Slow inference can leave little remaining freshness. JSON timestamps are Unix milliseconds; Telegram reports UTC. Convert to your local timezone when inspecting times.

## 12. Explicit entry/exit test without a chart signal

Stop all strategies/tests and confirm no BTCUSDT positions/open orders. In tab C:

```bash
python -m dual_futures_bot.demo_smoke --execute --max-notional 250
```

This submits the minimum valid market buy with a protective stop, then a reduce-only market sell for the observed amount. Reference notional is capped by the smaller of 250 USDT and 25% of free Demo USDT. The roundtrip is not atomic; errors can leave a position open. Expected success:

```text
DEMO ROUNDTRIP OK: no position and no open orders for this symbol.
```

`reports/demo-smoke.json` is created exclusively. On `FileExistsError`, read the journal and reconcile Bybit first:

```bash
cat reports/demo-smoke.json
```

Never delete the journal to bypass an error. A new `--journal reports/demo-smoke-2.json` is acceptable only after reconciling the previous test and confirming no positions/orders. See the [detailed smoke-test guide](DEMO_SMOKE.en.md).

## 13. Shutdown, Mac sleep and restarting

- Ctrl+C in C stops the trading loop; **it does not close exchange positions or cancel orders**.
- Ctrl+C in B stops analysis, not trading. The last report will expire.
- Closing A/Ollama stops inference; the next observer request will fail.
- Prevent sleep/network loss if expecting continuous operation. Check Bybit after shutdown/sleep. Accepted exchange stops may remain active, but verify them in the UI.
- Restart with the same state file and settings. Never use a new state to bypass `pending_order`, a settings mismatch or another error.

Activate the environment and provide required variables for each new terminal. This project does not automatically store API credentials on disk. Do not commit them or paste them into chat.

## 14. Update from GitHub

First Ctrl+C in B/C, inspect positions/stops and back up state/logs/local changes. Ollama can remain running.

```bash
cd ~/Downloads/TradeBot-git
git status --short
git pull --ff-only
source .venv/bin/activate
python -m pip install --only-binary=cryptography -e .
python -m unittest discover -s tests -v
```

If Git reports local changes/conflicts, preserve them before continuing. Do not use `reset --hard`, `git clean` or delete reports to force an update. Reports are Git-ignored and not supplied by the repository. Restart B/C after tests with original state paths. If tab C remains open and variables were not unset, credentials need not be reentered.

## 15. Troubleshooting

| Error | Action |
|---|---|
| `command not found: python` | Enter TradeBot-git and activate `.venv` |
| `No module named dual_futures_bot` | Install with `python -m pip install --only-binary=cryptography -e .` from the root |
| `No module named ...ai_advisor` | Wrong/old folder or checkout; inspect `pwd`, `git log -1 --oneline` and update |
| Missing pyproject / tests not importable | Commands were run from Downloads or another directory |
| Python `3.9.6 not in >=3.11` | Use Python 3.12 for a new environment; preserve old files/use a separate path rather than overwriting blindly |
| Rust/maturin/cryptography build failure | Upgrade pip, use binary cryptography; check macOS/architecture if no wheel exists |
| Missing/stale quote timestamp | Update for order-book fallback, check automatic system clock and network; keep freshness validation |
| `Set BYBIT_DEMO_API_KEY...` | Required variables are missing in this tab; repeat section 6 |
| `UnicodeEncodeError: latin-1` | Credential contains extraneous text; check format without printing values and reenter |
| Bybit `10005 Permission denied` | Enable Demo Read-Write and contract Orders permissions |
| Bybit `10010 Unmatched IP` | Correct external/VPN IP binding; no code/state change needed |
| zsh `quote>` | Unmatched/smart quotes: Ctrl+C and recopy; use hidden `read` for credentials |
| Nothing appears during `read -s` | Expected hidden input: Cmd+V then Enter; never replace the variable name with the token |
| Empty Telegram token/chat | Export both in this tab; section 7 |
| Telegram 401 / 400 chat not found / 403 | Respectively token / ID and Start with your bot / blocking or chat permissions |
| Missing `ollama` command | Install the application or use the full executable path |
| Cannot connect to Ollama | Open the app or run one `ollama serve` |
| Ollama 500/cancellation after two minutes | Update, use `--timeout 480`, inspect observer result/hint and server logs |
| `TruncatedModelResponse` | Try `--max-tokens 768`; more output takes longer |
| State settings mismatch | Restore original settings; do not evade it with new state without position reconciliation |
| `pending_order` | Locate client ID in Bybit, reconcile fills, position, stop and orders; no blind resubmission |

### Stale `.lock` files

Check processes first:

```bash
pgrep -fl 'dual_futures_bot.ai_advisor'
pgrep -fl 'dual_futures_bot --exchange'
```

Stop the relevant process in its own tab. Only after confirming it is no longer running, for the default observer report:

```bash
rm reports/ai-advisor.json.lock
```

For default trading state, **after Bybit/journal reconciliation**:

```bash
rm reports/demo-bybit.json.lock
```

These remove only locks, not state. Custom report/state paths have different lock names. An existing smoke-test `.json` is a journal, not a lock; do not delete it this way.

### Safely inspect Telegram's response

If delivery fails without details, this test prints status/description without the token:

```bash
python - <<'PY'
import os
import requests
token = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
chat = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
if not token or not chat:
    print('Token or chat ID is empty')
else:
    try:
        r = requests.post(f'https://api.telegram.org/bot{token}/sendMessage',
                          json={'chat_id': chat, 'text': 'TradeBot connection test'}, timeout=10)
        data = r.json()
        print('HTTP:', r.status_code)
        print('Result:', data.get('description', 'Sent' if data.get('ok') else 'Unknown response'))
    except Exception as exc:
        print('Connection error:', type(exc).__name__)
PY
```

When asking for help, provide error type/text, `pwd`, Python/macOS versions and relevant log lines with credentials removed. Never post the full process environment.

### `quote_unavailable` and stale AI reports

Current normal trading loops skip rejected quotes without orders rather than exiting. Inspect `reason`, `source`, `age_seconds` and eventual `quote_recovered`. Exchange time may be at most two seconds ahead; age above 60 seconds is still rejected. Persistent warnings require checking Bybit/network/clock; no orders does not prove an existing position is closed. Paper stops cannot run without a valid quote.

`ai_advisor: unavailable_or_stale` does not cause quote failures. Check tab B, latest report status/hint, path and matching timeframe. Slow inference plus pauses can create gaps in fresh reports. Stop only the observer and try `--interval 60 --timeout 480 --max-tokens 512` instead of the default 300-second pause. This increases load and cannot guarantee freshness. The ten-minute freshness limit remains; old recommendations never become trade signals.

## 16. Files and reference guides

| File | Contents |
|---|---|
| `reports/demo-bybit.json` | Demo state, latest account snapshot/events and possible pending order |
| `reports/paper-check.json` | Separate virtual check state |
| `reports/ai-advisor.json` | Latest AI assessment |
| `reports/ai-history.jsonl` | AI inputs/outputs/errors; grows without rotation |
| `reports/demo-smoke*.json` | Explicit execution-test journals |
| `.venv/` | Dependencies for this checkout |

[Strategy/backtest](README.en.md) · [Realtime/Demo](REALTIME.en.md) · [AI](AI.en.md) · [Telegram](TELEGRAM.en.md) · [Execution test](DEMO_SMOKE.en.md).

# Updated operation: one trader, explicit decisions and a testable policy

[Русский](REWORK.ru.md) · [Full installation/credentials](START_HERE.en.md)

## Diagnosis from the supplied logs

The excerpt contains 36 AI-observer records over roughly 1h51m: 35 successes and one error. All assessments were neutral; all technical signals were absent during an established EMA downtrend. There is no execution-process log, so the excerpt cannot establish that trading ran or that orders were rejected. The observer does not place orders.

The legacy policy enters only on a fresh EMA20/50 crossover. Starting mid-trend can mean waiting for hours. The new optional policy evaluates pullbacks inside an existing trend. It does not force trades on a timer or guarantee profit.

## 1. Update while preserving state

Stop the old trader and separate observer with Ctrl+C; leave Ollama running. Stopping does not close positions. Reconcile Bybit Demo positions/orders and back up reports. Never delete state/pending orders to update.

```bash
cd ~/Downloads/TradeBot-git
git status --short
git pull --ff-only
source .venv/bin/activate
python -m pip install --only-binary=cryptography -e .
python -m unittest discover -s tests -v
```

Preserve local changes if Git refuses the update. `ema-cross` remains the default for compatibility; select the new policy explicitly.

## 2. Test without credentials/orders

```bash
python -m dual_futures_bot --exchange bybit --mode realtime-paper --strategy trend-pullback --timeframe 15m --limit 200 --equity 1000 --fee-rate 0.00055 --cycles 1 --state reports/paper-trend.json
```

Expect `role: session`, then `role: trader`. This is the execution loop, not just an AI process. `decision.action` and `decision.reason` explain waiting/holding/entries. A single iteration does not guarantee a signal.

`--fee-rate 0.00055` means an assumed 0.055% per side, not automatic detection of your Bybit tier. Supply your actual rate. `--slippage-rate` defaults to 0.0002 (0.02% per side). Cost settings are part of state identity; do not change them on an existing state without reconciliation.

## 3. Single-command operation with AI

Keep Ollama running with the model downloaded. Stop a previously separate observer to avoid its report lock.

```bash
python -m dual_futures_bot --exchange bybit --mode realtime-paper --strategy trend-pullback --timeframe 15m --limit 200 --equity 1000 --fee-rate 0.00055 --with-ai --state reports/paper-trend.json
```

The trader owns the observer subprocess. Default files:

- latest report: `reports/ai-advisor.json`;
- observer history: `reports/ai-advisor.history.jsonl`;
- observer stdout/stderr: `reports/ai-advisor.log`.

Override `--ai-report` to relocate all three together. Inspect progress separately:

```bash
tail -n 20 reports/ai-advisor.log
```

Options: `--ai-model qwen2.5:3b`, `--ai-timeout 480`, `--ai-interval 60`, `--ai-max-tokens 512`. Trading does not wait for inference. AI errors/neutral assessments do not veto otherwise valid technical signals. Before the first fresh assessment, the report may be unavailable_or_stale.

BYBIT_* and TELEGRAM_* variables are stripped from the child environment. Stopping the trader stops only its owned observer, not Ollama. If retaining a separately managed observer, use only `--ai-report reports/ai-advisor.json`, without `--with-ai`.

## 4. Single-command Demo execution

Stop the old trader and reconcile positions/open orders on the symbol first. The new policy refuses an untracked position with `Unmanaged position`; never delete files to evade this. Transition while flat, without blindly canceling/closing unknown activity.

In the current tab configure Demo and optional Telegram variables using the [credential guide](START_HERE.en.md). Never put values in source/chat. Then:

```bash
python -m dual_futures_bot --exchange bybit --mode bybit-demo --strategy trend-pullback --timeframe 15m --limit 200 --equity 1000 --fee-rate 0.00055 --with-ai --state reports/demo-trend.json
```

This can place Demo orders. Add `--cycles 1` for one attempt; inference may not finish during it. Omit `--with-ai` to operate without a model.

Preserve the old `reports/demo-bybit.json`, which belongs to another policy. A new state is appropriate only after reconciling old positions/orders. Restart this policy with its original state/settings. A shared `reports/.execution_bybit_<symbol>.lock` prevents simultaneous Demo traders for a symbol within one checkout, even with different state files. This is a local guard, not a distributed lock across computers/checkouts. Do not share the account/symbol with other bots or manual trades.

## 5. Exact trend-pullback-v1 rules

Fixed rules, not fitted to user PnL:

- At least 60 continuous closed candles; EMA20/50 and ATR14.
- Direction from EMA20 versus EMA50; separation at least 0.25 ATR.
- Three-bar EMA20 slope agrees with direction.
- ATR/price between 0.05% and 5%; last-bar volume at least half the preceding 20-bar average.
- Close within one ATR of EMA20; a touch of its ±0.25 ATR zone within three bars.
- Last close confirms a rebound in the trend direction.
- The 3 ATR target distance must cover at least twice assumed roundtrip costs (fees/slippage; online also spread).
- Online spread at most 0.08%, valid exchange book time, and current price no more than one ATR away from signal close.

Target distance is a geometric cost screen, not a forecast or positive-expectancy proof. Funding and deeper order-book liquidity are not checked by this filter. Backtest/live share a causal policy, but indicator warmup/history length can change borderline outcomes.

Exits: fixed 2 ATR Stop Loss, 3 ATR Take Profit, EMA regime invalidation or 24 bars held. No trailing in this policy. Demo attaches exchange SL/TP on entry and verifies their presence after execution. Order status is polled read-only up to ten times; uncertain submissions are never retried. Ambiguity/unconfirmed protection preserves pending_order and stops for reconciliation.

After closing, wait three candles before reentry. Exchange-triggered exits are detected through position disappearance; this does not establish exact exit reason or realized PnL. Consult Bybit fills.

## 6. Risk and execution

- Sizing base is the smaller of configured equity and observed USDT equity.
- Risk up to 0.25% relative to the rounded stop plus modeled cost allowance; notional up to 25% of the base.
- New entries cannot exceed free USDT notional: the policy does not rely on leverage for sizing. It does not change exchange leverage/margin settings.
- Minimums, precision and maximum amount are checked. Undersized risk-budget orders wait with `below_exchange_minimum`; risk is never increased to meet a minimum.
- An account-equity decline from the daily baseline of 1% of the smaller of starting equity and configured --equity blocks entries, not protective exits (a 1000 allocation means a 10 USDT budget even on a larger Demo balance). Bybit coin equity is preferred; fallback is wallet plus the symbol's unrealized PnL. Use a dedicated USDT account. This is not a guaranteed loss ceiling.
- Quotes that expire during account reads block entry with `quote_expired_before_order`.
- Actual fills, fees, slippage and funding are exchange-determined; modeled budgets cannot guarantee results.

## 7. Waiting reasons

| `decision.reason` | Meaning |
|---|---|
| `awaiting_ema_cross` | Legacy strategy selected, no fresh crossover |
| `awaiting_next_closed_candle` | Candle already processed |
| `weak_trend` / `trend_slope_conflict` | Trend criteria failed |
| `price_too_far_from_ema` / `no_recent_pullback` | No suitable pullback |
| `rebound_not_confirmed` | Rebound not confirmed |
| `low_volume` / `low_volatility` / `high_volatility` | Market filters |
| `target_too_small_for_costs` / `spread_too_wide` | Cost/distance or spread restriction |
| `entry_price_moved` | Quote moved away from signal close |
| `below_exchange_minimum` | Risk-sized amount below exchange minimum |
| `insufficient_free_balance_without_leverage` | Insufficient free USDT notional |
| `post_exit_cooldown` | Reentry pause |
| `daily_loss_limit` | Daily entry halt |
| `position_open` | Already holding a position |

Events include `demo_order` and `position_closed_observed`. Order status `closed` does not necessarily mean the position closed. Telegram summaries include the last decision. No events is not itself an error; a trade is not itself profit.

## 8. Logs to send for diagnosis

`reports/demo-trend.jsonl` appends accepted trading cycles and rejected quotes, including price, analysis, decision, equity, positions and events. `reports/demo-trend.json` holds current state. `reports/ai-advisor.history.jsonl` is separate model history. These are distinct roles. Logs grow without rotation; monitor disk. Credentials are not recorded, but account data is financial information: review files before sharing.

```bash
tail -n 3 reports/demo-trend.jsonl
```

If the trader failed before journaling, include its traceback too. For pending_order, reconcile client ID, positions and orders in Bybit before restarting. Inspect all trading processes before removing a stale shared execution lock; do not delete state/journals.

## 9. Frozen-history comparison

On a machine with public API access, capture identical closed candles for both policies without sending orders:

```bash
python - <<'PY'
import json
from pathlib import Path
from dual_futures_bot.market_data import fetch_candles
rows = fetch_candles('bybit', 'BTC/USDT:USDT', '15m', 1000)
path = Path('reports/BTCUSDT-15m-sample.json')
path.parent.mkdir(parents=True, exist_ok=True)
if path.exists():
    raise SystemExit('Dataset already exists; preserve it or choose a new name')
path.write_text(json.dumps([list(vars(c).values()) for c in rows]))
print('Saved closed candles:', len(rows))
PY
python -m dual_futures_bot.benchmark --input reports/BTCUSDT-15m-sample.json --output reports/benchmark.json --equity 1000 --fee-rate 0.00055 --slippage-rate 0.0002
```

At least 240 candles are required. Both fixed policies use identical costs: first two thirds, then the following last third. Up to 200 preceding warmup bars are provided without warmup trades. No parameter fitting or automatic winner deployment. Reports include input SHA256, trade count, net result, fees and drawdown. Mark-to-market drawdown uses bar-close modeled equity, not the worst intrabar excursion.

Limitations: no funding/liquidations, real book or exchange sizing constraints; stop and target touching one OHLC bar are resolved conservatively with the stop first. A thousand candles is a short sample, insufficient for real-money deployment. Use further independent periods/regimes and forward Demo.

## 10. Evidence and outstanding work

Offline tests cover existing-trend entry without crossover, long/short symmetry, no forced entries in flat/costly markets, prefix invariance/no lookahead, full paper entry/exit auditing, attached SL/TP, cooldown, daily halt, minimums, read-only order polling and child lifecycle.

The new policy lost money after costs on synthetic random walks. The [validation note](VALIDATION.md) records this: more trades is not automatically better. Current Bybit/Binance history could not be retrieved in the cloud because the proxy returned CONNECT 403. Current-market performance and the new policy's actual Demo execution remain unverified. Unit tests and an old smoke-test success do not establish profitability.

This remains an experimental paper/Demo system without a real-money mode. Deployment evidence must come from execution logs and independent cost-adjusted comparisons, not the observer's message count.

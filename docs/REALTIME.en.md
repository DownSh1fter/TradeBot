# Market analysis and Bybit Demo

[Русский](REALTIME.ru.md) · [Main guide](README.en.md)

## Modes and analysis

Three modes are available: `backtest` (default), `realtime-paper`, and `bybit-demo`. REST polling runs every 10 seconds by default. This has polling latency; it is not WebSocket streaming, news analysis or AI. Closed chart candles feed EMA20/EMA50 trend/crossover signals and ATR14 volatility. Entries are blocked when ATR/price exceeds 5%. Analysis, signals and events print as JSON.

A signal requires a fresh crossover on the latest closed candle. An established trend alone does not trigger entry. EMA is recalculated over the downloaded window. Unfinished, stale, missing or invalid candles are rejected. Quotes require a timestamp no older than 60 seconds.

## Without credentials

After installation from the main guide:

```bash
python -m dual_futures_bot --exchange bybit --mode realtime-paper --timeframe 15m --limit 200 --poll-seconds 10 --state reports/paper-bybit.json
```

Add `--cycles 1` for one iteration. Paper fills use the observed last price with modeled fees/slippage. Stops are checked at each poll; trailing updates on a new closed candle. Moves between polls can be missed. This differs from candle backtesting.

## Connect Bybit Demo

1. Enable **Demo Trading** in Bybit and create a Demo API key with trading permission. Demo Trading and Testnet are separate environments. Use a dedicated Demo account without manual trading or other bots.
2. Set **one-way** position mode for linear USDT perpetuals. Configure margin/leverage in the Demo UI beforehand; the bot does not change them. Fund the virtual USDT balance.
3. Inject `BYBIT_DEMO_API_KEY` and `BYBIT_DEMO_API_SECRET` securely into the process environment. Never put values into the repository, reports or chat. `.env` is not automatically loaded. HMAC signing requires the actual secret inside the process; HTTPS proxy substitution cannot replace that injection.
4. Start with a single iteration:

```bash
python -m dual_futures_bot --exchange bybit --mode bybit-demo --symbol BTC/USDT:USDT --timeframe 15m --limit 200 --equity 1000 --cycles 1 --state reports/demo-bybit.json
```

Remove `--cycles 1` for continuous polling. Orders require a fresh signal, so no trade is not necessarily an error. All private API calls target `api-demo.bybit.com`, checked before submission. There is no real-money mode.

## Demo execution and risk

Entries are market orders with quantity rounded to exchange precision. Sizing equity is the smaller of the account's total USDT equity and `--equity`. Risk is 0.25%, maximum notional 25% of that base, stop distance 2×ATR. Orders below exchange minimums are rejected locally rather than increasing risk. A Bybit stop is attached to entry; after a confirmed fill the position is checked for a stop. Actual fills and fees are determined by the exchange.

An opposite signal closes the position with `reduceOnly`; it does not immediately reverse into a new position on that signal. Demo trailing updates are not implemented: the initial exchange stop remains. A daily account-equity loss of at least 1% from the first poll of the UTC day blocks new entries until the next day; it does not force liquidation of the position. Do not share the account: balance/position reconciliation does not separate other bots' activity.

## Persistence, shutdown and recovery

`--state` stores market, mode, risk settings, processed candle and events. Writes are atomic. Do not reuse a file across different markets/modes. Use separate files per process, but never run two Demo processes on the same account/symbol. A `.lock` file prevents concurrent use of one path. After a crash, remove a stale lock only after verifying the process has stopped.

Ctrl+C stops polling; **it does not close Demo positions or cancel orders**. Inspect them in Bybit. Paper positions persist and resume on restart. Paper stops do not run while stopped; an accepted Demo stop remains on the exchange.

Network errors stop the process. Before order submission a `pending_order` containing `client_id` is persisted. Timeouts, unknown statuses or unconfirmed stops never trigger an automatic retry. Locate the order by this ID in Bybit and reconcile fills, position, stop and open orders. Only after reconciliation and stopping the process, back up the JSON and set `pending_order` to `null`. Do not delete the whole state, which could replay a signal. Protect or close any position with an unconfirmed stop through the Demo UI first.

Missed signals during downtime are not replayed: only the latest closed candle is analyzed. Demo events store order IDs/statuses rather than complete accounting; inspect fills and PnL in Bybit. The JSON journal grows indefinitely; long-running deployments need separate storage.

## Connectivity and validation

Allow HTTPS to `api-demo.bybit.com` and `api.bybit.com`; CCXT metadata may require additional hosts. Keep TLS verification enabled. This cloud has network restrictions and no Demo keys. Offline logic and mocked API adapter tests pass, but actual market retrieval/Demo order submission remain unverified. Start with small virtual equity and inspect results in the Bybit UI.

Telegram: [Setup / Настройка](TELEGRAM.en.md)

## Bybit quote timestamp fix

CCXT may return a Bybit ticker with a price but no timestamp. The bot then retrieves the order book and uses the best bid/ask midpoint with the book's exchange timestamp. Analysis reports `quote_source` as `orderbook_midpoint` or `ticker_last`. This is a sizing reference, not a guaranteed fill price. Quotes older than 60 seconds, in the future, missing exchange time or with invalid books are rejected. Local receipt time never replaces exchange time. If freshness checks still fail, verify automatic system clock synchronization and network latency.

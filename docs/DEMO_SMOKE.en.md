# Bybit Demo entry/exit smoke test

Complete current installation, configuration and operations guide: [MANUAL.en.md](MANUAL.en.md).

[Complete step-by-step Mac setup guide](START_HERE.en.md)

[Русский](DEMO_SMOKE.ru.md)

One execution test without EMA/ATR signals: a market long entry followed by a reduce-only market exit for the observed position size. Bybit Demo Trading only; real-money execution is unsupported.

1. Stop all strategy processes using Ctrl+C. Confirm no positions/open orders on the chosen symbol. Do not use other bots or manual trading on that symbol during the test. This test does not automatically lock a separate strategy process.
2. Activate the environment and provide `BYBIT_DEMO_API_KEY` and `BYBIT_DEMO_API_SECRET` as documented. Use one-way mode and a linear USDT perpetual. Leverage/margin settings remain unchanged.
3. Run:

```bash
python -m dual_futures_bot.demo_smoke --execute --max-notional 250
```

The smallest metadata-compliant size is rounded up to the contract step, with a small buffer over minimum cost. Reference notional must fit the smaller of 250 USDT and 25% of free Demo USDT. You can lower `--max-notional`, but cannot exceed 250. This caps reference notional, not spending or actual fills: slippage can change execution cost. Fees/margin are determined by the exchange. For example, a 100 USDT minimum and 0.001 BTC step at 80000 require 0.002 BTC, or 160 USDT. If the minimum exceeds the cap, no entry is sent.

The entry includes a protective stop 2% below reference price. After terminal entry status and an observed position, a reduce-only market exit is sent immediately. API latency separates the orders; this is not atomic. Stop acceptance depends on Bybit and does not replace manual reconciliation after errors.

Expected result:

```text
DEMO ROUNDTRIP OK: no position and no open orders for this symbol.
```

`reports/demo-smoke.json` should show `stage: completed_flat`; Bybit Demo should show entry and exit fills. Consult the exchange for exact PnL. This tests execution/final flatness, not profitability. Telegram is not used for this test.

## Recovery and reruns

Stage/client ID are persisted before each order. Ambiguous/network errors never automatically resubmit orders. Only status and position reads are polled up to 10 times. After interruption/failure a position may remain: immediately inspect positions, stops, open orders and fills in Bybit Demo and close manually if required.

Journal creation is exclusive: an existing file blocks reruns. Do not delete it to bypass errors. Reconcile the exchange first. After a fully completed test and verifying no position/orders, another test can use a new journal:

```bash
python -m dual_futures_bot.demo_smoke --execute --max-notional 250 --journal reports/demo-smoke-2.json
```

Never run simultaneous tests with different journals. If no position is observed after entry (for example, a rapid stop), the test halts for reconciliation rather than reentering or claiming a successful roundtrip exit.

Offline tests cover the roundtrip, reduce-only exit, live endpoint rejection, preexisting positions, size caps and no resubmission after timeout. Actual Demo execution has not run in the cloud because working credentials are on the user's computer.

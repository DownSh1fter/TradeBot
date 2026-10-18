# Telegram notifications

[New single-command operation and trend-pullback policy](REWORK.en.md). Older commands below retain ema-cross unless a strategy is selected.

[Complete step-by-step Mac setup guide](START_HERE.en.md)

[Русский](TELEGRAM.ru.md) · [Bybit Demo](REALTIME.en.md)

Notifications work in `realtime-paper` and `bybit-demo`. This integration only sends messages; it accepts no trading commands. Historical backtests do not notify.

## Create your bot

1. Open the verified **@BotFather** in Telegram, send `/newbot`, choose a name and username. Treat the resulting token as a password.
2. Open your new bot and press **Start** or send `/start`.
3. Find your `chat_id`. For a private chat, **@userinfobot** can show your user `Id`; do not share your bot token with it. Groups have their own, usually negative, IDs. Add your bot with permission to send messages. All members of the configured chat can see the account information you send.

## macOS zsh setup

In the same VS Code terminal used to run TradeBot:

```bash
read -s "TELEGRAM_BOT_TOKEN?Telegram bot token: "
export TELEGRAM_BOT_TOKEN
echo
export TELEGRAM_CHAT_ID='123456789'
export TELEGRAM_STATUS_SECONDS='300'
```

Replace `123456789` with your chat ID. Hidden token input avoids command history. Summary interval defaults to 300 seconds, minimum 30. Token and chat ID must both be present to enable notifications; if both are absent the integration is disabled. `.env` is not loaded automatically. Variables entered in one terminal tab are not inherited by another tab.

Test without Bybit credentials or orders:

```bash
python -m dual_futures_bot --exchange bybit --mode realtime-paper --limit 200 --cycles 1 --state reports/telegram-paper.json
```

Expect a starting notification, a summary if market retrieval succeeds, and a completion message. Market failures trigger an error notification instead. Remove `--cycles 1` for continuous operation. Use the Bybit Demo guide's command with these Telegram variables for Demo trading, which can place virtual exchange orders.

## Message contents

- Startup, cycle completion, Ctrl+C and error type; detailed exceptions remain local.
- Summary: symbol/mode, last price, EMA20/50, trend, ATR14, ATR/price, signal/filter, USDT equity and entry-halt status.
- Paper: entry/exit, side, quantity, price, stop and modeled net exit PnL.
- Demo: order ID/status, side, requested/filled amount, average, cost and fee if returned by Bybit. Equity and position are the account reconciliation snapshot before the current cycle's action; the next poll updates them.
- Demo positions: side, contracts, entry/mark price, unrealized PnL, stop and leverage when available. Size/side changes or disappearance trigger a message. Disappearance does not establish the exit reason; consult Bybit executions for exact fills and realized PnL.

Message times are UTC. Headings are bilingual and analysis fields are English. Credentials and raw private API responses are not included. Messages are capped at 4000 characters and can be truncated; original events remain in local state.

## Latency and failures

Trading state is persisted before event notifications. Delivery depends on polling/network latency and is not instantaneous. Synchronous sends can delay the next poll by the request timeout (3 seconds connect/3 seconds read). There is no delivery queue or automatic retry: failed notifications are lost, a local warning is printed, and trading logic continues. Invalid variable configuration before startup stops startup.

A startup/error notification does not establish a successful Bybit connection. Forced termination or powering off may prevent shutdown messages. Telegram neither manages exchange stops nor closes positions.

If messages are missing, check Start, chat ID, token, send permissions and HTTPS access to `api.telegram.org`. Disable with:

```bash
unset TELEGRAM_BOT_TOKEN TELEGRAM_CHAT_ID
```

Tests mock HTTP delivery, throttle summaries, detect position changes and verify token-safe errors. Actual Telegram delivery has not been verified in the cloud because no token/chat ID was supplied.

A position opened and closed entirely between polls may be missed: this integration observes position snapshots, not an exchange execution stream.

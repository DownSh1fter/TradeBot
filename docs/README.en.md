# TradeBot — English guide

Complete current installation, configuration and operations guide: [MANUAL.en.md](MANUAL.en.md).

[New single-command operation and trend-pullback policy](REWORK.en.md). Older commands below retain ema-cross unless a strategy is selected.

[Complete step-by-step Mac setup guide](START_HERE.en.md)

[Русский](README.ru.md) · [Home](../README.md)

See [real-time analysis and Bybit Demo](REALTIME.en.md) for the new polling and Demo execution modes. The historical-mode guide follows.

## Purpose and requirements

This is a historical, paper-only futures simulator, not a continuously running trading service. It downloads public OHLCV candles from Binance or Bybit through CCXT, calculates signals and simulates trades. No account, API key, database or background service is required. Python 3.11+ and HTTPS access to the exchange are required. The two exchanges run separately; this is not an arbitrage bot.

## Installation

```bash
git clone https://github.com/DownSh1fter/TradeBot.git
cd TradeBot
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

On Windows PowerShell use `py -3.11 -m venv .venv` and `.venv\Scripts\Activate.ps1` instead of the creation/activation lines. Run all subsequent commands from the repository root with this environment active.

## Running

```bash
python -m dual_futures_bot --exchange binance --symbol BTC/USDT:USDT --timeframe 15m --limit 1000 --equity 10000
python -m dual_futures_bot --exchange bybit --symbol BTC/USDT:USDT --timeframe 15m --limit 1000 --equity 10000
python -m dual_futures_bot --help
```

| Option | Default | Meaning |
|---|---|---|
| `--exchange` | required | `binance` or `bybit` |
| `--symbol` | `BTC/USDT:USDT` | CCXT unified swap symbol |
| `--timeframe` | `15m` | Exchange-supported candle interval |
| `--limit` | `1000` | Requested candles, 60–1500 |
| `--equity` | `10000` | Positive finite starting equity |

The exchange may return fewer candles or impose a smaller limit. The current unfinished candle is removed; at least 60 closed candles must remain. Try a larger limit if necessary. No pagination is performed.

## How the simulation works

1. EMA(20) crossing above EMA(50) signals long; crossing below signals short. EMA starts from a simple average. ATR(14) uses Wilder smoothing.
2. A signal becomes available after a candle closes. Entry is at the next candle's open with adverse slippage. There is at most one position.
3. The initial stop is 2 × ATR from entry. Quantity is the smaller of `equity × 0.0025 / stop_distance` and `equity × 0.25 / entry_price`. The risk target excludes fees and slippage; gaps can exceed it.
4. An existing stop crossed at the open fills at that open. Otherwise a reversal exits at the open. Intrabar stops apply to both carried positions and new entries, then trailing stops update at the close for the next candle. Long stops only rise; short stops only fall.
5. The simulator charges 0.05% of notional on each side and 0.02% adverse slippage on entry and exit.
6. A realized daily loss of at least 1% of the UTC day's starting realized equity blocks further entries that day. It is not a guaranteed loss cap or an unrealized-loss stop. Remaining positions close at the final candle's close.

Defaults live in `RiskConfig` in `src/dual_futures_bot/simulator.py`; EMA periods are in `strategy.py`. They are Python API settings, not CLI options. Example:

```python
from dual_futures_bot.market_data import fetch_candles
from dual_futures_bot.simulator import RiskConfig, simulate
candles = fetch_candles('bybit', 'BTC/USDT:USDT', '15m', 1000)
report = simulate(candles, RiskConfig(initial_equity=5000, risk_fraction=0.001))
print(report['net_pnl'])
```

## Reports and limitations

JSON is written relative to the current directory: `reports/<exchange>_<symbol>_<timeframe>.json`. Repeating the same combination overwrites that report; copy it elsewhere to keep a run. The console omits the detailed trade list.

Fields include starting/final equity, net PnL and return fraction, trade count, win rate (fraction), fees, halted UTC days and trades with side, prices, quantity, times (Unix milliseconds), net PnL and exit reason. `max_drawdown_fraction` measures realized equity at trade exits, not intratrade mark-to-market drawdown. Multiply fractions by 100 for percentages. Gross PnL is not a separate report field; net PnL plus fees gives PnL before fees, still including slippage.

Funding, liquidation, margin accounting, order-book liquidity, exchange lot sizes and minimum orders are not modeled. Position size assumes linear price PnL; use linear USDT contracts for meaningful units. OHLC candles cannot reproduce the full intrabar price path. Short samples and these assumptions cannot establish future profitability. The historical mode has no order execution or automatic portfolio across exchanges; Bybit Demo execution is documented separately.

## Tests and troubleshooting

```bash
python -m unittest discover -s tests -v
```

Tests work offline and cover core strategy/risk behavior, stop ordering, numeric validation and mocked market data. They do not prove exchange connectivity. GitHub Actions runs the suite on Python 3.11 and 3.12.

For `ModuleNotFoundError`, activate the virtual environment and repeat installation. For invalid contracts/timeframes, check the exchange's supported swap markets. HTTP 403/451, DNS or proxy errors require checking network policy and regional availability; do not disable TLS verification. CCXT loads market metadata before candles, so additional exchange API hosts may be needed. Typical hosts are `api.bybit.com`, `api.binance.com`, `fapi.binance.com`, and `dapi.binance.com`. No keys are needed to fix public-market access.

Cloud validation: offline tests passed, but the onboarding network proxy rejected exchange requests with CONNECT 403. A real-data run remains unverified until network access is allowed.

## Project layout

`market_data.py`: download closed candles; `indicators.py`: EMA/ATR; `strategy.py`: signals; `simulator.py`: sizing/execution/report; `__main__.py`: CLI; `tests/`: offline regression tests.

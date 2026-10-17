# TradeBot / Dual Futures Bot

[Русская документация](docs/README.ru.md) · [English documentation](docs/README.en.md)

Симулятор фьючерсной стратегии EMA/ATR на публичных свечах Binance и Bybit.
Он не отправляет ордера и не требует API-ключей. Каждый запуск выполняет один исторический бэктест одной биржи.

A futures EMA/ATR strategy simulator using public Binance and Bybit candles.
It does not place orders or require API keys. Each invocation runs one historical backtest on one exchange.

Python 3.11+:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e .
python -m unittest discover -s tests -v
python -m dual_futures_bot --exchange bybit --symbol BTC/USDT:USDT --timeframe 15m --limit 1000
```

Windows activation: `.venv\Scripts\Activate.ps1`.

Результаты / Results: `reports/*.json` (ignored by Git).

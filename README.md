# TradeBot / Dual Futures Bot

[Русская документация](docs/README.ru.md) · [English documentation](docs/README.en.md)

Симулятор фьючерсной стратегии EMA/ATR на публичных свечах Binance и Bybit.
Поддерживает бэктест, анализ рынка с paper-сделками и ордера Bybit Demo. Реальной торговли нет.

[Анализатор и Bybit Demo — RU](docs/REALTIME.ru.md) · [Real-time analysis and Bybit Demo — EN](docs/REALTIME.en.md)

A futures EMA/ATR strategy simulator using public Binance and Bybit candles.
Supports backtesting, polling with paper execution and Bybit Demo orders. Real-money trading is not implemented.

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

Telegram: [Настройка на русском](docs/TELEGRAM.ru.md) · [English setup](docs/TELEGRAM.en.md)

Demo execution test: [RU](docs/DEMO_SMOKE.ru.md) · [EN](docs/DEMO_SMOKE.en.md)

Local Ollama observer: [RU](docs/AI.ru.md) · [EN](docs/AI.en.md) (advisory only; no order control).

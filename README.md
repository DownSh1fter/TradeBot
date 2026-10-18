# TradeBot / Dual Futures Bot

**Новый единый запуск, стратегия отката и причины ожидания:** [Русский](docs/REWORK.ru.md)

**Single-command operation, pullback policy and waiting diagnostics:** [English](docs/REWORK.en.md)

Research/Demo only. No profitability established; see [validation evidence](docs/VALIDATION.md).

**Пошаговая установка и запуск на Mac:** [Русский](docs/START_HERE.ru.md)

**Complete Mac setup and operation:** [English](docs/START_HERE.en.md)

От скачивания проекта до Bybit Demo, Telegram и Ollama: команды, ввод ключей, вкладки терминала, обновление и устранение ошибок.

From checkout to Bybit Demo, Telegram and Ollama: exact commands, credential entry, terminal tabs, updates and troubleshooting.

[Описание стратегии / RU](docs/README.ru.md) · [Strategy reference / EN](docs/README.en.md)

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

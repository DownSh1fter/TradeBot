# Local Ollama market observer

Complete current installation, configuration and operations guide: [MANUAL.en.md](MANUAL.en.md).

[New single-command operation and trend-pullback policy](REWORK.en.md). Older commands below retain ema-cross unless a strategy is selected.

[Complete step-by-step Mac setup guide](START_HERE.en.md)

[Русский](AI.ru.md) · [Main guide](README.en.md)

## Implemented scope

A separate process downloads public candles for the selected timeframe and 1h. Features include EMA20/50, ATR, 1/4/16-bar returns and volume relative to the preceding 20 bars. Up to 20 RSS/Atom headlines published within 24 hours are sent to local Ollama along with the market snapshot. Defaults are BBC World and CoinDesk; configure up to five alternative HTTPS feeds. Missing/failed sources are explicit in `news_coverage`.

Output is bullish/bearish/neutral, subjective confidence, a Russian explanation, risks and supporting headline IDs. This is an observer: it has no exchange keys/order tools and does not change trade signals. Headlines are untrusted input, never instructions. JSON validation limits malformed results and invented source IDs; it cannot establish factual correctness.

The existing EMA strategy remains independent. The observer does not browse the entire web, verify full articles, or model funding, the full order book or an economic calendar. Polling defaults to five minutes plus retrieval/inference time. This is not low-latency execution.

## macOS setup

Install and run Ollama from https://ollama.com/download/mac. Check its current macOS requirements; Python installation does not establish Ollama compatibility.

```bash
ollama pull qwen2.5:3b
ollama list
```

This is a small starting model, not a proven trading model. Disk/RAM/CPU/GPU use and speed depend on your Mac. If resources permit, download `qwen2.5:7b` separately and select it with `--model`. No cloud API/subscription is needed, but local resource/electricity costs remain. Requests target local `127.0.0.1:11434` only.

Update the repository while preserving prior state/logs/local changes. Activate/install the new checkout:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --only-binary=cryptography -e .
python -m unittest discover -s tests -v
python -m dual_futures_bot.ai_advisor --exchange bybit --timeframe 15m --cycles 1
```

The binary cryptography option avoids a known macOS source-build issue. A successful report has `status: ok`; errors have `status: error` plus an exception type and replace any prior success. Check Ollama availability/model installation and network access; request bodies/secrets are not logged.

Continuous observation, without orders:

```bash
python -m dual_futures_bot.ai_advisor --exchange bybit --timeframe 15m --model qwen2.5:3b
```

`--interval 300` sets the pause between runs (minimum 60 seconds). Repeat `--feed https://example.org/feed.xml` to replace defaults with up to five actual RSS/Atom URLs. Up to three HTTPS redirects are supported; HTTP downgrades are rejected. Missing/invalid/timezone-free dates, future items and items older than a day are skipped; duplicate headlines are removed. Source failures are visible rather than silently fabricated.

## Display next to trading output

In another terminal activate the same environment. Start with paper mode:

```bash
python -m dual_futures_bot --exchange bybit --mode realtime-paper --timeframe 15m --limit 200 --ai-report reports/ai-advisor.json --state reports/paper-with-ai.json
```

Results appear under `analysis.ai_advisor` and in Telegram summaries when configured. To display alongside the existing Demo strategy, add `--ai-report reports/ai-advisor.json` to its normal command while preserving its original state path. Never run two trading processes on one account/symbol.

Reports use input snapshot time, not generation completion time. Older than ten minutes, mismatched market/timeframe, failed or malformed reports become `unavailable_or_stale`. They neither trigger trades nor stop the baseline strategy. Inference in a separate process does not block paper-stop polling.

Ctrl+C stops only the observer; the report expires after ten minutes. Stopping the trading process does not close exchange positions.

## Evidence and evaluation

`reports/ai-advisor.json` is the latest report. `reports/ai-history.jsonl` records assessments/errors, market inputs, headlines, model and timestamps. Override with `--report`/`--history`; use separate paths per market/process. A lock protects each report path; remove stale locks only after confirming the process stopped. History has no rotation and grows over time. Reports are Git-ignored and contain no API keys.

Confidence is subjective, not a calibrated probability of profitable trading. Models can hallucinate; news can be wrong, irrelevant or priced in. Historical model evaluations may leak future information from training data.

Recommended next steps:

1. Record forward-only baseline performance and parallel AI assessments across market regimes and enough trades; a single smoke trade proves execution only.
2. Compare net PnL, drawdown, fees/funding, turnover, trade count and average result with identical price/cost assumptions.
3. Add measured spread, funding, liquidity and expected-move-versus-cost filters, then regime detection and aggregate risk limits.
4. Only after an independent comparison, test an AI entry filter or separate paper policy without EMA crosses. Neither is implemented here. Baseline strategy PnL cannot measure the observer's contribution because it does not affect orders.

Small profits are not guaranteed; small frequent targets are particularly cost-sensitive.

## Linked project and validation

https://github.com/Alishahryar1/free-claude-code routes providers for coding assistants; it supplies neither market intelligence nor news. Direct Ollama does not require it. Its code/installers were not included or executed.

Offline tests cover response schema, supplied news references, RSS/Atom dates, unavailable feeds, report freshness and tool-free Ollama requests. Actual Ollama inference and live RSS retrieval remain unverified in the cloud. Download/test the model on your Mac. No profitability improvement has been established.

## Slow Ollama / cancellation after two minutes

The early client used a 120-second read timeout. CPU prompt processing plus generation can exceed it. The updated observer prints progress stages, uses a 300-second default Ollama read timeout and a shorter 512-token output budget. HTTP 500 next to a two-minute cancellation can follow client timeout, though other 500 errors require checking server logs.

```bash
python -m dual_futures_bot.ai_advisor --exchange bybit --timeframe 15m --cycles 1 --timeout 480 --max-tokens 512
```

`--timeout` accepts 30–540 seconds for the Ollama response, not total analysis duration. `--max-tokens` accepts 256–2048 (default 512). If the model reaches the output limit, `TruncatedModelResponse` suggests increasing to 768 tokens. A longer timeout does not improve speed. The ten-minute input freshness limit remains enforced.

A smaller model can help: `ollama pull qwen2.5:1.5b`, then select `--model qwen2.5:1.5b`. Smaller models can reason/format less reliably. Avoid concurrent inference/observer processes. Local resource contention is possible, but the trading loop does not wait for inference.

import argparse
import json
import math
import re
from pathlib import Path
from datetime import datetime, timezone

from .market_data import fetch_candles
from .simulator import RiskConfig, simulate


def main() -> None:
    parser = argparse.ArgumentParser(description="Futures backtest, realtime paper analysis and Bybit Demo execution")
    parser.add_argument("--exchange", choices=["binance", "bybit"], required=True)
    parser.add_argument("--symbol", default="BTC/USDT:USDT")
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--equity", type=float, default=10_000)
    parser.add_argument('--mode', choices=['backtest', 'realtime-paper', 'bybit-demo'], default='backtest')
    parser.add_argument('--poll-seconds', type=float, default=10)
    parser.add_argument('--cycles', type=int, default=0, help='Realtime polls; 0 runs until Ctrl+C')
    parser.add_argument('--state', default='reports/realtime-state.json')
    parser.add_argument('--ai-report', help='Optional local Ollama observer report; never changes orders')
    parser.add_argument('--strategy', choices=['ema-cross', 'trend-pullback'], default='ema-cross')
    parser.add_argument('--with-ai', action='store_true', help='Start and own an Ollama observer; never changes signals')
    parser.add_argument('--ai-model', default='qwen2.5:3b')
    parser.add_argument('--ai-timeout', type=int, default=480)
    parser.add_argument('--ai-interval', type=int, default=60)
    parser.add_argument('--ai-max-tokens', type=int, default=512)
    parser.add_argument('--candles-json', help='Backtest only: JSON array of [timestamp, open, high, low, close, volume]')
    parser.add_argument('--fee-rate', type=float, default=.0005, help='Assumed fee fraction per side, e.g. .00055')
    parser.add_argument('--slippage-rate', type=float, default=.0002, help='Assumed adverse slippage fraction per side')
    args = parser.parse_args()
    if not 60 <= args.limit <= 1500:
        parser.error("--limit must be between 60 and 1500")
    if not math.isfinite(args.equity) or args.equity <= 0:
        parser.error("--equity must be positive")

    config = RiskConfig(initial_equity=args.equity, fee_rate=args.fee_rate, slippage_rate=args.slippage_rate)
    try:
        config.validate()
    except ValueError as exc:
        parser.error(str(exc))
    if args.candles_json and args.mode != 'backtest':
        parser.error('--candles-json is for backtest only')
    if args.with_ai and args.mode == 'backtest':
        parser.error('--with-ai is for realtime modes only')
    if not 30 <= args.ai_timeout <= 540 or args.ai_interval < 60 or not 256 <= args.ai_max_tokens <= 2048:
        parser.error('Invalid AI timeout/interval/token budget')
    if args.with_ai and not args.ai_report:
        args.ai_report = 'reports/ai-advisor.json'

    if args.mode in ('realtime-paper', 'bybit-demo'):
        from .realtime import run
        print(json.dumps(dict(role='session', mode=args.mode, strategy=args.strategy, ai_observer=args.with_ai, state=args.state)), flush=True)
        try:
            from .supervisor import advisor_process
            with advisor_process(args.with_ai, args.ai_report, args.exchange, args.symbol, args.timeframe,
                                 args.ai_model, args.ai_timeout, args.ai_interval, args.ai_max_tokens):
                run(args.exchange, args.symbol, args.timeframe, args.limit, args.equity,
                    args.state, args.poll_seconds, args.cycles, demo=args.mode == 'bybit-demo',
                    ai_report=args.ai_report, strategy=args.strategy, risk_config=config)
        except KeyboardInterrupt:
            print('Stopped. State retained. Check Bybit Demo for open positions when using demo mode.')
        return

    if args.candles_json:
        from .models import Candle
        candles = [Candle(*row) for row in json.loads(Path(args.candles_json).read_text())]
    else:
        candles = fetch_candles(args.exchange, args.symbol, args.timeframe, args.limit)
    if len(candles) < 60:
        raise SystemExit(f"Exchange returned only {len(candles)} candles; at least 60 are required.")
    report = simulate(candles, config, strategy=args.strategy)
    report.update({"exchange": args.exchange, "symbol": args.symbol, "timeframe": args.timeframe, "candles": len(candles), "funding_costs": "excluded", "generated_at": datetime.now(timezone.utc).isoformat(), "mode": "paper_only", "strategy": args.strategy})
    path = Path("reports") / f"{args.exchange}_{re.sub(r'[^A-Za-z0-9_-]', '_', args.symbol)}_{re.sub(r'[^A-Za-z0-9_-]', '_', args.timeframe)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "trades"}, indent=2))
    print(f"Full report: {path}")


if __name__ == "__main__":
    main()

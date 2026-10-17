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
    args = parser.parse_args()
    if not 60 <= args.limit <= 1500:
        parser.error("--limit must be between 60 and 1500")
    if not math.isfinite(args.equity) or args.equity <= 0:
        parser.error("--equity must be positive")

    if args.mode in ('realtime-paper', 'bybit-demo'):
        from .realtime import run
        try:
            run(args.exchange, args.symbol, args.timeframe, args.limit, args.equity,
                args.state, args.poll_seconds, args.cycles, demo=args.mode == 'bybit-demo', ai_report=args.ai_report)
        except KeyboardInterrupt:
            print('Stopped. State retained. Check Bybit Demo for open positions when using demo mode.')
        return

    candles = fetch_candles(args.exchange, args.symbol, args.timeframe, args.limit)
    if len(candles) < 60:
        raise SystemExit(f"Exchange returned only {len(candles)} candles; at least 60 are required.")
    report = simulate(candles, RiskConfig(initial_equity=args.equity))
    report.update({"exchange": args.exchange, "symbol": args.symbol, "timeframe": args.timeframe, "candles": len(candles), "funding_costs": "excluded", "generated_at": datetime.now(timezone.utc).isoformat(), "mode": "paper_only"})
    path = Path("reports") / f"{args.exchange}_{re.sub(r'[^A-Za-z0-9_-]', '_', args.symbol)}_{re.sub(r'[^A-Za-z0-9_-]', '_', args.timeframe)}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "trades"}, indent=2))
    print(f"Full report: {path}")


if __name__ == "__main__":
    main()

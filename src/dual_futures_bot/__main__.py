import argparse
import json
import math
import re
from pathlib import Path
from datetime import datetime, timezone

from .market_data import fetch_candles
from .simulator import RiskConfig, simulate


def main() -> None:
    parser = argparse.ArgumentParser(description="Paper-only futures strategy simulator")
    parser.add_argument("--exchange", choices=["binance", "bybit"], required=True)
    parser.add_argument("--symbol", default="BTC/USDT:USDT")
    parser.add_argument("--timeframe", default="15m")
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--equity", type=float, default=10_000)
    args = parser.parse_args()
    if not 60 <= args.limit <= 1500:
        parser.error("--limit must be between 60 and 1500")
    if not math.isfinite(args.equity) or args.equity <= 0:
        parser.error("--equity must be positive")

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

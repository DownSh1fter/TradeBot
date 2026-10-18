"""Compare fixed policies on frozen OHLCV JSON; reports evidence, never selects parameters."""
import argparse
import hashlib
import json
from pathlib import Path

from .models import Candle
from .simulator import RiskConfig, simulate


def compare(rows, equity=1000, fee_rate=.0005, slippage_rate=.0002):
    candles = [Candle(*row) for row in rows]
    if len(candles) < 240:
        raise ValueError('At least 240 candles required for chronological comparison')
    # Both policies have the same warmup and costs. No parameter fitting.
    config = RiskConfig(initial_equity=equity, fee_rate=fee_rate, slippage_rate=slippage_rate)
    config.validate()
    split = len(candles)*2//3
    report = dict(risk_assumptions=vars(config), candles=len(candles), split_index=split, test_starts_at=candles[split].timestamp,
                  validation='Fixed parameters; final third evaluated with up to 200 prior warmup candles; no warmup trades',
                  limitations=['No funding/liquidations', 'No exchange amount/minimum rules',
                               'Model fees/slippage, not actual fills', 'OHLC stop/target ambiguity: stop first'], policies={})
    for strategy in ('ema-cross', 'trend-pullback'):
        report['policies'][strategy] = {}
        for name, sample in [('development', candles[:split]), ('chronological_test', candles[max(0,split-200):])]:
            result = simulate(sample, config, strategy, trade_start_index=min(200,split) if name == 'chronological_test' else 0)
            report['policies'][strategy][name] = {k: v for k, v in result.items() if k != 'trades'}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, help='JSON OHLCV rows from a named, frozen data source')
    parser.add_argument('--output', default='reports/benchmark.json')
    parser.add_argument('--equity', type=float, default=1000)
    parser.add_argument('--fee-rate', type=float, default=.0005)
    parser.add_argument('--slippage-rate', type=float, default=.0002)
    args = parser.parse_args()
    data = Path(args.input).read_bytes()
    report = compare(json.loads(data), args.equity, args.fee_rate, args.slippage_rate)
    report['input_sha256'] = hashlib.sha256(data).hexdigest()
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, allow_nan=False))
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()

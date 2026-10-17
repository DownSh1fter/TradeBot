from .models import Candle


def fetch_candles(exchange_id: str, symbol: str, timeframe: str, limit: int) -> list[Candle]:
    try:
        import ccxt
    except ImportError as exc:
        raise RuntimeError("Install dependencies with: python -m pip install -e .") from exc
    if exchange_id not in {"binance", "bybit"}:
        raise ValueError("exchange must be binance or bybit")
    exchange_class = getattr(ccxt, exchange_id)
    exchange = exchange_class({"enableRateLimit": True, "trust_env": True, "timeout": 20000, "options": {"defaultType": "swap"}})
    try:
        exchange.load_markets()
        market = exchange.market(symbol)
        if not market.get("swap"):
            raise ValueError(f"{symbol} is not a swap contract on {exchange_id}")
        rows = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
        # Ignore the current, unfinished candle; signals require confirmed closes.
        cutoff = exchange.milliseconds() - exchange.parse_timeframe(timeframe) * 1000
        return [Candle(int(t), float(o), float(h), float(l), float(c), float(v)) for t, o, h, l, c, v in rows if t <= cutoff]
    finally:
        close = getattr(exchange, "close", None)
        if close is not None:
            close()

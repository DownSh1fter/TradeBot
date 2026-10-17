from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Signal:
    side: str
    timestamp: int
    reference_price: float
    atr: float


@dataclass
class Trade:
    side: str
    entry_time: int
    exit_time: int
    entry_price: float
    exit_price: float
    quantity: float
    fees: float
    pnl: float
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)

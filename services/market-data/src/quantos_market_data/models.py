"""Exchange-neutral contracts used by the A-share Market Radar."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


def _finite(value: float, field: str) -> None:
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"{field} must be finite")


@dataclass(frozen=True)
class StockQuote:
    symbol: str
    name: str
    exchange: str
    timestamp: datetime
    price: float
    prev_close: float
    change_pct: float
    volume: float
    amount: float
    turnover_rate: float
    volume_ratio: float
    amplitude_pct: float
    change_5m_pct: float = 0.0
    themes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if len(self.symbol) != 6 or not self.symbol.isdigit():
            raise ValueError("symbol must contain six digits")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        if self.exchange not in {"XSHG", "XSHE", "XBSE"}:
            raise ValueError("unsupported A-share exchange")
        for field in (
            "price", "prev_close", "change_pct", "volume", "amount",
            "turnover_rate", "volume_ratio", "amplitude_pct", "change_5m_pct",
        ):
            _finite(float(getattr(self, field)), field)
        if min(self.price, self.prev_close, self.volume, self.amount) < 0:
            raise ValueError("prices, volume, and amount must be non-negative")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "StockQuote":
        timestamp = value["timestamp"]
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return cls(
            symbol=str(value["symbol"]),
            name=str(value["name"]),
            exchange=str(value["exchange"]),
            timestamp=timestamp,
            price=float(value["price"]),
            prev_close=float(value["prev_close"]),
            change_pct=float(value["change_pct"]),
            volume=float(value["volume"]),
            amount=float(value["amount"]),
            turnover_rate=float(value["turnover_rate"]),
            volume_ratio=float(value["volume_ratio"]),
            amplitude_pct=float(value["amplitude_pct"]),
            change_5m_pct=float(value.get("change_5m_pct", 0.0)),
            themes=tuple(sorted(set(map(str, value.get("themes", ()))))),
        )


@dataclass(frozen=True)
class StockAnomaly:
    symbol: str
    name: str
    score: float
    direction: str
    reasons: tuple[str, ...]
    change_pct: float
    amount: float


@dataclass(frozen=True)
class ThemeHeat:
    theme: str
    score: float
    velocity_per_hour: float
    acceleration_per_hour2: float
    stock_count: int
    advancing_ratio: float
    anomaly_count: int
    mean_change_pct: float
    total_amount: float


@dataclass(frozen=True)
class MarketRadarReport:
    schema_version: str
    generated_at: datetime
    source: str
    quote_count: int
    anomalies: tuple[StockAnomaly, ...]
    themes: tuple[ThemeHeat, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["generated_at"] = self.generated_at.isoformat()
        return result

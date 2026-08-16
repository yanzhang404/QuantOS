"""Contracts for the US equity stage of the intraday options radar."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any


def _finite(value: float, field: str) -> None:
    if value != value or value in (float("inf"), float("-inf")):
        raise ValueError(f"{field} must be finite")


@dataclass(frozen=True)
class USEquityBar:
    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int
    vwap: float
    trade_count: int

    def __post_init__(self) -> None:
        if not self.symbol or len(self.symbol) > 15:
            raise ValueError("symbol must be present and at most 15 characters")
        if self.timestamp.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        for field in ("open", "high", "low", "close", "vwap"):
            _finite(float(getattr(self, field)), field)
        if min(self.open, self.high, self.low, self.close, self.vwap) <= 0:
            raise ValueError("bar prices must be positive")
        if self.high < max(self.open, self.close, self.low):
            raise ValueError("high must be the greatest bar price")
        if self.low > min(self.open, self.close, self.high):
            raise ValueError("low must be the smallest bar price")
        if self.volume < 0 or self.trade_count < 0:
            raise ValueError("volume and trade count must be non-negative")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "USEquityBar":
        timestamp = value.get("timestamp", value.get("t"))
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        return cls(
            symbol=str(value.get("symbol", value.get("S", ""))).upper(),
            timestamp=timestamp,
            open=float(value.get("open", value.get("o"))),
            high=float(value.get("high", value.get("h"))),
            low=float(value.get("low", value.get("l"))),
            close=float(value.get("close", value.get("c"))),
            volume=int(value.get("volume", value.get("v", 0))),
            vwap=float(value.get("vwap", value.get("vw"))),
            trade_count=int(value.get("trade_count", value.get("n", 0))),
        )


@dataclass(frozen=True)
class USHeatCandidate:
    symbol: str
    heat_score: float
    underlying_liquidity_score: float
    direction: str
    price: float
    change_1m_pct: float
    change_5m_pct: float
    momentum_acceleration_pct: float
    volume_ratio_5m: float
    dollar_volume_5m: float
    range_pct: float
    vwap_distance_pct: float
    bar_count: int
    option_tradability_status: str = "not_evaluated"


@dataclass(frozen=True)
class USMarketHeatReport:
    schema_version: str
    generated_at: datetime
    source: str
    input_bar_count: int
    tracked_symbols: int
    candidates: tuple[USHeatCandidate, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["generated_at"] = self.generated_at.isoformat()
        return value

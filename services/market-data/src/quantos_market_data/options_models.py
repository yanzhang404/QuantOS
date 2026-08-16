"""Normalized option-chain contracts and tradability reports."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any


@dataclass(frozen=True)
class OptionContractSnapshot:
    contract_symbol: str
    underlying_symbol: str
    expiration_date: date
    option_type: str
    strike_price: float
    bid_price: float
    ask_price: float
    bid_size: int
    ask_size: int
    quote_timestamp: datetime
    latest_trade_price: float | None = None
    daily_volume: int | None = None
    open_interest: int | None = None
    implied_volatility: float | None = None
    delta: float | None = None
    gamma: float | None = None
    theta: float | None = None
    vega: float | None = None
    feed: str = "unknown"

    def __post_init__(self) -> None:
        if not self.contract_symbol or not self.underlying_symbol:
            raise ValueError("contract and underlying symbols are required")
        if self.option_type not in {"call", "put"}:
            raise ValueError("option_type must be call or put")
        if self.quote_timestamp.tzinfo is None:
            raise ValueError("quote_timestamp must be timezone-aware")
        if min(self.strike_price, self.bid_price, self.ask_price) < 0:
            raise ValueError("strike, bid, and ask must be non-negative")
        if self.ask_price and self.bid_price > self.ask_price:
            raise ValueError("bid cannot exceed ask")
        if min(self.bid_size, self.ask_size) < 0:
            raise ValueError("quote sizes must be non-negative")
        if self.daily_volume is not None and self.daily_volume < 0:
            raise ValueError("daily_volume must be non-negative")
        if self.open_interest is not None and self.open_interest < 0:
            raise ValueError("open_interest must be non-negative")

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "OptionContractSnapshot":
        expiration = value["expiration_date"]
        if isinstance(expiration, str):
            expiration = date.fromisoformat(expiration)
        timestamp = value["quote_timestamp"]
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        optional_float = {
            name: None if value.get(name) is None else float(value[name])
            for name in (
                "latest_trade_price", "implied_volatility", "delta", "gamma", "theta", "vega"
            )
        }
        return cls(
            contract_symbol=str(value["contract_symbol"]),
            underlying_symbol=str(value["underlying_symbol"]),
            expiration_date=expiration,
            option_type=str(value["option_type"]),
            strike_price=float(value["strike_price"]),
            bid_price=float(value["bid_price"]),
            ask_price=float(value["ask_price"]),
            bid_size=int(value.get("bid_size", 0)),
            ask_size=int(value.get("ask_size", 0)),
            quote_timestamp=timestamp,
            daily_volume=None if value.get("daily_volume") is None else int(value["daily_volume"]),
            open_interest=None if value.get("open_interest") is None else int(value["open_interest"]),
            feed=str(value.get("feed", "unknown")),
            **optional_float,
        )


@dataclass(frozen=True)
class OptionTradability:
    contract_symbol: str
    option_type: str
    expiration_date: date
    strike_price: float
    score: float
    eligible: bool
    mid_price: float
    spread_pct: float
    quote_age_seconds: float
    daily_volume: int | None
    open_interest: int | None
    implied_volatility: float | None
    delta: float | None
    risk_flags: tuple[str, ...]


@dataclass(frozen=True)
class UnderlyingOptionSelection:
    symbol: str
    heat_score: float
    direction: str
    underlying_price: float
    status: str
    contracts_considered: int
    contracts: tuple[OptionTradability, ...]
    error: str | None = None


@dataclass(frozen=True)
class USOptionsRadarReport:
    schema_version: str
    generated_at: datetime
    equity_source: str
    options_source: str
    underlyings: tuple[UnderlyingOptionSelection, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["generated_at"] = self.generated_at.isoformat()
        for underlying in value["underlyings"]:
            for contract in underlying["contracts"]:
                contract["expiration_date"] = contract["expiration_date"].isoformat()
        return value

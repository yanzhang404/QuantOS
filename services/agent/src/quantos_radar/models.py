"""Validated market-radar.v1 input models."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from .errors import RadarValidationError

SCHEMA_VERSION = "1.0"
SYMBOL_PATTERN = re.compile(r"^[0-9]{6}\.(SH|SZ|BJ)$")


@dataclass(frozen=True, slots=True)
class Catalyst:
    title: str
    source: str
    url: str

    @classmethod
    def from_dict(cls, value: Any) -> Catalyst:
        record = _record(value, "catalyst")
        _exact_keys(record, {"title", "source", "url"}, "catalyst")
        return cls(
            title=_plain(record["title"], "catalyst.title", 240),
            source=_plain(record["source"], "catalyst.source", 80),
            url=_https_url(record["url"], "catalyst.url"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"title": self.title, "source": self.source, "url": self.url}


@dataclass(frozen=True, slots=True)
class RadarStockInput:
    symbol: str
    name: str
    last_price: float
    change_pct: float
    themes: tuple[str, ...]
    signals: tuple[str, ...]
    source_url: str
    observed_at: datetime
    relative_volume: float | None = None
    turnover_pct: float | None = None
    change_30m_pct: float | None = None
    new_high_20d: bool | None = None
    catalyst: Catalyst | None = None

    @classmethod
    def from_dict(cls, value: Any) -> RadarStockInput:
        record = _record(value, "stock")
        required = {
            "symbol",
            "name",
            "last_price",
            "change_pct",
            "themes",
            "signals",
            "source_url",
            "observed_at",
        }
        allowed = required | {
            "relative_volume",
            "turnover_pct",
            "change_30m_pct",
            "new_high_20d",
            "catalyst",
        }
        _allowed_keys(record, required, allowed, "stock")
        symbol = _plain(record["symbol"], "stock.symbol", 16)
        if not SYMBOL_PATTERN.fullmatch(symbol):
            raise RadarValidationError("stock.symbol must be a canonical A-share symbol")
        themes = _string_array(record["themes"], "stock.themes", 1, 8, 40)
        signals = _string_array(record["signals"], "stock.signals", 1, 8, 120)
        new_high = record.get("new_high_20d")
        if new_high is not None and not isinstance(new_high, bool):
            raise RadarValidationError("stock.new_high_20d must be boolean or null")
        catalyst = record.get("catalyst")
        return cls(
            symbol=symbol,
            name=_plain(record["name"], "stock.name", 80),
            last_price=_bounded_number(record["last_price"], "stock.last_price", 0, 1e9, False),
            change_pct=_bounded_number(record["change_pct"], "stock.change_pct", 0, 100, False),
            relative_volume=_optional_number(
                record.get("relative_volume"), "stock.relative_volume", 0, 100
            ),
            turnover_pct=_optional_number(record.get("turnover_pct"), "stock.turnover_pct", 0, 100),
            change_30m_pct=_optional_number(
                record.get("change_30m_pct"), "stock.change_30m_pct", -100, 100
            ),
            new_high_20d=new_high,
            themes=themes,
            signals=signals,
            source_url=_https_url(record["source_url"], "stock.source_url"),
            observed_at=_datetime(record["observed_at"], "stock.observed_at"),
            catalyst=None if catalyst is None else Catalyst.from_dict(catalyst),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "last_price": self.last_price,
            "change_pct": self.change_pct,
            "relative_volume": self.relative_volume,
            "turnover_pct": self.turnover_pct,
            "change_30m_pct": self.change_30m_pct,
            "new_high_20d": self.new_high_20d,
            "themes": list(self.themes),
            "signals": list(self.signals),
            "source_url": self.source_url,
            "observed_at": _isoformat(self.observed_at),
            "catalyst": None if self.catalyst is None else self.catalyst.to_dict(),
        }

    @property
    def has_full_quantitative_coverage(self) -> bool:
        return all(
            value is not None
            for value in (
                self.relative_volume,
                self.turnover_pct,
                self.change_30m_pct,
                self.new_high_20d,
            )
        )


@dataclass(frozen=True, slots=True)
class MarketRadarInput:
    market: str
    as_of: datetime
    status: str
    provider: str
    stocks: tuple[RadarStockInput, ...]

    @classmethod
    def from_dict(cls, value: Any) -> MarketRadarInput:
        record = _record(value, "radar input")
        _exact_keys(
            record,
            {"schema_version", "market", "as_of", "status", "provider", "stocks"},
            "radar input",
        )
        if record["schema_version"] != SCHEMA_VERSION or record["market"] != "CN":
            raise RadarValidationError("radar input version or market is unsupported")
        status = _plain(record["status"], "status", 16)
        if status not in {"complete", "partial", "sample"}:
            raise RadarValidationError("status must be complete, partial, or sample")
        raw_stocks = record["stocks"]
        if not isinstance(raw_stocks, list) or len(raw_stocks) > 100:
            raise RadarValidationError("stocks must be an array with at most 100 items")
        stocks = tuple(RadarStockInput.from_dict(item) for item in raw_stocks)
        if len({stock.symbol for stock in stocks}) != len(stocks):
            raise RadarValidationError("stock symbols must be unique")
        if status == "complete" and any(
            not stock.has_full_quantitative_coverage for stock in stocks
        ):
            raise RadarValidationError("complete radar input requires every heat component")
        as_of = _datetime(record["as_of"], "as_of")
        if any(
            stock.observed_at > as_of + timedelta(minutes=10)
            or stock.observed_at < as_of - timedelta(days=2)
            for stock in stocks
        ):
            raise RadarValidationError("stock observations must be recent and not future")
        return cls(
            market="CN",
            as_of=as_of,
            status=status,
            provider=_plain(record["provider"], "provider", 80),
            stocks=stocks,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "market": self.market,
            "as_of": _isoformat(self.as_of),
            "status": self.status,
            "provider": self.provider,
            "stocks": [stock.to_dict() for stock in self.stocks],
        }


def _record(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise RadarValidationError(f"{field} must be an object")
    return value


def _exact_keys(record: dict[str, Any], expected: set[str], field: str) -> None:
    _allowed_keys(record, expected, expected, field)


def _allowed_keys(
    record: dict[str, Any], required: set[str], allowed: set[str], field: str
) -> None:
    missing = required - record.keys()
    unknown = record.keys() - allowed
    if missing:
        raise RadarValidationError(f"{field} missing fields: {sorted(missing)}")
    if unknown:
        raise RadarValidationError(f"{field} has unknown fields: {sorted(unknown)}")


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RadarValidationError(f"{field} must be a number")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise RadarValidationError(f"{field} must be finite")
    return parsed


def _bounded_number(
    value: Any, field: str, minimum: float, maximum: float, include_minimum: bool = True
) -> float:
    parsed = _finite_number(value, field)
    valid_minimum = parsed >= minimum if include_minimum else parsed > minimum
    if not valid_minimum or parsed > maximum:
        raise RadarValidationError(f"{field} is outside its supported range")
    return parsed


def _optional_number(value: Any, field: str, minimum: float, maximum: float) -> float | None:
    return None if value is None else _bounded_number(value, field, minimum, maximum)


def _plain(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str):
        raise RadarValidationError(f"{field} must be bounded plain text")
    parsed = " ".join(value.split())
    if (
        not parsed
        or len(parsed) > maximum
        or any(character in parsed for character in ("\n", "\r", "`", "<", ">"))
    ):
        raise RadarValidationError(f"{field} must be bounded plain text")
    return parsed


def _string_array(
    value: Any, field: str, minimum: int, maximum: int, string_maximum: int
) -> tuple[str, ...]:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise RadarValidationError(f"{field} has an invalid item count")
    parsed = tuple(_plain(item, f"{field}[]", string_maximum) for item in value)
    if len(set(parsed)) != len(parsed):
        raise RadarValidationError(f"{field} must contain unique items")
    return parsed


def _datetime(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or len(value) > 64:
        raise RadarValidationError(f"{field} must be an ISO-8601 timestamp")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise RadarValidationError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise RadarValidationError(f"{field} requires a timezone")
    return parsed.astimezone(UTC)


def _https_url(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise RadarValidationError(f"{field} must be an HTTPS URL")
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    ):
        raise RadarValidationError(f"{field} must be an HTTPS URL")
    return value


def _isoformat(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

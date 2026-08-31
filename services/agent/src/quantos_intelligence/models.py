"""Validated intelligence.v1 input models."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from .errors import IntelligenceValidationError

SCHEMA_VERSION = "1.0"
FACTOR_KEYS = frozenset(
    {
        "crypto_volatility",
        "options_positioning",
        "perpetual_positioning",
        "momentum_volume",
        "liquidation_balance",
        "market_breadth",
        "macro_risk",
    }
)


@dataclass(frozen=True, slots=True)
class FactorObservation:
    key: str
    raw_value: float
    unit: str
    percentile: float
    source: str
    observed_at: datetime

    @classmethod
    def from_dict(cls, value: Any) -> FactorObservation:
        record = _record(value, "factor")
        _exact_keys(
            record,
            {"key", "raw_value", "unit", "percentile", "source", "observed_at"},
            "factor",
        )
        key = _bounded_string(record["key"], "factor.key", 64)
        if key not in FACTOR_KEYS:
            raise IntelligenceValidationError(f"unsupported factor key: {key}")
        return cls(
            key=key,
            raw_value=_finite_number(record["raw_value"], "factor.raw_value"),
            unit=_bounded_string(record["unit"], "factor.unit", 32),
            percentile=_bounded_number(record["percentile"], "factor.percentile", 0, 1),
            source=_https_url(record["source"], "factor.source"),
            observed_at=_datetime(record["observed_at"], "factor.observed_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "raw_value": self.raw_value,
            "unit": self.unit,
            "percentile": self.percentile,
            "source": self.source,
            "observed_at": _isoformat(self.observed_at),
        }


@dataclass(frozen=True, slots=True)
class NewsItem:
    id: str
    title: str
    summary: str
    url: str
    source: str
    published_at: datetime
    assets: tuple[str, ...]
    sentiment: float
    confidence: float
    relevance: float
    title_zh: str | None = None
    summary_zh: str | None = None

    @classmethod
    def from_dict(cls, value: Any) -> NewsItem:
        record = _record(value, "news")
        required = {
            "id",
            "title",
            "summary",
            "url",
            "source",
            "published_at",
            "assets",
            "sentiment",
            "confidence",
            "relevance",
        }
        _allowed_keys(record, required, required | {"title_zh", "summary_zh"}, "news")
        assets = record["assets"]
        if not isinstance(assets, list) or not 1 <= len(assets) <= 8:
            raise IntelligenceValidationError("news.assets must contain 1 to 8 assets")
        normalized_assets = tuple(
            _bounded_string(asset, "news.assets[]", 20).upper() for asset in assets
        )
        if len(set(normalized_assets)) != len(normalized_assets):
            raise IntelligenceValidationError("news.assets must be unique")
        return cls(
            id=_bounded_string(record["id"], "news.id", 128),
            title=_bounded_string(record["title"], "news.title", 240),
            summary=_bounded_string(record["summary"], "news.summary", 600),
            title_zh=_optional_string(record.get("title_zh"), "news.title_zh", 240),
            summary_zh=_optional_string(record.get("summary_zh"), "news.summary_zh", 600),
            url=_https_url(record["url"], "news.url"),
            source=_bounded_string(record["source"], "news.source", 80),
            published_at=_datetime(record["published_at"], "news.published_at"),
            assets=normalized_assets,
            sentiment=_bounded_number(record["sentiment"], "news.sentiment", -1, 1),
            confidence=_bounded_number(record["confidence"], "news.confidence", 0, 1),
            relevance=_bounded_number(record["relevance"], "news.relevance", 0, 1),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "summary": self.summary,
            **({"title_zh": self.title_zh} if self.title_zh else {}),
            **({"summary_zh": self.summary_zh} if self.summary_zh else {}),
            "url": self.url,
            "source": self.source,
            "published_at": _isoformat(self.published_at),
            "assets": list(self.assets),
            "sentiment": self.sentiment,
            "confidence": self.confidence,
            "relevance": self.relevance,
        }


@dataclass(frozen=True, slots=True)
class DailyIntelligenceInput:
    date: date
    as_of: datetime
    status: str
    factors: tuple[FactorObservation, ...]
    news: tuple[NewsItem, ...]
    previous_score: float | None = None

    @classmethod
    def from_dict(cls, value: Any) -> DailyIntelligenceInput:
        record = _record(value, "daily input")
        required = {"schema_version", "date", "as_of", "status", "factors", "news"}
        _allowed_keys(record, required, required | {"previous_score"}, "daily input")
        if record["schema_version"] != SCHEMA_VERSION:
            raise IntelligenceValidationError("schema_version must be 1.0")
        parsed_date = _date(record["date"])
        as_of = _datetime(record["as_of"], "as_of")
        if as_of.date() != parsed_date:
            raise IntelligenceValidationError("date must match the UTC as_of date")
        status = _bounded_string(record["status"], "status", 16)
        if status not in {"complete", "partial", "sample"}:
            raise IntelligenceValidationError("status must be complete, partial, or sample")
        raw_factors = record["factors"]
        if not isinstance(raw_factors, list):
            raise IntelligenceValidationError("factors must be an array")
        factors = tuple(FactorObservation.from_dict(item) for item in raw_factors)
        keys = [factor.key for factor in factors]
        if len(factors) != len(FACTOR_KEYS) or set(keys) != FACTOR_KEYS:
            raise IntelligenceValidationError("factors must contain every methodology factor once")
        if len(keys) != len(set(keys)):
            raise IntelligenceValidationError("factor keys must be unique")
        raw_news = record["news"]
        if not isinstance(raw_news, list) or len(raw_news) > 100:
            raise IntelligenceValidationError("news must be an array with at most 100 items")
        news = tuple(NewsItem.from_dict(item) for item in raw_news)
        if len({item.id for item in news}) != len(news):
            raise IntelligenceValidationError("news ids must be unique")
        if any(
            factor.observed_at > as_of + timedelta(minutes=5)
            or factor.observed_at < as_of - timedelta(days=7)
            for factor in factors
        ):
            raise IntelligenceValidationError("factor observations must be recent and not future")
        if any(
            item.published_at > as_of + timedelta(minutes=5)
            or item.published_at < as_of - timedelta(days=7)
            for item in news
        ):
            raise IntelligenceValidationError("news must be recent and not future")
        previous = record.get("previous_score")
        return cls(
            date=parsed_date,
            as_of=as_of,
            status=status,
            factors=factors,
            news=news,
            previous_score=(
                None if previous is None else _bounded_number(previous, "previous_score", 0, 100)
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "date": self.date.isoformat(),
            "as_of": _isoformat(self.as_of),
            "status": self.status,
            "factors": [factor.to_dict() for factor in self.factors],
            "news": [item.to_dict() for item in self.news],
            "previous_score": self.previous_score,
        }


def _record(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise IntelligenceValidationError(f"{field} must be an object")
    return value


def _exact_keys(record: dict[str, Any], expected: set[str], field: str) -> None:
    _allowed_keys(record, expected, expected, field)


def _allowed_keys(
    record: dict[str, Any], required: set[str], allowed: set[str], field: str
) -> None:
    missing = required - record.keys()
    unknown = record.keys() - allowed
    if missing:
        raise IntelligenceValidationError(f"{field} missing fields: {sorted(missing)}")
    if unknown:
        raise IntelligenceValidationError(f"{field} has unknown fields: {sorted(unknown)}")


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise IntelligenceValidationError(f"{field} must be a number")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise IntelligenceValidationError(f"{field} must be finite")
    return parsed


def _bounded_number(value: Any, field: str, minimum: float, maximum: float) -> float:
    parsed = _finite_number(value, field)
    if not minimum <= parsed <= maximum:
        raise IntelligenceValidationError(f"{field} must be between {minimum} and {maximum}")
    return parsed


def _bounded_string(value: Any, field: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise IntelligenceValidationError(f"{field} must be a non-empty string <= {maximum}")
    parsed = value.strip()
    if any(character in parsed for character in ("\n", "\r", "`", "<", ">")):
        raise IntelligenceValidationError(f"{field} must be bounded plain text")
    return parsed


def _optional_string(value: Any, field: str, maximum: int) -> str | None:
    if value is None:
        return None
    return _bounded_string(value, field, maximum)


def _https_url(value: Any, field: str) -> str:
    parsed_value = _bounded_string(value, field, 2048)
    parsed = urlsplit(parsed_value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise IntelligenceValidationError(f"{field} must be an HTTPS URL")
    if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        raise IntelligenceValidationError(f"{field} must not target localhost")
    return parsed_value


def _datetime(value: Any, field: str) -> datetime:
    text = _bounded_string(value, field, 64)
    normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise IntelligenceValidationError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None:
        raise IntelligenceValidationError(f"{field} must include a timezone")
    return parsed.astimezone(UTC)


def _date(value: Any) -> date:
    text = _bounded_string(value, "date", 10)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise IntelligenceValidationError("date must be ISO-8601") from exc


def _isoformat(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

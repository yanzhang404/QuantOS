"""Allow-listed public collectors for current intelligence.v1 inputs."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

from .errors import IntelligenceError, IntelligenceValidationError
from .models import FACTOR_KEYS, DailyIntelligenceInput, FactorObservation, NewsItem

DERIBIT = "https://www.deribit.com/api/v2"
BINANCE_SPOT = "https://api.binance.com"
BINANCE_FUTURES = "https://fapi.binance.com"
VIX_HISTORY = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
COINDESK_RSS = "https://www.coindesk.com/arc/outboundfeeds/rss"
USER_AGENT = "QuantOS-Research/0.5 public-read-only collector"
MAX_RESPONSE_BYTES = 4 << 20
MIN_HISTORY = 30
_BREADTH_SYMBOLS = (
    "BTCUSDT",
    "ETHUSDT",
    "BNBUSDT",
    "SOLUSDT",
    "XRPUSDT",
    "ADAUSDT",
    "DOGEUSDT",
    "AVAXUSDT",
    "LINKUSDT",
    "DOTUSDT",
)


@dataclass(frozen=True, slots=True)
class RawFactor:
    key: str
    value: float
    unit: str
    source: str
    observed_at: datetime


class ObservationHistory:
    def __init__(self, root: Path) -> None:
        self.root = root

    def record(
        self, factors: tuple[RawFactor, ...], date_key: str
    ) -> tuple[dict[str, float], bool, tuple[RawFactor, ...]]:
        records = self._read()
        try:
            parsed_date = date.fromisoformat(date_key)
        except ValueError as exc:
            raise IntelligenceValidationError("observation date must be ISO-8601") from exc
        if parsed_date.isoformat() != date_key:
            raise IntelligenceValidationError("observation date must be canonical ISO-8601")
        factor_records = {factor.key: _history_record(factor) for factor in factors}
        if len(factor_records) != len(factors) or set(factor_records) != FACTOR_KEYS:
            raise IntelligenceValidationError("daily observations must contain every factor once")
        existing = next((item for item in records if item["date"] == date_key), None)
        if existing is None:
            records.append({"date": date_key, "factors": factor_records})
        else:
            factor_records = existing["factors"]
        records = sorted(records, key=lambda item: item["date"])[-730:]
        self._write(records)
        pinned = tuple(_raw_factor(key, factor_records[key]) for key in sorted(factor_records))
        values = {factor.key: factor.value for factor in pinned}
        if len(records) < MIN_HISTORY:
            return dict.fromkeys(values, 0.5), False, pinned
        percentiles = {
            key: sum(float(item["factors"][key]["value"]) <= value for item in records)
            / len(records)
            for key, value in values.items()
        }
        return percentiles, True, pinned

    def _read(self) -> list[dict[str, Any]]:
        path = self.root / "observations.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except (OSError, json.JSONDecodeError) as exc:
            raise IntelligenceValidationError("observation history is invalid") from exc
        if not isinstance(raw, list) or len(raw) > 730:
            raise IntelligenceValidationError("observation history is invalid")
        dates: set[str] = set()
        for item in raw:
            if (
                not isinstance(item, dict)
                or set(item) != {"date", "factors"}
                or not isinstance(item["date"], str)
                or item["date"] in dates
                or not isinstance(item["factors"], dict)
                or set(item["factors"]) != FACTOR_KEYS
            ):
                raise IntelligenceValidationError("observation history is invalid")
            try:
                parsed_date = date.fromisoformat(item["date"])
                for key, value in item["factors"].items():
                    _raw_factor(key, value)
            except (TypeError, ValueError, IntelligenceValidationError) as exc:
                raise IntelligenceValidationError("observation history is invalid") from exc
            if parsed_date.isoformat() != item["date"]:
                raise IntelligenceValidationError("observation history is invalid")
            dates.add(item["date"])
        return raw

    def _write(self, records: list[dict[str, Any]]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".observations.", dir=self.root)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(records, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.root / "observations.json")
        finally:
            temporary.unlink(missing_ok=True)


class PublicIntelligenceCollector:
    def __init__(self, client: httpx.Client, history: ObservationHistory) -> None:
        self.client = client
        self.history = history

    def collect(
        self,
        *,
        as_of: datetime,
        previous_score: float | None = None,
    ) -> DailyIntelligenceInput:
        if as_of.tzinfo is None:
            raise IntelligenceValidationError("as_of must include a timezone")
        as_of = as_of.astimezone(UTC)
        raw = (
            self._crypto_volatility(as_of),
            self._options_positioning(as_of),
            self._perpetual_positioning(as_of),
            self._momentum_volume(as_of),
            self._liquidation_proxy(as_of),
            self._market_breadth(as_of),
            self._macro_risk(as_of),
        )
        if any(
            factor.observed_at > as_of + timedelta(minutes=5)
            or factor.observed_at < as_of - timedelta(days=5)
            for factor in raw
        ):
            raise IntelligenceError("public factor observation is stale or future-dated")
        news = self._news(as_of)
        percentiles, calibrated, pinned = self.history.record(raw, as_of.date().isoformat())
        factors: list[FactorObservation] = []
        for factor in pinned:
            factors.append(
                FactorObservation(
                    key=factor.key,
                    raw_value=factor.value,
                    unit=factor.unit,
                    percentile=percentiles[factor.key],
                    source=factor.source,
                    observed_at=factor.observed_at,
                )
            )
        daily = DailyIntelligenceInput(
            date=as_of.date(),
            as_of=as_of,
            status="complete" if calibrated else "partial",
            factors=tuple(factors),
            news=news,
            previous_score=previous_score,
        )
        return DailyIntelligenceInput.from_dict(daily.to_dict())

    def _crypto_volatility(self, as_of: datetime) -> RawFactor:
        payload = self._json(
            f"{DERIBIT}/public/get_volatility_index_data",
            {
                "currency": "BTC",
                "start_timestamp": int((as_of - timedelta(days=3)).timestamp() * 1000),
                "end_timestamp": int(as_of.timestamp() * 1000),
                "resolution": "1D",
            },
        )
        rows = payload.get("result", {}).get("data", [])
        row = _last_list(rows, 5, "Deribit DVOL")
        return RawFactor(
            "crypto_volatility",
            _number(row[4], "Deribit DVOL close"),
            "DVOL",
            f"{DERIBIT}/public/get_volatility_index_data",
            _milliseconds(row[0]),
        )

    def _options_positioning(self, as_of: datetime) -> RawFactor:
        payload = self._json(
            f"{DERIBIT}/public/get_book_summary_by_currency",
            {"currency": "BTC", "kind": "option"},
        )
        rows = payload.get("result")
        if not isinstance(rows, list) or not rows:
            raise IntelligenceError("Deribit option summary is empty")
        puts = calls = 0.0
        for row in rows:
            if not isinstance(row, dict):
                raise IntelligenceError("Deribit option summary is invalid")
            name = row.get("instrument_name")
            interest = _number(row.get("open_interest"), "Deribit option open interest")
            if isinstance(name, str) and name.endswith("-P"):
                puts += interest
            elif isinstance(name, str) and name.endswith("-C"):
                calls += interest
        if calls <= 0:
            raise IntelligenceError("Deribit option call open interest is zero")
        return RawFactor(
            "options_positioning",
            puts / calls,
            "put/call open interest",
            f"{DERIBIT}/public/get_book_summary_by_currency",
            as_of,
        )

    def _perpetual_positioning(self, as_of: datetime) -> RawFactor:
        rows = self._json(
            f"{BINANCE_FUTURES}/fapi/v1/fundingRate",
            {"symbol": "BTCUSDT", "limit": 1},
        )
        row = _last_dict(rows, "Binance funding")
        return RawFactor(
            "perpetual_positioning",
            _number(row.get("fundingRate"), "Binance funding rate"),
            "funding rate",
            f"{BINANCE_FUTURES}/fapi/v1/fundingRate",
            _milliseconds(row.get("fundingTime")),
        )

    def _momentum_volume(self, as_of: datetime) -> RawFactor:
        rows = self._json(
            f"{BINANCE_SPOT}/api/v3/klines",
            {"symbol": "BTCUSDT", "interval": "1d", "limit": 9},
        )
        if not isinstance(rows, list) or any(
            not isinstance(row, list) or len(row) < 8 for row in rows
        ):
            raise IntelligenceError("Binance daily Klines are incomplete")
        rows = [
            row for row in rows if _number(row[6], "Binance close time") <= as_of.timestamp() * 1000
        ]
        if len(rows) < 8:
            raise IntelligenceError("Binance closed daily Klines are incomplete")
        rows = rows[-8:]
        base = _number(rows[0][4], "Binance first close")
        latest = _number(rows[-1][4], "Binance latest close")
        volumes = [_number(row[7], "Binance quote volume") for row in rows]
        volume_ratio = volumes[-1] / (sum(volumes[:-1]) / len(volumes[:-1]))
        value = (latest / base - 1) * min(2.0, max(0.5, volume_ratio))
        return RawFactor(
            "momentum_volume",
            value,
            "volume-adjusted 7d return",
            f"{BINANCE_SPOT}/api/v3/klines",
            _milliseconds(rows[-1][6]),
        )

    def _liquidation_proxy(self, as_of: datetime) -> RawFactor:
        rows = self._json(
            f"{BINANCE_FUTURES}/futures/data/takerlongshortRatio",
            {"symbol": "BTCUSDT", "period": "1d", "limit": 1},
        )
        row = _last_dict(rows, "Binance taker ratio")
        return RawFactor(
            "liquidation_balance",
            _number(row.get("buySellRatio"), "Binance buy/sell ratio") - 1,
            "taker imbalance proxy",
            f"{BINANCE_FUTURES}/futures/data/takerlongshortRatio",
            _milliseconds(row.get("timestamp")),
        )

    def _market_breadth(self, as_of: datetime) -> RawFactor:
        rows = self._json(
            f"{BINANCE_SPOT}/api/v3/ticker/24hr",
            {"symbols": json.dumps(_BREADTH_SYMBOLS, separators=(",", ":"))},
        )
        if not isinstance(rows, list) or len(rows) != len(_BREADTH_SYMBOLS):
            raise IntelligenceError("Binance breadth universe is incomplete")
        if any(not isinstance(row, dict) for row in rows):
            raise IntelligenceError("Binance breadth response is invalid")
        advancing = sum(
            _number(row.get("priceChangePercent"), "Binance price change") > 0
            for row in rows
            if isinstance(row, dict)
        )
        return RawFactor(
            "market_breadth",
            advancing / len(_BREADTH_SYMBOLS),
            "advancing share",
            f"{BINANCE_SPOT}/api/v3/ticker/24hr",
            as_of,
        )

    def _macro_risk(self, as_of: datetime) -> RawFactor:
        text = self._text(VIX_HISTORY)
        rows = list(csv.DictReader(io.StringIO(text)))
        valid = [
            (row, _csv_date(row.get("DATE")))
            for row in rows
            if _csv_date(row.get("DATE")) <= as_of.date()
        ]
        if not valid:
            raise IntelligenceError("Cboe VIX history is empty")
        latest, latest_date = max(valid, key=lambda item: item[1])
        observed = datetime.combine(latest_date, datetime.min.time(), tzinfo=UTC)
        return RawFactor(
            "macro_risk",
            _number(latest.get("CLOSE"), "Cboe VIX close"),
            "VIX",
            VIX_HISTORY,
            observed,
        )

    def _news(self, as_of: datetime) -> tuple[NewsItem, ...]:
        root = ET.fromstring(self._bytes(COINDESK_RSS))
        items: list[NewsItem] = []
        for element in root.findall(".//item")[:40]:
            title = _plain_text(element.findtext("title"), 240)
            link = _safe_news_url(element.findtext("link"))
            published = parsedate_to_datetime(element.findtext("pubDate") or "").astimezone(UTC)
            if published > as_of + timedelta(minutes=5) or published < as_of - timedelta(hours=48):
                continue
            sentiment = _headline_sentiment(title)
            digest = hashlib.sha256(f"{title}\n{link}".encode()).hexdigest()[:16]
            items.append(
                NewsItem(
                    id=f"coindesk-{digest}",
                    title=title,
                    summary=(
                        "Source-linked headline from CoinDesk; open the original article "
                        "for context."
                    ),
                    url=link,
                    source="CoinDesk RSS",
                    published_at=published,
                    assets=_assets(title),
                    sentiment=sentiment,
                    confidence=0.45,
                    relevance=0.75,
                )
            )
            if len(items) == 20:
                break
        return tuple(items)

    def _json(self, url: str, params: dict[str, Any]) -> Any:
        try:
            return json.loads(self._bytes(url, params=params))
        except json.JSONDecodeError as exc:
            raise IntelligenceError("public collector returned invalid JSON") from exc

    def _text(self, url: str) -> str:
        return self._bytes(url).decode("utf-8-sig")

    def _bytes(self, url: str, *, params: dict[str, Any] | None = None) -> bytes:
        _allowed_url(url)
        try:
            response = self.client.get(url, params=params, headers={"User-Agent": USER_AGENT})
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise IntelligenceError("public collector request failed") from exc
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise IntelligenceError("public collector response is too large")
        _allowed_url(str(response.url).split("?", 1)[0])
        return response.content


def build_public_client() -> httpx.Client:
    return httpx.Client(timeout=httpx.Timeout(15), follow_redirects=False)


def _allowed_url(value: str) -> None:
    parsed = urlsplit(value)
    allowed = {
        ("www.deribit.com", "/api/v2/public/get_volatility_index_data"),
        ("www.deribit.com", "/api/v2/public/get_book_summary_by_currency"),
        ("api.binance.com", "/api/v3/klines"),
        ("api.binance.com", "/api/v3/ticker/24hr"),
        ("fapi.binance.com", "/fapi/v1/fundingRate"),
        ("fapi.binance.com", "/futures/data/takerlongshortRatio"),
        ("cdn.cboe.com", "/api/global/us_indices/daily_prices/VIX_History.csv"),
        ("www.coindesk.com", "/arc/outboundfeeds/rss"),
    }
    if (
        parsed.scheme != "https"
        or parsed.username
        or parsed.password
        or (parsed.hostname, parsed.path) not in allowed
    ):
        raise IntelligenceValidationError("collector URL is not allow-listed")


def _last_list(value: Any, minimum: int, label: str) -> list[Any]:
    if (
        not isinstance(value, list)
        or not value
        or not isinstance(value[-1], list)
        or len(value[-1]) < minimum
    ):
        raise IntelligenceError(f"{label} response is invalid")
    return value[-1]


def _last_dict(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, list) or not value or not isinstance(value[-1], dict):
        raise IntelligenceError(f"{label} response is invalid")
    return value[-1]


def _number(value: Any, label: str) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise IntelligenceError(f"{label} is invalid") from exc
    if not math.isfinite(parsed):
        raise IntelligenceError(f"{label} is invalid")
    return parsed


def _milliseconds(value: Any) -> datetime:
    return datetime.fromtimestamp(_number(value, "timestamp") / 1000, tz=UTC)


def _csv_date(value: Any):
    text = str(value or "").strip()
    for pattern in ("%m/%d/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern).date()
        except ValueError:
            continue
    raise IntelligenceError("Cboe VIX date is invalid")


def _plain_text(value: str | None, maximum: int) -> str:
    text = " ".join((value or "").split())
    if not text or len(text) > maximum or any(character in text for character in ("<", ">", "`")):
        raise IntelligenceError("RSS title is invalid")
    return text


def _safe_news_url(value: str | None) -> str:
    text = (value or "").strip()
    parsed = urlsplit(text)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or not (parsed.hostname == "coindesk.com" or parsed.hostname.endswith(".coindesk.com"))
    ):
        raise IntelligenceError("RSS article URL is invalid")
    return text


def _history_record(factor: RawFactor) -> dict[str, Any]:
    validated = FactorObservation.from_dict(
        {
            "key": factor.key,
            "raw_value": factor.value,
            "unit": factor.unit,
            "percentile": 0.5,
            "source": factor.source,
            "observed_at": factor.observed_at.isoformat(),
        }
    )
    return {
        "value": validated.raw_value,
        "unit": validated.unit,
        "source": validated.source,
        "observed_at": validated.observed_at.isoformat(),
    }


def _raw_factor(key: str, value: Any) -> RawFactor:
    if not isinstance(value, dict) or set(value) != {"value", "unit", "source", "observed_at"}:
        raise IntelligenceValidationError("observation history factor is invalid")
    validated = FactorObservation.from_dict(
        {
            "key": key,
            "raw_value": value["value"],
            "unit": value["unit"],
            "percentile": 0.5,
            "source": value["source"],
            "observed_at": value["observed_at"],
        }
    )
    return RawFactor(
        validated.key,
        validated.raw_value,
        validated.unit,
        validated.source,
        validated.observed_at,
    )


def _headline_sentiment(title: str) -> float:
    words = set(title.lower().replace("-", " ").split())
    positive = {"gain", "gains", "growth", "rally", "record", "approval", "adoption", "surge"}
    negative = {"loss", "losses", "hack", "fraud", "ban", "decline", "drop", "risk", "crash"}
    score = len(words & positive) - len(words & negative)
    return max(-1.0, min(1.0, score / 2))


def _assets(title: str) -> tuple[str, ...]:
    lowered = title.lower()
    assets = []
    if "bitcoin" in lowered or "btc" in lowered:
        assets.append("BTC")
    if "ethereum" in lowered or "ether" in lowered or "eth" in lowered:
        assets.append("ETH")
    return tuple(assets or ["CRYPTO"])

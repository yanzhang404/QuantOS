"""Public Binance USD-M derivatives observations and immutable storage."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import pyarrow as pa
import pyarrow.parquet as pq

from . import __version__
from .errors import ConfigurationError, DatasetError, DownloadError, MarketDataError
from .models import Interval, datetime_to_milliseconds, milliseconds_to_datetime, normalize_symbol

DERIVATIVES_SCHEMA_VERSION = "derivatives-market.v1"
DEFAULT_FUTURES_BASE_URL = "https://fapi.binance.com"
PARQUET_FILE_NAME = "part-00000.parquet"


@dataclass(frozen=True, slots=True)
class FundingRateObservation:
    symbol: str
    funding_time: datetime
    funding_rate: Decimal
    mark_price: Decimal | None
    rate_type: str

    @classmethod
    def from_binance(cls, raw: Any) -> FundingRateObservation:
        if not isinstance(raw, dict):
            raise DownloadError("Binance funding row must be an object")
        try:
            result = cls(
                normalize_symbol(str(raw["symbol"])),
                milliseconds_to_datetime(int(raw["fundingTime"])),
                Decimal(str(raw["fundingRate"])),
                None if raw.get("markPrice") in {None, ""} else Decimal(str(raw["markPrice"])),
                str(raw.get("rateType", "Regular")),
            )
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise DownloadError("invalid Binance funding row") from exc
        _validate_funding(result)
        return result

    def canonical(self) -> list[str | int | None]:
        return [
            self.symbol,
            datetime_to_milliseconds(self.funding_time),
            _decimal_string(self.funding_rate),
            None if self.mark_price is None else _decimal_string(self.mark_price),
            self.rate_type,
        ]


@dataclass(frozen=True, slots=True)
class OpenInterestObservation:
    symbol: str
    period: Interval
    timestamp: datetime
    open_interest: Decimal
    open_interest_value: Decimal

    @classmethod
    def from_binance(cls, raw: Any, period: Interval) -> OpenInterestObservation:
        if not isinstance(raw, dict):
            raise DownloadError("Binance open-interest row must be an object")
        try:
            result = cls(
                normalize_symbol(str(raw["symbol"])),
                period,
                milliseconds_to_datetime(int(raw["timestamp"])),
                Decimal(str(raw["sumOpenInterest"])),
                Decimal(str(raw["sumOpenInterestValue"])),
            )
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise DownloadError("invalid Binance open-interest row") from exc
        _validate_open_interest(result)
        return result

    def canonical(self) -> list[str | int]:
        return [
            self.symbol,
            self.period.value,
            datetime_to_milliseconds(self.timestamp),
            _decimal_string(self.open_interest),
            _decimal_string(self.open_interest_value),
        ]


class BinanceFuturesPublicClient:
    def __init__(
        self,
        *,
        base_url: str = DEFAULT_FUTURES_BASE_URL,
        timeout_seconds: float = 20,
        client: httpx.Client | None = None,
    ) -> None:
        configured = str(client.base_url) if client is not None else base_url
        parsed = urlsplit(configured)
        if (
            parsed.scheme != "https"
            or parsed.netloc != "fapi.binance.com"
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ConfigurationError("futures base URL must be the allow-listed public host")
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=base_url,
            timeout=timeout_seconds,
            headers={"User-Agent": "QuantOS-MarketData/0.5 public-read-only"},
            follow_redirects=False,
        )

    def __enter__(self) -> BinanceFuturesPublicClient:
        return self

    def __exit__(self, *_: object) -> None:
        if self._owns_client:
            self._client.close()

    def fetch_funding(
        self, *, symbol: str, start: datetime, end: datetime
    ) -> list[FundingRateObservation]:
        symbol = normalize_symbol(symbol)
        start_ms, end_ms = _bounds(start, end)
        cursor = start_ms
        result: list[FundingRateObservation] = []
        while cursor < end_ms:
            rows = self._request(
                "/fapi/v1/fundingRate",
                {"symbol": symbol, "startTime": cursor, "endTime": end_ms - 1, "limit": 1000},
            )
            if not rows:
                break
            parsed = [FundingRateObservation.from_binance(row) for row in rows]
            _validate_page_order(parsed, lambda item: item.funding_time)
            result.extend(
                item
                for item in parsed
                if start_ms <= datetime_to_milliseconds(item.funding_time) < end_ms
            )
            next_cursor = datetime_to_milliseconds(parsed[-1].funding_time) + 1
            if next_cursor <= cursor:
                raise DownloadError("funding pagination did not advance")
            cursor = next_cursor
            if len(rows) < 1000:
                break
        return _unique_sorted(result, lambda item: item.funding_time)

    def fetch_open_interest(
        self,
        *,
        symbol: str,
        period: Interval,
        start: datetime,
        end: datetime,
    ) -> list[OpenInterestObservation]:
        symbol = normalize_symbol(symbol)
        start_ms, end_ms = _bounds(start, end)
        if end - start > timedelta(days=31):
            raise ConfigurationError(
                "open-interest requests cannot exceed the public 1-month window"
            )
        cursor = start_ms
        result: list[OpenInterestObservation] = []
        while cursor < end_ms:
            rows = self._request(
                "/futures/data/openInterestHist",
                {
                    "symbol": symbol,
                    "period": period.value,
                    "startTime": cursor,
                    "endTime": end_ms - 1,
                    "limit": 500,
                },
            )
            if not rows:
                break
            parsed = [OpenInterestObservation.from_binance(row, period) for row in rows]
            _validate_page_order(parsed, lambda item: item.timestamp)
            result.extend(
                item
                for item in parsed
                if start_ms <= datetime_to_milliseconds(item.timestamp) < end_ms
            )
            next_cursor = datetime_to_milliseconds(parsed[-1].timestamp) + 1
            if next_cursor <= cursor:
                raise DownloadError("open-interest pagination did not advance")
            cursor = next_cursor
            if len(rows) < 500:
                break
        return _unique_sorted(result, lambda item: item.timestamp)

    def _request(self, path: str, params: dict[str, str | int]) -> list[Any]:
        if path not in {"/fapi/v1/fundingRate", "/futures/data/openInterestHist"}:
            raise ConfigurationError("unsupported futures endpoint")
        try:
            response = self._client.get(path, params=params)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise DownloadError("Binance Futures public request failed") from exc
        if (
            response.url.scheme != "https"
            or response.url.host != "fapi.binance.com"
            or response.url.port not in {None, 443}
        ):
            raise DownloadError("Binance Futures response left the allow-listed host")
        if len(response.content) > 8 << 20:
            raise DownloadError("Binance Futures response is too large")
        try:
            payload = response.json()
        except ValueError as exc:
            raise DownloadError("Binance Futures returned invalid JSON") from exc
        if not isinstance(payload, list):
            raise DownloadError("Binance Futures response must be an array")
        return payload


@dataclass(frozen=True, slots=True)
class DerivativeDatasetManifest:
    dataset_version: str
    schema_version: str
    series: str
    exchange: str
    symbol: str
    period: str | None
    requested_start: str
    requested_end: str
    data_start: str
    data_end: str
    row_count: int
    content_sha256: str
    source: str
    source_limit: str | None
    created_at: str
    producer: str
    file_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PublishedDerivativeDataset:
    path: Path
    manifest: DerivativeDatasetManifest


def download_funding_dataset(
    *,
    symbol: str,
    start: datetime,
    end: datetime,
    data_root: Path,
    now: datetime | None = None,
) -> PublishedDerivativeDataset:
    """Download one public funding range and atomically publish it."""

    with BinanceFuturesPublicClient() as client:
        rows = client.fetch_funding(symbol=symbol, start=start, end=end)
    clock = (lambda: now) if now is not None else (lambda: datetime.now(UTC))
    path, manifest = DerivativeDatasetStore(data_root, now=clock).publish_funding(
        rows,
        requested_start=start,
        requested_end=end,
    )
    return PublishedDerivativeDataset(path, manifest)


def download_open_interest_dataset(
    *,
    symbol: str,
    period: Interval,
    start: datetime,
    end: datetime,
    data_root: Path,
    now: datetime | None = None,
) -> PublishedDerivativeDataset:
    """Download one public open-interest range and atomically publish it."""

    with BinanceFuturesPublicClient() as client:
        rows = client.fetch_open_interest(
            symbol=symbol,
            period=period,
            start=start,
            end=end,
        )
    clock = (lambda: now) if now is not None else (lambda: datetime.now(UTC))
    path, manifest = DerivativeDatasetStore(data_root, now=clock).publish_open_interest(
        rows,
        requested_start=start,
        requested_end=end,
    )
    return PublishedDerivativeDataset(path, manifest)


class DerivativeDatasetStore:
    def __init__(self, root: Path, *, now=lambda: datetime.now(UTC)) -> None:
        self.root = root
        self.now = now

    def publish_funding(
        self,
        rows: list[FundingRateObservation],
        *,
        requested_start: datetime,
        requested_end: datetime,
    ) -> tuple[Path, DerivativeDatasetManifest]:
        for item in rows:
            _validate_funding(item)
        _validate_series(rows, requested_start, requested_end, lambda item: item.funding_time)
        first = rows[0]
        return self._publish(
            rows,
            series="funding-rate",
            symbol=first.symbol,
            period=None,
            requested_start=requested_start,
            requested_end=requested_end,
            source="https://fapi.binance.com/fapi/v1/fundingRate",
            source_limit=None,
            schema=_funding_schema(),
            records=[
                {
                    "symbol": item.symbol,
                    "funding_time": item.funding_time,
                    "funding_rate": item.funding_rate,
                    "mark_price": item.mark_price,
                    "rate_type": item.rate_type,
                }
                for item in rows
            ],
            data_start=first.funding_time,
            data_end=rows[-1].funding_time,
        )

    def publish_open_interest(
        self,
        rows: list[OpenInterestObservation],
        *,
        requested_start: datetime,
        requested_end: datetime,
    ) -> tuple[Path, DerivativeDatasetManifest]:
        for item in rows:
            _validate_open_interest(item)
        _validate_series(rows, requested_start, requested_end, lambda item: item.timestamp)
        first = rows[0]
        if any(item.period != first.period for item in rows):
            raise DatasetError("open-interest periods must be homogeneous")
        return self._publish(
            rows,
            series="open-interest",
            symbol=first.symbol,
            period=first.period.value,
            requested_start=requested_start,
            requested_end=requested_end,
            source="https://fapi.binance.com/futures/data/openInterestHist",
            source_limit="latest 1 month",
            schema=_open_interest_schema(),
            records=[
                {
                    "symbol": item.symbol,
                    "period": item.period.value,
                    "timestamp": item.timestamp,
                    "open_interest": item.open_interest,
                    "open_interest_value": item.open_interest_value,
                }
                for item in rows
            ],
            data_start=first.timestamp,
            data_end=rows[-1].timestamp,
        )

    def _publish(
        self,
        rows: list[Any],
        *,
        series: str,
        symbol: str,
        period: str | None,
        requested_start: datetime,
        requested_end: datetime,
        source: str,
        source_limit: str | None,
        schema: pa.Schema,
        records: list[dict[str, Any]],
        data_start: datetime,
        data_end: datetime,
    ) -> tuple[Path, DerivativeDatasetManifest]:
        content_hash = _content_hash(rows)
        version = content_hash[:16]
        parent = (
            self.root
            / "market"
            / "derivatives"
            / "exchange=binance"
            / f"series={series}"
            / f"symbol={symbol}"
        )
        if period:
            parent /= f"period={period}"
        final = parent / f"version={version}"
        if final.exists():
            manifest = self.verify(final)
            if manifest.content_sha256 != content_hash:
                raise DatasetError("derivatives dataset version collision")
            return final, manifest
        parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".publishing-", dir=parent))
        try:
            parquet = temporary / PARQUET_FILE_NAME
            pq.write_table(
                pa.Table.from_pylist(records, schema=schema), parquet, compression="zstd"
            )
            file_hash = _file_hash(parquet)
            manifest = DerivativeDatasetManifest(
                version,
                DERIVATIVES_SCHEMA_VERSION,
                series,
                "binance",
                symbol,
                period,
                _iso(requested_start),
                _iso(requested_end),
                _iso(data_start),
                _iso(data_end),
                len(rows),
                content_hash,
                source,
                source_limit,
                _iso(self.now()),
                f"quantos-market-data/{__version__}",
                file_hash,
            )
            (temporary / "manifest.json").write_text(
                json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            os.replace(temporary, final)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        return final, manifest

    def verify(self, path: Path) -> DerivativeDatasetManifest:
        try:
            raw = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
            manifest = DerivativeDatasetManifest(**raw)
            parquet = path / PARQUET_FILE_NAME
            file_hash = _file_hash(parquet)
            table = pq.read_table(parquet)
            rows = _rows_from_table(manifest, table)
            if not rows:
                raise DatasetError("derivatives dataset must not be empty")
            requested_start = _parse_iso(manifest.requested_start)
            requested_end = _parse_iso(manifest.requested_end)
            created_at = _parse_iso(manifest.created_at)
            content_hash = _content_hash(rows)
        except (
            OSError,
            ValueError,
            json.JSONDecodeError,
            TypeError,
            pa.ArrowException,
            MarketDataError,
        ) as exc:
            raise DatasetError("invalid derivatives dataset manifest") from exc
        expected_source = {
            "funding-rate": "https://fapi.binance.com/fapi/v1/fundingRate",
            "open-interest": "https://fapi.binance.com/futures/data/openInterestHist",
        }.get(manifest.series)
        if (
            manifest.schema_version != DERIVATIVES_SCHEMA_VERSION
            or expected_source is None
            or manifest.exchange != "binance"
            or manifest.symbol != normalize_symbol(manifest.symbol)
            or manifest.source != expected_source
            or manifest.source_limit
            != ("latest 1 month" if manifest.series == "open-interest" else None)
            or manifest.period
            != (rows[0].period.value if manifest.series == "open-interest" else None)
            or manifest.dataset_version != manifest.content_sha256[:16]
            or path.name != f"version={manifest.dataset_version}"
            or len(manifest.content_sha256) != 64
            or content_hash != manifest.content_sha256
            or manifest.file_sha256 != file_hash
            or table.num_rows != manifest.row_count
            or manifest.row_count != len(rows)
            or created_at > self.now() + timedelta(minutes=5)
        ):
            raise DatasetError("derivatives dataset verification failed")
        timestamp = (
            (lambda item: item.funding_time)
            if manifest.series == "funding-rate"
            else (lambda item: item.timestamp)
        )
        _validate_series(rows, requested_start, requested_end, timestamp)
        if manifest.data_start != _iso(timestamp(rows[0])) or manifest.data_end != _iso(
            timestamp(rows[-1])
        ):
            raise DatasetError("derivatives dataset verification failed")
        return manifest

    def load(
        self, path: Path
    ) -> tuple[
        DerivativeDatasetManifest,
        list[FundingRateObservation] | list[OpenInterestObservation],
    ]:
        """Verify and load normalized observations from one immutable version."""

        manifest = self.verify(path)
        try:
            table = pq.read_table(path / PARQUET_FILE_NAME)
            rows = _rows_from_table(manifest, table)
        except (OSError, TypeError, pa.ArrowException, MarketDataError) as exc:
            raise DatasetError("cannot load verified derivatives dataset") from exc
        return manifest, rows


def _validate_funding(item: FundingRateObservation) -> None:
    if (
        item.symbol != normalize_symbol(item.symbol)
        or datetime_to_milliseconds(item.funding_time) < 0
        or not item.funding_rate.is_finite()
        or item.rate_type not in {"Regular", "Special"}
        or (
            item.mark_price is not None
            and (not item.mark_price.is_finite() or item.mark_price <= 0)
        )
    ):
        raise DownloadError("invalid funding observation")


def _validate_open_interest(item: OpenInterestObservation) -> None:
    if (
        item.symbol != normalize_symbol(item.symbol)
        or not isinstance(item.period, Interval)
        or datetime_to_milliseconds(item.timestamp) < 0
        or not item.open_interest.is_finite()
        or not item.open_interest_value.is_finite()
        or item.open_interest < 0
        or item.open_interest_value < 0
    ):
        raise DownloadError("invalid open-interest observation")


def _bounds(start: datetime, end: datetime) -> tuple[int, int]:
    start_ms = datetime_to_milliseconds(start)
    end_ms = datetime_to_milliseconds(end)
    if start_ms >= end_ms:
        raise ConfigurationError("start must be earlier than end")
    return start_ms, end_ms


def _unique_sorted(rows: list[Any], timestamp) -> list[Any]:
    ordered = sorted(rows, key=timestamp)
    if len({timestamp(item) for item in ordered}) != len(ordered):
        raise DownloadError("derivatives observations contain duplicate timestamps")
    return ordered


def _validate_page_order(rows: list[Any], timestamp) -> None:
    times = [timestamp(item) for item in rows]
    if times != sorted(times) or len(times) != len(set(times)):
        raise DownloadError("Binance Futures page must be ordered and unique")


def _validate_series(rows: list[Any], start: datetime, end: datetime, timestamp) -> None:
    if not rows:
        raise DatasetError("derivatives dataset must not be empty")
    _bounds(start, end)
    symbols = {item.symbol for item in rows}
    times = [timestamp(item) for item in rows]
    if len(symbols) != 1 or times != sorted(times) or len(times) != len(set(times)):
        raise DatasetError("derivatives observations must be homogeneous, ordered, and unique")
    if times[0] < start.astimezone(UTC) or times[-1] >= end.astimezone(UTC):
        raise DatasetError("derivatives observations fall outside requested coverage")


def _funding_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("symbol", pa.string(), nullable=False),
            pa.field("funding_time", pa.timestamp("ms", tz="UTC"), nullable=False),
            pa.field("funding_rate", pa.decimal128(38, 18), nullable=False),
            pa.field("mark_price", pa.decimal128(38, 18), nullable=True),
            pa.field("rate_type", pa.string(), nullable=False),
        ],
        metadata={b"quantos.schema": DERIVATIVES_SCHEMA_VERSION.encode()},
    )


def _open_interest_schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("symbol", pa.string(), nullable=False),
            pa.field("period", pa.string(), nullable=False),
            pa.field("timestamp", pa.timestamp("ms", tz="UTC"), nullable=False),
            pa.field("open_interest", pa.decimal128(38, 18), nullable=False),
            pa.field("open_interest_value", pa.decimal128(38, 18), nullable=False),
        ],
        metadata={b"quantos.schema": DERIVATIVES_SCHEMA_VERSION.encode()},
    )


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_iso(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    result = datetime.fromisoformat(normalized)
    if result.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return result.astimezone(UTC)


def _decimal_string(value: Decimal) -> str:
    try:
        with localcontext() as context:
            context.prec = 38
            return format(value.quantize(Decimal("0.000000000000000001")), "f")
    except InvalidOperation as exc:
        raise DownloadError("derivatives decimal exceeds decimal128(38, 18)") from exc


def _content_hash(rows: list[Any]) -> str:
    payload = json.dumps([item.canonical() for item in rows], separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


def _rows_from_table(
    manifest: DerivativeDatasetManifest, table: pa.Table
) -> list[FundingRateObservation] | list[OpenInterestObservation]:
    expected_schema = (
        _funding_schema() if manifest.series == "funding-rate" else _open_interest_schema()
    )
    if table.schema != expected_schema:
        raise DatasetError("derivatives Parquet schema mismatch")
    records = table.to_pylist()
    if manifest.series == "funding-rate":
        rows = [
            FundingRateObservation(
                item["symbol"],
                item["funding_time"],
                item["funding_rate"],
                item["mark_price"],
                item["rate_type"],
            )
            for item in records
        ]
        for item in rows:
            _validate_funding(item)
        return rows
    if manifest.series == "open-interest":
        rows = [
            OpenInterestObservation(
                item["symbol"],
                Interval.parse(item["period"]),
                item["timestamp"],
                item["open_interest"],
                item["open_interest_value"],
            )
            for item in records
        ]
        for item in rows:
            _validate_open_interest(item)
        return rows
    raise DatasetError("unsupported derivatives series")

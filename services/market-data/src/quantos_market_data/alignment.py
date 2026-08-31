"""Causal point-in-time alignment of derivatives observations to closed Spot bars."""

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

import pyarrow as pa
import pyarrow.parquet as pq

from . import __version__
from .derivatives import (
    DerivativeDatasetManifest,
    DerivativeDatasetStore,
    FundingRateObservation,
    OpenInterestObservation,
)
from .errors import ConfigurationError, DatasetError, MarketDataError
from .models import Interval, Kline, datetime_to_milliseconds, normalize_symbol
from .storage import DatasetManifest, DatasetStore

ALIGNED_DERIVATIVES_SCHEMA_VERSION = "aligned-derivatives.v1"
ALIGNMENT_POLICY_VERSION = "asof-closed-bar.v1"
PARQUET_FILE_NAME = "part-00000.parquet"
AVAILABILITY_VALUES = frozenset({"matched", "no-prior-observation", "stale-observation"})


@dataclass(frozen=True, slots=True)
class AlignedDerivativeRow:
    series: str
    symbol: str
    spot_interval: Interval
    derivative_period: Interval | None
    bar_open_time: datetime
    decision_time: datetime
    observation_time: datetime | None
    age_ms: int | None
    availability: str
    funding_rate: Decimal | None
    mark_price: Decimal | None
    open_interest: Decimal | None
    open_interest_value: Decimal | None

    def canonical(self) -> list[str | int | None]:
        return [
            self.series,
            self.symbol,
            self.spot_interval.value,
            None if self.derivative_period is None else self.derivative_period.value,
            datetime_to_milliseconds(self.bar_open_time),
            datetime_to_milliseconds(self.decision_time),
            (
                None
                if self.observation_time is None
                else datetime_to_milliseconds(self.observation_time)
            ),
            self.age_ms,
            self.availability,
            _decimal_string(self.funding_rate),
            _decimal_string(self.mark_price),
            _decimal_string(self.open_interest),
            _decimal_string(self.open_interest_value),
        ]


@dataclass(frozen=True, slots=True)
class AlignedDerivativeManifest:
    dataset_version: str
    schema_version: str
    alignment_policy_version: str
    series: str
    exchange: str
    symbol: str
    spot_interval: str
    derivative_period: str | None
    spot_dataset_version: str
    spot_content_sha256: str
    derivative_dataset_version: str
    derivative_content_sha256: str
    requested_start: str
    requested_end: str
    max_age_ms: int
    row_count: int
    matched_count: int
    stale_count: int
    no_prior_count: int
    content_sha256: str
    created_at: str
    producer: str
    file_sha256: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PublishedAlignedDerivativeDataset:
    path: Path
    manifest: AlignedDerivativeManifest


def materialize_derivatives_alignment(
    *,
    spot_dataset: Path,
    derivative_dataset: Path,
    start: datetime,
    end: datetime,
    max_age_ms: int,
    output_root: Path,
    now: datetime | None = None,
) -> PublishedAlignedDerivativeDataset:
    """Verify both inputs, causally align them, and publish one immutable output."""

    if max_age_ms <= 0:
        raise ConfigurationError("maximum derivatives observation age must be positive")
    start_ms, end_ms = _bounds(start, end)
    spot_store = DatasetStore(spot_dataset)
    spot_store.verify(spot_dataset)
    spot_manifest = spot_store.load_manifest(spot_dataset)
    selected = [
        item
        for item in spot_store.load_klines(spot_dataset)
        if start_ms <= datetime_to_milliseconds(item.open_time) < end_ms
    ]
    if not selected:
        raise DatasetError("alignment range contains no Spot Klines")

    derivative_manifest, observations = DerivativeDatasetStore(derivative_dataset).load(
        derivative_dataset
    )
    rows = align_derivatives(
        selected,
        derivative_manifest=derivative_manifest,
        observations=observations,
        max_age_ms=max_age_ms,
    )
    clock = (lambda: now) if now is not None else (lambda: datetime.now(UTC))
    return AlignedDerivativeStore(output_root, now=clock).publish(
        rows,
        spot_manifest=spot_manifest,
        derivative_manifest=derivative_manifest,
        requested_start=start,
        requested_end=end,
        max_age_ms=max_age_ms,
    )


def align_derivatives(
    klines: list[Kline],
    *,
    derivative_manifest: DerivativeDatasetManifest,
    observations: list[FundingRateObservation] | list[OpenInterestObservation],
    max_age_ms: int,
) -> list[AlignedDerivativeRow]:
    """Apply a backward-only as-of match at each closed-bar decision time."""

    if max_age_ms <= 0:
        raise ConfigurationError("maximum derivatives observation age must be positive")
    if not klines or not observations:
        raise DatasetError("alignment inputs must not be empty")
    symbol = normalize_symbol(klines[0].symbol)
    interval = klines[0].interval
    if any(item.symbol != symbol or item.interval != interval for item in klines):
        raise DatasetError("Spot alignment input must have one symbol and interval")
    if derivative_manifest.symbol != symbol:
        raise DatasetError("Spot and derivatives symbols must match")

    series = derivative_manifest.series
    if series == "funding-rate" and not all(
        isinstance(item, FundingRateObservation) for item in observations
    ):
        raise DatasetError("funding manifest requires funding observations")
    if series == "open-interest" and not all(
        isinstance(item, OpenInterestObservation) for item in observations
    ):
        raise DatasetError("open-interest manifest requires open-interest observations")
    if series not in {"funding-rate", "open-interest"}:
        raise DatasetError("unsupported derivatives alignment series")

    observation_times = [_observation_time(item) for item in observations]
    if observation_times != sorted(observation_times) or len(observation_times) != len(
        set(observation_times)
    ):
        raise DatasetError("derivatives alignment input must be ordered and unique")

    result: list[AlignedDerivativeRow] = []
    cursor = -1
    for bar in klines:
        while (
            cursor + 1 < len(observations)
            and _observation_time(observations[cursor + 1]) <= bar.close_time
        ):
            cursor += 1
        observation = observations[cursor] if cursor >= 0 else None
        result.append(
            _aligned_row(
                bar,
                series=series,
                derivative_period=(
                    Interval.parse(derivative_manifest.period)
                    if derivative_manifest.period is not None
                    else None
                ),
                observation=observation,
                max_age_ms=max_age_ms,
            )
        )
    _validate_rows(result, max_age_ms=max_age_ms)
    return result


class AlignedDerivativeStore:
    def __init__(self, root: Path, *, now=lambda: datetime.now(UTC)) -> None:
        self.root = root
        self.now = now

    def publish(
        self,
        rows: list[AlignedDerivativeRow],
        *,
        spot_manifest: DatasetManifest,
        derivative_manifest: DerivativeDatasetManifest,
        requested_start: datetime,
        requested_end: datetime,
        max_age_ms: int,
    ) -> PublishedAlignedDerivativeDataset:
        _validate_rows(rows, max_age_ms=max_age_ms)
        first = rows[0]
        if (
            spot_manifest.symbol != first.symbol
            or spot_manifest.interval != first.spot_interval.value
        ):
            raise DatasetError("Spot manifest does not match aligned rows")
        if derivative_manifest.symbol != first.symbol or derivative_manifest.series != first.series:
            raise DatasetError("derivatives manifest does not match aligned rows")
        identity = _identity(
            rows,
            spot_manifest=spot_manifest,
            derivative_manifest=derivative_manifest,
            requested_start=requested_start,
            requested_end=requested_end,
            max_age_ms=max_age_ms,
        )
        content_hash = _content_hash(identity, rows)
        version = content_hash[:16]
        parent = (
            self.root
            / "features"
            / "derivatives-aligned"
            / f"series={first.series}"
            / f"symbol={first.symbol}"
            / f"spot_interval={first.spot_interval.value}"
        )
        if first.derivative_period is not None:
            parent /= f"derivative_period={first.derivative_period.value}"
        final = parent / f"version={version}"
        if final.exists():
            manifest = self.verify(final)
            if manifest.content_sha256 != content_hash:
                raise DatasetError("aligned derivatives dataset version collision")
            return PublishedAlignedDerivativeDataset(final, manifest)

        parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(tempfile.mkdtemp(prefix=".publishing-", dir=parent))
        try:
            parquet = temporary / PARQUET_FILE_NAME
            pq.write_table(_to_table(rows), parquet, compression="zstd")
            counts = _availability_counts(rows)
            manifest = AlignedDerivativeManifest(
                version,
                ALIGNED_DERIVATIVES_SCHEMA_VERSION,
                ALIGNMENT_POLICY_VERSION,
                first.series,
                "binance",
                first.symbol,
                first.spot_interval.value,
                None if first.derivative_period is None else first.derivative_period.value,
                spot_manifest.dataset_version,
                spot_manifest.content_sha256,
                derivative_manifest.dataset_version,
                derivative_manifest.content_sha256,
                _iso(requested_start),
                _iso(requested_end),
                max_age_ms,
                len(rows),
                counts["matched"],
                counts["stale-observation"],
                counts["no-prior-observation"],
                content_hash,
                _iso(self.now()),
                f"quantos-market-data/{__version__}",
                _file_hash(parquet),
            )
            (temporary / "manifest.json").write_text(
                json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, final)
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise
        return PublishedAlignedDerivativeDataset(final, manifest)

    def verify(self, path: Path) -> AlignedDerivativeManifest:
        try:
            manifest = AlignedDerivativeManifest(
                **json.loads((path / "manifest.json").read_text(encoding="utf-8"))
            )
            parquet = path / PARQUET_FILE_NAME
            table = pq.read_table(parquet)
            rows = _rows_from_table(table)
            if not rows:
                raise DatasetError("aligned derivatives dataset must not be empty")
            start = _parse_iso(manifest.requested_start)
            end = _parse_iso(manifest.requested_end)
            _bounds(start, end)
            identity = _manifest_identity(manifest)
            content_hash = _content_hash(identity, rows)
            counts = _availability_counts(rows)
            _validate_rows(rows, max_age_ms=manifest.max_age_ms)
        except (
            OSError,
            ValueError,
            TypeError,
            json.JSONDecodeError,
            pa.ArrowException,
            MarketDataError,
        ) as exc:
            raise DatasetError("invalid aligned derivatives dataset") from exc
        if (
            manifest.schema_version != ALIGNED_DERIVATIVES_SCHEMA_VERSION
            or manifest.alignment_policy_version != ALIGNMENT_POLICY_VERSION
            or manifest.exchange != "binance"
            or manifest.symbol != normalize_symbol(manifest.symbol)
            or rows[0].series != manifest.series
            or rows[0].symbol != manifest.symbol
            or rows[0].spot_interval.value != manifest.spot_interval
            or (None if rows[0].derivative_period is None else rows[0].derivative_period.value)
            != manifest.derivative_period
            or manifest.dataset_version != manifest.content_sha256[:16]
            or path.name != f"version={manifest.dataset_version}"
            or len(manifest.content_sha256) != 64
            or len(manifest.spot_content_sha256) != 64
            or len(manifest.derivative_content_sha256) != 64
            or content_hash != manifest.content_sha256
            or _file_hash(parquet) != manifest.file_sha256
            or manifest.row_count != len(rows)
            or manifest.matched_count != counts["matched"]
            or manifest.stale_count != counts["stale-observation"]
            or manifest.no_prior_count != counts["no-prior-observation"]
            or any(not (start <= item.bar_open_time < end) for item in rows)
        ):
            raise DatasetError("aligned derivatives dataset verification failed")
        return manifest

    def load(self, path: Path) -> tuple[AlignedDerivativeManifest, list[AlignedDerivativeRow]]:
        """Verify and load one causal feature-dataset version."""

        manifest = self.verify(path)
        try:
            rows = _rows_from_table(pq.read_table(path / PARQUET_FILE_NAME))
        except (OSError, TypeError, pa.ArrowException, MarketDataError) as exc:
            raise DatasetError("cannot load aligned derivatives dataset") from exc
        return manifest, rows


def _aligned_row(
    bar: Kline,
    *,
    series: str,
    derivative_period: Interval | None,
    observation: FundingRateObservation | OpenInterestObservation | None,
    max_age_ms: int,
) -> AlignedDerivativeRow:
    observation_time = None if observation is None else _observation_time(observation)
    age_ms = (
        None
        if observation_time is None
        else datetime_to_milliseconds(bar.close_time) - datetime_to_milliseconds(observation_time)
    )
    availability = (
        "no-prior-observation"
        if observation is None
        else "stale-observation"
        if age_ms is not None and age_ms > max_age_ms
        else "matched"
    )
    matched = availability == "matched"
    funding = observation if isinstance(observation, FundingRateObservation) else None
    interest = observation if isinstance(observation, OpenInterestObservation) else None
    return AlignedDerivativeRow(
        series,
        bar.symbol,
        bar.interval,
        derivative_period,
        bar.open_time,
        bar.close_time,
        observation_time,
        age_ms,
        availability,
        funding.funding_rate if matched and funding is not None else None,
        funding.mark_price if matched and funding is not None else None,
        interest.open_interest if matched and interest is not None else None,
        interest.open_interest_value if matched and interest is not None else None,
    )


def _validate_rows(rows: list[AlignedDerivativeRow], *, max_age_ms: int) -> None:
    if not rows or max_age_ms <= 0:
        raise DatasetError("aligned derivatives rows and maximum age must be positive")
    first = rows[0]
    bar_times = [item.bar_open_time for item in rows]
    if bar_times != sorted(bar_times) or len(bar_times) != len(set(bar_times)):
        raise DatasetError("aligned derivatives bars must be ordered and unique")
    for item in rows:
        if (
            item.series != first.series
            or item.symbol != first.symbol
            or item.symbol != normalize_symbol(item.symbol)
            or item.spot_interval != first.spot_interval
            or item.derivative_period != first.derivative_period
            or item.availability not in AVAILABILITY_VALUES
            or item.decision_time
            != item.bar_open_time + timedelta(milliseconds=item.spot_interval.milliseconds - 1)
            or (item.observation_time is not None and item.observation_time > item.decision_time)
            or (
                item.observation_time is None
                and (item.age_ms is not None or item.availability != "no-prior-observation")
            )
            or (item.availability == "no-prior-observation" and item.observation_time is not None)
            or (item.observation_time is not None and (item.age_ms is None or item.age_ms < 0))
            or (
                item.availability == "matched"
                and item.age_ms is not None
                and item.age_ms > max_age_ms
            )
            or (
                item.availability == "stale-observation"
                and (item.age_ms is None or item.age_ms <= max_age_ms)
            )
        ):
            raise DatasetError("invalid causal derivatives alignment row")
        _validate_values(item)


def _validate_values(item: AlignedDerivativeRow) -> None:
    values = (
        item.funding_rate,
        item.mark_price,
        item.open_interest,
        item.open_interest_value,
    )
    if any(value is not None and not value.is_finite() for value in values):
        raise DatasetError("aligned derivatives values must be finite")
    if item.availability != "matched" and any(value is not None for value in values):
        raise DatasetError("unavailable derivatives rows must not expose feature values")
    if item.series == "funding-rate":
        if (
            item.derivative_period is not None
            or item.open_interest is not None
            or item.open_interest_value is not None
        ):
            raise DatasetError("funding alignment has invalid typed values")
        if item.availability == "matched" and item.funding_rate is None:
            raise DatasetError("matched funding alignment requires a rate")
        if item.mark_price is not None and item.mark_price <= 0:
            raise DatasetError("funding alignment mark price must be positive")
    elif item.series == "open-interest":
        if (
            item.derivative_period is None
            or item.funding_rate is not None
            or item.mark_price is not None
        ):
            raise DatasetError("open-interest alignment has invalid typed values")
        if item.availability == "matched" and (
            item.open_interest is None or item.open_interest_value is None
        ):
            raise DatasetError("matched open-interest alignment requires values")
        if (item.open_interest is not None and item.open_interest < 0) or (
            item.open_interest_value is not None and item.open_interest_value < 0
        ):
            raise DatasetError("open-interest alignment values must be non-negative")
    else:
        raise DatasetError("unsupported aligned derivatives series")


def _identity(
    rows: list[AlignedDerivativeRow],
    *,
    spot_manifest: DatasetManifest,
    derivative_manifest: DerivativeDatasetManifest,
    requested_start: datetime,
    requested_end: datetime,
    max_age_ms: int,
) -> dict[str, Any]:
    return {
        "schema_version": ALIGNED_DERIVATIVES_SCHEMA_VERSION,
        "alignment_policy_version": ALIGNMENT_POLICY_VERSION,
        "series": rows[0].series,
        "symbol": rows[0].symbol,
        "spot_interval": rows[0].spot_interval.value,
        "derivative_period": (
            None if rows[0].derivative_period is None else rows[0].derivative_period.value
        ),
        "spot_dataset_version": spot_manifest.dataset_version,
        "spot_content_sha256": spot_manifest.content_sha256,
        "derivative_dataset_version": derivative_manifest.dataset_version,
        "derivative_content_sha256": derivative_manifest.content_sha256,
        "requested_start": _iso(requested_start),
        "requested_end": _iso(requested_end),
        "max_age_ms": max_age_ms,
    }


def _manifest_identity(manifest: AlignedDerivativeManifest) -> dict[str, Any]:
    return {
        key: getattr(manifest, key)
        for key in (
            "schema_version",
            "alignment_policy_version",
            "series",
            "symbol",
            "spot_interval",
            "derivative_period",
            "spot_dataset_version",
            "spot_content_sha256",
            "derivative_dataset_version",
            "derivative_content_sha256",
            "requested_start",
            "requested_end",
            "max_age_ms",
        )
    }


def _content_hash(identity: dict[str, Any], rows: list[AlignedDerivativeRow]) -> str:
    payload = {"identity": identity, "rows": [item.canonical() for item in rows]}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _to_table(rows: list[AlignedDerivativeRow]) -> pa.Table:
    return pa.Table.from_pylist(
        [
            {
                "series": item.series,
                "symbol": item.symbol,
                "spot_interval": item.spot_interval.value,
                "derivative_period": (
                    None if item.derivative_period is None else item.derivative_period.value
                ),
                "bar_open_time": item.bar_open_time,
                "decision_time": item.decision_time,
                "observation_time": item.observation_time,
                "age_ms": item.age_ms,
                "availability": item.availability,
                "funding_rate": item.funding_rate,
                "mark_price": item.mark_price,
                "open_interest": item.open_interest,
                "open_interest_value": item.open_interest_value,
            }
            for item in rows
        ],
        schema=_schema(),
    )


def _rows_from_table(table: pa.Table) -> list[AlignedDerivativeRow]:
    if table.schema != _schema():
        raise DatasetError("aligned derivatives Parquet schema mismatch")
    return [
        AlignedDerivativeRow(
            item["series"],
            item["symbol"],
            Interval.parse(item["spot_interval"]),
            (
                None
                if item["derivative_period"] is None
                else Interval.parse(item["derivative_period"])
            ),
            item["bar_open_time"],
            item["decision_time"],
            item["observation_time"],
            item["age_ms"],
            item["availability"],
            item["funding_rate"],
            item["mark_price"],
            item["open_interest"],
            item["open_interest_value"],
        )
        for item in table.to_pylist()
    ]


def _schema() -> pa.Schema:
    return pa.schema(
        [
            pa.field("series", pa.string(), nullable=False),
            pa.field("symbol", pa.string(), nullable=False),
            pa.field("spot_interval", pa.string(), nullable=False),
            pa.field("derivative_period", pa.string()),
            pa.field("bar_open_time", pa.timestamp("ms", tz="UTC"), nullable=False),
            pa.field("decision_time", pa.timestamp("ms", tz="UTC"), nullable=False),
            pa.field("observation_time", pa.timestamp("ms", tz="UTC")),
            pa.field("age_ms", pa.int64()),
            pa.field("availability", pa.string(), nullable=False),
            pa.field("funding_rate", pa.decimal128(38, 18)),
            pa.field("mark_price", pa.decimal128(38, 18)),
            pa.field("open_interest", pa.decimal128(38, 18)),
            pa.field("open_interest_value", pa.decimal128(38, 18)),
        ],
        metadata={b"quantos.schema": ALIGNED_DERIVATIVES_SCHEMA_VERSION.encode()},
    )


def _observation_time(item: FundingRateObservation | OpenInterestObservation) -> datetime:
    return item.funding_time if isinstance(item, FundingRateObservation) else item.timestamp


def _availability_counts(rows: list[AlignedDerivativeRow]) -> dict[str, int]:
    return {
        value: sum(item.availability == value for item in rows) for value in AVAILABILITY_VALUES
    }


def _decimal_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    try:
        with localcontext() as context:
            context.prec = 38
            return format(value.quantize(Decimal("0.000000000000000001")), "f")
    except InvalidOperation as exc:
        raise DatasetError("aligned decimal exceeds decimal128(38, 18)") from exc


def _bounds(start: datetime, end: datetime) -> tuple[int, int]:
    start_ms = datetime_to_milliseconds(start)
    end_ms = datetime_to_milliseconds(end)
    if start_ms >= end_ms:
        raise ConfigurationError("alignment start must be earlier than end")
    return start_ms, end_ms


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
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(UTC)

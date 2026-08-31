"""Application service for one reproducible market-data download."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from .binance import DEFAULT_BASE_URL, BinanceSpotClient
from .bundle import (
    PRODUCT_INTERVALS,
    PRODUCT_SYMBOLS,
    DatasetBundleStore,
    PublishedDatasetBundle,
)
from .errors import ConfigurationError
from .models import Interval, datetime_to_milliseconds
from .storage import DatasetStore, PublishedDataset
from .validation import validate_klines


def download_dataset(
    *,
    symbol: str,
    interval: Interval,
    start: datetime,
    end: datetime,
    data_root: Path,
    base_url: str = DEFAULT_BASE_URL,
    now: datetime | None = None,
) -> PublishedDataset:
    """Download, validate, and atomically publish one immutable dataset."""

    observed_now = now or datetime.now(UTC)
    current_boundary_ms = (
        datetime_to_milliseconds(observed_now) // interval.milliseconds
    ) * interval.milliseconds
    if datetime_to_milliseconds(end) > current_boundary_ms:
        raise ConfigurationError(f"end must not exceed the latest closed {interval.value} boundary")

    with BinanceSpotClient(base_url=base_url) as client:
        klines = client.fetch_klines(
            symbol=symbol,
            interval=interval,
            start=start,
            end=end,
        )
    report = validate_klines(
        klines,
        requested_start=start,
        requested_end=end,
    )
    report.raise_if_invalid()
    return DatasetStore(data_root).publish(
        klines,
        requested_start=start,
        requested_end=end,
        source=f"{base_url.rstrip('/')}/api/v3/klines",
        validation=report,
    )


def sync_product_matrix(
    *,
    start: datetime,
    end: datetime,
    data_root: Path,
    base_url: str = DEFAULT_BASE_URL,
    now: datetime | None = None,
) -> PublishedDatasetBundle:
    """Publish the complete BTC/ETH five-interval matrix as one bundle."""

    published = []
    for symbol in PRODUCT_SYMBOLS:
        for interval in PRODUCT_INTERVALS:
            published.append(
                download_dataset(
                    symbol=symbol,
                    interval=interval,
                    start=start,
                    end=end,
                    data_root=data_root,
                    base_url=base_url,
                    now=now,
                )
            )
    return DatasetBundleStore(data_root).publish(published)


def extend_dataset(
    *,
    dataset: Path,
    end: datetime,
    data_root: Path,
    base_url: str = DEFAULT_BASE_URL,
    now: datetime | None = None,
) -> PublishedDataset:
    """Extend one immutable dataset by downloading only its missing tail."""

    store = DatasetStore(data_root)
    store.verify(dataset)
    manifest = store.load_manifest(dataset)
    interval = Interval.parse(manifest.interval)
    previous_end = _manifest_datetime(manifest.requested_end)
    if end < previous_end:
        raise ConfigurationError("refresh end cannot precede the source dataset end")
    if end == previous_end:
        return PublishedDataset(dataset, manifest)

    observed_now = now or datetime.now(UTC)
    current_boundary_ms = (
        datetime_to_milliseconds(observed_now) // interval.milliseconds
    ) * interval.milliseconds
    if datetime_to_milliseconds(end) > current_boundary_ms:
        raise ConfigurationError(f"end must not exceed the latest closed {interval.value} boundary")
    expected_source = f"{base_url.rstrip('/')}/api/v3/klines"
    if manifest.source != expected_source:
        raise ConfigurationError("refresh source must match the immutable source dataset")

    with BinanceSpotClient(base_url=base_url) as client:
        tail = client.fetch_klines(
            symbol=manifest.symbol,
            interval=interval,
            start=previous_end,
            end=end,
        )
    combined = [*store.load_klines(dataset), *tail]
    requested_start = _manifest_datetime(manifest.requested_start)
    report = validate_klines(
        combined,
        requested_start=requested_start,
        requested_end=end,
    )
    report.raise_if_invalid()
    return store.publish(
        combined,
        requested_start=requested_start,
        requested_end=end,
        source=manifest.source,
        validation=report,
    )


def refresh_product_matrix(
    *,
    bundle: Path,
    end: datetime,
    data_root: Path,
    base_url: str = DEFAULT_BASE_URL,
    now: datetime | None = None,
) -> PublishedDatasetBundle:
    """Extend every member and atomically publish a replacement bundle."""

    bundle_store = DatasetBundleStore(data_root)
    source = bundle_store.verify(bundle)
    if end < _manifest_datetime(source.requested_end):
        raise ConfigurationError("refresh end cannot precede the source bundle end")
    if end == _manifest_datetime(source.requested_end):
        return PublishedDatasetBundle(bundle, source)

    published = [
        extend_dataset(
            dataset=data_root / member.dataset_path,
            end=end,
            data_root=data_root,
            base_url=base_url,
            now=now,
        )
        for member in source.members
    ]
    return bundle_store.publish(published)


def sync_current_product_matrix(
    *,
    start: datetime,
    data_root: Path,
    base_url: str = DEFAULT_BASE_URL,
    now: datetime | None = None,
) -> PublishedDatasetBundle:
    """Backfill or increment the matrix to the latest common closed boundary."""

    observed_now = now or datetime.now(UTC)
    end = latest_closed_matrix_end(observed_now)
    if start >= end:
        raise ConfigurationError("start must precede the latest closed matrix boundary")
    bundle_store = DatasetBundleStore(data_root)
    source = bundle_store.find_latest(requested_start=_manifest_isoformat(start))
    if source is None:
        return sync_product_matrix(
            start=start,
            end=end,
            data_root=data_root,
            base_url=base_url,
            now=observed_now,
        )
    return refresh_product_matrix(
        bundle=source.path,
        end=end,
        data_root=data_root,
        base_url=base_url,
        now=observed_now,
    )


def latest_closed_matrix_end(now: datetime) -> datetime:
    """Return UTC midnight, the latest boundary shared with the daily interval."""

    if now.tzinfo is None:
        raise ConfigurationError("current time must include a timezone")
    observed = now.astimezone(UTC)
    return observed.replace(hour=0, minute=0, second=0, microsecond=0)


def _manifest_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ConfigurationError("manifest timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _manifest_isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        raise ConfigurationError("timestamps must include a timezone")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

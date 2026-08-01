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

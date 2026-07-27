from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from quantos_market_data.errors import DatasetError
from quantos_market_data.query import query_klines
from quantos_market_data.storage import DatasetStore

from .conftest import make_kline


def test_publishes_verifies_and_reuses_content_addressed_dataset(
    tmp_path,
    start_time,
) -> None:
    fixed_now = datetime(2026, 7, 27, tzinfo=UTC)
    klines = [make_kline(start_time + timedelta(hours=index)) for index in range(3)]
    store = DatasetStore(tmp_path, now=lambda: fixed_now)

    first = store.publish(
        klines,
        requested_start=start_time,
        requested_end=start_time + timedelta(hours=3),
        source="https://example.test/api/v3/klines",
    )
    second = store.publish(
        klines,
        requested_start=start_time,
        requested_end=start_time + timedelta(hours=3),
        source="https://example.test/api/v3/klines",
    )

    assert first.path == second.path
    assert first.manifest.dataset_version == first.path.name.removeprefix("version=")
    assert first.manifest.row_count == 3
    assert first.manifest.created_at == "2026-07-27T00:00:00Z"
    assert store.verify(first.path).is_valid
    assert store.load_klines(first.path) == klines
    manifest = json.loads((first.path / "manifest.json").read_text())
    assert manifest["validation"]["is_valid"] is True


def test_detects_tampered_parquet(tmp_path, start_time) -> None:
    store = DatasetStore(tmp_path)
    published = store.publish(
        [make_kline(start_time)],
        requested_start=start_time,
        requested_end=start_time + timedelta(hours=1),
        source="https://example.test/api/v3/klines",
    )
    parquet_path = published.path / "part-00000.parquet"
    parquet_path.write_bytes(parquet_path.read_bytes() + b"tampered")

    with pytest.raises(DatasetError, match="checksum mismatch"):
        store.verify(published.path)


def test_duckdb_query_filters_one_dataset_version(tmp_path, start_time) -> None:
    klines = [make_kline(start_time + timedelta(hours=index)) for index in range(5)]
    published = DatasetStore(tmp_path).publish(
        klines,
        requested_start=start_time,
        requested_end=start_time + timedelta(hours=5),
        source="https://example.test/api/v3/klines",
    )

    rows = query_klines(
        published.path / "manifest.json",
        start=start_time + timedelta(hours=1),
        end=start_time + timedelta(hours=4),
        limit=2,
    )

    assert len(rows) == 2
    assert rows[0]["open_time"] == start_time + timedelta(hours=1)
    assert rows[0]["open_time"].utcoffset() == timedelta(0)
    assert rows[1]["open_time"] == start_time + timedelta(hours=2)

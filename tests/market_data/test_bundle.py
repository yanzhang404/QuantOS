from __future__ import annotations

import json
from datetime import timedelta

import pytest
from quantos_market_data.bundle import (
    BUNDLE_SCHEMA_VERSION,
    PRODUCT_INTERVALS,
    PRODUCT_SYMBOLS,
    DatasetBundleStore,
    coverage_evidence,
    write_coverage_evidence,
)
from quantos_market_data.errors import DatasetError
from quantos_market_data.storage import DatasetStore

from .conftest import make_kline


def publish_matrix(tmp_path, start_time):
    datasets = []
    requested_end = start_time + timedelta(days=1)
    for symbol in PRODUCT_SYMBOLS:
        for interval in PRODUCT_INTERVALS:
            rows = int(timedelta(days=1).total_seconds() * 1_000 / interval.milliseconds)
            datasets.append(
                DatasetStore(tmp_path).publish(
                    [
                        make_kline(
                            start_time + timedelta(milliseconds=interval.milliseconds * index),
                            symbol=symbol,
                            interval=interval,
                        )
                        for index in range(rows)
                    ],
                    requested_start=start_time,
                    requested_end=requested_end,
                    source="https://example.test/api/v3/klines",
                )
            )
    return datasets


def test_publishes_and_verifies_complete_immutable_bundle(tmp_path, start_time) -> None:
    datasets = publish_matrix(tmp_path, start_time)
    store = DatasetBundleStore(tmp_path, now=lambda: start_time)

    first = store.publish(datasets)
    repeated = store.publish(reversed(datasets))
    verified = store.verify(first.path)

    assert first.path == repeated.path
    assert first.manifest.bundle_version == repeated.manifest.bundle_version
    assert verified.schema_version == BUNDLE_SCHEMA_VERSION
    assert len(verified.members) == 10
    assert [item.interval for item in verified.members[:5]] == [
        item.value for item in PRODUCT_INTERVALS
    ]


def test_rejects_partial_bundle(tmp_path, start_time) -> None:
    datasets = publish_matrix(tmp_path, start_time)

    with pytest.raises(DatasetError, match="requested matrix"):
        DatasetBundleStore(tmp_path).publish(datasets[:-1])


def test_exports_repository_safe_coverage_evidence(tmp_path, start_time) -> None:
    bundle = DatasetBundleStore(tmp_path).publish(publish_matrix(tmp_path, start_time))
    evidence = coverage_evidence(bundle.manifest)
    output = tmp_path / "coverage.json"

    write_coverage_evidence(bundle.manifest, output)
    written = json.loads(output.read_text(encoding="utf-8"))

    assert evidence == written
    assert written["schema_version"] == "dataset-coverage.v1"
    assert written["member_count"] == 10
    assert all(member["status"] == "verified" for member in written["members"])
    assert all("dataset_path" not in member for member in written["members"])

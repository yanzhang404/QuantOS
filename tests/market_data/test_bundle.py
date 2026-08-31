from __future__ import annotations

import json
from dataclasses import replace
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


def publish_matrix(tmp_path, start_time, *, days: int = 1):
    datasets = []
    requested_end = start_time + timedelta(days=days)
    for symbol in PRODUCT_SYMBOLS:
        for interval in PRODUCT_INTERVALS:
            rows = int(timedelta(days=days).total_seconds() * 1_000 / interval.milliseconds)
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


def test_rejects_tampered_source_gap_evidence(tmp_path, start_time) -> None:
    store = DatasetBundleStore(tmp_path)
    bundle = store.publish(publish_matrix(tmp_path, start_time))
    manifest_path = bundle.path / "manifest.json"
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    raw["members"][0]["missing_interval_count"] = 1
    manifest_path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(DatasetError, match="member identity mismatch"):
        store.verify(bundle.path)


def test_exports_repository_safe_coverage_evidence(tmp_path, start_time) -> None:
    bundle = DatasetBundleStore(tmp_path).publish(publish_matrix(tmp_path, start_time))
    evidence = coverage_evidence(bundle.manifest)
    output = tmp_path / "coverage.json"

    write_coverage_evidence(bundle.manifest, output)
    written = json.loads(output.read_text(encoding="utf-8"))

    assert evidence == written
    assert written["schema_version"] == "dataset-coverage.v1"
    assert written["member_count"] == 10
    assert written["total_row_count"] == 830
    assert written["missing_interval_count"] == 0
    assert all(member["status"] == "verified" for member in written["members"])
    assert all("dataset_path" not in member for member in written["members"])


def test_coverage_evidence_sums_preserved_source_gaps(tmp_path, start_time) -> None:
    bundle = DatasetBundleStore(tmp_path).publish(publish_matrix(tmp_path, start_time))
    members = list(bundle.manifest.members)
    members[0] = replace(members[0], missing_interval_count=3)

    evidence = coverage_evidence(replace(bundle.manifest, members=tuple(members)))

    assert evidence["missing_interval_count"] == 3
    assert evidence["members"][0]["missing_interval_count"] == 3


def test_finds_latest_verified_bundle_for_historical_start(tmp_path, start_time) -> None:
    store = DatasetBundleStore(tmp_path)
    first = store.publish(publish_matrix(tmp_path, start_time))
    second = store.publish(publish_matrix(tmp_path, start_time, days=2))

    latest = store.find_latest(requested_start="2024-01-01T00:00:00Z")

    assert latest is not None
    assert latest.path == second.path
    assert latest.path != first.path
    assert latest.manifest.requested_end == "2024-01-03T00:00:00Z"
    assert store.find_latest(requested_start="2023-01-01T00:00:00Z") is None

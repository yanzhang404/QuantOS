from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from quantos_market_data.alignment import (
    AlignedDerivativeRow,
    AlignedDerivativeStore,
    align_derivatives,
    materialize_derivatives_alignment,
)
from quantos_market_data.derivatives import (
    DerivativeDatasetStore,
    FundingRateObservation,
    OpenInterestObservation,
)
from quantos_market_data.errors import ConfigurationError, DatasetError
from quantos_market_data.models import Interval
from quantos_market_data.storage import DatasetStore

from .conftest import make_kline

START = datetime(2026, 8, 1, tzinfo=UTC)
END = START + timedelta(hours=4)


def _input_datasets(tmp_path: Path):
    klines = [make_kline(START + timedelta(hours=index)) for index in range(4)]
    spot = DatasetStore(tmp_path / "inputs").publish(
        klines,
        requested_start=START,
        requested_end=END,
        source="https://api.binance.com/api/v3/klines",
    )
    funding = DerivativeDatasetStore(tmp_path / "inputs").publish_funding(
        [
            FundingRateObservation(
                "BTCUSDT",
                START + timedelta(hours=1, minutes=30),
                Decimal("0.0001"),
                Decimal("100"),
                "Regular",
            ),
            FundingRateObservation(
                "BTCUSDT",
                START + timedelta(hours=3, minutes=30),
                Decimal("-0.0002"),
                Decimal("101"),
                "Regular",
            ),
        ],
        requested_start=START,
        requested_end=END,
    )
    return spot, funding, klines


def test_materializes_backward_only_alignment_with_visible_missing_states(
    tmp_path: Path,
) -> None:
    spot, funding, _ = _input_datasets(tmp_path)

    result = materialize_derivatives_alignment(
        spot_dataset=spot.path,
        derivative_dataset=funding[0],
        start=START,
        end=END,
        max_age_ms=60 * 60 * 1000,
        output_root=tmp_path / "outputs",
        now=END,
    )
    store = AlignedDerivativeStore(tmp_path / "outputs", now=lambda: END)
    manifest, rows = store.load(result.path)

    assert manifest.row_count == 4
    assert manifest.matched_count == 2
    assert manifest.stale_count == 1
    assert manifest.no_prior_count == 1
    assert manifest.spot_dataset_version == spot.manifest.dataset_version
    assert manifest.derivative_dataset_version == funding[1].dataset_version
    assert [item.availability for item in rows] == [
        "no-prior-observation",
        "matched",
        "stale-observation",
        "matched",
    ]


def test_alignment_never_uses_a_future_observation_and_age_policy_changes_identity(
    tmp_path: Path,
) -> None:
    spot, funding, klines = _input_datasets(tmp_path)
    derivative_manifest, observations = DerivativeDatasetStore(tmp_path).load(funding[0])
    rows = align_derivatives(
        klines,
        derivative_manifest=derivative_manifest,
        observations=observations,
        max_age_ms=60 * 60 * 1000,
    )

    assert [item.availability for item in rows] == [
        "no-prior-observation",
        "matched",
        "stale-observation",
        "matched",
    ]
    assert rows[2].observation_time == START + timedelta(hours=1, minutes=30)
    assert rows[2].funding_rate is None
    assert all(
        item.observation_time is None or item.observation_time <= item.decision_time
        for item in rows
    )

    shorter = materialize_derivatives_alignment(
        spot_dataset=spot.path,
        derivative_dataset=funding[0],
        start=START,
        end=END,
        max_age_ms=15 * 60 * 1000,
        output_root=tmp_path / "outputs",
        now=END,
    )
    longer = materialize_derivatives_alignment(
        spot_dataset=spot.path,
        derivative_dataset=funding[0],
        start=START,
        end=END,
        max_age_ms=60 * 60 * 1000,
        output_root=tmp_path / "outputs",
        now=END,
    )
    assert shorter.manifest.dataset_version != longer.manifest.dataset_version
    assert shorter.manifest.matched_count == 0

    reused = materialize_derivatives_alignment(
        spot_dataset=spot.path,
        derivative_dataset=funding[0],
        start=START,
        end=END,
        max_age_ms=60 * 60 * 1000,
        output_root=tmp_path / "outputs",
        now=END,
    )
    assert reused.path == longer.path


def test_rejects_invalid_alignment_inputs(tmp_path: Path) -> None:
    _, funding, klines = _input_datasets(tmp_path)
    manifest, observations = DerivativeDatasetStore(tmp_path).load(funding[0])

    with pytest.raises(ConfigurationError, match="positive"):
        align_derivatives(
            klines,
            derivative_manifest=manifest,
            observations=observations,
            max_age_ms=0,
        )
    with pytest.raises(DatasetError, match="must not be empty"):
        align_derivatives(
            [],
            derivative_manifest=manifest,
            observations=observations,
            max_age_ms=1,
        )
    with pytest.raises(DatasetError, match="one symbol"):
        align_derivatives(
            [klines[0], make_kline(START + timedelta(hours=1), symbol="ETHUSDT")],
            derivative_manifest=manifest,
            observations=observations,
            max_age_ms=1,
        )
    with pytest.raises(DatasetError, match="symbols must match"):
        align_derivatives(
            klines,
            derivative_manifest=replace(manifest, symbol="ETHUSDT"),
            observations=observations,
            max_age_ms=1,
        )
    with pytest.raises(DatasetError, match="funding observations"):
        align_derivatives(
            klines,
            derivative_manifest=manifest,
            observations=[
                OpenInterestObservation(
                    "BTCUSDT", Interval.ONE_HOUR, START, Decimal("1"), Decimal("2")
                )
            ],
            max_age_ms=1,
        )
    with pytest.raises(DatasetError, match="open-interest observations"):
        align_derivatives(
            klines,
            derivative_manifest=replace(manifest, series="open-interest", period="1h"),
            observations=observations,
            max_age_ms=1,
        )
    with pytest.raises(DatasetError, match="unsupported"):
        align_derivatives(
            klines,
            derivative_manifest=replace(manifest, series="unknown"),
            observations=observations,
            max_age_ms=1,
        )
    with pytest.raises(DatasetError, match="ordered and unique"):
        align_derivatives(
            klines,
            derivative_manifest=manifest,
            observations=list(reversed(observations)),
            max_age_ms=1,
        )


def test_materializer_rejects_empty_ranges_and_nonpositive_age(tmp_path: Path) -> None:
    spot, funding, _ = _input_datasets(tmp_path)
    with pytest.raises(ConfigurationError, match="positive"):
        materialize_derivatives_alignment(
            spot_dataset=spot.path,
            derivative_dataset=funding[0],
            start=START,
            end=END,
            max_age_ms=0,
            output_root=tmp_path,
        )
    with pytest.raises(DatasetError, match="no Spot Klines"):
        materialize_derivatives_alignment(
            spot_dataset=spot.path,
            derivative_dataset=funding[0],
            start=END + timedelta(hours=1),
            end=END + timedelta(hours=2),
            max_age_ms=1,
            output_root=tmp_path,
        )


def test_aligns_typed_open_interest_values(tmp_path: Path) -> None:
    bar = make_kline(START)
    path, manifest = DerivativeDatasetStore(tmp_path).publish_open_interest(
        [
            OpenInterestObservation(
                "BTCUSDT",
                Interval.FIFTEEN_MINUTES,
                START + timedelta(minutes=45),
                Decimal("1000"),
                Decimal("100000"),
            )
        ],
        requested_start=START,
        requested_end=START + timedelta(hours=1),
    )
    loaded_manifest, observations = DerivativeDatasetStore(tmp_path).load(path)
    assert loaded_manifest == manifest

    rows = align_derivatives(
        [bar],
        derivative_manifest=loaded_manifest,
        observations=observations,
        max_age_ms=30 * 60 * 1000,
    )

    assert rows[0].availability == "matched"
    assert rows[0].derivative_period == Interval.FIFTEEN_MINUTES
    assert rows[0].open_interest_value == Decimal("100000")
    assert rows[0].funding_rate is None


def test_store_rejects_observation_after_decision_bar(tmp_path: Path) -> None:
    invalid = AlignedDerivativeRow(
        "funding-rate",
        "BTCUSDT",
        Interval.ONE_HOUR,
        None,
        START,
        START + timedelta(hours=1) - timedelta(milliseconds=1),
        START + timedelta(hours=1),
        -1,
        "matched",
        Decimal("0.1"),
        Decimal("100"),
        None,
        None,
    )
    with pytest.raises(DatasetError, match="causal"):
        AlignedDerivativeStore(tmp_path).publish(
            [invalid],
            spot_manifest=object(),
            derivative_manifest=object(),
            requested_start=START,
            requested_end=END,
            max_age_ms=60 * 60 * 1000,
        )


def test_store_rejects_manifest_identity_mismatches(tmp_path: Path) -> None:
    spot, funding, klines = _input_datasets(tmp_path)
    derivative_manifest, observations = DerivativeDatasetStore(tmp_path).load(funding[0])
    rows = align_derivatives(
        klines,
        derivative_manifest=derivative_manifest,
        observations=observations,
        max_age_ms=60 * 60 * 1000,
    )
    store = AlignedDerivativeStore(tmp_path)
    with pytest.raises(DatasetError, match="Spot manifest"):
        store.publish(
            rows,
            spot_manifest=replace(spot.manifest, symbol="ETHUSDT"),
            derivative_manifest=derivative_manifest,
            requested_start=START,
            requested_end=END,
            max_age_ms=60 * 60 * 1000,
        )
    with pytest.raises(DatasetError, match="derivatives manifest"):
        store.publish(
            rows,
            spot_manifest=spot.manifest,
            derivative_manifest=replace(derivative_manifest, symbol="ETHUSDT"),
            requested_start=START,
            requested_end=END,
            max_age_ms=60 * 60 * 1000,
        )


def test_store_rejects_invalid_typed_feature_values(tmp_path: Path) -> None:
    matched_funding = AlignedDerivativeRow(
        "funding-rate",
        "BTCUSDT",
        Interval.ONE_HOUR,
        None,
        START,
        START + timedelta(hours=1) - timedelta(milliseconds=1),
        START + timedelta(minutes=30),
        1_799_999,
        "matched",
        Decimal("0.1"),
        Decimal("100"),
        None,
        None,
    )
    matched_interest = replace(
        matched_funding,
        series="open-interest",
        derivative_period=Interval.ONE_HOUR,
        funding_rate=None,
        mark_price=None,
        open_interest=Decimal("10"),
        open_interest_value=Decimal("1000"),
    )
    invalid_rows = [
        replace(matched_funding, funding_rate=Decimal("NaN")),
        replace(matched_funding, availability="stale-observation", age_ms=4_000_000),
        replace(matched_funding, derivative_period=Interval.ONE_HOUR),
        replace(matched_funding, funding_rate=None),
        replace(matched_funding, mark_price=Decimal("-1")),
        replace(matched_interest, derivative_period=None),
        replace(matched_interest, open_interest=None),
        replace(matched_interest, open_interest=Decimal("-1")),
        replace(matched_funding, series="unknown"),
    ]
    invalid_rows[1] = replace(invalid_rows[1], funding_rate=Decimal("0.1"))

    for row in invalid_rows:
        with pytest.raises(DatasetError):
            AlignedDerivativeStore(tmp_path).publish(
                [row],
                spot_manifest=object(),
                derivative_manifest=object(),
                requested_start=START,
                requested_end=END,
                max_age_ms=60 * 60 * 1000,
            )

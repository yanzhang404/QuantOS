from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest
from quantos_market_data.errors import ValidationError
from quantos_market_data.validation import validate_klines

from .conftest import make_kline


def test_accepts_contiguous_valid_klines(start_time) -> None:
    klines = [make_kline(start_time + timedelta(hours=index)) for index in range(3)]

    report = validate_klines(klines)

    assert report.is_valid
    assert report.row_count == 3
    assert report.to_dict()["is_valid"] is True


def test_rejects_empty_dataset() -> None:
    report = validate_klines([])

    assert not report.is_valid
    with pytest.raises(ValidationError, match="no Klines"):
        report.raise_if_invalid()


def test_detects_gap_duplicate_and_invalid_values(start_time) -> None:
    first = make_kline(start_time)
    duplicate = first
    gap = make_kline(start_time + timedelta(hours=3))
    invalid = replace(
        make_kline(start_time + timedelta(hours=4)),
        high=Decimal("80"),
        volume=Decimal("-1"),
    )

    report = validate_klines([first, duplicate, gap, invalid])

    assert not report.is_valid
    assert report.duplicate_count == 1
    assert report.missing_count == 2
    assert report.invalid_ohlc_count == 1
    assert report.invalid_volume_count == 1


def test_detects_incomplete_requested_coverage(start_time) -> None:
    klines = [make_kline(start_time), make_kline(start_time + timedelta(hours=1))]

    report = validate_klines(
        klines,
        requested_start=start_time,
        requested_end=start_time + timedelta(hours=3),
    )

    assert not report.is_valid
    assert "fully cover" in report.errors[-1]

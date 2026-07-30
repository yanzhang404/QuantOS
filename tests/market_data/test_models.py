from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from quantos_market_data.errors import ConfigurationError, DownloadError
from quantos_market_data.models import (
    Interval,
    Kline,
    datetime_to_milliseconds,
    normalize_symbol,
)


def test_normalizes_supported_symbol_and_interval() -> None:
    assert normalize_symbol(" btcusdt ") == "BTCUSDT"
    assert Interval.parse("4h") is Interval.FOUR_HOURS
    assert Interval.parse("5m") is Interval.FIVE_MINUTES
    assert Interval.parse("15m") is Interval.FIFTEEN_MINUTES
    assert Interval.parse("1d") is Interval.ONE_DAY


def test_rejects_unsupported_contract_values() -> None:
    with pytest.raises(ConfigurationError, match="unsupported symbol"):
        normalize_symbol("SOLUSDT")
    with pytest.raises(ConfigurationError, match="unsupported interval"):
        Interval.parse("30m")


def test_requires_timezone_for_milliseconds() -> None:
    with pytest.raises(ConfigurationError, match="timezone"):
        datetime_to_milliseconds(datetime(2024, 1, 1))


def test_normalizes_binance_row() -> None:
    row = [
        1_704_067_200_000,
        "42000.1",
        "42100.2",
        "41900.3",
        "42050.4",
        "10.5",
        1_704_070_799_999,
        "441000.6",
        100,
        "5.2",
        "218000.3",
        "unused",
    ]

    kline = Kline.from_binance_row("BTCUSDT", Interval.ONE_HOUR, row)

    assert kline.open_time == datetime(2024, 1, 1, tzinfo=UTC)
    assert kline.close == Decimal("42050.4")
    assert kline.trade_count == 100
    assert kline.canonical_values()[0:3] == ["binance", "BTCUSDT", "1h"]


def test_rejects_short_binance_row() -> None:
    with pytest.raises(DownloadError, match="expected at least 11"):
        Kline.from_binance_row("BTCUSDT", Interval.ONE_HOUR, [1, 2])

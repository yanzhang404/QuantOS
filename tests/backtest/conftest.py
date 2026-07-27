from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from quantos_market_data.models import Interval, Kline


@pytest.fixture
def start_time() -> datetime:
    return datetime(2024, 1, 1, tzinfo=UTC)


@pytest.fixture
def price_klines(start_time):
    prices = [
        ("10", "10"),
        ("20", "9"),
        ("30", "8"),
        ("40", "9"),
    ]
    result: list[Kline] = []
    for index, (open_price, close_price) in enumerate(prices):
        open_time = start_time + timedelta(hours=index)
        high = str(max(Decimal(open_price), Decimal(close_price)) + Decimal("1"))
        low = str(min(Decimal(open_price), Decimal(close_price)) - Decimal("1"))
        result.append(
            Kline(
                exchange="binance",
                symbol="BTCUSDT",
                interval=Interval.ONE_HOUR,
                open_time=open_time,
                close_time=open_time + timedelta(hours=1) - timedelta(milliseconds=1),
                open=Decimal(open_price),
                high=Decimal(high),
                low=Decimal(low),
                close=Decimal(close_price),
                volume=Decimal("100"),
                quote_volume=Decimal("1000"),
                trade_count=10,
                taker_buy_base_volume=Decimal("50"),
                taker_buy_quote_volume=Decimal("500"),
            )
        )
    return result

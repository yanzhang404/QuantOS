from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from quantos_market_data.models import Interval, Kline


@pytest.fixture
def start_time() -> datetime:
    return datetime(2024, 1, 1, tzinfo=UTC)


def make_kline(
    open_time: datetime,
    *,
    interval: Interval = Interval.ONE_HOUR,
    symbol: str = "BTCUSDT",
    open_price: str = "100",
    high: str = "110",
    low: str = "90",
    close: str = "105",
    volume: str = "12.5",
) -> Kline:
    return Kline(
        exchange="binance",
        symbol=symbol,
        interval=interval,
        open_time=open_time,
        close_time=open_time
        + timedelta(milliseconds=interval.milliseconds)
        - timedelta(milliseconds=1),
        open=Decimal(open_price),
        high=Decimal(high),
        low=Decimal(low),
        close=Decimal(close),
        volume=Decimal(volume),
        quote_volume=Decimal("1280"),
        trade_count=42,
        taker_buy_base_volume=Decimal("6"),
        taker_buy_quote_volume=Decimal("640"),
    )

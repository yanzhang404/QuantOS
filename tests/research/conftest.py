from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from quantos_market_data.models import Interval, Kline


@pytest.fixture
def research_klines() -> list[Kline]:
    start = datetime(2024, 1, 1, tzinfo=UTC)
    pattern = (0, 2, 5, 8, 5, 2, -1, -4, -1, 2)
    result: list[Kline] = []
    previous = Decimal("100")
    for index in range(120):
        open_time = start + timedelta(hours=index)
        close = Decimal(100 + index // 20 + pattern[index % len(pattern)])
        result.append(
            Kline(
                exchange="binance",
                symbol="BTCUSDT",
                interval=Interval.ONE_HOUR,
                open_time=open_time,
                close_time=open_time + timedelta(hours=1) - timedelta(milliseconds=1),
                open=previous,
                high=max(previous, close) + Decimal("1"),
                low=min(previous, close) - Decimal("1"),
                close=close,
                volume=Decimal("100"),
                quote_volume=Decimal("10000"),
                trade_count=100,
                taker_buy_base_volume=Decimal("50"),
                taker_buy_quote_volume=Decimal("5000"),
            )
        )
        previous = close
    return result

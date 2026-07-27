from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import timedelta
from decimal import Decimal

import pytest
from quantos_backtest.errors import BacktestConfigurationError
from quantos_backtest.strategies import EmaCrossStrategy
from quantos_events import MarketEvent
from quantos_strategy import StrategyContext


def market_event(start_time, index: int, close: str) -> MarketEvent:
    open_time = start_time + timedelta(hours=index)
    close_time = open_time + timedelta(hours=1) - timedelta(milliseconds=1)
    return MarketEvent(
        timestamp=close_time,
        exchange="binance",
        symbol="BTCUSDT",
        interval="1h",
        open_time=open_time,
        close_time=close_time,
        open=Decimal(close),
        high=Decimal(close),
        low=Decimal(close),
        close=Decimal(close),
        volume=Decimal("1"),
    )


def test_events_are_immutable(start_time) -> None:
    event = market_event(start_time, 0, "100")

    with pytest.raises(FrozenInstanceError):
        event.close = Decimal("99")


def test_ema_strategy_emits_only_after_warmup_and_target_change(start_time) -> None:
    strategy = EmaCrossStrategy(fast_period=2, slow_period=3)
    context = StrategyContext(symbol="BTCUSDT", interval="1h")
    strategy.initialize(context)
    signals = [
        strategy.on_bar(context, market_event(start_time, index, close))
        for index, close in enumerate(["10", "9", "8", "10", "12", "7"])
    ]

    emitted = [item for item in signals if item is not None]
    assert [item.target_exposure for item in emitted] == [Decimal("1"), Decimal("0")]
    assert emitted[0].timestamp == market_event(start_time, 3, "10").close_time
    assert "EMA(2)" in emitted[0].reason


@pytest.mark.parametrize(
    ("fast", "slow"),
    [(0, 3), (3, 3), (4, 3)],
)
def test_ema_strategy_rejects_invalid_periods(fast: int, slow: int) -> None:
    with pytest.raises(BacktestConfigurationError, match="EMA periods"):
        EmaCrossStrategy(fast_period=fast, slow_period=slow)

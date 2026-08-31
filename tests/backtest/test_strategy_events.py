from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal

import pytest
from quantos_backtest.errors import BacktestConfigurationError
from quantos_backtest.strategies import (
    BuyAndHoldStrategy,
    DonchianAtrStrategy,
    EmaCrossStrategy,
    FundingFilteredEmaStrategy,
)
from quantos_events import FeatureObservation, MarketEvent
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


def range_event(
    start_time,
    index: int,
    *,
    high: str,
    low: str,
    close: str,
) -> MarketEvent:
    event = market_event(start_time, index, close)
    return MarketEvent(
        timestamp=event.timestamp,
        exchange=event.exchange,
        symbol=event.symbol,
        interval=event.interval,
        open_time=event.open_time,
        close_time=event.close_time,
        open=event.open,
        high=Decimal(high),
        low=Decimal(low),
        close=event.close,
        volume=event.volume,
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


def test_funding_filtered_ema_uses_matched_rate_and_fails_flat_when_missing(
    start_time,
) -> None:
    strategy = FundingFilteredEmaStrategy(
        fast_period=2,
        slow_period=3,
        max_funding_rate=Decimal("0.0001"),
    )
    context = StrategyContext(symbol="BTCUSDT", interval="1h")
    strategy.initialize(context)

    def with_funding(index: int, close: str, rate: str | None) -> MarketEvent:
        event = market_event(start_time, index, close)
        feature = FeatureObservation(
            feature_id="aligned-funding-rate",
            dataset_version="funding-v1",
            availability="matched" if rate is not None else "stale-observation",
            observation_time=event.close_time if rate is not None else None,
            age_ms=0 if rate is not None else None,
            values=() if rate is None else (("funding_rate", Decimal(rate)),),
        )
        return replace(event, features=(feature,))

    signals = [
        strategy.on_bar(context, with_funding(index, close, rate))
        for index, (close, rate) in enumerate(
            [
                ("10", "0"),
                ("9", "0"),
                ("8", "0"),
                ("10", "0.001"),
                ("12", "0"),
                ("13", None),
            ]
        )
    ]

    emitted = [item for item in signals if item is not None]
    assert [item.target_exposure for item in emitted] == [Decimal("1"), Decimal("0")]
    assert "funding 0" in emitted[0].reason
    assert "fail flat" in emitted[1].reason
    assert strategy.parameters["max_funding_rate"] == "0.0001"


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("0.02"), Decimal("-0.02")])
def test_funding_filtered_ema_rejects_unbounded_threshold(value: Decimal) -> None:
    with pytest.raises(BacktestConfigurationError, match="max_funding_rate"):
        FundingFilteredEmaStrategy(fast_period=2, slow_period=3, max_funding_rate=value)


def test_buy_and_hold_emits_one_benchmark_target(start_time) -> None:
    strategy = BuyAndHoldStrategy(target_exposure=Decimal("0.75"))
    context = StrategyContext(symbol="BTCUSDT", interval="1h")
    strategy.initialize(context)

    first = strategy.on_bar(context, market_event(start_time, 0, "100"))
    second = strategy.on_bar(context, market_event(start_time, 1, "101"))

    assert first is not None
    assert first.target_exposure == Decimal("0.75")
    assert second is None
    assert strategy.parameters == {"target_exposure": "0.75"}


def test_buy_and_hold_rejects_invalid_exposure() -> None:
    with pytest.raises(BacktestConfigurationError, match="target_exposure"):
        BuyAndHoldStrategy(target_exposure=Decimal("0"))


def test_donchian_uses_prior_channel_and_exits_on_prior_low(start_time) -> None:
    strategy = DonchianAtrStrategy(
        entry_period=3,
        exit_period=2,
        atr_period=3,
        target_annual_volatility=Decimal("0.20"),
        rebalance_threshold=Decimal("1"),
    )
    context = StrategyContext(symbol="BTCUSDT", interval="1h")
    strategy.initialize(context)
    bars = [
        range_event(start_time, 0, high="10", low="8", close="9"),
        range_event(start_time, 1, high="11", low="9", close="10"),
        range_event(start_time, 2, high="12", low="10", close="11"),
        range_event(start_time, 3, high="14", low="12", close="13"),
        range_event(start_time, 4, high="9", low="7", close="8"),
    ]

    signals = [strategy.on_bar(context, bar) for bar in bars]

    assert signals[:3] == [None, None, None]
    assert signals[3] is not None
    assert Decimal("0") < signals[3].target_exposure < Decimal("1")
    assert "prior 3-bar high 12" in signals[3].reason
    assert signals[4] is not None
    assert signals[4].target_exposure == Decimal("0")
    assert "prior 2-bar low 10" in signals[4].reason


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"entry_period": 1}, "entry_period"),
        ({"entry_period": 2, "exit_period": 3}, "exit_period"),
        ({"atr_period": 1}, "atr_period"),
        ({"target_annual_volatility": Decimal("0")}, "target_annual_volatility"),
        ({"max_exposure": Decimal("1.1")}, "max_exposure"),
        ({"rebalance_threshold": Decimal("-0.1")}, "rebalance_threshold"),
    ],
)
def test_donchian_rejects_invalid_configuration(kwargs, message: str) -> None:
    with pytest.raises(BacktestConfigurationError, match=message):
        DonchianAtrStrategy(**kwargs)

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from quantos_backtest import BacktestConfig, BacktestEngine
from quantos_events import FillEvent, MarketEvent, PortfolioEvent, SignalEvent
from quantos_metrics import calculate_metrics
from quantos_strategy import StrategyContext


class ScriptedStrategy:
    name = "scripted"
    version = "1.0"

    def __init__(self) -> None:
        self.count = 0
        self.parameters: dict[str, object] = {}
        self.fills: list[FillEvent] = []

    def initialize(self, context: StrategyContext) -> None:
        self.count = 0

    def on_bar(self, context: StrategyContext, event: MarketEvent):
        self.count += 1
        targets = {1: Decimal("1"), 3: Decimal("0")}
        if self.count not in targets:
            return None
        return SignalEvent(
            timestamp=event.close_time,
            symbol=context.symbol,
            target_exposure=targets[self.count],
            strategy=self.name,
            reason="scripted target",
        )

    def on_fill(self, context: StrategyContext, event: FillEvent) -> None:
        self.fills.append(event)

    def finalize(self, context: StrategyContext) -> None:
        return None


def test_engine_fills_signal_at_next_bar_open(price_klines) -> None:
    strategy = ScriptedStrategy()
    result = BacktestEngine().run(
        price_klines,
        strategy=strategy,
        strategy_parameters={},
        config=BacktestConfig(
            initial_cash=Decimal("1000"),
            fee_bps=Decimal("0"),
            slippage_bps=Decimal("0"),
            liquidate_at_end=False,
        ),
    )

    assert len(result.fills) == 2
    assert result.fills[0].timestamp == price_klines[1].open_time
    assert result.fills[0].price == price_klines[1].open
    assert result.fills[1].timestamp == price_klines[3].open_time
    assert result.fills[1].price == price_klines[3].open
    assert result.fills[0].quantity > 0
    assert result.fills[1].quantity < 0
    assert result.metrics.final_equity == pytest.approx(2000.0)
    assert tuple(strategy.fills) == result.fills


def test_engine_forces_end_liquidation(price_klines) -> None:
    strategy = ScriptedStrategy()
    result = BacktestEngine().run(
        price_klines[:2],
        strategy=strategy,
        strategy_parameters={},
        config=BacktestConfig(
            initial_cash=Decimal("1000"),
            fee_bps=Decimal("0"),
            slippage_bps=Decimal("0"),
            liquidate_at_end=True,
        ),
    )

    assert result.fills[-1].reason == "forced end-of-backtest liquidation"
    assert result.equity_curve[-1].position_quantity == 0


def test_metrics_calculate_return_sharpe_drawdown_and_costs() -> None:
    timestamp = datetime(2024, 1, 1, tzinfo=UTC)
    curve = [
        PortfolioEvent(timestamp, "BTCUSDT", Decimal("100"), Decimal("0"), Decimal("1"), equity)
        for equity in (Decimal("100"), Decimal("110"), Decimal("90"))
    ]
    fill = FillEvent(
        timestamp=timestamp,
        symbol="BTCUSDT",
        quantity=Decimal("-1"),
        price=Decimal("100"),
        notional=Decimal("100"),
        fee=Decimal("1.5"),
        slippage_bps=Decimal("5"),
        reason="test",
    )

    metrics = calculate_metrics(curve, [fill], interval="1h")

    assert metrics.total_return == pytest.approx(-0.1)
    assert metrics.max_drawdown == pytest.approx(20 / 110)
    assert metrics.sharpe_ratio is not None
    assert metrics.trade_count == 1
    assert metrics.fees_paid == 1.5


def test_metrics_reject_empty_or_unsupported_input() -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        calculate_metrics([], [], interval="1h")
    event = PortfolioEvent(
        datetime(2024, 1, 1, tzinfo=UTC),
        "BTCUSDT",
        Decimal("1"),
        Decimal("0"),
        Decimal("1"),
        Decimal("1"),
    )
    with pytest.raises(ValueError, match="unsupported"):
        calculate_metrics([event], [], interval="30m")


@pytest.mark.parametrize("interval", ["5m", "15m", "1h", "4h", "1d"])
def test_metrics_supports_product_timeframes(interval: str) -> None:
    timestamp = datetime(2024, 1, 1, tzinfo=UTC)
    curve = [
        PortfolioEvent(
            timestamp,
            "BTCUSDT",
            Decimal("100"),
            Decimal("0"),
            Decimal("1"),
            equity,
        )
        for equity in (Decimal("100"), Decimal("101"), Decimal("102"))
    ]

    assert calculate_metrics(curve, [], interval=interval).total_return == pytest.approx(0.02)

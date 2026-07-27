from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from quantos_backtest.config import BacktestConfig
from quantos_backtest.errors import BacktestConfigurationError, PortfolioError
from quantos_backtest.execution import ExecutionModel, TargetOrderManager
from quantos_backtest.portfolio import Portfolio
from quantos_backtest.risk import LongOnlyRiskEngine
from quantos_events import FillEvent, SignalEvent


def approved_risk(target: str = "1"):
    signal = SignalEvent(
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        symbol="BTCUSDT",
        target_exposure=Decimal(target),
        strategy="test",
        reason="test",
    )
    return LongOnlyRiskEngine(max_target_exposure=Decimal("1")).evaluate(
        signal,
        symbol="BTCUSDT",
    )


def test_order_fill_applies_adverse_slippage_fee_and_cash_limit() -> None:
    portfolio = Portfolio(symbol="BTCUSDT", initial_cash=Decimal("1000"))
    execution = ExecutionModel(fee_bps=Decimal("10"), slippage_bps=Decimal("10"))
    order = TargetOrderManager().create_order(
        approved_risk(),
        timestamp=datetime(2024, 1, 2, tzinfo=UTC),
        reference_price=Decimal("100"),
        portfolio=portfolio,
        execution=execution,
    )

    assert order is not None
    fill = execution.fill(order)
    assert fill.price == Decimal("100.100")
    assert fill.fee > 0
    portfolio.apply_fill(fill)
    assert portfolio.position_quantity > 0
    assert portfolio.cash >= 0
    assert portfolio.equity(Decimal("100")) < Decimal("1000")


def test_risk_rejects_short_and_over_limit_targets() -> None:
    risk = LongOnlyRiskEngine(max_target_exposure=Decimal("0.5"))
    for target in (Decimal("-1"), Decimal("0.6")):
        signal = SignalEvent(
            timestamp=datetime(2024, 1, 1, tzinfo=UTC),
            symbol="BTCUSDT",
            target_exposure=target,
            strategy="test",
            reason="test",
        )
        assert not risk.evaluate(signal, symbol="BTCUSDT").approved


def test_portfolio_rejects_symbol_mismatch_and_short_fill() -> None:
    portfolio = Portfolio(symbol="BTCUSDT", initial_cash=Decimal("1000"))
    fill = FillEvent(
        timestamp=datetime(2024, 1, 1, tzinfo=UTC),
        symbol="ETHUSDT",
        quantity=Decimal("1"),
        price=Decimal("100"),
        notional=Decimal("100"),
        fee=Decimal("0"),
        slippage_bps=Decimal("0"),
        reason="test",
    )
    with pytest.raises(PortfolioError, match="symbol"):
        portfolio.apply_fill(fill)
    with pytest.raises(PortfolioError, match="short"):
        portfolio.apply_fill(
            FillEvent(
                timestamp=fill.timestamp,
                symbol="BTCUSDT",
                quantity=Decimal("-1"),
                price=Decimal("100"),
                notional=Decimal("100"),
                fee=Decimal("0"),
                slippage_bps=Decimal("0"),
                reason="test",
            )
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"initial_cash": Decimal("0")},
        {"fee_bps": Decimal("-1")},
        {"slippage_bps": Decimal("-1")},
        {"max_target_exposure": Decimal("1.1")},
    ],
)
def test_backtest_config_rejects_unsafe_values(kwargs) -> None:
    with pytest.raises(BacktestConfigurationError):
        BacktestConfig(**kwargs)

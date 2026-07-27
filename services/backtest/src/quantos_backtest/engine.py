"""Deterministic event-driven Kline replay engine."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from quantos_events import (
    FillEvent,
    MarketEvent,
    MetricEvent,
    OrderEvent,
    PortfolioEvent,
    RiskEvent,
    SignalEvent,
)
from quantos_market_data.models import Kline
from quantos_market_data.validation import validate_klines
from quantos_metrics import PerformanceMetrics, calculate_metrics
from quantos_metrics import __version__ as metrics_version
from quantos_strategy import Strategy, StrategyContext

from .config import BacktestConfig
from .execution import ExecutionModel, TargetOrderManager
from .portfolio import Portfolio
from .risk import LongOnlyRiskEngine
from .version import __version__

BacktestEvent = (
    MarketEvent | SignalEvent | RiskEvent | OrderEvent | FillEvent | PortfolioEvent | MetricEvent
)


@dataclass(frozen=True, slots=True)
class BacktestResult:
    engine_version: str
    metrics_version: str
    strategy_name: str
    strategy_version: str
    strategy_parameters: dict[str, Any]
    symbol: str
    interval: str
    config: BacktestConfig
    metrics: PerformanceMetrics
    fills: tuple[FillEvent, ...]
    equity_curve: tuple[PortfolioEvent, ...]
    events: tuple[BacktestEvent, ...]


class BacktestEngine:
    """Replay closed Klines and fill approved signals at the next bar open."""

    version = __version__

    def run(
        self,
        klines: list[Kline],
        *,
        strategy: Strategy,
        strategy_parameters: dict[str, Any],
        config: BacktestConfig,
    ) -> BacktestResult:
        report = validate_klines(klines)
        report.raise_if_invalid()
        first = klines[0]
        context = StrategyContext(symbol=first.symbol, interval=first.interval.value)
        strategy.initialize(context)

        portfolio = Portfolio(symbol=first.symbol, initial_cash=config.initial_cash)
        risk_engine = LongOnlyRiskEngine(
            max_target_exposure=config.max_target_exposure,
        )
        execution = ExecutionModel(
            fee_bps=config.fee_bps,
            slippage_bps=config.slippage_bps,
        )
        order_manager = TargetOrderManager()
        pending_risk: RiskEvent | None = None
        events: list[BacktestEvent] = []
        fills: list[FillEvent] = []
        equity_curve: list[PortfolioEvent] = []

        for kline in klines:
            if pending_risk is not None:
                order = order_manager.create_order(
                    pending_risk,
                    timestamp=kline.open_time,
                    reference_price=kline.open,
                    portfolio=portfolio,
                    execution=execution,
                )
                pending_risk = None
                if order is not None:
                    events.append(order)
                    fill = execution.fill(order)
                    events.append(fill)
                    fills.append(fill)
                    portfolio.apply_fill(fill)
                    strategy.on_fill(context, fill)

            market_event = _market_event(kline)
            events.append(market_event)
            portfolio_event = portfolio.snapshot(
                timestamp=kline.close_time,
                market_price=kline.close,
            )
            events.append(portfolio_event)
            equity_curve.append(portfolio_event)

            signal = strategy.on_bar(context, market_event)
            if signal is not None:
                events.append(signal)
                risk = risk_engine.evaluate(signal, symbol=first.symbol)
                events.append(risk)
                if risk.approved:
                    pending_risk = risk

        if config.liquidate_at_end and portfolio.position_quantity > 0:
            last = klines[-1]
            order = OrderEvent(
                timestamp=last.close_time,
                symbol=first.symbol,
                quantity=-portfolio.position_quantity,
                reference_price=last.close,
                reason="forced end-of-backtest liquidation",
            )
            events.append(order)
            fill = execution.fill(order)
            events.append(fill)
            fills.append(fill)
            portfolio.apply_fill(fill)
            strategy.on_fill(context, fill)
            final_portfolio = portfolio.snapshot(
                timestamp=last.close_time,
                market_price=last.close,
            )
            events.append(final_portfolio)
            equity_curve[-1] = final_portfolio
        strategy.finalize(context)

        metrics = calculate_metrics(
            equity_curve,
            fills,
            interval=first.interval.value,
        )
        metric_time = klines[-1].close_time
        for name, value in metrics.to_dict().items():
            events.append(MetricEvent(timestamp=metric_time, name=name, value=value))

        return BacktestResult(
            engine_version=self.version,
            metrics_version=metrics_version,
            strategy_name=strategy.name,
            strategy_version=strategy.version,
            strategy_parameters=dict(strategy_parameters),
            symbol=first.symbol,
            interval=first.interval.value,
            config=config,
            metrics=metrics,
            fills=tuple(fills),
            equity_curve=tuple(equity_curve),
            events=tuple(events),
        )


def _market_event(kline: Kline) -> MarketEvent:
    return MarketEvent(
        timestamp=kline.close_time,
        exchange=kline.exchange,
        symbol=kline.symbol,
        interval=kline.interval.value,
        open_time=kline.open_time,
        close_time=kline.close_time,
        open=kline.open,
        high=kline.high,
        low=kline.low,
        close=kline.close,
        volume=kline.volume,
    )

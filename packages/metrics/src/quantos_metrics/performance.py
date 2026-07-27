"""Performance metrics with explicit annualization assumptions."""

from __future__ import annotations

import math
import statistics
from dataclasses import asdict, dataclass
from decimal import Decimal
from itertools import pairwise

from quantos_events import FillEvent, PortfolioEvent

PERIODS_PER_YEAR = {
    "1h": 365 * 24,
    "4h": 365 * 6,
}


@dataclass(frozen=True, slots=True)
class PerformanceMetrics:
    initial_equity: float
    final_equity: float
    total_return: float
    sharpe_ratio: float | None
    max_drawdown: float
    fill_count: int
    trade_count: int
    fees_paid: float

    def to_dict(self) -> dict[str, float | int | None]:
        return asdict(self)


def calculate_metrics(
    equity_curve: list[PortfolioEvent],
    fills: list[FillEvent],
    *,
    interval: str,
) -> PerformanceMetrics:
    if not equity_curve:
        raise ValueError("equity curve must not be empty")
    if interval not in PERIODS_PER_YEAR:
        raise ValueError(f"unsupported metric interval: {interval}")

    equities = [float(item.equity) for item in equity_curve]
    initial_equity = equities[0]
    final_equity = equities[-1]
    if initial_equity <= 0:
        raise ValueError("initial equity must be positive")

    returns = [current / previous - 1 for previous, current in pairwise(equities) if previous != 0]
    sharpe_ratio: float | None = None
    if len(returns) >= 2:
        deviation = statistics.stdev(returns)
        if deviation > 0:
            sharpe_ratio = (
                statistics.mean(returns) / deviation * math.sqrt(PERIODS_PER_YEAR[interval])
            )

    peak = equities[0]
    max_drawdown = 0.0
    for equity in equities:
        peak = max(peak, equity)
        drawdown = (peak - equity) / peak if peak > 0 else 0.0
        max_drawdown = max(max_drawdown, drawdown)

    fees_paid = sum((item.fee for item in fills), start=Decimal("0"))
    return PerformanceMetrics(
        initial_equity=initial_equity,
        final_equity=final_equity,
        total_return=final_equity / initial_equity - 1,
        sharpe_ratio=sharpe_ratio,
        max_drawdown=max_drawdown,
        fill_count=len(fills),
        trade_count=sum(1 for item in fills if item.quantity < 0),
        fees_paid=float(fees_paid),
    )

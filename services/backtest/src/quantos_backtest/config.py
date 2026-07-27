"""Explicit assumptions for one backtest run."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal

from .errors import BacktestConfigurationError


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    initial_cash: Decimal = Decimal("100000")
    fee_bps: Decimal = Decimal("10")
    slippage_bps: Decimal = Decimal("5")
    max_target_exposure: Decimal = Decimal("1")
    liquidate_at_end: bool = True

    def __post_init__(self) -> None:
        if self.initial_cash <= 0:
            raise BacktestConfigurationError("initial_cash must be positive")
        if self.fee_bps < 0:
            raise BacktestConfigurationError("fee_bps must be non-negative")
        if self.slippage_bps < 0:
            raise BacktestConfigurationError("slippage_bps must be non-negative")
        if not Decimal("0") < self.max_target_exposure <= Decimal("1"):
            raise BacktestConfigurationError("max_target_exposure must be in (0, 1]")

    def to_dict(self) -> dict[str, str | bool]:
        values = asdict(self)
        return {
            key: str(value) if isinstance(value, Decimal) else value
            for key, value in values.items()
        }

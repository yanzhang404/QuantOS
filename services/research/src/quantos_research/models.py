"""Research workflow contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from quantos_backtest import BacktestConfig, BacktestResult
from quantos_market_data.models import Kline

from .errors import ResearchConfigurationError


@dataclass(frozen=True, slots=True)
class ResearchConfig:
    fast_periods: tuple[int, ...]
    slow_periods: tuple[int, ...]
    train_ratio: Decimal = Decimal("0.6")
    validation_ratio: Decimal = Decimal("0.2")
    min_bars_per_split: int = 20
    backtest: BacktestConfig = field(default_factory=BacktestConfig)

    def __post_init__(self) -> None:
        if not self.fast_periods or not self.slow_periods:
            raise ResearchConfigurationError("fast and slow period grids must not be empty")
        if any(period < 1 for period in self.fast_periods):
            raise ResearchConfigurationError("fast periods must be positive")
        if any(period < 2 for period in self.slow_periods):
            raise ResearchConfigurationError("slow periods must be at least 2")
        if self.train_ratio <= 0 or self.validation_ratio <= 0:
            raise ResearchConfigurationError("split ratios must be positive")
        if self.train_ratio + self.validation_ratio >= 1:
            raise ResearchConfigurationError(
                "train_ratio + validation_ratio must leave a positive test split"
            )
        if self.min_bars_per_split < 3:
            raise ResearchConfigurationError("min_bars_per_split must be at least 3")
        if not any(fast < slow for fast in self.fast_periods for slow in self.slow_periods):
            raise ResearchConfigurationError("parameter grid has no valid fast < slow pair")

    @property
    def candidates(self) -> tuple[tuple[int, int], ...]:
        return tuple(
            sorted(
                (fast, slow)
                for fast in set(self.fast_periods)
                for slow in set(self.slow_periods)
                if fast < slow
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fast_periods": list(self.fast_periods),
            "slow_periods": list(self.slow_periods),
            "train_ratio": str(self.train_ratio),
            "validation_ratio": str(self.validation_ratio),
            "test_ratio": str(Decimal("1") - self.train_ratio - self.validation_ratio),
            "min_bars_per_split": self.min_bars_per_split,
            "backtest": self.backtest.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class TimeSplit:
    train: tuple[Kline, ...]
    validation: tuple[Kline, ...]
    test: tuple[Kline, ...]


@dataclass(frozen=True, slots=True)
class CandidateResult:
    fast_period: int
    slow_period: int
    train: BacktestResult
    validation: BacktestResult
    train_run_id: str
    validation_run_id: str

    @property
    def score(self) -> float:
        sharpe = self.validation.metrics.sharpe_ratio
        return float("-inf") if sharpe is None else sharpe


@dataclass(frozen=True, slots=True)
class ReviewFinding:
    severity: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class ResearchStudy:
    config: ResearchConfig
    split: TimeSplit
    candidates: tuple[CandidateResult, ...]
    winner: CandidateResult
    test: BacktestResult
    stress: BacktestResult
    test_run_id: str
    stress_run_id: str
    findings: tuple[ReviewFinding, ...]

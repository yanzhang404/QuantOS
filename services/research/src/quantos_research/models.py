"""Research workflow contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from itertools import product
from typing import Any

from quantos_backtest import BacktestConfig, BacktestResult
from quantos_market_data.models import Kline

from .errors import ResearchConfigurationError

ParameterValue = int | str
_MAX_GRID_AXIS_VALUES = 32
_MAX_CANDIDATES = 256


@dataclass(frozen=True, slots=True)
class ParameterSet:
    values: tuple[tuple[str, ParameterValue], ...]

    @classmethod
    def from_dict(cls, values: dict[str, ParameterValue]) -> ParameterSet:
        if not values:
            raise ResearchConfigurationError("strategy parameters must not be empty")
        normalized: list[tuple[str, ParameterValue]] = []
        for name, value in sorted(values.items()):
            if (
                not name.isidentifier()
                or len(name) > 64
                or isinstance(value, bool)
                or not isinstance(value, (int, str))
            ):
                raise ResearchConfigurationError("strategy parameters are invalid")
            if isinstance(value, str) and (not value or len(value) > 128):
                raise ResearchConfigurationError("strategy parameters are invalid")
            normalized.append((name, value))
        return cls(tuple(normalized))

    def to_dict(self) -> dict[str, ParameterValue]:
        return dict(self.values)

    def __getitem__(self, name: str) -> ParameterValue:
        try:
            return dict(self.values)[name]
        except KeyError as exc:
            raise ResearchConfigurationError(f"strategy parameter {name} is unavailable") from exc


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
        _validate_grid_axis(self.fast_periods, "fast periods")
        _validate_grid_axis(self.slow_periods, "slow periods")
        if any(period < 1 for period in self.fast_periods):
            raise ResearchConfigurationError("fast periods must be positive")
        if any(period < 2 for period in self.slow_periods):
            raise ResearchConfigurationError("slow periods must be at least 2")
        _validate_split(self.train_ratio, self.validation_ratio, self.min_bars_per_split)
        if not any(fast < slow for fast in self.fast_periods for slow in self.slow_periods):
            raise ResearchConfigurationError("parameter grid has no valid fast < slow pair")
        if len(self.candidates) > _MAX_CANDIDATES:
            raise ResearchConfigurationError("parameter grid exceeds 256 valid candidates")

    @property
    def candidates(self) -> tuple[ParameterSet, ...]:
        return tuple(
            ParameterSet.from_dict({"fast_period": fast, "slow_period": slow})
            for fast, slow in sorted(
                {
                    (fast, slow)
                    for fast in set(self.fast_periods)
                    for slow in set(self.slow_periods)
                    if fast < slow
                }
            )
        )

    @property
    def strategy_name(self) -> str:
        return "ema-cross"

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy_name,
            "fast_periods": list(self.fast_periods),
            "slow_periods": list(self.slow_periods),
            "train_ratio": str(self.train_ratio),
            "validation_ratio": str(self.validation_ratio),
            "test_ratio": str(Decimal("1") - self.train_ratio - self.validation_ratio),
            "min_bars_per_split": self.min_bars_per_split,
            "backtest": self.backtest.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class DonchianResearchConfig:
    entry_periods: tuple[int, ...]
    exit_periods: tuple[int, ...]
    atr_periods: tuple[int, ...]
    target_annual_volatility: Decimal = Decimal("0.20")
    max_exposure: Decimal = Decimal("1")
    rebalance_threshold: Decimal = Decimal("0.05")
    train_ratio: Decimal = Decimal("0.6")
    validation_ratio: Decimal = Decimal("0.2")
    min_bars_per_split: int = 20
    backtest: BacktestConfig = field(default_factory=BacktestConfig)

    def __post_init__(self) -> None:
        if not self.entry_periods or not self.exit_periods or not self.atr_periods:
            raise ResearchConfigurationError("Donchian period grids must not be empty")
        _validate_grid_axis(self.entry_periods, "entry periods")
        _validate_grid_axis(self.exit_periods, "exit periods")
        _validate_grid_axis(self.atr_periods, "ATR periods")
        if any(period < 2 for period in self.entry_periods):
            raise ResearchConfigurationError("entry periods must be at least 2")
        if any(period < 1 for period in self.exit_periods):
            raise ResearchConfigurationError("exit periods must be positive")
        if any(period < 2 for period in self.atr_periods):
            raise ResearchConfigurationError("ATR periods must be at least 2")
        if not any(
            exit_period <= entry
            for entry, exit_period in product(self.entry_periods, self.exit_periods)
        ):
            raise ResearchConfigurationError("Donchian grid has no valid exit <= entry candidate")
        if len(self.candidates) > _MAX_CANDIDATES:
            raise ResearchConfigurationError("parameter grid exceeds 256 valid candidates")
        if not self.target_annual_volatility.is_finite() or self.target_annual_volatility <= 0:
            raise ResearchConfigurationError("target annual volatility must be positive")
        if not self.max_exposure.is_finite() or not Decimal("0") < self.max_exposure <= Decimal(
            "1"
        ):
            raise ResearchConfigurationError("max exposure must be in (0, 1]")
        if not self.rebalance_threshold.is_finite() or not Decimal(
            "0"
        ) <= self.rebalance_threshold <= Decimal("1"):
            raise ResearchConfigurationError("rebalance threshold must be in [0, 1]")
        _validate_split(self.train_ratio, self.validation_ratio, self.min_bars_per_split)

    @property
    def candidates(self) -> tuple[ParameterSet, ...]:
        return tuple(
            ParameterSet.from_dict(
                {
                    "entry_period": entry,
                    "exit_period": exit_period,
                    "atr_period": atr,
                    "target_annual_volatility": str(self.target_annual_volatility),
                    "max_exposure": str(self.max_exposure),
                    "rebalance_threshold": str(self.rebalance_threshold),
                }
            )
            for entry, exit_period, atr in sorted(
                {
                    (entry, exit_period, atr)
                    for entry, exit_period, atr in product(
                        set(self.entry_periods), set(self.exit_periods), set(self.atr_periods)
                    )
                    if exit_period <= entry
                }
            )
        )

    @property
    def strategy_name(self) -> str:
        return "donchian-atr"

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy_name,
            "entry_periods": list(self.entry_periods),
            "exit_periods": list(self.exit_periods),
            "atr_periods": list(self.atr_periods),
            "target_annual_volatility": str(self.target_annual_volatility),
            "max_exposure": str(self.max_exposure),
            "rebalance_threshold": str(self.rebalance_threshold),
            "train_ratio": str(self.train_ratio),
            "validation_ratio": str(self.validation_ratio),
            "test_ratio": str(Decimal("1") - self.train_ratio - self.validation_ratio),
            "min_bars_per_split": self.min_bars_per_split,
            "backtest": self.backtest.to_dict(),
        }


ResearchConfigLike = ResearchConfig | DonchianResearchConfig


def _validate_grid_axis(periods: tuple[int, ...], label: str) -> None:
    if any(isinstance(period, bool) or not isinstance(period, int) for period in periods):
        raise ResearchConfigurationError(f"{label} must contain integers")
    if len(set(periods)) > _MAX_GRID_AXIS_VALUES:
        raise ResearchConfigurationError(f"{label} exceed 32 unique values")


def _validate_split(train_ratio: Decimal, validation_ratio: Decimal, minimum: int) -> None:
    if not train_ratio.is_finite() or not validation_ratio.is_finite():
        raise ResearchConfigurationError("split ratios must be finite")
    if train_ratio <= 0 or validation_ratio <= 0:
        raise ResearchConfigurationError("split ratios must be positive")
    if train_ratio + validation_ratio >= 1:
        raise ResearchConfigurationError(
            "train_ratio + validation_ratio must leave a positive test split"
        )
    if minimum < 3:
        raise ResearchConfigurationError("min_bars_per_split must be at least 3")


@dataclass(frozen=True, slots=True)
class TimeSplit:
    train: tuple[Kline, ...]
    validation: tuple[Kline, ...]
    test: tuple[Kline, ...]


@dataclass(frozen=True, slots=True)
class CandidateResult:
    parameters: ParameterSet
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
    config: ResearchConfigLike
    strategy_name: str
    strategy_version: str
    split: TimeSplit
    candidates: tuple[CandidateResult, ...]
    winner: CandidateResult
    test: BacktestResult
    stress: BacktestResult
    test_run_id: str
    stress_run_id: str
    findings: tuple[ReviewFinding, ...]


@dataclass(frozen=True, slots=True)
class RobustnessConfig:
    fold_count: int = 3
    min_bars_per_window: int = 20
    minimum_positive_fold_ratio: Decimal = Decimal("0.6")
    neighbor_retention_ratio: Decimal = Decimal("0.5")
    cost_retention_ratio: Decimal = Decimal("0.5")

    def __post_init__(self) -> None:
        if self.fold_count < 2 or self.fold_count > 10:
            raise ResearchConfigurationError("fold_count must be between 2 and 10")
        if self.min_bars_per_window < 3:
            raise ResearchConfigurationError("min_bars_per_window must be at least 3")
        for name, value in (
            ("minimum_positive_fold_ratio", self.minimum_positive_fold_ratio),
            ("neighbor_retention_ratio", self.neighbor_retention_ratio),
            ("cost_retention_ratio", self.cost_retention_ratio),
        ):
            if value <= 0 or value > 1:
                raise ResearchConfigurationError(f"{name} must be greater than 0 and at most 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "fold_count": self.fold_count,
            "min_bars_per_window": self.min_bars_per_window,
            "minimum_positive_fold_ratio": str(self.minimum_positive_fold_ratio),
            "neighbor_retention_ratio": str(self.neighbor_retention_ratio),
            "cost_retention_ratio": str(self.cost_retention_ratio),
        }


@dataclass(frozen=True, slots=True)
class RobustnessRun:
    label: str
    symbol: str
    parameters: ParameterSet
    run_id: str
    result: BacktestResult


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    index: int
    train: tuple[Kline, ...]
    validation: tuple[Kline, ...]
    test: tuple[Kline, ...]
    winner_parameters: ParameterSet
    validation_run_id: str
    test_run_id: str
    test_result: BacktestResult


@dataclass(frozen=True, slots=True)
class RobustnessGate:
    name: str
    passed: bool
    reason: str
    observations: dict[str, Any]
    run_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "reason": self.reason,
            "observations": self.observations,
            "run_ids": list(self.run_ids),
        }


@dataclass(frozen=True, slots=True)
class RobustnessReview:
    config: RobustnessConfig
    research_config: ResearchConfigLike
    primary_study: ResearchStudy
    folds: tuple[WalkForwardFold, ...]
    neighbors: tuple[RobustnessRun, ...]
    markets: tuple[RobustnessRun, ...]
    gates: tuple[RobustnessGate, ...]

    @property
    def passed(self) -> bool:
        return all(gate.passed for gate in self.gates)

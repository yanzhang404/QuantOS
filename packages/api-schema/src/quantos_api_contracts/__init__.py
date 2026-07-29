"""Versioned product API contracts shared with the Python compute plane."""

from .backtest_v1 import (
    BacktestConfigContract,
    BacktestSubmission,
    BacktestTask,
    ContractValidationError,
    DatasetRef,
    ExperimentMetrics,
    ExperimentRecord,
    StrategyRef,
    TaskError,
    strategy_catalog,
)

__all__ = [
    "BacktestConfigContract",
    "BacktestSubmission",
    "BacktestTask",
    "ContractValidationError",
    "DatasetRef",
    "ExperimentMetrics",
    "ExperimentRecord",
    "StrategyRef",
    "TaskError",
    "strategy_catalog",
]

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
from .candidate_v1 import CandidateParameter, CandidateProposal, CandidateSource

__all__ = [
    "BacktestConfigContract",
    "BacktestSubmission",
    "BacktestTask",
    "CandidateParameter",
    "CandidateProposal",
    "CandidateSource",
    "ContractValidationError",
    "DatasetRef",
    "ExperimentMetrics",
    "ExperimentRecord",
    "StrategyRef",
    "TaskError",
    "strategy_catalog",
]

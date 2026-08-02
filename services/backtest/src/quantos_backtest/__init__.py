"""Deterministic Kline-level event-driven backtesting."""

from .config import BacktestConfig
from .engine import BacktestEngine, BacktestResult, FeatureDatasetInput
from .version import __version__

__all__ = [
    "BacktestConfig",
    "BacktestEngine",
    "BacktestResult",
    "FeatureDatasetInput",
    "__version__",
]

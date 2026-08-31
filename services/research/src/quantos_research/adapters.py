"""Bounded strategy-specific adapters for chronological research."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from quantos_backtest.strategies import DonchianAtrStrategy, EmaCrossStrategy
from quantos_strategy import Strategy

from .errors import ResearchConfigurationError
from .models import (
    DonchianResearchConfig,
    ParameterSet,
    ResearchConfig,
    ResearchConfigLike,
)


class StrategyResearchAdapter(Protocol):
    name: str
    version: str
    candidates: tuple[ParameterSet, ...]

    def build(self, parameters: ParameterSet) -> Strategy: ...

    def minimum_bars(self, parameters: ParameterSet) -> int: ...

    def neighbors(self, winner: ParameterSet) -> tuple[ParameterSet, ...]: ...

    def rank_key(self, parameters: ParameterSet) -> tuple[Any, ...]: ...

    def label(self, parameters: ParameterSet) -> str: ...


class EmaResearchAdapter:
    name = EmaCrossStrategy.name
    version = EmaCrossStrategy.version

    def __init__(self, config: ResearchConfig) -> None:
        self.config = config
        self.candidates = config.candidates

    def build(self, parameters: ParameterSet) -> EmaCrossStrategy:
        return EmaCrossStrategy(
            fast_period=_integer(parameters, "fast_period"),
            slow_period=_integer(parameters, "slow_period"),
        )

    def minimum_bars(self, parameters: ParameterSet) -> int:
        return _integer(parameters, "slow_period")

    def neighbors(self, winner: ParameterSet) -> tuple[ParameterSet, ...]:
        return _grid_neighbors(
            winner,
            self.candidates,
            {
                "fast_period": tuple(sorted(set(self.config.fast_periods))),
                "slow_period": tuple(sorted(set(self.config.slow_periods))),
            },
        )

    def rank_key(self, parameters: ParameterSet) -> tuple[int, int]:
        return (
            _integer(parameters, "fast_period"),
            _integer(parameters, "slow_period"),
        )

    def label(self, parameters: ParameterSet) -> str:
        fast, slow = self.rank_key(parameters)
        return f"EMA({fast}, {slow})"


class DonchianResearchAdapter:
    name = DonchianAtrStrategy.name
    version = DonchianAtrStrategy.version

    def __init__(self, config: DonchianResearchConfig) -> None:
        self.config = config
        self.candidates = config.candidates

    def build(self, parameters: ParameterSet) -> DonchianAtrStrategy:
        return DonchianAtrStrategy(
            entry_period=_integer(parameters, "entry_period"),
            exit_period=_integer(parameters, "exit_period"),
            atr_period=_integer(parameters, "atr_period"),
            target_annual_volatility=_decimal(parameters, "target_annual_volatility"),
            max_exposure=_decimal(parameters, "max_exposure"),
            rebalance_threshold=_decimal(parameters, "rebalance_threshold"),
        )

    def minimum_bars(self, parameters: ParameterSet) -> int:
        return (
            max(
                _integer(parameters, "entry_period"),
                _integer(parameters, "exit_period"),
                _integer(parameters, "atr_period"),
            )
            + 1
        )

    def neighbors(self, winner: ParameterSet) -> tuple[ParameterSet, ...]:
        return _grid_neighbors(
            winner,
            self.candidates,
            {
                "entry_period": tuple(sorted(set(self.config.entry_periods))),
                "exit_period": tuple(sorted(set(self.config.exit_periods))),
                "atr_period": tuple(sorted(set(self.config.atr_periods))),
            },
        )

    def rank_key(self, parameters: ParameterSet) -> tuple[int, int, int]:
        return (
            _integer(parameters, "entry_period"),
            _integer(parameters, "exit_period"),
            _integer(parameters, "atr_period"),
        )

    def label(self, parameters: ParameterSet) -> str:
        entry, exit_period, atr = self.rank_key(parameters)
        return f"Donchian ATR(entry={entry}, exit={exit_period}, atr={atr})"


def adapter_for(config: ResearchConfigLike) -> StrategyResearchAdapter:
    if isinstance(config, ResearchConfig):
        return EmaResearchAdapter(config)
    if isinstance(config, DonchianResearchConfig):
        return DonchianResearchAdapter(config)
    raise ResearchConfigurationError("research strategy is unsupported")


def _grid_neighbors(
    winner: ParameterSet,
    candidates: tuple[ParameterSet, ...],
    axes: dict[str, tuple[int, ...]],
) -> tuple[ParameterSet, ...]:
    candidate_set = set(candidates)
    neighbors: set[ParameterSet] = set()
    winner_values = winner.to_dict()
    for name, values in axes.items():
        current = _integer(winner, name)
        position = values.index(current)
        for neighbor_position in (position - 1, position + 1):
            if not 0 <= neighbor_position < len(values):
                continue
            changed = {**winner_values, name: values[neighbor_position]}
            candidate = ParameterSet.from_dict(changed)
            if candidate in candidate_set:
                neighbors.add(candidate)
    return tuple(sorted(neighbors, key=lambda item: item.values))


def _integer(parameters: ParameterSet, name: str) -> int:
    value = parameters[name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ResearchConfigurationError(f"strategy parameter {name} must be an integer")
    return value


def _decimal(parameters: ParameterSet, name: str) -> Decimal:
    value = parameters[name]
    if not isinstance(value, str):
        raise ResearchConfigurationError(f"strategy parameter {name} must be a decimal string")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ResearchConfigurationError(
            f"strategy parameter {name} must be a decimal string"
        ) from exc
    if not result.is_finite():
        raise ResearchConfigurationError(f"strategy parameter {name} must be finite")
    return result

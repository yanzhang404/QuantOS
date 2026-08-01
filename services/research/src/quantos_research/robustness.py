"""Deterministic robustness gates for candidate promotion evidence."""

from __future__ import annotations

import statistics

from quantos_backtest import BacktestEngine
from quantos_backtest.artifacts import ExperimentStore
from quantos_backtest.strategies import EmaCrossStrategy
from quantos_market_data.models import Kline
from quantos_market_data.storage import DatasetManifest

from .errors import ResearchConfigurationError
from .models import (
    CandidateResult,
    ResearchConfig,
    ResearchStudy,
    RobustnessConfig,
    RobustnessGate,
    RobustnessReview,
    RobustnessRun,
    WalkForwardFold,
)


def walk_forward_windows(
    klines: list[Kline],
    *,
    fold_count: int,
    min_bars_per_window: int,
) -> tuple[tuple[tuple[Kline, ...], tuple[Kline, ...], tuple[Kline, ...]], ...]:
    block_count = fold_count + 2
    base_size, remainder = divmod(len(klines), block_count)
    if base_size < min_bars_per_window:
        raise ResearchConfigurationError(
            f"walk-forward blocks contain only {base_size} bars; "
            f"each requires at least {min_bars_per_window}"
        )
    blocks: list[tuple[Kline, ...]] = []
    start = 0
    for index in range(block_count):
        size = base_size + (1 if index < remainder else 0)
        blocks.append(tuple(klines[start : start + size]))
        start += size
    return tuple(
        (
            tuple(item for block in blocks[: index + 1] for item in block),
            blocks[index + 1],
            blocks[index + 2],
        )
        for index in range(fold_count)
    )


class RobustnessRunner:
    def __init__(self, *, engine: BacktestEngine | None = None) -> None:
        self.engine = engine or BacktestEngine()

    def run(
        self,
        primary_klines: list[Kline],
        *,
        primary_manifest: DatasetManifest,
        primary_study: ResearchStudy,
        research_config: ResearchConfig,
        robustness_config: RobustnessConfig,
        experiment_store: ExperimentStore,
        peer_datasets: tuple[tuple[list[Kline], DatasetManifest], ...],
    ) -> RobustnessReview:
        if primary_manifest.symbol != primary_klines[0].symbol:
            raise ResearchConfigurationError("primary manifest does not match Kline symbol")
        folds = self._walk_forward(
            primary_klines,
            manifest=primary_manifest,
            research_config=research_config,
            robustness_config=robustness_config,
            experiment_store=experiment_store,
        )
        neighbors = self._neighbors(
            primary_study,
            manifest=primary_manifest,
            research_config=research_config,
            experiment_store=experiment_store,
        )
        markets = self._markets(
            primary_study,
            primary_manifest=primary_manifest,
            research_config=research_config,
            experiment_store=experiment_store,
            peer_datasets=peer_datasets,
        )
        gates = (
            _walk_forward_gate(folds, robustness_config),
            _neighbor_gate(neighbors, primary_study.test.metrics.total_return, robustness_config),
            _cost_gate(primary_study, robustness_config),
            _market_gate(markets),
        )
        return RobustnessReview(
            config=robustness_config,
            research_config=research_config,
            primary_study=primary_study,
            folds=folds,
            neighbors=neighbors,
            markets=markets,
            gates=gates,
        )

    def _walk_forward(
        self,
        klines: list[Kline],
        *,
        manifest: DatasetManifest,
        research_config: ResearchConfig,
        robustness_config: RobustnessConfig,
        experiment_store: ExperimentStore,
    ) -> tuple[WalkForwardFold, ...]:
        windows = walk_forward_windows(
            klines,
            fold_count=robustness_config.fold_count,
            min_bars_per_window=robustness_config.min_bars_per_window,
        )
        folds: list[WalkForwardFold] = []
        for index, (train, validation, test) in enumerate(windows, start=1):
            candidates: list[CandidateResult] = []
            for fast, slow in research_config.candidates:
                train_result = self._backtest(train, fast, slow, research_config)
                validation_result = self._backtest(validation, fast, slow, research_config)
                train_artifact = experiment_store.publish(train_result, dataset=manifest)
                validation_artifact = experiment_store.publish(validation_result, dataset=manifest)
                candidates.append(
                    CandidateResult(
                        fast_period=fast,
                        slow_period=slow,
                        train=train_result,
                        validation=validation_result,
                        train_run_id=train_artifact.run_id,
                        validation_run_id=validation_artifact.run_id,
                    )
                )
            winner = sorted(
                candidates,
                key=lambda item: (-item.score, item.fast_period, item.slow_period),
            )[0]
            test_result = self._backtest(
                test,
                winner.fast_period,
                winner.slow_period,
                research_config,
            )
            test_artifact = experiment_store.publish(test_result, dataset=manifest)
            folds.append(
                WalkForwardFold(
                    index=index,
                    train=train,
                    validation=validation,
                    test=test,
                    winner_fast_period=winner.fast_period,
                    winner_slow_period=winner.slow_period,
                    validation_run_id=winner.validation_run_id,
                    test_run_id=test_artifact.run_id,
                    test_result=test_result,
                )
            )
        return tuple(folds)

    def _neighbors(
        self,
        study: ResearchStudy,
        *,
        manifest: DatasetManifest,
        research_config: ResearchConfig,
        experiment_store: ExperimentStore,
    ) -> tuple[RobustnessRun, ...]:
        winner = (study.winner.fast_period, study.winner.slow_period)
        fast_values = sorted(set(research_config.fast_periods))
        slow_values = sorted(set(research_config.slow_periods))
        candidates = set(research_config.candidates)
        neighbors: set[tuple[int, int]] = set()
        for values, coordinate in ((fast_values, 0), (slow_values, 1)):
            current = winner[coordinate]
            position = values.index(current)
            for neighbor_position in (position - 1, position + 1):
                if 0 <= neighbor_position < len(values):
                    pair = list(winner)
                    pair[coordinate] = values[neighbor_position]
                    candidate = (pair[0], pair[1])
                    if candidate in candidates:
                        neighbors.add(candidate)
        results: list[RobustnessRun] = []
        for fast, slow in sorted(neighbors):
            result = self._backtest(study.split.test, fast, slow, research_config)
            artifact = experiment_store.publish(result, dataset=manifest)
            results.append(
                RobustnessRun(
                    label=f"EMA({fast}, {slow})",
                    symbol=manifest.symbol,
                    fast_period=fast,
                    slow_period=slow,
                    run_id=artifact.run_id,
                    result=result,
                )
            )
        return tuple(results)

    def _markets(
        self,
        study: ResearchStudy,
        *,
        primary_manifest: DatasetManifest,
        research_config: ResearchConfig,
        experiment_store: ExperimentStore,
        peer_datasets: tuple[tuple[list[Kline], DatasetManifest], ...],
    ) -> tuple[RobustnessRun, ...]:
        fast = study.winner.fast_period
        slow = study.winner.slow_period
        results = [
            RobustnessRun(
                label=primary_manifest.symbol,
                symbol=primary_manifest.symbol,
                fast_period=fast,
                slow_period=slow,
                run_id=study.test_run_id,
                result=study.test,
            )
        ]
        start = study.split.test[0].open_time
        end = study.split.test[-1].open_time
        seen = {primary_manifest.symbol}
        for klines, manifest in peer_datasets:
            if manifest.symbol in seen:
                raise ResearchConfigurationError("peer datasets must use distinct symbols")
            if manifest.interval != primary_manifest.interval:
                raise ResearchConfigurationError(
                    "peer dataset interval must match primary interval"
                )
            aligned = tuple(item for item in klines if start <= item.open_time <= end)
            if len(aligned) < max(research_config.min_bars_per_split, slow):
                raise ResearchConfigurationError(
                    f"peer dataset {manifest.symbol} has insufficient aligned holdout bars"
                )
            result = self._backtest(aligned, fast, slow, research_config)
            artifact = experiment_store.publish(result, dataset=manifest)
            results.append(
                RobustnessRun(
                    label=manifest.symbol,
                    symbol=manifest.symbol,
                    fast_period=fast,
                    slow_period=slow,
                    run_id=artifact.run_id,
                    result=result,
                )
            )
            seen.add(manifest.symbol)
        return tuple(results)

    def _backtest(
        self,
        klines: tuple[Kline, ...],
        fast: int,
        slow: int,
        config: ResearchConfig,
    ):
        if slow > len(klines):
            raise ResearchConfigurationError(
                f"slow period {slow} exceeds a window containing {len(klines)} bars"
            )
        strategy = EmaCrossStrategy(fast_period=fast, slow_period=slow)
        return self.engine.run(
            list(klines),
            strategy=strategy,
            strategy_parameters=strategy.parameters,
            config=config.backtest,
        )


def _walk_forward_gate(
    folds: tuple[WalkForwardFold, ...], config: RobustnessConfig
) -> RobustnessGate:
    returns = [fold.test_result.metrics.total_return for fold in folds]
    positive_ratio = sum(value > 0 for value in returns) / len(returns)
    median_return = statistics.median(returns)
    passed = positive_ratio >= float(config.minimum_positive_fold_ratio) and median_return > 0
    return RobustnessGate(
        name="walk_forward",
        passed=passed,
        reason=(
            "positive-fold ratio and median return meet the configured thresholds"
            if passed
            else "walk-forward evidence is not consistently positive"
        ),
        observations={
            "fold_count": len(folds),
            "positive_fold_ratio": positive_ratio,
            "minimum_positive_fold_ratio": str(config.minimum_positive_fold_ratio),
            "median_return": median_return,
            "returns": returns,
        },
        run_ids=tuple(fold.test_run_id for fold in folds),
    )


def _neighbor_gate(
    neighbors: tuple[RobustnessRun, ...],
    baseline_return: float,
    config: RobustnessConfig,
) -> RobustnessGate:
    returns = [item.result.metrics.total_return for item in neighbors]
    median_return = statistics.median(returns) if returns else float("-inf")
    retention = median_return / baseline_return if baseline_return > 0 else float("-inf")
    passed = (
        len(neighbors) >= 2
        and baseline_return > 0
        and median_return > 0
        and retention >= float(config.neighbor_retention_ratio)
    )
    return RobustnessGate(
        name="neighboring_parameters",
        passed=passed,
        reason=(
            "neighbor median remains positive and retains enough baseline return"
            if passed
            else "neighboring parameters do not provide stable positive evidence"
        ),
        observations={
            "neighbor_count": len(neighbors),
            "baseline_return": baseline_return,
            "median_return": median_return if returns else None,
            "retention_ratio": retention if baseline_return > 0 and returns else None,
            "minimum_retention_ratio": str(config.neighbor_retention_ratio),
            "returns": returns,
        },
        run_ids=tuple(item.run_id for item in neighbors),
    )


def _cost_gate(study: ResearchStudy, config: RobustnessConfig) -> RobustnessGate:
    baseline = study.test.metrics.total_return
    stressed = study.stress.metrics.total_return
    retention = stressed / baseline if baseline > 0 else float("-inf")
    passed = baseline > 0 and stressed > 0 and retention >= float(config.cost_retention_ratio)
    return RobustnessGate(
        name="doubled_costs",
        passed=passed,
        reason=(
            "doubled-cost return remains positive and retains enough baseline return"
            if passed
            else "doubled costs erase too much of the holdout result"
        ),
        observations={
            "baseline_return": baseline,
            "stressed_return": stressed,
            "retention_ratio": retention if baseline > 0 else None,
            "minimum_retention_ratio": str(config.cost_retention_ratio),
        },
        run_ids=(study.test_run_id, study.stress_run_id),
    )


def _market_gate(markets: tuple[RobustnessRun, ...]) -> RobustnessGate:
    returns = {item.symbol: item.result.metrics.total_return for item in markets}
    passed = len(markets) >= 2 and all(value > 0 for value in returns.values())
    return RobustnessGate(
        name="multiple_markets",
        passed=passed,
        reason=(
            "fixed winner parameters remain positive in every reviewed market"
            if passed
            else "at least two positive aligned markets are required"
        ),
        observations={"market_count": len(markets), "returns": returns},
        run_ids=tuple(item.run_id for item in markets),
    )

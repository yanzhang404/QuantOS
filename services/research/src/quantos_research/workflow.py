"""Chronological parameter selection with an untouched holdout."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from quantos_backtest import BacktestEngine
from quantos_backtest.artifacts import ExperimentStore
from quantos_backtest.strategies import EmaCrossStrategy
from quantos_market_data.models import Kline
from quantos_market_data.storage import DatasetManifest

from .errors import ResearchConfigurationError
from .models import CandidateResult, ResearchConfig, ResearchStudy, TimeSplit
from .review import review_study


def split_chronologically(klines: list[Kline], config: ResearchConfig) -> TimeSplit:
    total = len(klines)
    train_end = int(Decimal(total) * config.train_ratio)
    validation_end = train_end + int(Decimal(total) * config.validation_ratio)
    counts = (train_end, validation_end - train_end, total - validation_end)
    if min(counts) < config.min_bars_per_split:
        raise ResearchConfigurationError(
            "chronological split is too small: "
            f"train={counts[0]}, validation={counts[1]}, test={counts[2]}; "
            f"each requires at least {config.min_bars_per_split} bars"
        )
    return TimeSplit(
        train=tuple(klines[:train_end]),
        validation=tuple(klines[train_end:validation_end]),
        test=tuple(klines[validation_end:]),
    )


class ResearchRunner:
    def __init__(self, *, engine: BacktestEngine | None = None) -> None:
        self.engine = engine or BacktestEngine()

    def run(
        self,
        klines: list[Kline],
        *,
        manifest: DatasetManifest,
        config: ResearchConfig,
        experiment_store: ExperimentStore,
    ) -> ResearchStudy:
        split = split_chronologically(klines, config)
        candidates: list[CandidateResult] = []
        for fast, slow in config.candidates:
            train = self._backtest(split.train, fast, slow, config)
            validation = self._backtest(split.validation, fast, slow, config)
            train_artifacts = experiment_store.publish(train, dataset=manifest)
            validation_artifacts = experiment_store.publish(validation, dataset=manifest)
            candidates.append(
                CandidateResult(
                    fast_period=fast,
                    slow_period=slow,
                    train=train,
                    validation=validation,
                    train_run_id=train_artifacts.run_id,
                    validation_run_id=validation_artifacts.run_id,
                )
            )

        ranked = tuple(
            sorted(
                candidates,
                key=lambda item: (
                    -item.score,
                    item.fast_period,
                    item.slow_period,
                ),
            )
        )
        winner = ranked[0]
        test = self._backtest(split.test, winner.fast_period, winner.slow_period, config)
        stress_config = replace(
            config,
            backtest=replace(
                config.backtest,
                fee_bps=config.backtest.fee_bps * 2,
                slippage_bps=config.backtest.slippage_bps * 2,
            ),
        )
        stress = self._backtest(
            split.test,
            winner.fast_period,
            winner.slow_period,
            stress_config,
        )
        test_artifacts = experiment_store.publish(test, dataset=manifest)
        stress_artifacts = experiment_store.publish(stress, dataset=manifest)
        findings = review_study(
            config=config,
            candidates=ranked,
            winner=winner,
            test=test,
            stress=stress,
        )
        return ResearchStudy(
            config=config,
            split=split,
            candidates=ranked,
            winner=winner,
            test=test,
            stress=stress,
            test_run_id=test_artifacts.run_id,
            stress_run_id=stress_artifacts.run_id,
            findings=findings,
        )

    def _backtest(
        self,
        klines: tuple[Kline, ...],
        fast: int,
        slow: int,
        config: ResearchConfig,
    ):
        if slow > len(klines):
            raise ResearchConfigurationError(
                f"slow period {slow} exceeds a split containing {len(klines)} bars"
            )
        strategy = EmaCrossStrategy(fast_period=fast, slow_period=slow)
        return self.engine.run(
            list(klines),
            strategy=strategy,
            strategy_parameters=strategy.parameters,
            config=config.backtest,
        )

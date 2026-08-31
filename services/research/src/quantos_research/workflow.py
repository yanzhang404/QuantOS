"""Chronological parameter selection with an untouched holdout."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

from quantos_backtest import BacktestEngine
from quantos_backtest.artifacts import ExperimentStore
from quantos_market_data.models import Kline
from quantos_market_data.storage import DatasetManifest

from .adapters import StrategyResearchAdapter, adapter_for
from .errors import ResearchConfigurationError
from .models import CandidateResult, ParameterSet, ResearchConfigLike, ResearchStudy, TimeSplit
from .review import review_study


def split_chronologically(klines: list[Kline], config: ResearchConfigLike) -> TimeSplit:
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
        config: ResearchConfigLike,
        experiment_store: ExperimentStore,
    ) -> ResearchStudy:
        adapter = adapter_for(config)
        split = split_chronologically(klines, config)
        candidates: list[CandidateResult] = []
        for parameters in adapter.candidates:
            train = self._backtest(split.train, parameters, config, adapter)
            validation = self._backtest(split.validation, parameters, config, adapter)
            train_artifacts = experiment_store.publish(train, dataset=manifest)
            validation_artifacts = experiment_store.publish(validation, dataset=manifest)
            candidates.append(
                CandidateResult(
                    parameters=parameters,
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
                    adapter.rank_key(item.parameters),
                ),
            )
        )
        winner = ranked[0]
        test = self._backtest(split.test, winner.parameters, config, adapter)
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
            winner.parameters,
            stress_config,
            adapter_for(stress_config),
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
            strategy_name=adapter.name,
            strategy_version=adapter.version,
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
        parameters: ParameterSet,
        config: ResearchConfigLike,
        adapter: StrategyResearchAdapter,
    ):
        minimum = adapter.minimum_bars(parameters)
        if minimum > len(klines):
            raise ResearchConfigurationError(
                f"strategy warmup {minimum} exceeds a split containing {len(klines)} bars"
            )
        strategy = adapter.build(parameters)
        return self.engine.run(
            list(klines),
            strategy=strategy,
            strategy_parameters=strategy.parameters,
            config=config.backtest,
        )

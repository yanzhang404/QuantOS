from __future__ import annotations

import json
from datetime import timedelta
from decimal import Decimal

import pytest
from quantos_backtest import BacktestConfig, BacktestEngine
from quantos_backtest.artifacts import ExperimentStore
from quantos_backtest.strategies import EmaCrossStrategy
from quantos_cli import main
from quantos_market_data.storage import DatasetStore
from quantos_research.artifacts import StudyStore, compare_runs
from quantos_research.errors import ResearchConfigurationError, ResearchError
from quantos_research.models import ResearchConfig
from quantos_research.workflow import ResearchRunner, split_chronologically


def _config() -> ResearchConfig:
    return ResearchConfig(
        fast_periods=(2, 3),
        slow_periods=(5, 7),
        train_ratio=Decimal("0.5"),
        validation_ratio=Decimal("0.25"),
        min_bars_per_split=20,
        backtest=BacktestConfig(
            initial_cash=Decimal("1000"),
            fee_bps=Decimal("1"),
            slippage_bps=Decimal("1"),
        ),
    )


def _dataset(tmp_path, research_klines):
    return DatasetStore(tmp_path / "data").publish(
        research_klines,
        requested_start=research_klines[0].open_time,
        requested_end=research_klines[-1].open_time + timedelta(hours=1),
        source="fixture",
    )


def test_chronological_split_is_contiguous_and_rejects_short_samples(
    research_klines,
) -> None:
    split = split_chronologically(research_klines, _config())

    assert [len(split.train), len(split.validation), len(split.test)] == [60, 30, 30]
    assert split.train[-1].open_time < split.validation[0].open_time
    assert split.validation[-1].open_time < split.test[0].open_time

    with pytest.raises(ResearchConfigurationError, match="too small"):
        split_chronologically(research_klines[:30], _config())


def test_run_identity_includes_evaluation_range(tmp_path, research_klines) -> None:
    dataset = _dataset(tmp_path, research_klines)
    strategy_a = EmaCrossStrategy(fast_period=2, slow_period=5)
    strategy_b = EmaCrossStrategy(fast_period=2, slow_period=5)
    config = BacktestConfig()
    first = BacktestEngine().run(
        research_klines[:60],
        strategy=strategy_a,
        strategy_parameters=strategy_a.parameters,
        config=config,
    )
    second = BacktestEngine().run(
        research_klines[60:],
        strategy=strategy_b,
        strategy_parameters=strategy_b.parameters,
        config=config,
    )
    store = ExperimentStore(tmp_path / "runs")

    first_artifact = store.publish(first, dataset=dataset.manifest)
    second_artifact = store.publish(second, dataset=dataset.manifest)

    assert first_artifact.run_id != second_artifact.run_id
    raw = json.loads((first_artifact.path / "run.json").read_text())
    assert raw["dataset"]["evaluation"]["bar_count"] == 60


def test_sweep_tests_only_the_validation_winner_and_reuses_study(
    tmp_path,
    research_klines,
) -> None:
    dataset = _dataset(tmp_path, research_klines)
    experiment_store = ExperimentStore(tmp_path / "artifacts" / "experiments")
    study = ResearchRunner().run(
        research_klines,
        manifest=dataset.manifest,
        config=_config(),
        experiment_store=experiment_store,
    )

    assert len(study.candidates) == 4
    assert study.test.strategy_parameters == study.winner.validation.strategy_parameters
    assert study.stress.strategy_parameters == study.test.strategy_parameters
    assert study.stress.config.fee_bps == study.test.config.fee_bps * 2
    assert len(list((tmp_path / "artifacts" / "experiments").iterdir())) == 10
    assert any(item.code == "NEXT_BAR_EXECUTION" for item in study.findings)

    store = StudyStore(tmp_path / "artifacts" / "studies")
    first_id, first_path, first_reused = store.publish(study, dataset=dataset.manifest)
    second_id, second_path, second_reused = store.publish(study, dataset=dataset.manifest)

    assert not first_reused
    assert second_reused
    assert first_id == second_id
    assert first_path == second_path
    payload = json.loads((first_path / "study.json").read_text())
    assert payload["selection_policy"].startswith("rank on validation")
    assert (first_path / "leaderboard.csv").is_file()
    assert "Untouched holdout run" in (first_path / "review.md").read_text()


def test_cli_sweep_compare_and_review(capsys, tmp_path, research_klines) -> None:
    dataset = _dataset(tmp_path, research_klines)
    output = tmp_path / "artifacts"

    assert (
        main(
            [
                "experiment",
                "sweep",
                "--dataset",
                str(dataset.path),
                "--fast",
                "2,3",
                "--slow",
                "5",
                "--train-ratio",
                "0.5",
                "--validation-ratio",
                "0.25",
                "--min-bars",
                "20",
                "--output-root",
                str(output),
            ]
        )
        == 0
    )
    sweep_payload = json.loads(capsys.readouterr().out)
    study_path = output / "studies" / sweep_payload["study_id"]
    run_paths = sorted((output / "experiments").glob("*/run.json"))

    assert (
        main(
            [
                "experiment",
                "compare",
                "--run",
                str(run_paths[0]),
                "--run",
                str(run_paths[1]),
            ]
        )
        == 0
    )
    comparison = json.loads(capsys.readouterr().out)
    assert len(comparison) == 2

    assert main(["review", "show", "--study", str(study_path)]) == 0
    assert "Automated findings" in capsys.readouterr().out


def test_compare_rejects_one_run(tmp_path) -> None:
    with pytest.raises(ResearchError, match="at least two"):
        compare_runs([tmp_path / "run.json"])

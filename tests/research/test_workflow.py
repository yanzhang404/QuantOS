from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

import pytest
from quantos_backtest import BacktestConfig, BacktestEngine
from quantos_backtest.artifacts import ExperimentStore
from quantos_backtest.strategies import EmaCrossStrategy
from quantos_cli import main
from quantos_market_data.storage import DatasetStore
from quantos_research.artifacts import RobustnessStore, StudyStore, compare_runs
from quantos_research.errors import ResearchConfigurationError, ResearchError
from quantos_research.models import DonchianResearchConfig, ResearchConfig, RobustnessConfig
from quantos_research.robustness import RobustnessRunner, walk_forward_windows
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


def _donchian_config() -> DonchianResearchConfig:
    return DonchianResearchConfig(
        entry_periods=(4, 5),
        exit_periods=(2, 3),
        atr_periods=(3, 4),
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
    assert payload["schema_version"] == "research-study.v2"
    assert payload["strategy"]["name"] == "ema-cross"
    assert set(payload["winner"]["parameters"]) == {"fast_period", "slow_period"}
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


def test_cli_rejects_parameters_from_another_strategy(capsys, tmp_path, research_klines) -> None:
    dataset = _dataset(tmp_path, research_klines)
    assert (
        main(
            [
                "experiment",
                "sweep",
                "--dataset",
                str(dataset.path),
                "--fast",
                "2",
                "--slow",
                "5",
                "--entry",
                "20",
            ]
        )
        == 2
    )
    assert "does not accept Donchian" in capsys.readouterr().err


def test_compare_rejects_one_run(tmp_path) -> None:
    with pytest.raises(ResearchError, match="at least two"):
        compare_runs([tmp_path / "run.json"])


def test_donchian_study_uses_strategy_specific_parameters_and_artifacts(
    tmp_path,
    research_klines,
) -> None:
    dataset = _dataset(tmp_path, research_klines)
    experiments = ExperimentStore(tmp_path / "artifacts" / "experiments")
    config = _donchian_config()

    study = ResearchRunner().run(
        research_klines,
        manifest=dataset.manifest,
        config=config,
        experiment_store=experiments,
    )

    assert study.strategy_name == "donchian-atr"
    assert study.strategy_version == "1.0.0"
    assert len(study.candidates) == 8
    assert study.test.strategy_parameters == study.winner.parameters.to_dict()
    assert study.stress.strategy_parameters == study.test.strategy_parameters
    assert set(study.winner.parameters.to_dict()) == {
        "atr_period",
        "entry_period",
        "exit_period",
        "max_exposure",
        "rebalance_threshold",
        "target_annual_volatility",
    }

    _, path, _ = StudyStore(tmp_path / "artifacts" / "studies").publish(
        study,
        dataset=dataset.manifest,
    )
    payload = json.loads((path / "study.json").read_text())
    assert payload["schema_version"] == "research-study.v2"
    assert payload["strategy"]["name"] == "donchian-atr"
    assert "Donchian ATR" in (path / "review.md").read_text()


def test_donchian_config_rejects_non_finite_fixed_parameters() -> None:
    with pytest.raises(ResearchConfigurationError, match="target annual volatility"):
        DonchianResearchConfig(
            entry_periods=(4,),
            exit_periods=(2,),
            atr_periods=(3,),
            target_annual_volatility=Decimal("NaN"),
        )

    with pytest.raises(ResearchConfigurationError, match="256 valid candidates"):
        DonchianResearchConfig(
            entry_periods=tuple(range(20, 30)),
            exit_periods=tuple(range(1, 11)),
            atr_periods=tuple(range(2, 12)),
        )


def test_walk_forward_windows_expand_without_future_leakage(research_klines) -> None:
    windows = walk_forward_windows(
        research_klines,
        fold_count=3,
        min_bars_per_window=20,
    )

    assert [(len(train), len(validation), len(test)) for train, validation, test in windows] == [
        (24, 24, 24),
        (48, 24, 24),
        (72, 24, 24),
    ]
    for train, validation, test in windows:
        assert train[-1].open_time < validation[0].open_time
        assert validation[-1].open_time < test[0].open_time

    with pytest.raises(ResearchConfigurationError, match="walk-forward blocks"):
        walk_forward_windows(
            research_klines[:50],
            fold_count=3,
            min_bars_per_window=20,
        )


def test_robustness_review_links_all_four_gates_and_is_reusable(
    tmp_path,
    research_klines,
) -> None:
    primary = _dataset(tmp_path / "primary", research_klines)
    peer_klines = [replace(item, symbol="ETHUSDT") for item in research_klines]
    peer = _dataset(tmp_path / "peer", peer_klines)
    experiments = ExperimentStore(tmp_path / "artifacts" / "experiments")
    study = ResearchRunner().run(
        research_klines,
        manifest=primary.manifest,
        config=_config(),
        experiment_store=experiments,
    )
    review = RobustnessRunner().run(
        research_klines,
        primary_manifest=primary.manifest,
        primary_study=study,
        research_config=_config(),
        robustness_config=RobustnessConfig(),
        experiment_store=experiments,
        peer_datasets=((peer_klines, peer.manifest),),
    )

    assert [gate.name for gate in review.gates] == [
        "walk_forward",
        "neighboring_parameters",
        "doubled_costs",
        "multiple_markets",
    ]
    assert len(review.folds) == 3
    assert len(review.neighbors) >= 2
    assert {item.symbol for item in review.markets} == {"BTCUSDT", "ETHUSDT"}
    assert review.passed == all(gate.passed for gate in review.gates)

    store = RobustnessStore(tmp_path / "artifacts" / "robustness")
    first_id, first_path, first_reused = store.publish(
        review,
        datasets=(primary.manifest, peer.manifest),
    )
    second_id, second_path, second_reused = store.publish(
        review,
        datasets=(primary.manifest, peer.manifest),
    )
    assert not first_reused
    assert second_reused
    assert first_id == second_id
    assert first_path == second_path
    payload = json.loads((first_path / "robustness.json").read_text())
    assert payload["schema_version"] == "robustness-review.v2"
    assert payload["strategy"]["name"] == "ema-cross"
    assert set(payload["strategy"]["winner"]) == {"fast_period", "slow_period"}
    assert len(payload["gates"]) == 4
    assert len(payload["walk_forward"]) == 3
    assert (first_path / "walk-forward.csv").is_file()
    assert "does not promote" in (first_path / "review.md").read_text()


def test_cli_builds_robustness_review(capsys, tmp_path, research_klines) -> None:
    primary = _dataset(tmp_path / "primary", research_klines)
    peer_klines = [replace(item, symbol="ETHUSDT") for item in research_klines]
    peer = _dataset(tmp_path / "peer", peer_klines)
    output = tmp_path / "artifacts"

    assert (
        main(
            [
                "experiment",
                "robustness",
                "--dataset",
                str(primary.path),
                "--peer-dataset",
                str(peer.path),
                "--fast",
                "2,3",
                "--slow",
                "5,7",
                "--train-ratio",
                "0.5",
                "--validation-ratio",
                "0.25",
                "--min-bars",
                "20",
                "--folds",
                "3",
                "--output-root",
                str(output),
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert len(payload["review_id"]) == 16
    assert len(payload["gates"]) == 4
    assert (output / "robustness" / payload["review_id"] / "robustness.json").is_file()


def test_donchian_robustness_and_cli_are_strategy_specific(
    capsys,
    tmp_path,
    research_klines,
) -> None:
    primary = _dataset(tmp_path / "primary", research_klines)
    peer_klines = [replace(item, symbol="ETHUSDT") for item in research_klines]
    peer = _dataset(tmp_path / "peer", peer_klines)
    output = tmp_path / "artifacts"

    assert (
        main(
            [
                "experiment",
                "robustness",
                "--strategy",
                "donchian-atr",
                "--dataset",
                str(primary.path),
                "--peer-dataset",
                str(peer.path),
                "--entry",
                "4,5",
                "--exit",
                "2,3",
                "--atr",
                "3,4",
                "--train-ratio",
                "0.5",
                "--validation-ratio",
                "0.25",
                "--min-bars",
                "20",
                "--folds",
                "3",
                "--output-root",
                str(output),
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    payload = json.loads(
        (output / "robustness" / result["review_id"] / "robustness.json").read_text()
    )
    assert payload["schema_version"] == "robustness-review.v2"
    assert payload["strategy"]["name"] == "donchian-atr"
    assert len(payload["walk_forward"]) == 3
    assert len(payload["neighbors"]) >= 2
    assert {item["symbol"] for item in payload["markets"]} == {"BTCUSDT", "ETHUSDT"}

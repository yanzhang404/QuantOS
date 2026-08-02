from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from quantos_backtest import BacktestConfig, BacktestEngine
from quantos_backtest.artifacts import ExperimentStore
from quantos_cli import main
from quantos_market_data.storage import DatasetStore

from .test_engine_metrics import ScriptedStrategy


def test_experiment_store_is_content_addressed_and_reusable(
    tmp_path,
    price_klines,
) -> None:
    dataset = DatasetStore(tmp_path / "data").publish(
        price_klines,
        requested_start=price_klines[0].open_time,
        requested_end=price_klines[-1].open_time
        + (price_klines[1].open_time - price_klines[0].open_time),
        source="fixture",
    )
    strategy = ScriptedStrategy()
    result = BacktestEngine().run(
        price_klines,
        strategy=strategy,
        strategy_parameters={},
        config=BacktestConfig(
            initial_cash=Decimal("1000"),
            fee_bps=Decimal("0"),
            slippage_bps=Decimal("0"),
        ),
    )
    store = ExperimentStore(
        tmp_path / "experiments",
        now=lambda: datetime(2026, 7, 27, tzinfo=UTC),
    )

    first = store.publish(result, dataset=dataset.manifest)
    second = store.publish(result, dataset=dataset.manifest)

    assert not first.reused
    assert second.reused
    assert first.path == second.path
    assert {item.name for item in first.path.iterdir()} == {
        "run.json",
        "metrics.json",
        "bars.csv",
        "fills.csv",
        "equity.csv",
        "report.md",
    }
    run = json.loads((first.path / "run.json").read_text())
    assert run["dataset"]["version"] == dataset.manifest.dataset_version
    assert run["artifact_schema_version"] == "experiment-artifacts.v3"
    assert run["features"] == []
    assert run["dataset"]["data_start"] == "2024-01-01T00:00:00Z"
    assert run["status"] == "completed"
    assert len((first.path / "bars.csv").read_text().splitlines()) == 5
    assert "next Kline open" in (first.path / "report.md").read_text()


def test_root_cli_runs_backtest_and_writes_artifacts(
    capsys,
    tmp_path,
    price_klines,
) -> None:
    dataset = DatasetStore(tmp_path / "data").publish(
        price_klines,
        requested_start=price_klines[0].open_time,
        requested_end=price_klines[-1].open_time
        + (price_klines[1].open_time - price_klines[0].open_time),
        source="fixture",
    )
    output_root = tmp_path / "runs"

    exit_code = main(
        [
            "backtest",
            "run",
            "--dataset",
            str(dataset.path),
            "--fast",
            "1",
            "--slow",
            "2",
            "--initial-cash",
            "1000",
            "--fee-bps",
            "0",
            "--slippage-bps",
            "0",
            "--output-root",
            str(output_root),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["run_id"]
    assert (output_root / payload["run_id"] / "report.md").is_file()
    run = json.loads((output_root / payload["run_id"] / "run.json").read_text())
    assert [item["instance"] for item in run["features"]] == ["fast_ema", "slow_ema"]
    assert all(len(item["definition_sha256"]) == 64 for item in run["features"])
    assert "Feature lineage" in (output_root / payload["run_id"] / "report.md").read_text()


def test_root_cli_lists_versioned_feature_registry(capsys) -> None:
    assert main(["backtest", "features"]) == 0
    registry = json.loads(capsys.readouterr().out)
    assert registry["schema_version"] == "feature-registry.v1"
    assert {item["feature_id"] for item in registry["features"]} == {
        "ema",
        "atr",
        "prior-high-channel",
        "prior-low-channel",
    }


def test_root_cli_preserves_data_commands(capsys, tmp_path, price_klines) -> None:
    dataset = DatasetStore(tmp_path / "data").publish(
        price_klines,
        requested_start=price_klines[0].open_time,
        requested_end=price_klines[-1].open_time
        + (price_klines[1].open_time - price_klines[0].open_time),
        source="fixture",
    )

    assert main(["data", "validate", "--dataset", str(dataset.path)]) == 0
    assert json.loads(capsys.readouterr().out)["is_valid"] is True


def test_root_cli_runs_bounded_range_with_explicit_strategy_exposure(
    capsys,
    tmp_path,
    price_klines,
) -> None:
    dataset = DatasetStore(tmp_path / "data").publish(
        price_klines,
        requested_start=price_klines[0].open_time,
        requested_end=price_klines[-1].open_time
        + (price_klines[1].open_time - price_klines[0].open_time),
        source="fixture",
    )
    output_root = tmp_path / "runs"

    assert (
        main(
            [
                "backtest",
                "run",
                "--dataset",
                str(dataset.path),
                "--strategy",
                "buy-and-hold",
                "--target-exposure",
                "0.5",
                "--max-target-exposure",
                "0.8",
                "--start",
                price_klines[0].open_time.isoformat(),
                "--end",
                price_klines[2].open_time.isoformat(),
                "--output-root",
                str(output_root),
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    run = json.loads((output_root / payload["run_id"] / "run.json").read_text())
    assert run["dataset"]["evaluation"]["bar_count"] == 2
    assert run["strategy"]["parameters"]["target_exposure"] == "0.5"


@pytest.mark.parametrize(
    ("strategy", "extra"),
    [
        ("buy-and-hold", []),
        (
            "donchian-atr",
            [
                "--entry-period",
                "2",
                "--exit-period",
                "1",
                "--atr-period",
                "2",
                "--target-annual-volatility",
                "0.2",
            ],
        ),
    ],
)
def test_root_cli_runs_formal_strategies(
    capsys,
    tmp_path,
    price_klines,
    strategy,
    extra,
) -> None:
    dataset = DatasetStore(tmp_path / "data").publish(
        price_klines,
        requested_start=price_klines[0].open_time,
        requested_end=price_klines[-1].open_time
        + (price_klines[1].open_time - price_klines[0].open_time),
        source="fixture",
    )
    output_root = tmp_path / "runs"

    assert (
        main(
            [
                "backtest",
                "run",
                "--dataset",
                str(dataset.path),
                "--strategy",
                strategy,
                "--output-root",
                str(output_root),
                *extra,
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    run = json.loads((output_root / payload["run_id"] / "run.json").read_text())
    assert run["strategy"]["name"] == strategy

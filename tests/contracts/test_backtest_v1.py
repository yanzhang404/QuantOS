from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from quantos_api_contracts import (
    BacktestSubmission,
    BacktestTask,
    ContractValidationError,
    ExperimentMetrics,
    ExperimentRecord,
    StrategyRef,
    TaskError,
    strategy_catalog,
)

ROOT = Path(__file__).parents[2]
SCHEMA = ROOT / "packages" / "api-schema" / "schemas" / "backtest.v1.schema.json"


def submission_payload() -> dict:
    return {
        "schema_version": "1.0",
        "idempotency_key": "web-20260729-0001",
        "label": "BTC Donchian sensitivity",
        "note": "Manual parameter review before comparison.",
        "dataset": {
            "bundle_version": "47a8b29be444e2ba",
            "version": "024f23d9a629502e",
            "content_sha256": ("024f23d9a629502eabf7c8186735938cb585ab76286b072e20ded76c1b4bc7b3"),
            "symbol": "BTCUSDT",
            "interval": "4h",
            "data_start": "2025-01-01T00:00:00Z",
            "data_end": "2026-07-01T00:00:00Z",
        },
        "strategy": {
            "name": "donchian-atr",
            "version": "1.0.0",
            "parameters": {
                "entry_period": 55,
                "exit_period": 20,
                "atr_period": 20,
                "target_annual_volatility": "0.20",
                "max_exposure": "1",
                "rebalance_threshold": "0.05",
            },
        },
        "config": {
            "initial_cash": "100000",
            "fee_bps": "10",
            "slippage_bps": "5",
            "max_target_exposure": "1",
            "liquidate_at_end": True,
        },
    }


def test_submission_round_trips_exact_versioned_values() -> None:
    payload = submission_payload()

    submission = BacktestSubmission.from_dict(payload)

    assert submission.to_dict() == payload
    assert submission.dataset.data_start == datetime(2025, 1, 1, tzinfo=UTC)
    assert submission.strategy.parameters["target_annual_volatility"] == "0.20"


@pytest.mark.parametrize("interval", ["1h", "4h", "1d"])
def test_submission_accepts_strategy_intervals(interval: str) -> None:
    payload = submission_payload()
    payload["dataset"]["interval"] = interval

    assert BacktestSubmission.from_dict(payload).dataset.interval == interval


def test_submission_rejects_strategy_on_unsupported_interval() -> None:
    payload = submission_payload()
    payload["dataset"]["interval"] = "15m"

    with pytest.raises(ContractValidationError, match="does not support"):
        BacktestSubmission.from_dict(payload)


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("fee_bps", -1, "exact decimal string"),
        ("fee_bps", "1001", r"\[0, 1000\]"),
        ("initial_cash", "1E+5", "plain decimal"),
        ("max_target_exposure", "0", r"\(0, 1\]"),
    ],
)
def test_submission_rejects_unsafe_or_inexact_config(
    field: str,
    value: object,
    match: str,
) -> None:
    payload = submission_payload()
    payload["config"][field] = value

    with pytest.raises(ContractValidationError, match=match):
        BacktestSubmission.from_dict(payload)


def test_submission_rejects_paths_and_unknown_boundary_fields() -> None:
    payload = submission_payload()
    payload["dataset"]["path"] = "/tmp/private-market-data"

    with pytest.raises(ContractValidationError, match="unknown fields: path"):
        BacktestSubmission.from_dict(payload)


def test_strategy_parameters_are_strict_and_cross_validated() -> None:
    with pytest.raises(ContractValidationError, match="fast_period must be less"):
        StrategyRef(
            name="ema-cross",
            version="1.0.0",
            parameters={"fast_period": 50, "slow_period": 20},
        )

    with pytest.raises(ContractValidationError, match="exit_period must not exceed"):
        StrategyRef(
            name="donchian-atr",
            version="1.0.0",
            parameters={
                "entry_period": 20,
                "exit_period": 21,
                "atr_period": 20,
                "target_annual_volatility": "0.20",
                "max_exposure": "1",
                "rebalance_threshold": "0.05",
            },
        )


def test_strategy_exposure_cannot_bypass_configured_risk_limit() -> None:
    payload = submission_payload()
    payload["config"]["max_target_exposure"] = "0.5"

    with pytest.raises(ContractValidationError, match="strategy exposure cannot exceed"):
        BacktestSubmission.from_dict(payload)


def test_task_state_requires_consistent_lifecycle_fields() -> None:
    request = BacktestSubmission.from_dict(submission_payload())
    created = datetime(2026, 7, 29, 12, tzinfo=UTC)
    queued = BacktestTask(
        task_id="task_0123456789abcdef",
        status="queued",
        created_at=created,
        request=request,
    )
    assert queued.to_dict()["run_id"] is None

    succeeded = BacktestTask(
        task_id="task_0123456789abcdef",
        status="succeeded",
        created_at=created,
        started_at=created + timedelta(seconds=1),
        finished_at=created + timedelta(seconds=4),
        request=request,
        run_id="336fe16f3f221153",
        reused=False,
    )
    assert succeeded.to_dict()["status"] == "succeeded"

    with pytest.raises(ContractValidationError, match="requires timestamps and error"):
        BacktestTask(
            task_id="task_0123456789abcdef",
            status="failed",
            created_at=created,
            started_at=created + timedelta(seconds=1),
            finished_at=created + timedelta(seconds=4),
            request=request,
        )


def test_failed_task_exposes_safe_structured_error() -> None:
    request = BacktestSubmission.from_dict(submission_payload())
    created = datetime(2026, 7, 29, 12, tzinfo=UTC)
    task = BacktestTask(
        task_id="task_fedcba9876543210",
        status="failed",
        created_at=created,
        started_at=created,
        finished_at=created + timedelta(seconds=2),
        request=request,
        error=TaskError(
            code="dataset_not_found",
            message="The selected immutable dataset is unavailable.",
            retryable=False,
        ),
    )

    assert task.to_dict()["error"] == {
        "code": "dataset_not_found",
        "message": "The selected immutable dataset is unavailable.",
        "retryable": False,
    }


def test_experiment_record_only_exposes_relative_artifact_names() -> None:
    request = BacktestSubmission.from_dict(submission_payload())
    metrics = ExperimentMetrics(
        initial_equity=100000,
        final_equity=99967.37,
        total_return=-0.0003263,
        sharpe_ratio=0.0122,
        max_drawdown=0.0943,
        trade_count=76,
        fill_count=152,
        fees_paid=2495.31,
    )
    record = ExperimentRecord(
        run_id="336fe16f3f221153",
        created_at=datetime(2026, 7, 29, tzinfo=UTC),
        request=request,
        engine_version="0.2.0",
        metrics_version="0.1.0",
        metrics=metrics,
        artifacts=("metrics.json", "fills.csv", "equity.csv", "report.md"),
    )
    assert record.to_dict()["artifacts"] == [
        "metrics.json",
        "fills.csv",
        "equity.csv",
        "report.md",
    ]

    with pytest.raises(ContractValidationError, match="relative file names"):
        ExperimentRecord(
            run_id="336fe16f3f221153",
            created_at=datetime(2026, 7, 29, tzinfo=UTC),
            request=request,
            engine_version="0.2.0",
            metrics_version="0.1.0",
            metrics=metrics,
            artifacts=("/tmp/report.md",),
        )


def test_language_neutral_schema_and_catalog_cover_python_contract() -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    definitions = schema["$defs"]
    catalog = strategy_catalog()

    assert schema["$id"].endswith("backtest.v1.schema.json")
    assert {
        "backtest_submission",
        "backtest_task",
        "experiment_record",
        "experiment_visualization",
        "strategy_catalog",
    } <= definitions.keys()
    assert all(
        {
            "category",
            "stage",
            "implementation",
            "supported_intervals",
        }
        <= strategy.keys()
        for strategy in catalog["strategies"]
    )
    assert [item["name"] for item in catalog["strategies"]] == [
        "buy-and-hold",
        "ema-cross",
        "donchian-atr",
    ]
    assert {
        parameter["key"]
        for strategy in catalog["strategies"]
        if strategy["name"] == "donchian-atr"
        for parameter in strategy["parameters"]
    } == set(submission_payload()["strategy"]["parameters"])

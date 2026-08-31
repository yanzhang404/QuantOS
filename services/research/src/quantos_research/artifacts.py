"""Content-addressed research studies and experiment comparison."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quantos_market_data.storage import DatasetManifest

from .adapters import adapter_for
from .errors import ResearchError
from .models import ResearchStudy, RobustnessReview


class StudyStore:
    def __init__(
        self,
        root: Path,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.root = root
        self._now = now

    def publish(
        self,
        study: ResearchStudy,
        *,
        dataset: DatasetManifest,
    ) -> tuple[str, Path, bool]:
        study_id = _study_id(study, dataset)
        final_path = self.root / study_id
        required = ("study.json", "leaderboard.csv", "review.md")
        if final_path.exists():
            if not all((final_path / name).is_file() for name in required):
                raise ResearchError(f"incomplete existing study: {final_path}")
            return study_id, final_path, True

        self.root.mkdir(parents=True, exist_ok=True)
        temporary_path = Path(tempfile.mkdtemp(prefix=".publishing-", dir=self.root))
        try:
            payload = _study_payload(study_id, study, dataset, self._now())
            (temporary_path / "study.json").write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            _write_leaderboard(temporary_path / "leaderboard.csv", study)
            (temporary_path / "review.md").write_text(
                _review_markdown(study_id, study, dataset),
                encoding="utf-8",
            )
            os.replace(temporary_path, final_path)
        except Exception:
            shutil.rmtree(temporary_path, ignore_errors=True)
            raise
        return study_id, final_path, False


class RobustnessStore:
    def __init__(
        self,
        root: Path,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.root = root
        self._now = now

    def publish(
        self,
        review: RobustnessReview,
        *,
        datasets: tuple[DatasetManifest, ...],
    ) -> tuple[str, Path, bool]:
        review_id = _robustness_id(review, datasets)
        final_path = self.root / review_id
        required = ("robustness.json", "walk-forward.csv", "review.md")
        if final_path.exists():
            if not all((final_path / name).is_file() for name in required):
                raise ResearchError(f"incomplete existing robustness review: {final_path}")
            return review_id, final_path, True

        self.root.mkdir(parents=True, exist_ok=True)
        temporary_path = Path(tempfile.mkdtemp(prefix=".publishing-", dir=self.root))
        try:
            payload = _robustness_payload(review_id, review, datasets, self._now())
            (temporary_path / "robustness.json").write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            _write_walk_forward(temporary_path / "walk-forward.csv", review)
            (temporary_path / "review.md").write_text(
                _robustness_markdown(review_id, review, datasets),
                encoding="utf-8",
            )
            os.replace(temporary_path, final_path)
        except Exception:
            shutil.rmtree(temporary_path, ignore_errors=True)
            raise
        return review_id, final_path, False


def compare_runs(paths: list[Path]) -> list[dict[str, Any]]:
    if len(paths) < 2:
        raise ResearchError("compare requires at least two run.json files")
    rows: list[dict[str, Any]] = []
    for path in paths:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            rows.append(
                {
                    "run_id": raw["run_id"],
                    "dataset_version": raw["dataset"]["version"],
                    "data_start": raw["dataset"]["evaluation"]["data_start"],
                    "data_end": raw["dataset"]["evaluation"]["data_end"],
                    "strategy": raw["strategy"]["name"],
                    "parameters": raw["strategy"]["parameters"],
                    "fee_bps": raw["config"]["fee_bps"],
                    "slippage_bps": raw["config"]["slippage_bps"],
                    **raw["metrics"],
                }
            )
        except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ResearchError(f"invalid run artifact: {path}") from exc
    return rows


def _study_id(study: ResearchStudy, dataset: DatasetManifest) -> str:
    identity = {
        "strategy": [study.strategy_name, study.strategy_version],
        "dataset_version": dataset.dataset_version,
        "dataset_content_sha256": dataset.content_sha256,
        "config": study.config.to_dict(),
        "candidate_runs": [
            [item.train_run_id, item.validation_run_id] for item in study.candidates
        ],
        "test_run_id": study.test_run_id,
        "stress_run_id": study.stress_run_id,
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def _robustness_id(
    review: RobustnessReview,
    datasets: tuple[DatasetManifest, ...],
) -> str:
    identity = {
        "datasets": [
            [item.dataset_version, item.content_sha256, item.symbol, item.interval]
            for item in datasets
        ],
        "research_config": review.research_config.to_dict(),
        "robustness_config": review.config.to_dict(),
        "primary_test_run_id": review.primary_study.test_run_id,
        "gates": [item.to_dict() for item in review.gates],
    }
    encoded = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()[:16]


def _study_payload(
    study_id: str,
    study: ResearchStudy,
    dataset: DatasetManifest,
    created_at: datetime,
) -> dict[str, Any]:
    def split_payload(items) -> dict[str, Any]:
        return {
            "data_start": _isoformat(items[0].open_time),
            "data_end": _isoformat(items[-1].open_time),
            "bar_count": len(items),
        }

    return {
        "schema_version": "research-study.v2",
        "study_id": study_id,
        "status": "completed",
        "created_at": _isoformat(created_at),
        "selection_policy": "rank on validation Sharpe only; test selected winner once",
        "dataset": {
            "version": dataset.dataset_version,
            "content_sha256": dataset.content_sha256,
            "symbol": dataset.symbol,
            "interval": dataset.interval,
        },
        "strategy": {
            "name": study.strategy_name,
            "version": study.strategy_version,
        },
        "config": study.config.to_dict(),
        "splits": {
            "train": split_payload(study.split.train),
            "validation": split_payload(study.split.validation),
            "test": split_payload(study.split.test),
        },
        "winner": {
            "parameters": study.winner.parameters.to_dict(),
            "validation_run_id": study.winner.validation_run_id,
            "test_run_id": study.test_run_id,
            "stress_run_id": study.stress_run_id,
        },
        "findings": [item.to_dict() for item in study.findings],
        "artifacts": ["leaderboard.csv", "review.md"],
    }


def _write_leaderboard(path: Path, study: ResearchStudy) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "rank",
                "parameters_json",
                "train_run_id",
                "train_return",
                "validation_run_id",
                "validation_return",
                "validation_sharpe",
            ]
        )
        for rank, item in enumerate(study.candidates, start=1):
            writer.writerow(
                [
                    rank,
                    json.dumps(item.parameters.to_dict(), sort_keys=True, separators=(",", ":")),
                    item.train_run_id,
                    item.train.metrics.total_return,
                    item.validation_run_id,
                    item.validation.metrics.total_return,
                    item.validation.metrics.sharpe_ratio,
                ]
            )


def _write_walk_forward(path: Path, review: RobustnessReview) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "fold",
                "train_start",
                "train_end",
                "validation_start",
                "validation_end",
                "test_start",
                "test_end",
                "parameters_json",
                "validation_run_id",
                "test_run_id",
                "test_return",
                "test_sharpe",
                "test_max_drawdown",
            ]
        )
        for fold in review.folds:
            writer.writerow(
                [
                    fold.index,
                    _isoformat(fold.train[0].open_time),
                    _isoformat(fold.train[-1].open_time),
                    _isoformat(fold.validation[0].open_time),
                    _isoformat(fold.validation[-1].open_time),
                    _isoformat(fold.test[0].open_time),
                    _isoformat(fold.test[-1].open_time),
                    json.dumps(
                        fold.winner_parameters.to_dict(),
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                    fold.validation_run_id,
                    fold.test_run_id,
                    fold.test_result.metrics.total_return,
                    fold.test_result.metrics.sharpe_ratio,
                    fold.test_result.metrics.max_drawdown,
                ]
            )


def _review_markdown(
    study_id: str,
    study: ResearchStudy,
    dataset: DatasetManifest,
) -> str:
    findings = "\n".join(
        f"- **{item.severity.upper()} `{item.code}`** — {item.message}" for item in study.findings
    )
    winner = adapter_for(study.config).label(study.winner.parameters)
    return f"""# QuantOS Research Review

## Study

- Study ID: `{study_id}`
- Dataset: `{dataset.dataset_version}` (`{dataset.content_sha256}`)
- Symbol / interval: `{dataset.symbol}` / `{dataset.interval}`
- Selection: validation Sharpe only
- Winner: {winner}
- Validation run: `{study.winner.validation_run_id}`
- Untouched holdout run: `{study.test_run_id}`
- Doubled-cost stress run: `{study.stress_run_id}`

## Holdout metrics

- Total return: `{study.test.metrics.total_return:.6%}`
- Sharpe ratio: `{study.test.metrics.sharpe_ratio}`
- Maximum drawdown: `{study.test.metrics.max_drawdown:.6%}`
- Completed trades: `{study.test.metrics.trade_count}`

## Automated findings

{findings}

This is an automated validity review of a historical simulation, not investment advice.
"""


def _robustness_payload(
    review_id: str,
    review: RobustnessReview,
    datasets: tuple[DatasetManifest, ...],
    created_at: datetime,
) -> dict[str, Any]:
    return {
        "schema_version": "robustness-review.v2",
        "review_id": review_id,
        "status": "completed",
        "created_at": _isoformat(created_at),
        "passed": review.passed,
        "strategy": {
            "name": review.primary_study.strategy_name,
            "version": review.primary_study.strategy_version,
            "winner": review.primary_study.winner.parameters.to_dict(),
        },
        "datasets": [
            {
                "version": item.dataset_version,
                "content_sha256": item.content_sha256,
                "symbol": item.symbol,
                "interval": item.interval,
            }
            for item in datasets
        ],
        "research_config": review.research_config.to_dict(),
        "robustness_config": review.config.to_dict(),
        "gates": [item.to_dict() for item in review.gates],
        "walk_forward": [
            {
                "fold": fold.index,
                "winner": fold.winner_parameters.to_dict(),
                "train": _range_payload(fold.train),
                "validation": _range_payload(fold.validation),
                "test": _range_payload(fold.test),
                "validation_run_id": fold.validation_run_id,
                "test_run_id": fold.test_run_id,
                "test_metrics": fold.test_result.metrics.to_dict(),
            }
            for fold in review.folds
        ],
        "neighbors": [_robustness_run_payload(item) for item in review.neighbors],
        "markets": [_robustness_run_payload(item) for item in review.markets],
        "artifacts": ["walk-forward.csv", "review.md"],
    }


def _range_payload(items) -> dict[str, Any]:
    return {
        "data_start": _isoformat(items[0].open_time),
        "data_end": _isoformat(items[-1].open_time),
        "bar_count": len(items),
    }


def _robustness_run_payload(item) -> dict[str, Any]:
    return {
        "label": item.label,
        "symbol": item.symbol,
        "parameters": item.parameters.to_dict(),
        "run_id": item.run_id,
        "metrics": item.result.metrics.to_dict(),
    }


def _robustness_markdown(
    review_id: str,
    review: RobustnessReview,
    datasets: tuple[DatasetManifest, ...],
) -> str:
    status = "PASS" if review.passed else "FAIL"
    gates = "\n".join(
        f"- **{'PASS' if gate.passed else 'FAIL'} `{gate.name}`** — {gate.reason}"
        for gate in review.gates
    )
    dataset_lines = "\n".join(
        f"- `{item.symbol}` / `{item.interval}`: `{item.dataset_version}` (`{item.content_sha256}`)"
        for item in datasets
    )
    winner = adapter_for(review.research_config).label(review.primary_study.winner.parameters)
    return f"""# QuantOS Robustness Review

## Result

- Review ID: `{review_id}`
- Overall gate: **{status}**
- Strategy: {winner}
- Primary holdout Run: `{review.primary_study.test_run_id}`

## Immutable datasets

{dataset_lines}

## Gates

{gates}

Passing is necessary evidence for a promotion proposal. It does not promote the strategy,
authorize paper or live trading, or constitute investment advice.
"""


def _isoformat(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

"""Atomic experiment metadata, artifacts, and Markdown reports."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from quantos_events import MarketEvent
from quantos_market_data.storage import DatasetManifest

from .engine import BacktestResult
from .errors import BacktestError
from .features import resolve_feature_lineage

ARTIFACT_SCHEMA_VERSION = "experiment-artifacts.v3"


@dataclass(frozen=True, slots=True)
class ExperimentArtifacts:
    run_id: str
    path: Path
    reused: bool


class ExperimentStore:
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
        result: BacktestResult,
        *,
        dataset: DatasetManifest,
    ) -> ExperimentArtifacts:
        run_id = _run_id(result, dataset)
        final_path = self.root / run_id
        required = (
            "run.json",
            "metrics.json",
            "bars.csv",
            "fills.csv",
            "equity.csv",
            "report.md",
        )
        if final_path.exists():
            if not all((final_path / name).is_file() for name in required):
                raise BacktestError(f"incomplete existing experiment: {final_path}")
            return ExperimentArtifacts(run_id=run_id, path=final_path, reused=True)

        self.root.mkdir(parents=True, exist_ok=True)
        temporary_path = Path(tempfile.mkdtemp(prefix=".publishing-", dir=self.root))
        try:
            metrics = result.metrics.to_dict()
            features = resolve_feature_lineage(result.strategy_name, result.strategy_parameters)
            run = {
                "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
                "run_id": run_id,
                "status": "completed",
                "created_at": _isoformat(self._now()),
                "dataset": {
                    "version": dataset.dataset_version,
                    "content_sha256": dataset.content_sha256,
                    "schema_version": dataset.schema_version,
                    "symbol": dataset.symbol,
                    "interval": dataset.interval,
                    "data_start": _isoformat(result.data_start),
                    "data_end": _isoformat(result.data_end),
                    "evaluation": {
                        "data_start": _isoformat(result.data_start),
                        "data_end": _isoformat(result.data_end),
                        "bar_count": result.bar_count,
                    },
                },
                "strategy": {
                    "name": result.strategy_name,
                    "version": result.strategy_version,
                    "parameters": result.strategy_parameters,
                },
                "features": list(features),
                "engine_version": result.engine_version,
                "metrics_version": result.metrics_version,
                "config": result.config.to_dict(),
                "metrics": metrics,
                "artifacts": [
                    "metrics.json",
                    "bars.csv",
                    "fills.csv",
                    "equity.csv",
                    "report.md",
                ],
            }
            _write_json(temporary_path / "run.json", run)
            _write_json(temporary_path / "metrics.json", metrics)
            _write_bars(temporary_path / "bars.csv", result)
            _write_fills(temporary_path / "fills.csv", result)
            _write_equity(temporary_path / "equity.csv", result)
            (temporary_path / "report.md").write_text(
                _markdown_report(result, dataset, run_id),
                encoding="utf-8",
            )
            os.replace(temporary_path, final_path)
        except Exception:
            shutil.rmtree(temporary_path, ignore_errors=True)
            raise
        return ExperimentArtifacts(run_id=run_id, path=final_path, reused=False)


def _run_id(result: BacktestResult, dataset: DatasetManifest) -> str:
    features = resolve_feature_lineage(result.strategy_name, result.strategy_parameters)
    identity = {
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "dataset_version": dataset.dataset_version,
        "dataset_content_sha256": dataset.content_sha256,
        "evaluation_data_start": _isoformat(result.data_start),
        "evaluation_data_end": _isoformat(result.data_end),
        "evaluation_bar_count": result.bar_count,
        "strategy_name": result.strategy_name,
        "strategy_version": result.strategy_version,
        "strategy_parameters": result.strategy_parameters,
        "features": list(features),
        "engine_version": result.engine_version,
        "metrics_version": result.metrics_version,
        "config": result.config.to_dict(),
    }
    payload = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()[:16]


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_fills(path: Path, result: BacktestResult) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "symbol", "quantity", "price", "notional", "fee", "reason"])
        for item in result.fills:
            writer.writerow(
                [
                    _isoformat(item.timestamp),
                    item.symbol,
                    str(item.quantity),
                    str(item.price),
                    str(item.notional),
                    str(item.fee),
                    item.reason,
                ]
            )


def _write_bars(path: Path, result: BacktestResult) -> None:
    bars = [item for item in result.events if isinstance(item, MarketEvent)][-2000:]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["open_time", "open", "high", "low", "close", "volume"])
        for item in bars:
            writer.writerow(
                [
                    _isoformat(item.open_time),
                    str(item.open),
                    str(item.high),
                    str(item.low),
                    str(item.close),
                    str(item.volume),
                ]
            )


def _write_equity(path: Path, result: BacktestResult) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "cash", "position_quantity", "market_price", "equity"])
        for item in result.equity_curve:
            writer.writerow(
                [
                    _isoformat(item.timestamp),
                    str(item.cash),
                    str(item.position_quantity),
                    str(item.market_price),
                    str(item.equity),
                ]
            )


def _markdown_report(
    result: BacktestResult,
    dataset: DatasetManifest,
    run_id: str,
) -> str:
    metrics = result.metrics
    sharpe = "N/A" if metrics.sharpe_ratio is None else f"{metrics.sharpe_ratio:.6f}"
    features = resolve_feature_lineage(result.strategy_name, result.strategy_parameters)
    feature_lines = (
        "\n".join(
            f"- `{item['instance']}` → `{item['feature_id']}` `{item['version']}` "
            f"with `{json.dumps(item['parameters'], sort_keys=True)}`"
            for item in features
        )
        or "- No registered derived features."
    )
    return f"""# QuantOS Backtest Report

## Run

- Run ID: `{run_id}`
- Dataset version: `{dataset.dataset_version}`
- Dataset content SHA-256: `{dataset.content_sha256}`
- Symbol / interval: `{result.symbol}` / `{result.interval}`
- Evaluation range: `{_isoformat(result.data_start)}` to `{_isoformat(result.data_end)}`
- Bars evaluated: `{result.bar_count}`
- Strategy: `{result.strategy_name}` `{result.strategy_version}`
- Engine: `{result.engine_version}`
- Metrics: `{result.metrics_version}`

## Parameters

```json
{json.dumps(result.strategy_parameters, indent=2, sort_keys=True)}
```

## Feature lineage

{feature_lines}

## Assumptions

- Signals are generated after a Kline closes.
- Approved targets execute at the next Kline open.
- Fee: `{result.config.fee_bps}` bps per fill.
- Fixed adverse slippage: `{result.config.slippage_bps}` bps per fill.
- Long-only maximum target exposure: `{result.config.max_target_exposure}`.
- End-of-test liquidation: `{result.config.liquidate_at_end}`.

## Metrics

| Metric | Value |
| --- | ---: |
| Initial equity | {metrics.initial_equity:.6f} |
| Final equity | {metrics.final_equity:.6f} |
| Total return | {metrics.total_return:.6%} |
| Sharpe ratio | {sharpe} |
| Maximum drawdown | {metrics.max_drawdown:.6%} |
| Completed trades | {metrics.trade_count} |
| Fills | {metrics.fill_count} |
| Fees paid | {metrics.fees_paid:.6f} |

## Artifacts

- `run.json`
- `metrics.json`
- `bars.csv`
- `fills.csv`
- `equity.csv`

This report describes a historical simulation and is not investment advice.
"""


def _isoformat(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

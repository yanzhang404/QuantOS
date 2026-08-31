"""Export a compact, reproducible strategy-visualization artifact."""

from __future__ import annotations

import argparse
import csv
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--study", required=True, type=Path)
    parser.add_argument("--market-root", required=True, type=Path)
    parser.add_argument("--experiments-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--window-bars", default=240, type=int)
    args = parser.parse_args()

    if args.window_bars < 60:
        parser.error("--window-bars must be at least 60")

    study = json.loads(args.study.read_text(encoding="utf-8"))
    base_runs = {
        (run["dataset"], run["strategy"]): run for run in study["runs"] if "cost_stress" not in run
    }
    artifact: dict[str, Any] = {
        "schema_version": "1.0",
        "generated_from": args.study.name,
        "as_of": study["as_of"],
        "window_bars": args.window_bars,
        "datasets": {},
    }

    for dataset_key, dataset in sorted(study["datasets"].items()):
        asset, period = dataset_key.split("_", maxsplit=1)
        symbol = f"{asset.upper()}USDT"
        parquet_path = (
            args.market_root
            / f"exchange=binance/symbol={symbol}/interval=4h"
            / f"version={dataset['dataset_version']}"
            / "part-00000.parquet"
        )
        bars = _read_bars(parquet_path)[-args.window_bars :]
        start = _parse_time(bars[0]["time"])
        end = _parse_time(bars[-1]["close_time"])
        runs: dict[str, Any] = {}

        for strategy in ("buy-and-hold", "ema-cross", "donchian-atr"):
            run = base_runs[(dataset_key, strategy)]
            run_path = args.experiments_root / run["run_id"]
            equity = _read_equity(run_path / "equity.csv", start=start, end=end)
            fills = _read_fills(run_path / "fills.csv", start=start, end=end)
            runs[strategy] = {
                "run_id": run["run_id"],
                "metrics": {
                    "total_return": run["total_return"],
                    "sharpe_ratio": run["sharpe_ratio"],
                    "max_drawdown": run["max_drawdown"],
                    "trade_count": run["trade_count"],
                    "fill_count": run["fill_count"],
                    "fees_paid": run["fees_paid"],
                },
                "equity": equity,
                "fills": fills,
            }

        artifact["datasets"][dataset_key] = {
            "symbol": symbol,
            "interval": "4h",
            "period": period,
            "dataset_version": dataset["dataset_version"],
            "content_sha256": dataset["content_sha256"],
            "bars": [
                {key: value for key, value in bar.items() if key != "close_time"} for bar in bars
            ],
            "runs": runs,
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(artifact, separators=(",", ":"), ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return 0


def _read_bars(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"missing immutable Kline partition: {path}")
    table = pq.read_table(
        path,
        columns=["open_time", "close_time", "open", "high", "low", "close", "volume"],
    )
    result = []
    for row in table.to_pylist():
        result.append(
            {
                "time": _isoformat(row["open_time"]),
                "close_time": _isoformat(row["close_time"]),
                "open": round(float(row["open"]), 4),
                "high": round(float(row["high"]), 4),
                "low": round(float(row["low"]), 4),
                "close": round(float(row["close"]), 4),
                "volume": round(float(row["volume"]), 6),
            }
        )
    return result


def _read_equity(path: Path, *, start: datetime, end: datetime) -> list[dict[str, Any]]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    peak = Decimal("0")
    result = []
    for row in rows:
        equity = Decimal(row["equity"])
        peak = max(peak, equity)
        timestamp = _parse_time(row["timestamp"])
        if start <= timestamp <= end:
            result.append(
                {
                    "time": _isoformat(timestamp),
                    "equity": round(float(equity), 4),
                    "drawdown": round(float(equity / peak - 1), 8) if peak else 0,
                    "position": round(float(row["position_quantity"]), 10),
                }
            )
    return result


def _read_fills(path: Path, *, start: datetime, end: datetime) -> list[dict[str, Any]]:
    result = []
    for row in csv.DictReader(path.open(encoding="utf-8")):
        timestamp = _parse_time(row["timestamp"])
        if start <= timestamp <= end:
            quantity = Decimal(row["quantity"])
            result.append(
                {
                    "time": _isoformat(timestamp),
                    "side": "buy" if quantity > 0 else "sell",
                    "price": round(float(row["price"]), 4),
                    "quantity": round(float(abs(quantity)), 10),
                    "fee": round(float(row["fee"]), 4),
                    "reason": row["reason"],
                }
            )
    return result


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _isoformat(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())

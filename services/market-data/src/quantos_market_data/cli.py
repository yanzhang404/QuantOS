"""Command-line entry point for the QuantOS market-data workflow."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .binance import DEFAULT_BASE_URL
from .errors import MarketDataError
from .models import Interval
from .query import json_value, query_klines
from .service import download_dataset
from .storage import DatasetStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quantos", description="QuantOS research tooling")
    commands = parser.add_subparsers(dest="module", required=True)
    data = commands.add_parser("data", help="manage immutable market datasets")
    data_commands = data.add_subparsers(dest="command", required=True)

    download = data_commands.add_parser("download", help="download and publish Binance Klines")
    download.add_argument("--symbol", required=True, help="BTCUSDT or ETHUSDT")
    download.add_argument("--interval", required=True, choices=[item.value for item in Interval])
    download.add_argument("--start", required=True, type=_datetime, help="inclusive UTC ISO-8601")
    download.add_argument("--end", required=True, type=_datetime, help="exclusive UTC ISO-8601")
    download.add_argument("--data-root", type=Path, default=Path("data"))
    download.add_argument("--base-url", default=DEFAULT_BASE_URL, help=argparse.SUPPRESS)

    validate = data_commands.add_parser("validate", help="verify a published dataset")
    validate.add_argument("--dataset", required=True, type=Path)

    query = data_commands.add_parser("query", help="query one dataset version with DuckDB")
    query.add_argument("--dataset", required=True, type=Path)
    query.add_argument("--start", type=_datetime)
    query.add_argument("--end", type=_datetime)
    query.add_argument("--limit", type=int, default=100)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.module == "data" and args.command == "download":
            result = download_dataset(
                symbol=args.symbol,
                interval=Interval.parse(args.interval),
                start=args.start,
                end=args.end,
                data_root=args.data_root,
                base_url=args.base_url,
            )
            _print_json(
                {
                    "dataset": str(result.path),
                    "manifest": str(result.path / "manifest.json"),
                    "dataset_version": result.manifest.dataset_version,
                    "rows": result.manifest.row_count,
                }
            )
            return 0
        if args.module == "data" and args.command == "validate":
            store = DatasetStore(args.dataset)
            report = store.verify(args.dataset)
            _print_json(report.to_dict())
            return 0
        if args.module == "data" and args.command == "query":
            rows = query_klines(
                args.dataset,
                start=args.start,
                end=args.end,
                limit=args.limit,
            )
            for row in rows:
                _print_json(row)
            return 0
    except MarketDataError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    parser.error("unsupported command")
    return 2


def _datetime(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid ISO-8601 timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone")
    return parsed.astimezone(UTC)


def _print_json(value: dict[str, Any]) -> None:
    print(json.dumps(value, default=json_value, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())

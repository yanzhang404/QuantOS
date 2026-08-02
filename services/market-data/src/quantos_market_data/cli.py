"""Command-line entry point for the QuantOS market-data workflow."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .alignment import AlignedDerivativeStore, materialize_derivatives_alignment
from .binance import DEFAULT_BASE_URL
from .bundle import DatasetBundleStore, write_coverage_evidence
from .derivatives import (
    DerivativeDatasetStore,
    download_funding_dataset,
    download_open_interest_dataset,
)
from .errors import MarketDataError
from .models import Interval
from .query import json_value, query_klines
from .service import download_dataset, sync_current_product_matrix, sync_product_matrix
from .storage import DatasetStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quantos", description="QuantOS research tooling")
    commands = parser.add_subparsers(dest="module", required=True)
    register_parser(commands)
    return parser


def register_parser(commands: Any) -> None:
    data = commands.add_parser("data", help="manage immutable market datasets")
    data_commands = data.add_subparsers(dest="command", required=True)

    download = data_commands.add_parser("download", help="download and publish Binance Klines")
    download.add_argument("--symbol", required=True, help="BTCUSDT or ETHUSDT")
    download.add_argument("--interval", required=True, choices=[item.value for item in Interval])
    download.add_argument("--start", required=True, type=_datetime, help="inclusive UTC ISO-8601")
    download.add_argument("--end", required=True, type=_datetime, help="exclusive UTC ISO-8601")
    download.add_argument("--data-root", type=Path, default=Path("data"))
    download.add_argument("--base-url", default=DEFAULT_BASE_URL, help=argparse.SUPPRESS)

    derivatives = data_commands.add_parser(
        "derivatives", help="download immutable public funding or open-interest data"
    )
    derivatives.add_argument("--series", required=True, choices=("funding-rate", "open-interest"))
    derivatives.add_argument("--symbol", required=True, help="BTCUSDT or ETHUSDT")
    derivatives.add_argument(
        "--period",
        choices=[item.value for item in Interval],
        help="required for open-interest; omitted for funding-rate",
    )
    derivatives.add_argument(
        "--start", required=True, type=_datetime, help="inclusive UTC ISO-8601"
    )
    derivatives.add_argument("--end", required=True, type=_datetime, help="exclusive UTC ISO-8601")
    derivatives.add_argument("--data-root", type=Path, default=Path("data"))

    validate_derivatives = data_commands.add_parser(
        "validate-derivatives", help="verify an immutable derivatives dataset"
    )
    validate_derivatives.add_argument("--dataset", required=True, type=Path)

    align_derivatives = data_commands.add_parser(
        "align-derivatives", help="causally align derivatives data to closed Spot bars"
    )
    align_derivatives.add_argument("--spot-dataset", required=True, type=Path)
    align_derivatives.add_argument("--derivative-dataset", required=True, type=Path)
    align_derivatives.add_argument(
        "--start", required=True, type=_datetime, help="inclusive Spot bar open time"
    )
    align_derivatives.add_argument(
        "--end", required=True, type=_datetime, help="exclusive Spot bar open time"
    )
    align_derivatives.add_argument(
        "--max-age",
        required=True,
        type=_duration_ms,
        help="maximum observation age, for example 12h or 30m",
    )
    align_derivatives.add_argument("--output-root", type=Path, default=Path("data"))

    validate_alignment = data_commands.add_parser(
        "validate-alignment", help="verify a causal derivatives feature dataset"
    )
    validate_alignment.add_argument("--dataset", required=True, type=Path)

    sync_matrix = data_commands.add_parser(
        "sync-matrix", help="download and version the BTC/ETH five-interval matrix"
    )
    sync_matrix.add_argument(
        "--start", required=True, type=_datetime, help="inclusive UTC ISO-8601"
    )
    sync_matrix.add_argument("--end", required=True, type=_datetime, help="exclusive UTC ISO-8601")
    sync_matrix.add_argument("--data-root", type=Path, default=Path("data"))
    sync_matrix.add_argument("--base-url", default=DEFAULT_BASE_URL, help=argparse.SUPPRESS)

    sync_current = data_commands.add_parser(
        "sync-current", help="backfill or increment the matrix to the latest closed UTC day"
    )
    sync_current.add_argument(
        "--start", required=True, type=_datetime, help="fixed historical UTC start"
    )
    sync_current.add_argument("--data-root", type=Path, default=Path("data"))
    sync_current.add_argument("--coverage-output", type=Path)
    sync_current.add_argument("--base-url", default=DEFAULT_BASE_URL, help=argparse.SUPPRESS)

    export_coverage = data_commands.add_parser(
        "export-coverage", help="export compact verified coverage evidence"
    )
    export_coverage.add_argument("--bundle", required=True, type=Path)
    export_coverage.add_argument("--data-root", type=Path, default=Path("data"))
    export_coverage.add_argument("--output", required=True, type=Path)

    validate = data_commands.add_parser("validate", help="verify a published dataset")
    validate.add_argument("--dataset", required=True, type=Path)

    query = data_commands.add_parser("query", help="query one dataset version with DuckDB")
    query.add_argument("--dataset", required=True, type=Path)
    query.add_argument("--start", type=_datetime)
    query.add_argument("--end", type=_datetime)
    query.add_argument("--limit", type=int, default=100)


def run(args: argparse.Namespace) -> int:
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
    if args.module == "data" and args.command == "derivatives":
        if args.series == "funding-rate":
            if args.period is not None:
                raise MarketDataError("--period must be omitted for funding-rate")
            result = download_funding_dataset(
                symbol=args.symbol,
                start=args.start,
                end=args.end,
                data_root=args.data_root,
            )
        else:
            if args.period is None:
                raise MarketDataError("--period is required for open-interest")
            result = download_open_interest_dataset(
                symbol=args.symbol,
                period=Interval.parse(args.period),
                start=args.start,
                end=args.end,
                data_root=args.data_root,
            )
        _print_json(
            {
                "dataset": str(result.path),
                "manifest": str(result.path / "manifest.json"),
                "dataset_version": result.manifest.dataset_version,
                "series": result.manifest.series,
                "rows": result.manifest.row_count,
                "source_limit": result.manifest.source_limit,
            }
        )
        return 0
    if args.module == "data" and args.command == "validate-derivatives":
        manifest = DerivativeDatasetStore(args.dataset).verify(args.dataset)
        _print_json({"is_valid": True, **manifest.to_dict()})
        return 0
    if args.module == "data" and args.command == "align-derivatives":
        result = materialize_derivatives_alignment(
            spot_dataset=args.spot_dataset,
            derivative_dataset=args.derivative_dataset,
            start=args.start,
            end=args.end,
            max_age_ms=args.max_age,
            output_root=args.output_root,
        )
        _print_json(
            {
                "dataset": str(result.path),
                "manifest": str(result.path / "manifest.json"),
                "dataset_version": result.manifest.dataset_version,
                "series": result.manifest.series,
                "rows": result.manifest.row_count,
                "matched": result.manifest.matched_count,
                "stale": result.manifest.stale_count,
                "no_prior": result.manifest.no_prior_count,
            }
        )
        return 0
    if args.module == "data" and args.command == "validate-alignment":
        manifest = AlignedDerivativeStore(args.dataset).verify(args.dataset)
        _print_json({"is_valid": True, **manifest.to_dict()})
        return 0
    if args.module == "data" and args.command == "sync-matrix":
        result = sync_product_matrix(
            start=args.start,
            end=args.end,
            data_root=args.data_root,
            base_url=args.base_url,
        )
        _print_json(
            {
                "bundle": str(result.path),
                "manifest": str(result.path / "manifest.json"),
                "bundle_version": result.manifest.bundle_version,
                "members": [
                    {
                        "symbol": item.symbol,
                        "interval": item.interval,
                        "dataset_version": item.dataset_version,
                        "rows": item.row_count,
                    }
                    for item in result.manifest.members
                ],
            }
        )
        return 0
    if args.module == "data" and args.command == "sync-current":
        result = sync_current_product_matrix(
            start=args.start,
            data_root=args.data_root,
            base_url=args.base_url,
        )
        if args.coverage_output is not None:
            write_coverage_evidence(result.manifest, args.coverage_output)
        _print_json(
            {
                "bundle": str(result.path),
                "bundle_version": result.manifest.bundle_version,
                "requested_start": result.manifest.requested_start,
                "requested_end": result.manifest.requested_end,
                "members": len(result.manifest.members),
                "rows": sum(item.row_count for item in result.manifest.members),
                "coverage_output": (
                    str(args.coverage_output) if args.coverage_output is not None else None
                ),
            }
        )
        return 0
    if args.module == "data" and args.command == "export-coverage":
        store = DatasetBundleStore(args.data_root)
        manifest = store.verify(args.bundle)
        write_coverage_evidence(manifest, args.output)
        _print_json(
            {
                "bundle_version": manifest.bundle_version,
                "members": len(manifest.members),
                "output": str(args.output),
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
    raise MarketDataError("unsupported data command")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except MarketDataError as exc:
        print(f"error: {exc}", file=sys.stderr)
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


def _duration_ms(value: str) -> int:
    units = (("ms", 1), ("s", 1_000), ("m", 60_000), ("h", 3_600_000), ("d", 86_400_000))
    for suffix, multiplier in units:
        if value.endswith(suffix):
            try:
                amount = int(value[: -len(suffix)])
            except ValueError as exc:
                raise argparse.ArgumentTypeError(f"invalid duration: {value}") from exc
            if amount <= 0:
                raise argparse.ArgumentTypeError("duration must be positive")
            return amount * multiplier
    raise argparse.ArgumentTypeError("duration must end in ms, s, m, h, or d")


def _print_json(value: dict[str, Any]) -> None:
    print(json.dumps(value, default=json_value, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())

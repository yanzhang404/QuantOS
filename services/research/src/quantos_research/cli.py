"""Research workflow command registration."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from quantos_backtest import BacktestConfig
from quantos_backtest.artifacts import ExperimentStore
from quantos_market_data.storage import DatasetStore

from .artifacts import StudyStore, compare_runs
from .models import ResearchConfig
from .workflow import ResearchRunner


def register_parser(commands: Any) -> None:
    experiment = commands.add_parser(
        "experiment",
        help="run and compare reproducible research studies",
    )
    experiment_commands = experiment.add_subparsers(dest="command", required=True)
    sweep = experiment_commands.add_parser(
        "sweep",
        help="select EMA parameters chronologically and test the winner out of sample",
    )
    sweep.add_argument("--dataset", required=True, type=Path)
    sweep.add_argument("--fast", required=True, type=_periods)
    sweep.add_argument("--slow", required=True, type=_periods)
    sweep.add_argument("--train-ratio", type=_decimal, default=Decimal("0.6"))
    sweep.add_argument("--validation-ratio", type=_decimal, default=Decimal("0.2"))
    sweep.add_argument("--min-bars", type=int, default=20)
    sweep.add_argument("--initial-cash", type=_decimal, default=Decimal("100000"))
    sweep.add_argument("--fee-bps", type=_decimal, default=Decimal("10"))
    sweep.add_argument("--slippage-bps", type=_decimal, default=Decimal("5"))
    sweep.add_argument("--max-target-exposure", type=_decimal, default=Decimal("1"))
    sweep.add_argument("--no-liquidate", action="store_false", dest="liquidate_at_end")
    sweep.add_argument("--output-root", type=Path, default=Path("artifacts"))

    compare = experiment_commands.add_parser("compare", help="compare completed runs")
    compare.add_argument("--run", required=True, action="append", type=Path)

    review = commands.add_parser("review", help="inspect a persisted research review")
    review_commands = review.add_subparsers(dest="command", required=True)
    show = review_commands.add_parser("show", help="print a study's automated review")
    show.add_argument("--study", required=True, type=Path)


def run(args: argparse.Namespace) -> int:
    if args.module == "review":
        print((args.study / "review.md").read_text(encoding="utf-8"), end="")
        return 0
    if args.command == "compare":
        print(json.dumps(compare_runs(args.run), indent=2, sort_keys=True))
        return 0

    dataset_store = DatasetStore(args.dataset)
    dataset_store.verify(args.dataset)
    manifest = dataset_store.load_manifest(args.dataset)
    klines = dataset_store.load_klines(args.dataset)
    config = ResearchConfig(
        fast_periods=args.fast,
        slow_periods=args.slow,
        train_ratio=args.train_ratio,
        validation_ratio=args.validation_ratio,
        min_bars_per_split=args.min_bars,
        backtest=BacktestConfig(
            initial_cash=args.initial_cash,
            fee_bps=args.fee_bps,
            slippage_bps=args.slippage_bps,
            max_target_exposure=args.max_target_exposure,
            liquidate_at_end=args.liquidate_at_end,
        ),
    )
    study = ResearchRunner().run(
        klines,
        manifest=manifest,
        config=config,
        experiment_store=ExperimentStore(args.output_root / "experiments"),
    )
    study_id, path, reused = StudyStore(args.output_root / "studies").publish(
        study,
        dataset=manifest,
    )
    print(
        json.dumps(
            {
                "study_id": study_id,
                "artifacts": str(path),
                "reused": reused,
                "winner": {
                    "fast_period": study.winner.fast_period,
                    "slow_period": study.winner.slow_period,
                },
                "test_run_id": study.test_run_id,
                "stress_run_id": study.stress_run_id,
                "findings": [item.to_dict() for item in study.findings],
            },
            sort_keys=True,
        )
    )
    return 0


def _periods(value: str) -> tuple[int, ...]:
    try:
        periods = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid period list: {value}") from exc
    if not periods:
        raise argparse.ArgumentTypeError("period list must not be empty")
    return periods


def _decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError(f"invalid decimal: {value}") from exc

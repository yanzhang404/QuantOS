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

from .artifacts import RobustnessStore, StudyStore, compare_runs
from .errors import ResearchConfigurationError
from .models import (
    DonchianResearchConfig,
    ResearchConfig,
    ResearchConfigLike,
    RobustnessConfig,
)
from .robustness import RobustnessRunner
from .workflow import ResearchRunner


def register_parser(commands: Any) -> None:
    experiment = commands.add_parser(
        "experiment",
        help="run and compare reproducible research studies",
    )
    experiment_commands = experiment.add_subparsers(dest="command", required=True)
    sweep = experiment_commands.add_parser(
        "sweep",
        help="select strategy parameters chronologically and test the winner out of sample",
    )
    sweep.add_argument("--dataset", required=True, type=Path)
    _add_strategy_arguments(sweep)
    sweep.add_argument("--train-ratio", type=_decimal, default=Decimal("0.6"))
    sweep.add_argument("--validation-ratio", type=_decimal, default=Decimal("0.2"))
    sweep.add_argument("--min-bars", type=int, default=20)
    sweep.add_argument("--initial-cash", type=_decimal, default=Decimal("100000"))
    sweep.add_argument("--fee-bps", type=_decimal, default=Decimal("10"))
    sweep.add_argument("--slippage-bps", type=_decimal, default=Decimal("5"))
    sweep.add_argument("--max-target-exposure", type=_decimal, default=Decimal("1"))
    sweep.add_argument("--no-liquidate", action="store_false", dest="liquidate_at_end")
    sweep.add_argument("--output-root", type=Path, default=Path("artifacts"))

    robustness = experiment_commands.add_parser(
        "robustness",
        help="evaluate walk-forward, neighboring-parameter, cost, and peer-market gates",
    )
    robustness.add_argument("--dataset", required=True, type=Path)
    robustness.add_argument("--peer-dataset", required=True, action="append", type=Path)
    _add_strategy_arguments(robustness)
    robustness.add_argument("--train-ratio", type=_decimal, default=Decimal("0.6"))
    robustness.add_argument("--validation-ratio", type=_decimal, default=Decimal("0.2"))
    robustness.add_argument("--min-bars", type=int, default=20)
    robustness.add_argument("--folds", type=int, default=3)
    robustness.add_argument("--minimum-positive-fold-ratio", type=_decimal, default=Decimal("0.6"))
    robustness.add_argument("--neighbor-retention-ratio", type=_decimal, default=Decimal("0.5"))
    robustness.add_argument("--cost-retention-ratio", type=_decimal, default=Decimal("0.5"))
    robustness.add_argument("--initial-cash", type=_decimal, default=Decimal("100000"))
    robustness.add_argument("--fee-bps", type=_decimal, default=Decimal("10"))
    robustness.add_argument("--slippage-bps", type=_decimal, default=Decimal("5"))
    robustness.add_argument("--max-target-exposure", type=_decimal, default=Decimal("1"))
    robustness.add_argument("--no-liquidate", action="store_false", dest="liquidate_at_end")
    robustness.add_argument("--output-root", type=Path, default=Path("artifacts"))

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
    config = _research_config(
        args,
        backtest=BacktestConfig(
            initial_cash=args.initial_cash,
            fee_bps=args.fee_bps,
            slippage_bps=args.slippage_bps,
            max_target_exposure=args.max_target_exposure,
            liquidate_at_end=args.liquidate_at_end,
        ),
    )
    experiment_store = ExperimentStore(args.output_root / "experiments")
    study = ResearchRunner().run(
        klines,
        manifest=manifest,
        config=config,
        experiment_store=experiment_store,
    )
    study_id, path, reused = StudyStore(args.output_root / "studies").publish(
        study,
        dataset=manifest,
    )
    if args.command == "robustness":
        peers = tuple(_load_dataset(path) for path in args.peer_dataset)
        robustness_config = RobustnessConfig(
            fold_count=args.folds,
            min_bars_per_window=args.min_bars,
            minimum_positive_fold_ratio=args.minimum_positive_fold_ratio,
            neighbor_retention_ratio=args.neighbor_retention_ratio,
            cost_retention_ratio=args.cost_retention_ratio,
        )
        review = RobustnessRunner().run(
            klines,
            primary_manifest=manifest,
            primary_study=study,
            research_config=config,
            robustness_config=robustness_config,
            experiment_store=experiment_store,
            peer_datasets=peers,
        )
        review_id, review_path, review_reused = RobustnessStore(
            args.output_root / "robustness"
        ).publish(
            review,
            datasets=(manifest, *(peer_manifest for _, peer_manifest in peers)),
        )
        print(
            json.dumps(
                {
                    "study_id": study_id,
                    "review_id": review_id,
                    "artifacts": str(review_path),
                    "reused": review_reused,
                    "passed": review.passed,
                    "gates": [item.to_dict() for item in review.gates],
                },
                sort_keys=True,
            )
        )
        return 0

    print(
        json.dumps(
            {
                "study_id": study_id,
                "artifacts": str(path),
                "reused": reused,
                "strategy": study.strategy_name,
                "winner": study.winner.parameters.to_dict(),
                "test_run_id": study.test_run_id,
                "stress_run_id": study.stress_run_id,
                "findings": [item.to_dict() for item in study.findings],
            },
            sort_keys=True,
        )
    )
    return 0


def _load_dataset(path: Path):
    store = DatasetStore(path)
    store.verify(path)
    return store.load_klines(path), store.load_manifest(path)


def _add_strategy_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--strategy",
        choices=("ema-cross", "donchian-atr"),
        default="ema-cross",
    )
    parser.add_argument("--fast", type=_periods)
    parser.add_argument("--slow", type=_periods)
    parser.add_argument("--entry", type=_periods)
    parser.add_argument("--exit", dest="exit_periods", type=_periods)
    parser.add_argument("--atr", type=_periods)
    parser.add_argument("--target-annual-volatility", type=_decimal)
    parser.add_argument("--max-exposure", type=_decimal)
    parser.add_argument("--rebalance-threshold", type=_decimal)


def _research_config(
    args: argparse.Namespace,
    *,
    backtest: BacktestConfig,
) -> ResearchConfigLike:
    common = {
        "train_ratio": args.train_ratio,
        "validation_ratio": args.validation_ratio,
        "min_bars_per_split": args.min_bars,
        "backtest": backtest,
    }
    if args.strategy == "ema-cross":
        if any(
            value is not None
            for value in (
                args.entry,
                args.exit_periods,
                args.atr,
                args.target_annual_volatility,
                args.max_exposure,
                args.rebalance_threshold,
            )
        ):
            raise ResearchConfigurationError("EMA research does not accept Donchian ATR parameters")
        if args.fast is None or args.slow is None:
            raise ResearchConfigurationError("EMA research requires --fast and --slow")
        return ResearchConfig(
            fast_periods=args.fast,
            slow_periods=args.slow,
            **common,
        )
    if args.fast is not None or args.slow is not None:
        raise ResearchConfigurationError("Donchian ATR research does not accept EMA parameters")
    if args.entry is None or args.exit_periods is None or args.atr is None:
        raise ResearchConfigurationError(
            "Donchian ATR research requires --entry, --exit, and --atr"
        )
    return DonchianResearchConfig(
        entry_periods=args.entry,
        exit_periods=args.exit_periods,
        atr_periods=args.atr,
        target_annual_volatility=(
            args.target_annual_volatility
            if args.target_annual_volatility is not None
            else Decimal("0.20")
        ),
        max_exposure=(args.max_exposure if args.max_exposure is not None else Decimal("1")),
        rebalance_threshold=(
            args.rebalance_threshold if args.rebalance_threshold is not None else Decimal("0.05")
        ),
        **common,
    )


def _periods(value: str) -> tuple[int, ...]:
    try:
        periods = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid period list: {value}") from exc
    if not periods:
        raise argparse.ArgumentTypeError("period list must not be empty")
    return periods


def _decimal(value: str) -> Decimal:
    if len(value) > 64:
        raise argparse.ArgumentTypeError("decimal value is too long")
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError(f"invalid decimal: {value}") from exc

"""Backtest command registration and execution."""

from __future__ import annotations

import argparse
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from quantos_market_data.storage import DatasetStore

from .artifacts import ExperimentStore
from .config import BacktestConfig
from .engine import BacktestEngine
from .strategies import EmaCrossStrategy


def register_parser(commands: Any) -> None:
    backtest = commands.add_parser("backtest", help="run reproducible historical simulations")
    backtest_commands = backtest.add_subparsers(dest="command", required=True)
    run = backtest_commands.add_parser("run", help="run an EMA cross backtest")
    run.add_argument("--dataset", required=True, type=Path)
    run.add_argument("--strategy", choices=["ema-cross"], default="ema-cross")
    run.add_argument("--fast", type=int, default=20)
    run.add_argument("--slow", type=int, default=50)
    run.add_argument("--initial-cash", type=_decimal, default=Decimal("100000"))
    run.add_argument("--fee-bps", type=_decimal, default=Decimal("10"))
    run.add_argument("--slippage-bps", type=_decimal, default=Decimal("5"))
    run.add_argument("--max-target-exposure", type=_decimal, default=Decimal("1"))
    run.add_argument("--no-liquidate", action="store_false", dest="liquidate_at_end")
    run.add_argument("--output-root", type=Path, default=Path("artifacts/experiments"))


def run(args: argparse.Namespace) -> int:
    store = DatasetStore(args.dataset)
    store.verify(args.dataset)
    manifest = store.load_manifest(args.dataset)
    klines = store.load_klines(args.dataset)
    strategy = EmaCrossStrategy(fast_period=args.fast, slow_period=args.slow)
    config = BacktestConfig(
        initial_cash=args.initial_cash,
        fee_bps=args.fee_bps,
        slippage_bps=args.slippage_bps,
        max_target_exposure=args.max_target_exposure,
        liquidate_at_end=args.liquidate_at_end,
    )
    result = BacktestEngine().run(
        klines,
        strategy=strategy,
        strategy_parameters=strategy.parameters,
        config=config,
    )
    artifacts = ExperimentStore(args.output_root).publish(result, dataset=manifest)
    print(
        json.dumps(
            {
                "run_id": artifacts.run_id,
                "artifacts": str(artifacts.path),
                "reused": artifacts.reused,
                "metrics": result.metrics.to_dict(),
            },
            sort_keys=True,
        )
    )
    return 0


def _decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError(f"invalid decimal: {value}") from exc

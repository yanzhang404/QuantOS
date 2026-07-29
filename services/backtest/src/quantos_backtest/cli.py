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
from .strategies import BuyAndHoldStrategy, DonchianAtrStrategy, EmaCrossStrategy


def register_parser(commands: Any) -> None:
    backtest = commands.add_parser("backtest", help="run reproducible historical simulations")
    backtest_commands = backtest.add_subparsers(dest="command", required=True)
    run = backtest_commands.add_parser("run", help="run a built-in strategy backtest")
    run.add_argument("--dataset", required=True, type=Path)
    run.add_argument(
        "--strategy",
        choices=["buy-and-hold", "ema-cross", "donchian-atr"],
        default="ema-cross",
    )
    run.add_argument("--fast", type=int, default=20)
    run.add_argument("--slow", type=int, default=50)
    run.add_argument("--entry-period", type=int, default=20)
    run.add_argument("--exit-period", type=int, default=10)
    run.add_argument("--atr-period", type=int, default=20)
    run.add_argument(
        "--target-annual-volatility",
        type=_decimal,
        default=Decimal("0.20"),
    )
    run.add_argument("--rebalance-threshold", type=_decimal, default=Decimal("0.05"))
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
    strategy = _strategy(args)
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


def _strategy(args: argparse.Namespace):
    if args.strategy == "buy-and-hold":
        return BuyAndHoldStrategy(target_exposure=args.max_target_exposure)
    if args.strategy == "donchian-atr":
        return DonchianAtrStrategy(
            entry_period=args.entry_period,
            exit_period=args.exit_period,
            atr_period=args.atr_period,
            target_annual_volatility=args.target_annual_volatility,
            max_exposure=args.max_target_exposure,
            rebalance_threshold=args.rebalance_threshold,
        )
    return EmaCrossStrategy(fast_period=args.fast, slow_period=args.slow)


def _decimal(value: str) -> Decimal:
    try:
        return Decimal(value)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError(f"invalid decimal: {value}") from exc

"""QuantOS command-line composition root."""

from __future__ import annotations

import argparse
import sys

from quantos_backtest import cli as backtest_cli
from quantos_backtest.errors import BacktestError
from quantos_market_data import cli as data_cli
from quantos_market_data.errors import MarketDataError
from quantos_research import cli as research_cli
from quantos_research.errors import ResearchError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="quantos", description="QuantOS research tooling")
    commands = parser.add_subparsers(dest="module", required=True)
    data_cli.register_parser(commands)
    backtest_cli.register_parser(commands)
    research_cli.register_parser(commands)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.module == "data":
            return data_cli.run(args)
        if args.module == "backtest":
            return backtest_cli.run(args)
        if args.module in {"experiment", "review"}:
            return research_cli.run(args)
    except (MarketDataError, BacktestError, ResearchError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    parser.error("unsupported module")
    return 2

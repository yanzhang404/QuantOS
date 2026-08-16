"""Command-line composition root for Market Radar v0.1."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .providers import EastmoneyAShareProvider, JsonSnapshotProvider, load_theme_map
from .radar import MarketRadarService, RadarConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the QuantOS A-share Market Radar")
    parser.add_argument("--provider", choices=("eastmoney", "json"), default="eastmoney")
    parser.add_argument("--input", help="Recorded quote JSON; required for --provider json")
    parser.add_argument("--theme-map", help="JSON mapping symbols to themes or themes to symbols")
    parser.add_argument("--state", default="data/market-radar/state.json")
    parser.add_argument("--output", help="Write the report to this path instead of stdout")
    parser.add_argument("--pretty", action="store_true")
    parser.add_argument("--min-triggers", type=int, default=2)
    parser.add_argument("--price-change-pct", type=float, default=5.0)
    parser.add_argument("--extreme-price-change-pct", type=float, default=7.0)
    parser.add_argument("--turnover-rate", type=float, default=8.0)
    parser.add_argument("--volume-ratio", type=float, default=2.0)
    parser.add_argument("--amplitude-pct", type=float, default=8.0)
    parser.add_argument("--change-5m-pct", type=float, default=1.0)
    parser.add_argument("--amount", type=float, default=100_000_000.0)
    parser.add_argument("--history-limit", type=int, default=24)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.provider == "json":
        if not args.input:
            raise SystemExit("--input is required when --provider json")
        provider = JsonSnapshotProvider(args.input)
    else:
        provider = EastmoneyAShareProvider(theme_map=load_theme_map(args.theme_map))
    report = MarketRadarService(
        provider=provider,
        config=RadarConfig(
            price_change_pct=args.price_change_pct,
            extreme_price_change_pct=args.extreme_price_change_pct,
            turnover_rate=args.turnover_rate,
            volume_ratio=args.volume_ratio,
            amplitude_pct=args.amplitude_pct,
            change_5m_pct=args.change_5m_pct,
            amount=args.amount,
            min_triggers=args.min_triggers,
            history_limit=args.history_limit,
        ),
        state_path=args.state,
    ).run()
    payload = json.dumps(
        report.to_dict(), ensure_ascii=False, indent=2 if args.pretty else None
    )
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())

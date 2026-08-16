"""CLI composition root for the US live equity heat radar."""

from __future__ import annotations

import argparse
import asyncio
import os
import json
from pathlib import Path

from .alpaca import AlpacaBarStream, JsonLineBarStream
from .notifiers import CompositeNotifier, ConsoleNotifier, WebhookNotifier
from .options import (
    AlpacaOptionChainProvider, JsonOptionChainProvider, USOptionRadarService,
)
from .us_radar import USHeatConfig, USLiveRadarRunner
from .evaluation import RadarOutcomeEvaluator


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run QuantOS US equity heat radar")
    subparsers = parser.add_subparsers(dest="command", required=True)
    replay = subparsers.add_parser("replay", help="Replay recorded JSON Lines bars")
    replay.add_argument("--input", required=True)
    replay.add_argument("--delay-seconds", type=float, default=0.0)
    replay.add_argument("--option-chain", help="Normalized option-chain JSON for replay")
    live = subparsers.add_parser("live", help="Stream live Alpaca minute bars")
    live.add_argument("--feed", choices=("sip", "iex", "delayed_sip"), default="sip")
    live.add_argument(
        "--options-feed", choices=("none", "opra", "indicative"), default="none"
    )
    evaluate = subparsers.add_parser("evaluate", help="Evaluate saved alert outcomes")
    evaluate.add_argument("--reports", required=True)
    evaluate.add_argument("--bars", required=True)
    evaluate.add_argument("--horizons", default="5,15,30")
    evaluate.add_argument("--output")
    for child in (replay, live):
        child.add_argument("--top", type=int, default=20)
        child.add_argument("--min-score", type=float, default=35.0)
        child.add_argument("--min-price", type=float, default=2.0)
        child.add_argument("--min-dollar-volume", type=float, default=1_000_000.0)
        child.add_argument("--push-interval", type=float, default=300.0)
        child.add_argument("--output-jsonl", default="data/us-market-radar/reports.jsonl")
        child.add_argument("--option-top", type=int, default=10)
        child.add_argument("--webhook-url")
        child.add_argument(
            "--webhook-format", choices=("slack", "wecom", "generic"), default="slack"
        )
    return parser


async def _run(args: argparse.Namespace) -> None:
    if args.command == "replay":
        provider = JsonLineBarStream(args.input, args.delay_seconds)
        option_provider = JsonOptionChainProvider(args.option_chain) if args.option_chain else None
    else:
        api_key = os.environ.get("APCA_API_KEY_ID", "")
        api_secret = os.environ.get("APCA_API_SECRET_KEY", "")
        if not api_key or not api_secret:
            raise SystemExit(
                "APCA_API_KEY_ID and APCA_API_SECRET_KEY are required for live mode"
            )
        provider = AlpacaBarStream(api_key, api_secret, args.feed)
        option_provider = (
            None if args.options_feed == "none" else
            AlpacaOptionChainProvider(api_key, api_secret, args.options_feed)
        )
    notifiers = [ConsoleNotifier()]
    if args.webhook_url:
        notifiers.append(WebhookNotifier(args.webhook_url, args.webhook_format))
    config = USHeatConfig(
        top_n=args.top,
        min_heat_score=args.min_score,
        min_price=args.min_price,
        min_dollar_volume_5m=args.min_dollar_volume,
    )
    await USLiveRadarRunner(
        provider=provider,
        notifier=CompositeNotifier(notifiers),
        config=config,
        push_interval_seconds=args.push_interval,
        report_path=args.output_jsonl,
        option_service=(
            USOptionRadarService(option_provider, top_underlyings=args.option_top)
            if option_provider else None
        ),
    ).run()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "evaluate":
        horizons = tuple(int(item.strip()) for item in args.horizons.split(",") if item.strip())
        report = RadarOutcomeEvaluator(horizons).evaluate_files(args.reports, args.bars)
        payload = json.dumps(report.to_dict(), ensure_ascii=False, indent=2)
        if args.output:
            output = Path(args.output)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(payload + "\n", encoding="utf-8")
        else:
            print(payload)
        return 0
    try:
        asyncio.run(_run(args))
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

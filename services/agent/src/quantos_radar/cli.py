"""Command-line entry point for Market Radar collection and publication."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .collector import PublicRadarCollector, build_public_client
from .errors import RadarValidationError
from .models import MarketRadarInput
from .refresh import RadarRefresher, _atomic_json
from .scoring import build_snapshot
from .store import load_baselines, publish_snapshot


def register_parser(commands: Any) -> None:
    radar = commands.add_parser("radar", help="monitor deterministic A-share stock and theme heat")
    subcommands = radar.add_subparsers(dest="command", required=True)
    build = subcommands.add_parser("build", help="validate a radar input and publish a snapshot")
    build.add_argument("--input", required=True, type=Path)
    build.add_argument("--output-root", type=Path, default=Path("var/quantos/radar"))
    collect = subcommands.add_parser("collect", help="collect one bounded A-share snapshot input")
    collect.add_argument("--output", required=True, type=Path)
    collect.add_argument("--as-of", type=_argument_datetime, default=None)
    refresh = subcommands.add_parser("refresh", help="collect and publish one ten-minute bucket")
    refresh.add_argument("--input-root", type=Path, default=Path("var/quantos/radar-inputs"))
    refresh.add_argument("--output-root", type=Path, default=Path("var/quantos/radar"))
    refresh.add_argument("--as-of", type=_argument_datetime, default=None)


def run(args: argparse.Namespace) -> int:
    if args.module != "radar":
        raise RadarValidationError("unsupported radar command")
    if args.command == "collect":
        with build_public_client() as client:
            radar = PublicRadarCollector(client).collect(as_of=args.as_of or datetime.now(UTC))
        _atomic_json(args.output, radar.to_dict())
        print(json.dumps(_summary(radar, args.output), sort_keys=True))
        return 0
    if args.command == "refresh":
        result = RadarRefresher(
            input_root=args.input_root,
            output_root=args.output_root,
        ).run(as_of=args.as_of)
        print(json.dumps(result, sort_keys=True))
        return 0
    if args.command != "build":
        raise RadarValidationError("unsupported radar command")
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RadarValidationError("radar input must be valid JSON") from exc
    radar = MarketRadarInput.from_dict(payload)
    snapshot = build_snapshot(radar, load_baselines(args.output_root, radar.as_of))
    history, latest = publish_snapshot(snapshot, args.output_root)
    print(
        json.dumps(
            {
                "as_of": snapshot["as_of"],
                "stock_count": len(snapshot["stocks"]),
                "theme_count": len(snapshot["themes"]),
                "snapshot": str(history),
                "latest": str(latest),
            },
            sort_keys=True,
        )
    )
    return 0


def _summary(radar: MarketRadarInput, output: Path) -> dict[str, Any]:
    return {
        "as_of": radar.to_dict()["as_of"],
        "status": radar.status,
        "stock_count": len(radar.stocks),
        "output": str(output),
    }


def _argument_datetime(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("as-of must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("as-of requires a timezone")
    return parsed.astimezone(UTC)

"""Command-line entry point for daily intelligence publication."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .errors import IntelligenceValidationError
from .models import DailyIntelligenceInput
from .scoring import build_snapshot
from .store import publish_snapshot


def register_parser(commands: Any) -> None:
    intelligence = commands.add_parser(
        "intelligence", help="build deterministic daily market intelligence"
    )
    subcommands = intelligence.add_subparsers(dest="command", required=True)
    build = subcommands.add_parser("build", help="validate an Agent input and publish a snapshot")
    build.add_argument("--input", required=True, type=Path)
    build.add_argument("--output-root", type=Path, default=Path("var/quantos/intelligence"))


def run(args: argparse.Namespace) -> int:
    if args.module != "intelligence" or args.command != "build":
        raise IntelligenceValidationError("unsupported intelligence command")
    try:
        payload = json.loads(args.input.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise IntelligenceValidationError("input must be valid JSON") from exc
    daily = DailyIntelligenceInput.from_dict(payload)
    snapshot = build_snapshot(daily)
    daily_path, latest_path = publish_snapshot(snapshot, args.output_root)
    print(
        json.dumps(
            {
                "date": snapshot["date"],
                "score": snapshot["score"],
                "label": snapshot["label"],
                "snapshot": str(daily_path),
                "latest": str(latest_path),
            },
            sort_keys=True,
        )
    )
    return 0

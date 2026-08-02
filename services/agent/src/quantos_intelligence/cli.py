"""Command-line entry point for daily intelligence publication."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .collector import ObservationHistory, PublicIntelligenceCollector, build_public_client
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

    collect = subcommands.add_parser("collect", help="collect an allow-listed public input")
    collect.add_argument("--output", required=True, type=Path)
    collect.add_argument(
        "--history-root",
        type=Path,
        default=Path("var/quantos/intelligence-observations"),
    )
    collect.add_argument("--as-of", type=_datetime, default=None)
    collect.add_argument("--previous-snapshot", type=Path)


def run(args: argparse.Namespace) -> int:
    if args.module != "intelligence":
        raise IntelligenceValidationError("unsupported intelligence command")
    if args.command == "collect":
        previous_score = _previous_score(args.previous_snapshot)
        with build_public_client() as client:
            daily = PublicIntelligenceCollector(
                client,
                ObservationHistory(args.history_root),
            ).collect(as_of=args.as_of or datetime.now(UTC), previous_score=previous_score)
        _write_json(args.output, daily.to_dict())
        print(
            json.dumps(
                {
                    "date": daily.date.isoformat(),
                    "status": daily.status,
                    "factor_count": len(daily.factors),
                    "news_count": len(daily.news),
                    "output": str(args.output),
                },
                sort_keys=True,
            )
        )
        return 0
    if args.command != "build":
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


def _datetime(value: str) -> datetime:
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("as-of must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("as-of requires a timezone")
    return parsed.astimezone(UTC)


def _previous_score(path: Path | None) -> float | None:
    if path is None:
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        score = raw["score"]
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 100:
            raise ValueError
        return float(score)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise IntelligenceValidationError("previous snapshot is invalid") from exc


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

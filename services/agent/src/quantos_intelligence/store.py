"""Atomic local publication for immutable daily intelligence snapshots."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def publish_snapshot(snapshot: dict[str, Any], output_root: Path) -> tuple[Path, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    daily_path = output_root / f"{snapshot['date']}.json"
    latest_path = output_root / "latest.json"
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    _atomic_write(daily_path, payload)
    _atomic_write(latest_path, payload)
    return daily_path, latest_path


def _atomic_write(path: Path, payload: str) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)

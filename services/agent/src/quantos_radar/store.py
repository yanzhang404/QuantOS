"""Atomic publication and bounded baseline loading for Market Radar."""

from __future__ import annotations

import fcntl
import json
import os
import stat
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .errors import RadarValidationError
from .scoring import METHODOLOGY_VERSION

MAX_SNAPSHOT_BYTES = 4 << 20


def publish_snapshot(snapshot: dict[str, Any], output_root: Path) -> tuple[Path, Path]:
    as_of = _datetime(snapshot.get("as_of"))
    bucket = as_of.strftime("%H%M")
    history_path = output_root / "snapshots" / as_of.date().isoformat() / f"{bucket}.json"
    latest_path = output_root / "latest.json"
    payload = json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    encoded = payload.encode("utf-8")
    if len(encoded) > MAX_SNAPSHOT_BYTES:
        raise RadarValidationError("radar snapshot is too large")
    output_root.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(output_root / "publish.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        existing_latest = _read_existing(latest_path)
        if existing_latest is not None:
            try:
                latest_at = _datetime(json.loads(existing_latest).get("as_of"))
            except (json.JSONDecodeError, AttributeError) as exc:
                raise RadarValidationError("radar latest snapshot is invalid") from exc
            if latest_at > as_of:
                raise RadarValidationError("radar latest snapshot cannot move backward")
            if latest_at == as_of and existing_latest != payload:
                raise RadarValidationError("radar latest bucket contains different content")
        _write_immutable(history_path, payload)
        if existing_latest != payload:
            _atomic_write(latest_path, payload)
    finally:
        os.close(descriptor)
    return history_path, latest_path


def load_baselines(output_root: Path, as_of: datetime) -> list[dict[str, Any]]:
    snapshots_root = output_root / "snapshots"
    if not snapshots_root.exists():
        return []
    earliest = as_of.astimezone(UTC) - timedelta(minutes=75)
    records: list[dict[str, Any]] = []
    paths = sorted(snapshots_root.glob("*/*.json"), reverse=True)[:32]
    for path in paths:
        try:
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode) or path.is_symlink() or info.st_size > 2 << 20:
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            observed = _datetime(payload.get("as_of"))
        except (OSError, json.JSONDecodeError, RadarValidationError):
            continue
        if (
            observed < earliest
            or observed >= as_of
            or payload.get("methodology_version") != METHODOLOGY_VERSION
        ):
            continue
        records.append(payload)
    return records


def _atomic_write(path: Path, payload: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_immutable(path: Path, payload: str) -> None:
    existing = _read_existing(path)
    if existing is not None:
        if existing != payload:
            raise RadarValidationError("radar snapshot bucket contains different content")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            if _read_existing(path) != payload:
                raise RadarValidationError(
                    "radar snapshot bucket contains different content"
                ) from exc
    finally:
        temporary.unlink(missing_ok=True)


def _read_existing(path: Path) -> str | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if (
        not stat.S_ISREG(info.st_mode)
        or path.is_symlink()
        or not 0 < info.st_size <= MAX_SNAPSHOT_BYTES
    ):
        raise RadarValidationError("radar snapshot file is invalid")
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RadarValidationError("radar snapshot file is invalid") from exc


def _datetime(value: Any) -> datetime:
    if not isinstance(value, str):
        raise RadarValidationError("radar snapshot timestamp is invalid")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise RadarValidationError("radar snapshot timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise RadarValidationError("radar snapshot timestamp is invalid")
    return parsed.astimezone(UTC)

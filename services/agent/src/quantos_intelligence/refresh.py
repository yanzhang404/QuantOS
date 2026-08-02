"""Observable single-writer refresh workflow for daily intelligence."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx

from .collector import ObservationHistory, PublicIntelligenceCollector, build_public_client
from .errors import IntelligenceError, IntelligenceValidationError
from .models import DailyIntelligenceInput
from .scoring import build_snapshot
from .store import publish_snapshot

HEALTH_SCHEMA_VERSION = "1.0"
HEALTH_STATES = frozenset({"running", "succeeded", "failed"})
ERROR_CODES = frozenset({"collection_failed", "publication_failed"})


@dataclass(frozen=True, slots=True)
class RefreshHealth:
    state: str
    last_attempt_at: datetime
    last_success_at: datetime | None
    last_success_date: date | None
    consecutive_failures: int
    last_error_code: str | None

    @classmethod
    def from_dict(cls, value: Any) -> RefreshHealth:
        if not isinstance(value, dict) or set(value) != {
            "schema_version",
            "state",
            "last_attempt_at",
            "last_success_at",
            "last_success_date",
            "consecutive_failures",
            "last_error_code",
        }:
            raise IntelligenceValidationError("refresh health is invalid")
        if value["schema_version"] != HEALTH_SCHEMA_VERSION or value["state"] not in HEALTH_STATES:
            raise IntelligenceValidationError("refresh health is invalid")
        failures = value["consecutive_failures"]
        error_code = value["last_error_code"]
        if (
            isinstance(failures, bool)
            or not isinstance(failures, int)
            or not 0 <= failures <= 365
            or error_code not in ERROR_CODES | {None}
        ):
            raise IntelligenceValidationError("refresh health is invalid")
        success_at = _optional_datetime(value["last_success_at"])
        success_date = _optional_date(value["last_success_date"])
        if (success_at is None) != (success_date is None):
            raise IntelligenceValidationError("refresh health success fields must appear together")
        if value["state"] == "succeeded" and (success_at is None or failures or error_code):
            raise IntelligenceValidationError("successful refresh health is inconsistent")
        if value["state"] == "failed" and (failures < 1 or error_code is None):
            raise IntelligenceValidationError("failed refresh health is inconsistent")
        if value["state"] == "running" and error_code is not None:
            raise IntelligenceValidationError("running refresh health is inconsistent")
        return cls(
            state=value["state"],
            last_attempt_at=_datetime(value["last_attempt_at"]),
            last_success_at=success_at,
            last_success_date=success_date,
            consecutive_failures=failures,
            last_error_code=error_code,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": HEALTH_SCHEMA_VERSION,
            "state": self.state,
            "last_attempt_at": _isoformat(self.last_attempt_at),
            "last_success_at": (
                None if self.last_success_at is None else _isoformat(self.last_success_at)
            ),
            "last_success_date": (
                None if self.last_success_date is None else self.last_success_date.isoformat()
            ),
            "consecutive_failures": self.consecutive_failures,
            "last_error_code": self.last_error_code,
        }


class IntelligenceRefresher:
    def __init__(
        self,
        *,
        input_root: Path,
        history_root: Path,
        output_root: Path,
        client_factory: Callable[[], httpx.Client] = build_public_client,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.input_root = input_root
        self.history_root = history_root
        self.output_root = output_root
        self.client_factory = client_factory
        self.now = now

    def run(self, *, as_of: datetime | None = None) -> dict[str, Any]:
        attempt_at = self.now().astimezone(UTC)
        if as_of is not None and as_of.tzinfo is None:
            raise IntelligenceValidationError("as_of must include a timezone")
        collection_at = (as_of or attempt_at).astimezone(UTC)
        self.output_root.mkdir(parents=True, exist_ok=True)
        lock_path = self.output_root / "refresh.lock"
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise IntelligenceError("daily intelligence refresh is already running") from exc
            return self._run_locked(attempt_at, collection_at)
        finally:
            os.close(descriptor)

    def _run_locked(self, attempt_at: datetime, collection_at: datetime) -> dict[str, Any]:
        prior = self._read_health()
        self._write_health(
            RefreshHealth(
                "running",
                attempt_at,
                prior.last_success_at if prior else None,
                prior.last_success_date if prior else None,
                prior.consecutive_failures if prior else 0,
                None,
            )
        )
        input_path = self.input_root / f"{collection_at.date().isoformat()}.json"
        try:
            daily = self._load_or_collect(input_path, collection_at)
        except (IntelligenceError, OSError, ValueError):
            self._record_failure(attempt_at, prior, "collection_failed")
            raise
        try:
            snapshot = build_snapshot(daily)
            daily_path, latest_path = publish_snapshot(snapshot, self.output_root)
        except (IntelligenceError, OSError, ValueError):
            self._record_failure(attempt_at, prior, "publication_failed")
            raise
        completed_at = self.now().astimezone(UTC)
        self._write_health(
            RefreshHealth("succeeded", attempt_at, completed_at, daily.date, 0, None)
        )
        return {
            "date": daily.date.isoformat(),
            "status": daily.status,
            "score": snapshot["score"],
            "input": str(input_path),
            "snapshot": str(daily_path),
            "latest": str(latest_path),
            "health": str(self.output_root / "refresh-health.json"),
        }

    def _load_or_collect(self, input_path: Path, as_of: datetime) -> DailyIntelligenceInput:
        try:
            payload = json.loads(input_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            previous_score = _previous_score(self.output_root / "latest.json")
            with self.client_factory() as client:
                daily = PublicIntelligenceCollector(
                    client, ObservationHistory(self.history_root)
                ).collect(as_of=as_of, previous_score=previous_score)
            _atomic_json(input_path, daily.to_dict())
            return daily
        except (OSError, json.JSONDecodeError) as exc:
            raise IntelligenceValidationError("daily refresh input is invalid") from exc
        daily = DailyIntelligenceInput.from_dict(payload)
        if daily.date != as_of.date():
            raise IntelligenceValidationError("daily refresh input date is invalid")
        return daily

    def _record_failure(
        self, attempt_at: datetime, prior: RefreshHealth | None, error_code: str
    ) -> None:
        failures = min(365, (prior.consecutive_failures if prior else 0) + 1)
        self._write_health(
            RefreshHealth(
                "failed",
                attempt_at,
                prior.last_success_at if prior else None,
                prior.last_success_date if prior else None,
                failures,
                error_code,
            )
        )

    def _read_health(self) -> RefreshHealth | None:
        try:
            payload = json.loads(
                (self.output_root / "refresh-health.json").read_text(encoding="utf-8")
            )
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            raise IntelligenceValidationError("refresh health is invalid") from exc
        return RefreshHealth.from_dict(payload)

    def _write_health(self, health: RefreshHealth) -> None:
        validated = RefreshHealth.from_dict(health.to_dict())
        _atomic_json(self.output_root / "refresh-health.json", validated.to_dict())


def _previous_score(path: Path) -> float | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        raise IntelligenceValidationError("previous intelligence snapshot is invalid") from exc
    score = payload.get("score") if isinstance(payload, dict) else None
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not 0 <= score <= 100:
        raise IntelligenceValidationError("previous intelligence snapshot is invalid")
    return float(score)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
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


def _datetime(value: Any) -> datetime:
    if not isinstance(value, str) or len(value) > 64:
        raise IntelligenceValidationError("refresh health timestamp is invalid")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise IntelligenceValidationError("refresh health timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise IntelligenceValidationError("refresh health timestamp is invalid")
    return parsed.astimezone(UTC)


def _optional_datetime(value: Any) -> datetime | None:
    return None if value is None else _datetime(value)


def _optional_date(value: Any) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str) or len(value) != 10:
        raise IntelligenceValidationError("refresh health date is invalid")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise IntelligenceValidationError("refresh health date is invalid") from exc


def _isoformat(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

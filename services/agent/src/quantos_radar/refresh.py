"""Observable single-writer refresh workflow for intraday Market Radar."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from .collector import PublicRadarCollector, build_public_client
from .errors import RadarError, RadarValidationError
from .models import MarketRadarInput
from .scoring import build_snapshot
from .store import load_baselines, publish_snapshot

HEALTH_SCHEMA_VERSION = "1.0"
HEALTH_STATES = frozenset({"running", "succeeded", "failed"})
ERROR_CODES = frozenset({"collection_failed", "publication_failed"})


@dataclass(frozen=True, slots=True)
class RefreshHealth:
    state: str
    last_attempt_at: datetime
    last_success_at: datetime | None
    last_success_bucket: str | None
    consecutive_failures: int
    last_error_code: str | None

    @classmethod
    def from_dict(cls, value: Any) -> RefreshHealth:
        expected = {
            "schema_version",
            "state",
            "last_attempt_at",
            "last_success_at",
            "last_success_bucket",
            "consecutive_failures",
            "last_error_code",
        }
        if not isinstance(value, dict) or set(value) != expected:
            raise RadarValidationError("radar refresh health is invalid")
        state = value["state"]
        failures = value["consecutive_failures"]
        error_code = value["last_error_code"]
        if (
            value["schema_version"] != HEALTH_SCHEMA_VERSION
            or state not in HEALTH_STATES
            or isinstance(failures, bool)
            or not isinstance(failures, int)
            or not 0 <= failures <= 1000
            or error_code not in ERROR_CODES | {None}
        ):
            raise RadarValidationError("radar refresh health is invalid")
        success_at = _optional_datetime(value["last_success_at"])
        success_bucket = value["last_success_bucket"]
        if success_bucket is not None and (
            not isinstance(success_bucket, str)
            or len(success_bucket) != 17
            or not success_bucket.endswith("Z")
        ):
            raise RadarValidationError("radar refresh health bucket is invalid")
        if (success_at is None) != (success_bucket is None):
            raise RadarValidationError("radar refresh success fields must appear together")
        if state == "succeeded" and (success_at is None or failures or error_code):
            raise RadarValidationError("successful radar refresh health is inconsistent")
        if state == "failed" and (failures < 1 or error_code is None):
            raise RadarValidationError("failed radar refresh health is inconsistent")
        if state == "running" and error_code is not None:
            raise RadarValidationError("running radar refresh health is inconsistent")
        return cls(
            state=state,
            last_attempt_at=_datetime(value["last_attempt_at"]),
            last_success_at=success_at,
            last_success_bucket=success_bucket,
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
            "last_success_bucket": self.last_success_bucket,
            "consecutive_failures": self.consecutive_failures,
            "last_error_code": self.last_error_code,
        }


class RadarRefresher:
    def __init__(
        self,
        *,
        input_root: Path,
        output_root: Path,
        client_factory: Callable[[], httpx.Client] = build_public_client,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.input_root = input_root
        self.output_root = output_root
        self.client_factory = client_factory
        self.now = now

    def run(self, *, as_of: datetime | None = None) -> dict[str, Any]:
        attempt_at = self.now().astimezone(UTC)
        if as_of is not None and as_of.tzinfo is None:
            raise RadarValidationError("as_of must include a timezone")
        collection_at = _bucket(as_of or attempt_at)
        observed_at = collection_at if as_of is not None else attempt_at
        self.output_root.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(self.output_root / "refresh.lock", os.O_CREAT | os.O_RDWR, 0o600)
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RadarError("market radar refresh is already running") from exc
            return self._run_locked(attempt_at, collection_at, observed_at)
        finally:
            os.close(descriptor)

    def _run_locked(
        self, attempt_at: datetime, collection_at: datetime, observed_at: datetime
    ) -> dict[str, Any]:
        prior = self._read_health()
        self._write_health(
            RefreshHealth(
                "running",
                attempt_at,
                prior.last_success_at if prior else None,
                prior.last_success_bucket if prior else None,
                prior.consecutive_failures if prior else 0,
                None,
            )
        )
        input_path = (
            self.input_root
            / collection_at.date().isoformat()
            / f"{collection_at.strftime('%H%M')}.json"
        )
        try:
            radar = self._load_or_collect(input_path, collection_at, observed_at)
        except (RadarError, OSError, ValueError):
            self._record_failure(attempt_at, prior, "collection_failed")
            raise
        try:
            snapshot = build_snapshot(radar, load_baselines(self.output_root, radar.as_of))
            history_path, latest_path = publish_snapshot(snapshot, self.output_root)
        except (RadarError, OSError, ValueError):
            self._record_failure(attempt_at, prior, "publication_failed")
            raise
        completed_at = self.now().astimezone(UTC)
        bucket = _bucket_key(collection_at)
        self._write_health(RefreshHealth("succeeded", attempt_at, completed_at, bucket, 0, None))
        return {
            "as_of": snapshot["as_of"],
            "status": snapshot["status"],
            "stock_count": len(snapshot["stocks"]),
            "theme_count": len(snapshot["themes"]),
            "input": str(input_path),
            "snapshot": str(history_path),
            "latest": str(latest_path),
            "health": str(self.output_root / "refresh-health.json"),
        }

    def _load_or_collect(
        self, input_path: Path, as_of: datetime, observed_at: datetime
    ) -> MarketRadarInput:
        try:
            payload = json.loads(input_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            with self.client_factory() as client:
                radar = PublicRadarCollector(client).collect(as_of=as_of, observed_at=observed_at)
            _atomic_json(input_path, radar.to_dict())
            return radar
        except (OSError, json.JSONDecodeError) as exc:
            raise RadarValidationError("radar refresh input is invalid") from exc
        radar = MarketRadarInput.from_dict(payload)
        if radar.as_of != as_of:
            raise RadarValidationError("radar refresh input bucket is invalid")
        return radar

    def _record_failure(
        self, attempt_at: datetime, prior: RefreshHealth | None, error_code: str
    ) -> None:
        failures = min(1000, (prior.consecutive_failures if prior else 0) + 1)
        self._write_health(
            RefreshHealth(
                "failed",
                attempt_at,
                prior.last_success_at if prior else None,
                prior.last_success_bucket if prior else None,
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
            raise RadarValidationError("radar refresh health is invalid") from exc
        return RefreshHealth.from_dict(payload)

    def _write_health(self, health: RefreshHealth) -> None:
        validated = RefreshHealth.from_dict(health.to_dict())
        _atomic_json(self.output_root / "refresh-health.json", validated.to_dict())


def _bucket(value: datetime) -> datetime:
    value = value.astimezone(UTC)
    return value.replace(minute=value.minute // 10 * 10, second=0, microsecond=0)


def _bucket_key(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ")


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
        raise RadarValidationError("radar refresh timestamp is invalid")
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise RadarValidationError("radar refresh timestamp is invalid") from exc
    if parsed.tzinfo is None:
        raise RadarValidationError("radar refresh timestamp is invalid")
    return parsed.astimezone(UTC)


def _optional_datetime(value: Any) -> datetime | None:
    return None if value is None else _datetime(value)


def _isoformat(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

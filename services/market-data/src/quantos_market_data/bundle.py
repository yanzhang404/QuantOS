"""Atomic manifests for complete, immutable market-data matrices."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .errors import DatasetError
from .models import Interval
from .storage import DatasetStore, PublishedDataset

BUNDLE_SCHEMA_VERSION = "dataset-bundle.v1"
COVERAGE_SCHEMA_VERSION = "dataset-coverage.v1"
BUNDLE_MANIFEST_FILE_NAME = "manifest.json"
PRODUCT_SYMBOLS = ("BTCUSDT", "ETHUSDT")
PRODUCT_INTERVALS = (
    Interval.FIVE_MINUTES,
    Interval.FIFTEEN_MINUTES,
    Interval.ONE_HOUR,
    Interval.FOUR_HOURS,
    Interval.ONE_DAY,
)


@dataclass(frozen=True, slots=True)
class DatasetBundleMember:
    symbol: str
    interval: str
    dataset_version: str
    content_sha256: str
    row_count: int
    requested_start: str
    requested_end: str
    dataset_path: str


@dataclass(frozen=True, slots=True)
class DatasetBundleManifest:
    bundle_version: str
    schema_version: str
    source: str
    market_type: str
    requested_start: str
    requested_end: str
    created_at: str
    members: tuple[DatasetBundleMember, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["members"] = [asdict(item) for item in self.members]
        return result

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> DatasetBundleManifest:
        try:
            return cls(
                bundle_version=str(raw["bundle_version"]),
                schema_version=str(raw["schema_version"]),
                source=str(raw["source"]),
                market_type=str(raw["market_type"]),
                requested_start=str(raw["requested_start"]),
                requested_end=str(raw["requested_end"]),
                created_at=str(raw["created_at"]),
                members=tuple(DatasetBundleMember(**item) for item in raw["members"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DatasetError("invalid dataset bundle manifest") from exc


@dataclass(frozen=True, slots=True)
class PublishedDatasetBundle:
    path: Path
    manifest: DatasetBundleManifest


class DatasetBundleStore:
    """Publish one immutable identity for a fully verified dataset matrix."""

    def __init__(
        self,
        root: Path,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.root = root
        self._now = now

    def publish(
        self,
        datasets: Iterable[PublishedDataset],
        *,
        symbols: tuple[str, ...] = PRODUCT_SYMBOLS,
        intervals: tuple[Interval, ...] = PRODUCT_INTERVALS,
    ) -> PublishedDatasetBundle:
        published = list(datasets)
        expected = {(symbol, interval.value) for symbol in symbols for interval in intervals}
        actual = {(item.manifest.symbol, item.manifest.interval) for item in published}
        if len(published) != len(expected) or actual != expected:
            raise DatasetError("dataset bundle members do not match the requested matrix")

        dataset_store = DatasetStore(self.root)
        members: list[DatasetBundleMember] = []
        sources: set[str] = set()
        ranges: set[tuple[str, str]] = set()
        for item in published:
            dataset_store.verify(item.path)
            manifest = dataset_store.load_manifest(item.path)
            if manifest != item.manifest:
                raise DatasetError(
                    f"dataset manifest changed during bundle publication: {item.path}"
                )
            try:
                relative_path = item.path.resolve().relative_to(self.root.resolve())
            except ValueError as exc:
                raise DatasetError(f"dataset is outside the bundle data root: {item.path}") from exc
            sources.add(manifest.source)
            ranges.add((manifest.requested_start, manifest.requested_end))
            members.append(
                DatasetBundleMember(
                    symbol=manifest.symbol,
                    interval=manifest.interval,
                    dataset_version=manifest.dataset_version,
                    content_sha256=manifest.content_sha256,
                    row_count=manifest.row_count,
                    requested_start=manifest.requested_start,
                    requested_end=manifest.requested_end,
                    dataset_path=relative_path.as_posix(),
                )
            )

        if len(sources) != 1 or len(ranges) != 1:
            raise DatasetError("dataset bundle members must share one source and requested range")
        members.sort(key=lambda item: (item.symbol, _interval_index(item.interval)))
        requested_start, requested_end = next(iter(ranges))
        source = next(iter(sources))
        bundle_version = _bundle_hash(source, requested_start, requested_end, members)[:16]
        parent = self.root / "bundles" / "market" / "spot" / "exchange=binance"
        final_path = parent / f"version={bundle_version}"

        if final_path.exists():
            manifest = self.load_manifest(final_path)
            self.verify(final_path)
            return PublishedDatasetBundle(final_path, manifest)

        parent.mkdir(parents=True, exist_ok=True)
        temporary_path = Path(tempfile.mkdtemp(prefix=".publishing-", dir=parent))
        manifest = DatasetBundleManifest(
            bundle_version=bundle_version,
            schema_version=BUNDLE_SCHEMA_VERSION,
            source=source,
            market_type="spot",
            requested_start=requested_start,
            requested_end=requested_end,
            created_at=_isoformat(self._now()),
            members=tuple(members),
        )
        try:
            (temporary_path / BUNDLE_MANIFEST_FILE_NAME).write_text(
                json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary_path, final_path)
        except Exception:
            shutil.rmtree(temporary_path, ignore_errors=True)
            raise
        return PublishedDatasetBundle(final_path, manifest)

    def load_manifest(self, bundle: Path) -> DatasetBundleManifest:
        manifest_path = _manifest_path(bundle)
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DatasetError(f"cannot read dataset bundle manifest: {manifest_path}") from exc
        if not isinstance(raw, dict):
            raise DatasetError("dataset bundle manifest must contain an object")
        return DatasetBundleManifest.from_dict(raw)

    def verify(self, bundle: Path) -> DatasetBundleManifest:
        manifest = self.load_manifest(bundle)
        if manifest.schema_version != BUNDLE_SCHEMA_VERSION:
            raise DatasetError(f"unsupported dataset bundle schema: {manifest.schema_version}")
        expected = {
            (symbol, interval.value) for symbol in PRODUCT_SYMBOLS for interval in PRODUCT_INTERVALS
        }
        if {(item.symbol, item.interval) for item in manifest.members} != expected:
            raise DatasetError("dataset bundle is incomplete")
        for member in manifest.members:
            dataset_path = self.root / member.dataset_path
            DatasetStore(self.root).verify(dataset_path)
            source = DatasetStore(self.root).load_manifest(dataset_path)
            if (
                source.dataset_version != member.dataset_version
                or source.content_sha256 != member.content_sha256
                or source.row_count != member.row_count
                or source.requested_start != member.requested_start
                or source.requested_end != member.requested_end
            ):
                raise DatasetError(f"dataset bundle member identity mismatch: {dataset_path}")
        digest = _bundle_hash(
            manifest.source,
            manifest.requested_start,
            manifest.requested_end,
            list(manifest.members),
        )[:16]
        if digest != manifest.bundle_version:
            raise DatasetError("dataset bundle version does not match its members")
        return manifest


def coverage_evidence(manifest: DatasetBundleManifest) -> dict[str, Any]:
    """Return the compact repository-safe projection used by the workspace."""

    return {
        "schema_version": COVERAGE_SCHEMA_VERSION,
        "bundle_version": manifest.bundle_version,
        "source": manifest.source,
        "market_type": manifest.market_type,
        "requested_start": manifest.requested_start,
        "requested_end": manifest.requested_end,
        "member_count": len(manifest.members),
        "members": [
            {
                "symbol": item.symbol,
                "interval": item.interval,
                "dataset_version": item.dataset_version,
                "content_sha256": item.content_sha256,
                "row_count": item.row_count,
                "status": "verified",
            }
            for item in manifest.members
        ],
    }


def write_coverage_evidence(manifest: DatasetBundleManifest, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(f"{output.suffix}.tmp")
    temporary.write_text(
        json.dumps(coverage_evidence(manifest), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, output)


def _bundle_hash(
    source: str,
    requested_start: str,
    requested_end: str,
    members: list[DatasetBundleMember],
) -> str:
    payload = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "source": source,
        "requested_start": requested_start,
        "requested_end": requested_end,
        "members": [
            {
                "symbol": item.symbol,
                "interval": item.interval,
                "dataset_version": item.dataset_version,
                "content_sha256": item.content_sha256,
                "row_count": item.row_count,
            }
            for item in members
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _interval_index(value: str) -> int:
    try:
        return [item.value for item in PRODUCT_INTERVALS].index(value)
    except ValueError as exc:
        raise DatasetError(f"unsupported interval in bundle: {value}") from exc


def _manifest_path(value: Path) -> Path:
    return value if value.name == BUNDLE_MANIFEST_FILE_NAME else value / BUNDLE_MANIFEST_FILE_NAME


def _isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        raise DatasetError("bundle timestamps must include a timezone")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

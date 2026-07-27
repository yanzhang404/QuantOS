"""Immutable, content-addressed Parquet dataset storage."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from . import __version__
from .errors import DatasetError
from .models import Interval, Kline
from .validation import ValidationReport, validate_klines

PARQUET_FILE_NAME = "part-00000.parquet"
MANIFEST_FILE_NAME = "manifest.json"

KLINE_SCHEMA = pa.schema(
    [
        pa.field("exchange", pa.string(), nullable=False),
        pa.field("symbol", pa.string(), nullable=False),
        pa.field("interval", pa.string(), nullable=False),
        pa.field("open_time", pa.timestamp("ms", tz="UTC"), nullable=False),
        pa.field("close_time", pa.timestamp("ms", tz="UTC"), nullable=False),
        pa.field("open", pa.decimal128(38, 18), nullable=False),
        pa.field("high", pa.decimal128(38, 18), nullable=False),
        pa.field("low", pa.decimal128(38, 18), nullable=False),
        pa.field("close", pa.decimal128(38, 18), nullable=False),
        pa.field("volume", pa.decimal128(38, 18), nullable=False),
        pa.field("quote_volume", pa.decimal128(38, 18), nullable=False),
        pa.field("trade_count", pa.int64(), nullable=False),
        pa.field("taker_buy_base_volume", pa.decimal128(38, 18), nullable=False),
        pa.field("taker_buy_quote_volume", pa.decimal128(38, 18), nullable=False),
    ],
    metadata={
        b"quantos.schema": Kline.SCHEMA_VERSION.encode(),
        b"quantos.module": b"market-data",
    },
)


@dataclass(frozen=True, slots=True)
class DatasetFile:
    path: str
    sha256: str
    bytes: int
    rows: int


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    dataset_version: str
    schema_version: str
    source: str
    exchange: str
    market_type: str
    symbol: str
    interval: str
    requested_start: str
    requested_end: str
    data_start: str
    data_end: str
    created_at: str
    row_count: int
    content_sha256: str
    producer: str
    validation: dict[str, Any]
    files: tuple[DatasetFile, ...]

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["files"] = [asdict(item) for item in self.files]
        return result

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> DatasetManifest:
        try:
            return cls(
                dataset_version=str(raw["dataset_version"]),
                schema_version=str(raw["schema_version"]),
                source=str(raw["source"]),
                exchange=str(raw["exchange"]),
                market_type=str(raw["market_type"]),
                symbol=str(raw["symbol"]),
                interval=str(raw["interval"]),
                requested_start=str(raw["requested_start"]),
                requested_end=str(raw["requested_end"]),
                data_start=str(raw["data_start"]),
                data_end=str(raw["data_end"]),
                created_at=str(raw["created_at"]),
                row_count=int(raw["row_count"]),
                content_sha256=str(raw["content_sha256"]),
                producer=str(raw["producer"]),
                validation=dict(raw["validation"]),
                files=tuple(DatasetFile(**item) for item in raw["files"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise DatasetError("invalid dataset manifest") from exc


@dataclass(frozen=True, slots=True)
class PublishedDataset:
    path: Path
    manifest: DatasetManifest


class DatasetStore:
    """Publishes immutable Kline datasets below a local data root."""

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
        klines: list[Kline],
        *,
        requested_start: datetime,
        requested_end: datetime,
        source: str,
        validation: ValidationReport | None = None,
    ) -> PublishedDataset:
        report = validation or validate_klines(
            klines,
            requested_start=requested_start,
            requested_end=requested_end,
        )
        report.raise_if_invalid()
        first = klines[0]
        content_sha256 = _content_hash(klines)
        dataset_version = content_sha256[:16]
        parent = (
            self.root
            / "market"
            / "spot"
            / f"exchange={first.exchange}"
            / f"symbol={first.symbol}"
            / f"interval={first.interval.value}"
        )
        final_path = parent / f"version={dataset_version}"

        if final_path.exists():
            manifest = self.load_manifest(final_path)
            if manifest.content_sha256 != content_sha256:
                raise DatasetError(f"dataset version collision at {final_path}")
            self.verify(final_path)
            return PublishedDataset(final_path, manifest)

        parent.mkdir(parents=True, exist_ok=True)
        temporary_path = Path(tempfile.mkdtemp(prefix=".publishing-", dir=parent))
        try:
            parquet_path = temporary_path / PARQUET_FILE_NAME
            table = _to_arrow_table(klines)
            pq.write_table(
                table,
                parquet_path,
                version="2.6",
                compression="zstd",
                use_dictionary=["exchange", "symbol", "interval"],
                write_statistics=True,
            )
            file_record = DatasetFile(
                path=PARQUET_FILE_NAME,
                sha256=_file_sha256(parquet_path),
                bytes=parquet_path.stat().st_size,
                rows=len(klines),
            )
            manifest = DatasetManifest(
                dataset_version=dataset_version,
                schema_version=Kline.SCHEMA_VERSION,
                source=source,
                exchange=first.exchange,
                market_type="spot",
                symbol=first.symbol,
                interval=first.interval.value,
                requested_start=_isoformat(requested_start),
                requested_end=_isoformat(requested_end),
                data_start=_isoformat(first.open_time),
                data_end=_isoformat(klines[-1].open_time),
                created_at=_isoformat(self._now()),
                row_count=len(klines),
                content_sha256=content_sha256,
                producer=f"quantos-market-data/{__version__}",
                validation=report.to_dict(),
                files=(file_record,),
            )
            manifest_path = temporary_path / MANIFEST_FILE_NAME
            manifest_path.write_text(
                json.dumps(manifest.to_dict(), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary_path, final_path)
        except Exception:
            shutil.rmtree(temporary_path, ignore_errors=True)
            raise

        return PublishedDataset(final_path, manifest)

    def load_manifest(self, dataset: Path) -> DatasetManifest:
        manifest_path = _manifest_path(dataset)
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DatasetError(f"cannot read manifest: {manifest_path}") from exc
        if not isinstance(raw, dict):
            raise DatasetError(f"manifest must contain an object: {manifest_path}")
        return DatasetManifest.from_dict(raw)

    def load_klines(self, dataset: Path) -> list[Kline]:
        dataset_path = _dataset_path(dataset)
        parquet_path = dataset_path / PARQUET_FILE_NAME
        try:
            rows = pq.read_table(parquet_path, schema=KLINE_SCHEMA).to_pylist()
        except (OSError, pa.ArrowException) as exc:
            raise DatasetError(f"cannot read Parquet dataset: {parquet_path}") from exc
        return [_row_to_kline(row) for row in rows]

    def verify(self, dataset: Path) -> ValidationReport:
        dataset_path = _dataset_path(dataset)
        manifest = self.load_manifest(dataset_path)
        if manifest.schema_version != Kline.SCHEMA_VERSION:
            raise DatasetError(
                f"unsupported schema {manifest.schema_version!r}; expected {Kline.SCHEMA_VERSION!r}"
            )
        for file_record in manifest.files:
            file_path = dataset_path / file_record.path
            if not file_path.is_file():
                raise DatasetError(f"dataset file is missing: {file_path}")
            if _file_sha256(file_path) != file_record.sha256:
                raise DatasetError(f"dataset file checksum mismatch: {file_path}")
        klines = self.load_klines(dataset_path)
        if len(klines) != manifest.row_count:
            raise DatasetError("manifest row count does not match Parquet data")
        if _content_hash(klines) != manifest.content_sha256:
            raise DatasetError("manifest content hash does not match normalized rows")
        report = validate_klines(
            klines,
            requested_start=_parse_isoformat(manifest.requested_start),
            requested_end=_parse_isoformat(manifest.requested_end),
        )
        report.raise_if_invalid()
        return report


def _to_arrow_table(klines: list[Kline]) -> pa.Table:
    return pa.Table.from_pylist(
        [
            {
                "exchange": item.exchange,
                "symbol": item.symbol,
                "interval": item.interval.value,
                "open_time": item.open_time,
                "close_time": item.close_time,
                "open": item.open,
                "high": item.high,
                "low": item.low,
                "close": item.close,
                "volume": item.volume,
                "quote_volume": item.quote_volume,
                "trade_count": item.trade_count,
                "taker_buy_base_volume": item.taker_buy_base_volume,
                "taker_buy_quote_volume": item.taker_buy_quote_volume,
            }
            for item in klines
        ],
        schema=KLINE_SCHEMA,
    )


def _row_to_kline(row: dict[str, Any]) -> Kline:
    return Kline(
        exchange=str(row["exchange"]),
        symbol=str(row["symbol"]),
        interval=Interval.parse(str(row["interval"])),
        open_time=row["open_time"],
        close_time=row["close_time"],
        open=Decimal(row["open"]),
        high=Decimal(row["high"]),
        low=Decimal(row["low"]),
        close=Decimal(row["close"]),
        volume=Decimal(row["volume"]),
        quote_volume=Decimal(row["quote_volume"]),
        trade_count=int(row["trade_count"]),
        taker_buy_base_volume=Decimal(row["taker_buy_base_volume"]),
        taker_buy_quote_volume=Decimal(row["taker_buy_quote_volume"]),
    )


def _content_hash(klines: list[Kline]) -> str:
    digest = hashlib.sha256()
    digest.update(Kline.SCHEMA_VERSION.encode())
    digest.update(b"\n")
    for item in klines:
        encoded = json.dumps(
            item.canonical_values(),
            ensure_ascii=True,
            separators=(",", ":"),
        ).encode()
        digest.update(encoded)
        digest.update(b"\n")
    return digest.hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _dataset_path(value: Path) -> Path:
    return value.parent if value.name == MANIFEST_FILE_NAME else value


def _manifest_path(value: Path) -> Path:
    return value if value.name == MANIFEST_FILE_NAME else value / MANIFEST_FILE_NAME


def _isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        raise DatasetError("manifest timestamps must include a timezone")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _parse_isoformat(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DatasetError(f"invalid manifest timestamp: {value!r}") from exc
    if parsed.tzinfo is None:
        raise DatasetError(f"manifest timestamp lacks timezone: {value!r}")
    return parsed.astimezone(UTC)

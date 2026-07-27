"""DuckDB queries over one immutable dataset version."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import duckdb

from .errors import ConfigurationError, DatasetError
from .storage import MANIFEST_FILE_NAME, DatasetStore


def query_klines(
    dataset: Path,
    *,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Query one dataset version in open-time order."""

    if limit < 1 or limit > 100_000:
        raise ConfigurationError("limit must be between 1 and 100000")
    dataset_path = dataset.parent if dataset.name == MANIFEST_FILE_NAME else dataset
    manifest = DatasetStore(dataset_path).load_manifest(dataset_path)
    parquet_files = [str((dataset_path / item.path).resolve()) for item in manifest.files]
    if not parquet_files:
        raise DatasetError("dataset manifest contains no files")

    conditions: list[str] = []
    parameters: list[Any] = [parquet_files]
    if start is not None:
        conditions.append("open_time >= ?")
        parameters.append(start)
    if end is not None:
        conditions.append("open_time < ?")
        parameters.append(end)
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    parameters.append(limit)

    sql = f"""
        SELECT
            exchange,
            symbol,
            interval,
            open_time,
            close_time,
            open,
            high,
            low,
            close,
            volume,
            quote_volume,
            trade_count,
            taker_buy_base_volume,
            taker_buy_quote_volume
        FROM read_parquet(?)
        {where_clause}
        ORDER BY open_time
        LIMIT ?
    """
    connection = duckdb.connect(database=":memory:")
    try:
        cursor = connection.execute(sql, parameters)
        columns = [item[0] for item in cursor.description]
        return [
            {column: _normalize_value(value) for column, value in zip(columns, row, strict=True)}
            for row in cursor.fetchall()
        ]
    except duckdb.Error as exc:
        raise DatasetError(f"DuckDB query failed: {exc}") from exc
    finally:
        connection.close()


def json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if isinstance(value, Decimal):
        return str(value)
    return value


def _normalize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.astimezone(UTC)
    return value

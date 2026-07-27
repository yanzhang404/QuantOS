# ADR-0003: Store historical analytical data in Parquet and query it with DuckDB

- Status: Accepted
- Date: 2026-07-27

## Context

V0.1 needs reproducible historical Kline datasets that are efficient for
columnar scans, portable, inspectable, and practical on a developer workstation.
A database-first ingestion stack would add operations before the access patterns
and scale are known. CSV lacks types, compression, and reliable schema metadata.

## Decision

Store normalized historical market data and derived feature datasets as
immutable, versioned Parquet files. Query them locally with DuckDB.

Each dataset version will have a manifest containing:

- exchange/source and normalization schema version;
- symbols, intervals, and inclusive time bounds;
- creation time and ingestion code version;
- row counts, partitions, and content checksums;
- validation results and parent dataset references where applicable.

Corrections create a new version; published dataset files are not mutated in
place. DuckDB databases are disposable query state and are not the source of
truth.

## Consequences

Positive:

- columnar storage and predicate pushdown suit research scans;
- datasets remain portable across Python and other runtimes;
- immutable files and manifests support reproducibility;
- DuckDB requires minimal local operations.

Tradeoffs:

- concurrent transactional writes are not supported;
- partition and small-file policies need deliberate design;
- manifests and validation must be implemented, not assumed.

PostgreSQL remains the future home for transactional experiment metadata, while
object storage may later hold Parquet and artifacts without changing the format.

# Market Data

The first market-data vertical slice is implemented as the
`quantos-market-data` Python package. It:

- downloads public Binance Spot Klines through the market-data-only endpoint;
- supports BTCUSDT/ETHUSDT and 5m/15m/1h/4h/1d;
- uses inclusive-start, exclusive-end UTC ranges;
- validates identity, ordering, timestamps, OHLC, and volume, while counting
  exchange maintenance gaps instead of fabricating bars;
- publishes content-addressed immutable Parquet versions and JSON manifests;
- verifies checksums and queries a selected version through DuckDB.
- publishes an atomic `dataset-bundle.v1` manifest only after every requested
  symbol/interval member has been downloaded and verified.

See the [Kline schema](kline-schema.md) and
[ADR-0003](../adr/0003-parquet-duckdb.md).

## Commands

Install the locked development environment:

```bash
uv sync --all-groups
```

Download one closed historical range:

```bash
uv run quantos data download \
  --symbol BTCUSDT \
  --interval 1h \
  --start 2024-01-01T00:00:00Z \
  --end 2024-01-08T00:00:00Z
```

The command prints the dataset and manifest paths. Use that immutable version
for validation and queries:

```bash
uv run quantos data validate --dataset data/market/spot/exchange=binance/...
uv run quantos data query --dataset data/market/spot/exchange=binance/... --limit 10
```

Generated data stays below `data/` and is excluded from Git.

Download and version the complete product matrix for one common UTC range:

```bash
uv run quantos data sync-matrix \
  --start 2024-01-01T00:00:00Z \
  --end 2024-02-01T00:00:00Z
```

The command prints the immutable bundle path, bundle version, and exact member
dataset identities. The range must align to all requested intervals; the
default matrix includes `1d`, so use UTC day boundaries. A bundle is not
published if any matrix member is missing or invalid. Historical intervals
absent from the exchange response remain explicit in validation evidence.

Backfill once and then refresh to the latest common closed boundary:

```bash
uv run quantos data sync-current \
  --start 2021-01-01T00:00:00Z \
  --data-root data \
  --coverage-output apps/web/app/multi-timeframe-coverage.v1.json
```

The first call downloads the complete matrix. Later calls discover the newest
verified bundle with the same start, request only the missing tail, publish a
new immutable bundle, and atomically refresh the compact workspace evidence.
The latest common boundary is UTC midnight because `1d` belongs to the matrix.

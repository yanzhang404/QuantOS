# Market Data

The first market-data vertical slice is implemented as the
`quantos-market-data` Python package. It:

- downloads public Binance Spot Klines through the market-data-only endpoint;
- supports BTCUSDT/ETHUSDT and 5m/15m/1h/4h/1d;
- uses inclusive-start, exclusive-end UTC ranges;
- validates identity, ordering, continuity, timestamps, OHLC, and volume;
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
published if any member is missing or invalid.

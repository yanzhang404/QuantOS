# Market Data

The first V0.1 vertical slice is implemented as the `quantos-market-data`
Python package. It:

- downloads public Binance Spot Klines through the market-data-only endpoint;
- supports BTCUSDT/ETHUSDT and 1h/4h;
- uses inclusive-start, exclusive-end UTC ranges;
- validates identity, ordering, continuity, timestamps, OHLC, and volume;
- publishes content-addressed immutable Parquet versions and JSON manifests;
- verifies checksums and queries a selected version through DuckDB.

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

# Market Data Example

The following creates a small, reproducible BTCUSDT hourly dataset:

```bash
uv run quantos data download \
  --symbol BTCUSDT \
  --interval 1h \
  --start 2024-01-01T00:00:00Z \
  --end 2024-01-03T00:00:00Z \
  --data-root data
```

Copy the printed `dataset` path into:

```bash
uv run quantos data validate --dataset "<dataset>"
uv run quantos data query --dataset "<dataset>" --limit 5
```

Do not commit the generated `data/` directory. A research experiment should
record the printed `dataset_version` and retain the corresponding manifest and
artifact in managed storage.

## Multi-timeframe coverage evidence

`../../apps/web/app/multi-timeframe-coverage.v1.json` is the compact projection
of verified bundle `c165549a7700426a`. It records real public Binance Spot coverage for BTCUSDT and
ETHUSDT at `5m`, `15m`, `1h`, `4h`, and `1d` from 2021-01-01 through the
exclusive 2026-08-02 boundary: 1,691,776 source bars across ten members. The
ignored local bundle retains the source manifests and Parquet rows; this
committed evidence retains exact dataset versions, hashes, row counts, source
gap counts, and the bundle identity used by the workspace.

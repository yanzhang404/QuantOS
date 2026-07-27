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

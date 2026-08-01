# Market Data Service

Owns exchange adapters, normalization, validation, Parquet publication, dataset
version manifests, and read-only analytical queries.

## Package boundaries

- `binance.py`: public Spot REST adapter, pagination, and bounded retries.
- `models.py`: exchange-neutral `kline.v1` contract.
- `validation.py`: deterministic quality rules.
- `storage.py`: atomic, immutable Parquet publication and verification.
- `bundle.py`: atomic identity and publication for a verified dataset matrix.
- `query.py`: DuckDB queries scoped to one dataset version.
- `service.py`: single-dataset, tail extension, and current-matrix orchestration.
- `cli.py`: human and automation entry point.

The adapter has no authenticated endpoint, API-key parameter, account model, or
order capability.

The normalized interval vocabulary supports `5m`, `15m`, `1h`, `4h`, and `1d`.
An interval becomes runnable only after the public-data pipeline publishes a
real immutable dataset version; recognizing an interval never fabricates data.

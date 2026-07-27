# Market Data Service

Owns exchange adapters, normalization, validation, Parquet publication, dataset
version manifests, and read-only analytical queries.

## Package boundaries

- `binance.py`: public Spot REST adapter, pagination, and bounded retries.
- `models.py`: exchange-neutral `kline.v1` contract.
- `validation.py`: deterministic quality rules.
- `storage.py`: atomic, immutable Parquet publication and verification.
- `query.py`: DuckDB queries scoped to one dataset version.
- `service.py`: download → validate → publish orchestration.
- `cli.py`: human and automation entry point.

The adapter has no authenticated endpoint, API-key parameter, account model, or
order capability.

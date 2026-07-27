# Market Data

V0.1 will ingest public Binance Klines for BTCUSDT and ETHUSDT at 1h and 4h,
normalize them into an exchange-neutral schema, validate continuity and
uniqueness, and publish immutable Parquet dataset versions.

See [ADR-0003](../adr/0003-parquet-duckdb.md).

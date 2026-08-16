# Market Data

V0.1 will ingest public Binance Klines for BTCUSDT and ETHUSDT at 1h and 4h,
normalize them into an exchange-neutral schema, validate continuity and
uniqueness, and publish immutable Parquet dataset versions.

See [ADR-0003](../adr/0003-parquet-duckdb.md).

The market-data module also contains an A-share Market Radar v0.1. It consumes
point-in-time full-market quotes through an exchange-neutral provider, detects
stock-level anomalies, and aggregates a supplied theme-membership map into heat,
velocity, and acceleration rankings. This observational path is read-only and
does not change strategy, risk, or execution ownership. See
[ADR-0004](../adr/0004-a-share-market-radar.md).

US equity heat is the first stage of an intraday-options screening funnel. It
ranks exchange-wide one-minute bars before the second stage fetches bounded
option snapshots for only the highest-ranked underlyings. See
[ADR-0005](../adr/0005-us-equity-live-radar.md) and
[ADR-0006](../adr/0006-top-candidate-option-snapshots.md).

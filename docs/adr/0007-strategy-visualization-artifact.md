# ADR-0007: Derive a compact strategy visualization artifact

- Status: Accepted
- Date: 2026-07-29

## Context

The read-only workspace can compare aggregate metrics, but a strategy review
also needs synchronized Klines, fills, portfolio equity, position exposure, and
drawdown. The immutable market datasets and experiment directories already
contain those records. Importing entire Parquet datasets and CSV experiment
artifacts into the browser would make the first frontend unnecessarily large
and would couple it to Python storage formats.

## Decision

Add a deterministic export boundary that derives a compact, versioned JSON
artifact from:

- an immutable Kline dataset version;
- the matching `run.json`, `fills.csv`, and `equity.csv` files;
- the committed study summary that links datasets to Run IDs.

The first artifact contains the latest 240 four-hour bars for every supported
asset and observation window. For each built-in strategy it includes fills,
equity, position quantity, and running-peak drawdown aligned to that window.
Every view retains the source dataset version, content hash, and Run ID.

The browser remains read-only. Switching strategy, asset, or observation window
selects another immutable view; it does not rerun a strategy or mutate research
state.

## Consequences

Positive:

- Kline, fill, equity, and drawdown charts use real reproducible evidence;
- the browser receives a small purpose-built contract instead of storage files;
- the same UI can compare multiple strategies without introducing an API;
- the exporter can become the contract fixture for a future read-only API.

Tradeoffs:

- the committed artifact shows a bounded review window rather than every bar;
- new or changed experiment results require re-exporting the artifact;
- JSON duplicates a small portion of immutable source data;
- interactive backtest execution remains deferred to the control-plane API.

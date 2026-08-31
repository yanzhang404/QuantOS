# ADR-0010: Serve experiment visualization as a derived read model

- Status: Accepted
- Date: 2026-07-30

## Context

Interactive backtests already create immutable experiment directories containing
`run.json`, `fills.csv`, and `equity.csv`. The web workspace can submit and
observe Tasks, but its charts still read a committed build-time visualization
artifact. A successful Task therefore produces a different Run ID without
changing the displayed metrics, fills, equity, or drawdown.

Serving storage paths or raw CSV files to the browser would expose persistence
details and duplicate parsing logic in the client. Re-exporting the committed
visualization artifact after every manual run would also make an interactive
workflow unnecessarily stateful.

## Decision

Add a read-only `GET /api/v1/experiments/{run_id}` resource. The Go control
plane resolves a validated Run ID beneath its trusted experiment root and
derives a versioned JSON read model from the immutable experiment artifacts.
The response contains:

- experiment, dataset, strategy, engine, metrics, and configuration identity;
- normalized fills with an explicit buy or sell side;
- equity points with position quantity and running-peak drawdown.
- a bounded tail of normalized OHLCV bars copied from the exact evaluated
  immutable dataset.

The endpoint never accepts an artifact path. It validates file names, bounds
artifact sizes, parses numeric values strictly, and returns safe structured
errors. Each new Run stores at most the latest 2,000 evaluated bars in
`bars.csv`; this is a visualization projection, not a replacement dataset.
A Run can replace a chart only when its dataset version, content hash, symbol,
and interval match the selected immutable member.
Adding this required artifact advances the artifact identity to
`experiment-artifacts.v2`, so pre-existing Runs remain readable evidence and
new executions never collide with directories that lack `bars.csv`.

Selecting a successful Task loads its Experiment and makes that Run the single
source for metric cards, fill markers, equity, drawdown, and the fill table.
Changing strategy, asset, or observation window clears an incompatible manual
Run and returns to the committed baseline.

## Consequences

Positive:

- parameter changes become visible immediately after a backtest succeeds;
- the browser consumes stable JSON rather than internal CSV storage formats;
- all displayed dynamic results retain immutable Run and dataset identity;
- live execution remains outside the read-only experiment boundary.

Tradeoffs:

- the Go API performs bounded CSV parsing for each uncached detail request;
- Kline coverage remains limited to the bounded Run visualization tail;
- experiment comparison and server-side caching remain later increments.

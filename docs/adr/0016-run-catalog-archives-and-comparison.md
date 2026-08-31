# ADR-0016: Keep Run evidence immutable while managing a separate review catalog

- Status: Accepted
- Date: 2026-08-01

## Context

QuantOS persists every completed backtest as an immutable experiment directory,
but the product can only load a Run when its identifier is already known. As
the strategy library grows, researchers need to find prior evidence, hide stale
review clutter, and compare several parameter choices without deleting or
rewriting reproducible artifacts.

## Decision

Add a Run catalog projection over completed experiment artifacts.

- `GET /api/v1/experiments` returns bounded summaries and supports exact
  `symbol`, `interval`, and `strategy` filters plus an `archived` mode.
- Run summaries contain immutable dataset, strategy, configuration, version,
  and metric fields but omit Kline, equity, and fill series.
- Archival is reversible review metadata. `PUT` and `DELETE` on
  `/api/v1/experiment-archives/{run_id}` create or remove a timestamped marker
  in the API state root. They never modify the experiment directory.
- The default catalog excludes archived Runs. Callers may include all Runs or
  request archived Runs only.
- The workspace may compare two to four Runs. A normalized percent-return
  series starts every selected Run at zero so different initial capital and
  evaluation windows do not imply a false dollar comparison. Metric and input
  differences remain visible beside the chart.
- Comparison is observational only. Selecting, filtering, or archiving a Run
  cannot trigger a backtest, strategy promotion, or trading action.

The file-backed archive index remains a single-process boundary, matching the
existing task store and hosted single-replica constraint.

## Consequences

Positive:

- saved Run evidence becomes discoverable without loading large chart series;
- housekeeping does not weaken reproducibility or delete evidence;
- strategy, market, timeframe, parameter, cost, and result differences can be
  reviewed together;
- the catalog contract can later move to PostgreSQL without changing Run
  artifacts.

Tradeoffs:

- catalog listing scans local experiment metadata and is intentionally bounded;
- archive markers are review state, not part of a Run's content identity;
- comparisons with different evaluation windows require an explicit warning
  and normalized returns rather than aligned portfolio dollars.

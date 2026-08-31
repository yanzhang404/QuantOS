# ADR-0013: Organize the product workspace around four result-first views

- Status: Accepted
- Date: 2026-08-01

## Context

The first QuantOS workspace placed research context, daily intelligence,
strategy selection, backtest configuration, comparison, and provenance in one
long document. That was useful for validating the first vertical slice, but it
now obscures the product's primary workflow: select a strategy, inspect its
result, change its parameters, run a reproducible backtest, and compare the
immutable Run with prior evidence.

The next stage must also make room for multi-timeframe datasets, robustness
review, Agent-proposed candidates, and source-linked market intelligence
without turning the workspace into a dense report.

## Decision

Organize the workspace into four independent views:

- **Overview** presents the deterministic sentiment snapshot, recent evidence,
  candidate status, and data health.
- **Strategies** presents a folder-style strategy tree, result-first metrics,
  charts and fills, plus strategy-specific editable parameters.
- **Runs** presents immutable historical runs, filters, stress results, and
  multi-Run comparison.
- **Data** presents immutable dataset identities, supported intervals, and data
  lineage.

The first implementation retains hash-addressable client views so the current
single-worker deployment and API state remain intact. Each view has a distinct
URL fragment, title, and active navigation state. A later filesystem-route
split may occur without changing these product boundaries.

The Strategies view removes the report-style hero and large lifecycle diagram.
It displays final capital, net return, profit/loss, maximum drawdown, Sharpe,
trades, fills, and fees before configuration and detail charts. Strategy code
remains repository-owned and read-only in the browser; only manifest-declared
parameters are editable.

Sentiment uses two explicit color semantics. The 0–100 level uses red for fear,
amber/neutral for the middle range, and green for greed. The change value uses
red for a decrease and green for an increase. Color is always accompanied by a
number and label, and sentiment remains contextual research data rather than a
trading signal.

## Consequences

Positive:

- users can understand the product by task instead of scrolling a report;
- strategy results and money outcomes are visible before parameters and charts;
- daily intelligence becomes prominent without dominating strategy work;
- future Runs and Data capabilities have stable product homes;
- hash-addressable views preserve shareable local navigation with low migration
  risk.

Tradeoffs:

- the first split is client-side rather than separate server routes;
- the Runs view initially reuses committed comparison evidence while immutable
  filtering and four-Run comparison are built next;
- the Data view initially exposes existing lineage before all five immutable
  intervals are loaded;
- red/green color cannot be the only carrier of meaning and requires accessible
  labels throughout the UI.

# ADR-0011: Separate strategy library from research lifecycle

- Status: Accepted
- Date: 2026-07-30

## Context

The first QuantOS workspace presents a research review, strategy execution,
comparison, and data provenance in one long page. Global navigation occupies a
permanent left rail while strategy selection is a horizontal control inside the
page. This makes research and strategy concepts appear interchangeable, places
the result below the configuration form, and leaves no scalable location for a
growing set of independently parameterized strategies.

Strategy parameter metadata is also duplicated between the API and web client.
Adding a strategy therefore requires editing multiple user-interface branches
even though the API already exposes a versioned strategy catalog.

## Decision

Adopt these product and contract boundaries:

- **Research Center** owns hypotheses, evidence, robustness review, candidate
  validation, and promotion decisions.
- **Strategy Library** owns reusable versioned strategy implementations,
  categories, supported intervals, parameter manifests, and lifecycle stage.
- **Run** combines one immutable dataset, one strategy version and parameter
  set, explicit simulation assumptions, and one shared backtest engine.
- **Data & Reproducibility** explains the lineage of a selected Run and is
  presented as detail rather than a peer workflow.

Global navigation moves to a top application bar. The Strategy Library receives
its own folder-style left tree grouped by trend, benchmark, mean-reversion, and
intraday categories. Candidate folders may be empty and must not imply that an
unvalidated strategy exists.

The strategy catalog becomes the user-interface manifest. Every definition
contains category, lifecycle stage, implementation reference, supported
intervals, and parameter specifications. The browser renders parameter fields
from this manifest instead of maintaining strategy-specific form branches.
Each strategy continues to own separate implementation code while all
strategies share the event clock, portfolio, risk, execution, metrics, and
artifact pipeline.

Run pages are result-first: capital, return, drawdown, Sharpe ratio, trades,
fills, and fees appear above configuration and detailed charts.

The interval vocabulary expands to `5m`, `15m`, `1h`, `4h`, and `1d`. A strategy
may declare a subset, and a Run still requires an actually available immutable
dataset. Adding an interval to the vocabulary never fabricates or silently
downloads market data.

Candidate strategy progression is:

```text
hypothesis → candidate → robustness review → approved library strategy
```

Promotion remains a human decision supported by reproducible evidence. AI may
propose and implement candidates but may not silently label them validated.

## Consequences

Positive:

- research and reusable strategy concepts become visibly distinct;
- the strategy library can grow without horizontal-control sprawl;
- parameter forms follow the authoritative strategy manifest;
- new intervals share the same deterministic backtest infrastructure;
- the user sees outcomes before implementation details;
- AI-assisted discovery has an explicit evidence and approval boundary.

Tradeoffs:

- strategy metadata must remain compatible across Python, Go, and web clients;
- newly recognized intervals require real datasets before they can run;
- candidate persistence and promotion APIs remain a later transactional
  increment; the first view reflects committed research evidence only.
